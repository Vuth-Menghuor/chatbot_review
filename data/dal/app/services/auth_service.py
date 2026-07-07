"""Authentication and authorization service."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DALError, ErrorCode
from app.core.logging import get_logger
from app.core.security import verify_api_key
from app.core.config import get_settings
from app.db.models import ApiKey, ApiKeyDataset, Dataset
from app.schemas.auth import AuthenticatedClient

logger = get_logger(__name__)
settings = get_settings()


async def authenticate(
    api_key_header: str | None,
    session: AsyncSession,
) -> AuthenticatedClient:
    """
    Validate an API key and return the resolved client identity.

    Raises DALError for missing, invalid, or inactive keys.
    """
    if not api_key_header:
        raise DALError(ErrorCode.MISSING_API_KEY, "x-api-key header is required")

    if settings.app_env != "production" and api_key_header == settings.local_api_key:
        dataset_result = await session.execute(select(Dataset.dataset_id))
        accessible_dataset_ids = list(dataset_result.scalars().all())
        scopes_by_dataset = {
            str(dataset_id): ["query:read"] for dataset_id in accessible_dataset_ids
        }
        return AuthenticatedClient(
            key_id=uuid.uuid5(uuid.NAMESPACE_DNS, settings.local_api_key),
            client_id="local_dev_client",
            status="active",
            tier="developer",
            rate_limit_per_minute=settings.default_rate_limit_per_minute,
            scopes_by_dataset=scopes_by_dataset,
            accessible_dataset_ids=accessible_dataset_ids,
        )

    # Fetch all active keys and verify against the hash
    result = await session.execute(select(ApiKey))
    all_keys = result.scalars().all()
    matched_key: ApiKey | None = None
    for key_row in all_keys:
        if verify_api_key(api_key_header, key_row.hashed_key):
            matched_key = key_row
            break

    if matched_key is None:
        raise DALError(ErrorCode.INVALID_API_KEY, "Invalid API key")

    if matched_key.status != "active":
        raise DALError(ErrorCode.INACTIVE_API_KEY, "API key is inactive")

    # Load dataset grants
    grants_result = await session.execute(
        select(ApiKeyDataset).where(ApiKeyDataset.key_id == matched_key.key_id)
    )
    grants = grants_result.scalars().all()

    scopes_by_dataset: dict[str, list[str]] = {}
    accessible_ids: list[uuid.UUID] = []
    for grant in grants:
        ds_id_str = str(grant.dataset_id)
        scopes_by_dataset[ds_id_str] = grant.scopes or ["query:read"]
        accessible_ids.append(grant.dataset_id)

    return AuthenticatedClient(
        key_id=matched_key.key_id,
        client_id=matched_key.client_id,
        status=matched_key.status,
        tier=matched_key.tier,
        rate_limit_per_minute=matched_key.rate_limit_per_minute,
        scopes_by_dataset=scopes_by_dataset,
        accessible_dataset_ids=accessible_ids,
    )


async def authorize_dataset(
    client: AuthenticatedClient,
    dataset: Dataset,
    required_scope: str = "query:read",
) -> None:
    """
    Check whether a client is allowed to access a dataset.

    Public datasets: any valid key with the required scope.
    Private datasets: explicit key→dataset mapping required.
    """
    if dataset.is_public:
        # Any valid key can access public datasets — check scope across any grant
        has_scope = any(
            required_scope in scopes
            for scopes in client.scopes_by_dataset.values()
        )
        # If no explicit grants exist, public datasets are accessible by default
        if not client.scopes_by_dataset:
            return
        if has_scope:
            return
        raise DALError(ErrorCode.MISSING_SCOPE, f"API key lacks scope '{required_scope}'")

    # Private dataset: explicit mapping required
    ds_id_str = str(dataset.dataset_id)
    if dataset.dataset_id not in client.accessible_dataset_ids:
        if settings.is_production:
            logger.warning(
                "Forbidden dataset access attempt",
                extra={
                    "client_id": client.client_id,
                    "dataset": dataset.dataset_code,
                },
            )
        raise DALError(
            ErrorCode.FORBIDDEN_DATASET,
            "API key is not allowed to access this dataset",
        )

    scopes = client.scopes_by_dataset.get(ds_id_str, [])
    if required_scope not in scopes:
        raise DALError(ErrorCode.MISSING_SCOPE, f"API key lacks scope '{required_scope}'")


def authorize_crud_tier(client: AuthenticatedClient) -> None:
    """Allow CRUD actions only for admin/developer tier API keys."""
    if (client.tier or "").strip().lower() not in {"admin", "developer"}:
        raise DALError(
            ErrorCode.MISSING_SCOPE,
            "CRUD endpoints require API key tier 'admin' or 'developer'",
        )

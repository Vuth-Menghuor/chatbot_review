"""Metadata read endpoints (optional, gated by metadata:read scope)."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.api.deps import AuthClient, MetadataSession, OperationalSession
from app.core.config import get_settings
from app.core.errors import DALError, ErrorCode
from app.core.rate_limit import limiter
from app.schemas.query import NormalizedDatasetInfoQuery
from app.schemas.response import (
    CacheInfo,
    DatasetInfoResponse,
    ErrorResponse,
    MetaInfo,
)
from app.services import (
    audit_service,
    auth_service,
    dataset_service,
    metadata_service,
    query_service,
)
from app.utils.hashing import compute_query_fingerprint

router = APIRouter(prefix="/v1/metadata", tags=["Metadata"])


@router.get(
    "/datasets",
    summary="List available datasets",
    description="Returns all active datasets. Requires a valid API key.",
)
@limiter.limit(
    f"{get_settings().default_rate_limit_per_minute}/minute"
)
async def list_datasets(
    request: Request,
    client: AuthClient,
    session: MetadataSession,
):
    """List all active datasets."""
    datasets = await metadata_service.list_datasets(session)
    return {
        "datasets": [
            {
                "dataset_code": ds.dataset_code,
                "name": ds.name,
                "description": ds.description,
                "is_public": ds.is_public,
            }
            for ds in datasets
        ]
    }


@router.get(
    "/dataset/{dataset}",
    summary="Get dataset details",
    description="Returns metadata for a specific dataset, including dimensions and measures. Requires a valid API key.",
    response_model=DatasetInfoResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication error"},
        403: {"model": ErrorResponse, "description": "Authorization error"},
        404: {"model": ErrorResponse, "description": "Dataset not found"},
        422: {"model": ErrorResponse, "description": "Invalid route/path parameter"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
@limiter.limit(
    f"{get_settings().default_rate_limit_per_minute}/minute"
)
async def get_dataset_details(
    request: Request,
    dataset: Annotated[
        str,
        Path(
            pattern=r"^[A-Za-z0-9_-]+$",
            description="Dataset code. Allowed characters: letters, digits, underscore, and hyphen.",
            examples=["trade_volume"],
        ),
    ],
    client: AuthClient,
    meta_session: MetadataSession,
    ops_session: OperationalSession,
    version: str | None = Query(
        None,
        description="Dataset version to query, e.g. '1.0'. If not provided, the default version will be used.",
        examples=["1.0"],
    ),
):
    """Get details for a specific dataset."""
    request_id = getattr(request.state, "request_id", "unknown")
    start_time = time.perf_counter()

    # Audit context
    audit_kwargs: dict = {
        "request_id": request_id,
        "client_id": client.client_id,
        "dataset": dataset,
    }
    try:
        # Rate limiting is handled by SlowAPI middleware (keyed by x-api-key)

        # --- Resolve dataset ---
        ds = await dataset_service.get_dataset(dataset, meta_session)

        # --- Resolve version ---
        ds_version = await dataset_service.resolve_version(dataset, version, meta_session)
        audit_kwargs["dataset_version"] = ds_version.version

        # --- Authorize ---
        await auth_service.authorize_dataset(client, ds)

        # --- Load concept ---
        concept = await dataset_service.load_concept(dataset, ds_version.version, meta_session)

        # --- Cache policy ---
        cache_policy = await metadata_service.get_cache_policy(ds.dataset_id, meta_session)
        cache_enabled = cache_policy.enabled if cache_policy else False
        cache_ttl = cache_policy.ttl_seconds if cache_policy else 300

        # Build normalized query
        normalized = NormalizedDatasetInfoQuery(
            dataset=dataset,
            version=ds_version.version,
        )

        # --- Execute ---
        info, cache_hit = await query_service.execute_query_dataset_codelist(
            normalized,
            concept,
            ops_session,
            cache_enabled=cache_enabled,
            cache_ttl=cache_ttl,
            is_public=ds.is_public,
            client_id=client.client_id,
        )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # --- Audit (success) ---
        fingerprint = compute_query_fingerprint(normalized)
        await audit_service.write_audit_log(
            meta_session,
            **audit_kwargs,
            status_code=200,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            query_fingerprint=fingerprint,
            request_params={
                "dataset": dataset,
                "version": ds_version.version,
            },
        )

        # --- Build response ---
        return DatasetInfoResponse(
            request_id=request_id,
            dataset=dataset,
            version=ds_version.version,
            frequency=info.get("frequency"),
            dimensions=info.get("dimensions", []),
            measures=info.get("measures", []),
            period=info.get("period"),
            cache=CacheInfo(hit=cache_hit, ttl_seconds=cache_ttl if cache_enabled else None),
            meta=MetaInfo(latency_ms=latency_ms),
        )

    except DALError:
        # Re-raise DAL errors — middleware handles them
        raise
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        # Audit (failure)
        await audit_service.write_audit_log(
            meta_session,
            **audit_kwargs,
            status_code=500,
            latency_ms=latency_ms,
            error_summary=str(exc)[:500],
        )
        raise DALError(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred") from exc

"""Dataset and version resolution service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DALError, ErrorCode
from app.core.logging import get_logger
from app.core.config import get_settings
from app.db.models import Dataset, DatasetMapping, DatasetVersion
from app.schemas.metadata import DatasetConcept
from app.schemas.request import CreateDatasetRequest

logger = get_logger(__name__)
settings = get_settings()


async def get_dataset(dataset_code: str, session: AsyncSession) -> Dataset:
    """Load a dataset by code. Raises if not found or inactive."""
    result = await session.execute(
        select(Dataset).where(
            Dataset.dataset_code == dataset_code,
            Dataset.status == "active",
        )
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise DALError(ErrorCode.DATASET_NOT_FOUND, f"Dataset '{dataset_code}' not found")
    return dataset


async def resolve_version(
    dataset_code: str,
    version: str | None,
    session: AsyncSession,
) -> DatasetVersion:
    """
    Resolve a dataset version. If version is None, use the default.
    Raises if version not found or inactive.
    """
    if version:
        result = await session.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_code == dataset_code,
                DatasetVersion.version == version,
                DatasetVersion.status == "active",
            )
        )
    else:
        result = await session.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_code == dataset_code,
                DatasetVersion.is_default == True,  # noqa: E712
                DatasetVersion.status == "active",
            )
        )

    ds_version = result.scalar_one_or_none()
    if ds_version is None:
        label = version or "default"
        raise DALError(
            ErrorCode.VERSION_NOT_FOUND,
            f"Version '{label}' not found for dataset '{dataset_code}'",
        )
    return ds_version


async def load_concept(
    dataset_code: str,
    version: str,
    session: AsyncSession,
) -> DatasetConcept:
    """Load and parse the dataset concept JSONB from the mapping table."""
    result = await session.execute(
        select(DatasetMapping).where(
            DatasetMapping.dataset_code == dataset_code,
            DatasetMapping.version == version,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        raise DALError(
            ErrorCode.VERSION_NOT_FOUND,
            f"Concept mapping not found for '{dataset_code}' v{version}",
        )

    try:
        if not settings.is_production:
            logger.info(
                "Parsing dataset concept",
                extra={"dataset_code": dataset_code, "version": version},
            )
            logger.debug(f"Raw concept JSON: {mapping.dataset_concept}")
        concept = DatasetConcept.model_validate(mapping.dataset_concept)
    except Exception as exc:
        if not settings.is_production:
            logger.error(
                "Failed to parse dataset concept",
                extra={"dataset_code": dataset_code, "version": version, "error": str(exc)},
            )
        raise DALError(
            ErrorCode.INTERNAL_ERROR,
            "Failed to parse dataset concept metadata",
        ) from exc

    return concept


# CRUD operations for dataset metadata management (admin use only) could be added here, e.g. create/update dataset concepts, versions, etc.
async def create_dataset(
    payload: CreateDatasetRequest,
    session: AsyncSession,
) -> Dataset:
    """Create a dataset in metadata DB and return the created row."""
    existing = await session.execute(
        select(Dataset).where(Dataset.dataset_code == payload.dataset_code)
    )
    if existing.scalar_one_or_none() is not None:
        raise DALError(
            ErrorCode.VALIDATION_ERROR,
            f"Dataset '{payload.dataset_code}' already exists",
        )

    dataset = Dataset(
        dataset_code=payload.dataset_code,
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
        status=payload.status,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset

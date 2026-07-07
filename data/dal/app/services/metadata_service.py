"""Metadata service — cache policy lookups and metadata read endpoints."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CachePolicy, Dataset


async def get_cache_policy(
    dataset_id,
    session: AsyncSession,
) -> CachePolicy | None:
    """Load the cache policy for a dataset. Returns None if not configured."""
    result = await session.execute(
        select(CachePolicy).where(CachePolicy.dataset_id == dataset_id)
    )
    return result.scalar_one_or_none()


async def list_datasets(session: AsyncSession) -> list[Dataset]:
    """List all active datasets."""
    result = await session.execute(
        select(Dataset).where(Dataset.status == "active").order_by(Dataset.dataset_code)
    )
    return list(result.scalars().all())
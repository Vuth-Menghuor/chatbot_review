"""Shared FastAPI dependencies for DB sessions, Redis, and auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.metadata_session import get_metadata_session
from app.db.operational_session import get_operational_session
from app.schemas.auth import AuthenticatedClient
from app.services import auth_service

# Type aliases for cleaner endpoint signatures
MetadataSession = Annotated[AsyncSession, Depends(get_metadata_session)]
OperationalSession = Annotated[AsyncSession, Depends(get_operational_session)]


async def get_authenticated_client(
    x_api_key: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_metadata_session),
) -> AuthenticatedClient:
    """Dependency that authenticates the caller via x-api-key header."""
    return await auth_service.authenticate(x_api_key, session)


AuthClient = Annotated[AuthenticatedClient, Depends(get_authenticated_client)]

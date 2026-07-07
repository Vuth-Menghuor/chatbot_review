"""Pydantic schemas for auth-related DTOs."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class AuthenticatedClient(BaseModel):
    """Resolved identity after API key validation."""

    key_id: uuid.UUID
    client_id: str
    status: str
    tier: str
    rate_limit_per_minute: int
    scopes_by_dataset: dict[str, list[str]]  # dataset_id -> scopes
    accessible_dataset_ids: list[uuid.UUID]

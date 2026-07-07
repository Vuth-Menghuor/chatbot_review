"""Pydantic request models."""

from __future__ import annotations

from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class CreateDatasetRequest(BaseModel):
    """Request payload for creating a dataset in metadata DB."""

    dataset_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_public: bool = False
    status: str = Field(default="active", min_length=1, max_length=20)
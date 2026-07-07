"""SQLAlchemy ORM models for the metadata database."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all metadata models."""

    pass


# ------------------------------------------------------------------
# Dataset
# ------------------------------------------------------------------
class Dataset(Base):
    __tablename__ = "dataset"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    versions: Mapped[list[DatasetVersion]] = relationship(back_populates="dataset", foreign_keys="[DatasetVersion.dataset_code]")
    cache_policy: Mapped[CachePolicy | None] = relationship(back_populates="dataset", uselist=False, foreign_keys="[CachePolicy.dataset_id]")
    access_grants: Mapped[list[ApiKeyDataset]] = relationship(back_populates="dataset", foreign_keys="[ApiKeyDataset.dataset_id]")


# ------------------------------------------------------------------
# Dataset Version
# ------------------------------------------------------------------
class DatasetVersion(Base):
    __tablename__ = "dataset_version"
    __table_args__ = (
        UniqueConstraint("dataset_code", "version", name="uq_dataset_version"),
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_code: Mapped[str] = mapped_column(
        String(100), ForeignKey("dataset.dataset_code"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    dataset: Mapped[Dataset] = relationship(back_populates="versions")


# ------------------------------------------------------------------
# Dataset Mapping (concept stored as JSONB)
# ------------------------------------------------------------------
class DatasetMapping(Base):
    __tablename__ = "dataset_mapping"
    __table_args__ = (
        UniqueConstraint("dataset_code", "version", name="uq_dataset_mapping_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset_concept: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ------------------------------------------------------------------
# API Key
# ------------------------------------------------------------------
class ApiKey(Base):
    __tablename__ = "api_key"

    key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    tier: Mapped[str] = mapped_column(String(50), default="standard", nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    dataset_grants: Mapped[list[ApiKeyDataset]] = relationship(back_populates="api_key")


# ------------------------------------------------------------------
# API Key ↔ Dataset access grant
# ------------------------------------------------------------------
class ApiKeyDataset(Base):
    __tablename__ = "api_key_dataset"
    __table_args__ = (
        UniqueConstraint("key_id", "dataset_id", name="uq_key_dataset"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_key.key_id"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset.dataset_id"), nullable=False, index=True
    )
    scopes: Mapped[list] = mapped_column(JSONB, default=["query:read"], nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    api_key: Mapped[ApiKey] = relationship(back_populates="dataset_grants")
    dataset: Mapped[Dataset] = relationship(back_populates="access_grants")


# ------------------------------------------------------------------
# Cache Policy
# ------------------------------------------------------------------
class CachePolicy(Base):
    __tablename__ = "cache_policy"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset.dataset_id"), unique=True, nullable=False, index=True
    )
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    dataset: Mapped[Dataset] = relationship(back_populates="cache_policy")


# ------------------------------------------------------------------
# Audit Log
# ------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_requested_at", "requested_at"),
        Index("ix_audit_log_client_dataset", "client_id", "dataset"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    cache_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    query_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

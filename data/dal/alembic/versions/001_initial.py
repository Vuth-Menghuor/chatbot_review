"""initial metadata schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- dataset ---
    op.create_table(
        "dataset",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_code", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- dataset_version ---
    op.create_table(
        "dataset_version",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_code", sa.String(100), sa.ForeignKey("dataset.dataset_code"), nullable=False, index=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_code", "version", name="uq_dataset_version"),
    )

    # --- dataset_mapping ---
    op.create_table(
        "dataset_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_code", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("dataset_concept", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_code", "version", name="uq_dataset_mapping_version"),
    )

    # --- api_key ---
    op.create_table(
        "api_key",
        sa.Column("key_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("hashed_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("tier", sa.String(50), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- api_key_dataset ---
    op.create_table(
        "api_key_dataset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_key.key_id"), nullable=False, index=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset.dataset_id"), nullable=False, index=True),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"query:read\"]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("key_id", "dataset_id", name="uq_key_dataset"),
    )

    # --- cache_policy ---
    op.create_table(
        "cache_policy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset.dataset_id"), nullable=False, unique=True, index=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(100), nullable=True),
        sa.Column("dataset", sa.String(100), nullable=True),
        sa.Column("dataset_version", sa.String(50), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=True),
        sa.Column("query_fingerprint", sa.String(64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("request_params", postgresql.JSONB(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_requested_at", "audit_log", ["requested_at"])
    op.create_index("ix_audit_log_client_dataset", "audit_log", ["client_id", "dataset"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("cache_policy")
    op.drop_table("api_key_dataset")
    op.drop_table("api_key")
    op.drop_table("dataset_mapping")
    op.drop_table("dataset_version")
    op.drop_table("dataset")

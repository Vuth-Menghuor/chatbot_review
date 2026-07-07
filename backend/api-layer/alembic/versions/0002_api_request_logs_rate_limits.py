"""Rename request_logs to api_request_logs and add rate_limits audit table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_api_logs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)

    op.rename_table("request_logs", "api_request_logs")
    op.execute("ALTER INDEX IF EXISTS ix_request_logs_user_id RENAME TO ix_api_request_logs_user_id")

    op.add_column("api_request_logs", sa.Column("query_string", sa.String(2048), nullable=True))
    op.add_column("api_request_logs", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column("api_request_logs", sa.Column("error_detail", sa.String(512), nullable=True))
    op.create_index("ix_api_request_logs_request_id", "api_request_logs", ["request_id"])

    op.create_table(
        "rate_limits",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("limit_key", sa.String(255), nullable=False),
        sa.Column("path", sa.String(2048), nullable=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rate_limits_user_id", "rate_limits", ["user_id"])
    op.create_index("ix_rate_limits_ip_address", "rate_limits", ["ip_address"])
    op.create_index("ix_rate_limits_limit_key", "rate_limits", ["limit_key"])


def downgrade():
    op.drop_index("ix_rate_limits_limit_key", table_name="rate_limits")
    op.drop_index("ix_rate_limits_ip_address", table_name="rate_limits")
    op.drop_index("ix_rate_limits_user_id", table_name="rate_limits")
    op.drop_table("rate_limits")

    op.drop_index("ix_api_request_logs_request_id", table_name="api_request_logs")
    op.drop_column("api_request_logs", "error_detail")
    op.drop_column("api_request_logs", "request_id")
    op.drop_column("api_request_logs", "query_string")

    op.execute("ALTER INDEX IF EXISTS ix_api_request_logs_user_id RENAME TO ix_request_logs_user_id")
    op.rename_table("api_request_logs", "request_logs")

"""Create API Layer tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("users", sa.Column("id", uuid, primary_key=True), sa.Column("full_name", sa.String(255), nullable=False), sa.Column("email", sa.String(320), nullable=False), sa.Column("hashed_password", sa.String(255), nullable=False), sa.Column("role", sa.String(50), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *timestamps(), sa.UniqueConstraint("email"))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("refresh_tokens", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_table("api_keys", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("key_hash", sa.String(64), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("last_used_at", sa.DateTime(timezone=True)))
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_table("projects", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("color", sa.String(32)), sa.Column("icon", sa.String(64)), sa.Column("status", sa.String(20), nullable=False), sa.Column("is_pinned", sa.Boolean(), nullable=False), sa.Column("is_archived", sa.Boolean(), nullable=False), sa.Column("last_activity_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_user_status", "projects", ["user_id", "status"])
    op.create_table("chat_threads", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("project_id", uuid, sa.ForeignKey("projects.id", ondelete="SET NULL")), sa.Column("title", sa.String(255)), sa.Column("status", sa.String(20), nullable=False), sa.Column("is_pinned", sa.Boolean(), nullable=False), sa.Column("is_archived", sa.Boolean(), nullable=False), sa.Column("last_message_preview", sa.String(120)), sa.Column("last_activity_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])
    op.create_index("ix_chat_threads_project_id", "chat_threads", ["project_id"])
    op.create_index("ix_chat_threads_status", "chat_threads", ["status"])
    op.create_index("ix_chats_user_status", "chat_threads", ["user_id", "status"])
    op.create_table("request_logs", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid), sa.Column("method", sa.String(10), nullable=False), sa.Column("path", sa.String(2048), nullable=False), sa.Column("status_code", sa.Integer(), nullable=False), sa.Column("ip_address", sa.String(64)), sa.Column("user_agent", sa.String(512)), sa.Column("duration_ms", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_request_logs_user_id", "request_logs", ["user_id"])
    op.create_table("audit_logs", sa.Column("id", uuid, primary_key=True), sa.Column("user_id", uuid), sa.Column("action", sa.String(100), nullable=False), sa.Column("resource", sa.String(100), nullable=False), sa.Column("metadata", sa.JSON()), sa.Column("ip_address", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade():
    for table in ["audit_logs", "request_logs", "chat_threads", "projects", "api_keys", "refresh_tokens", "users"]:
        op.drop_table(table)

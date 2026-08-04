"""Add chat share snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_chat_shares"
down_revision = "0004_user_profile_fields"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "chat_shares",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("chat_id", uuid, sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(96), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("title", sa.String(255)),
        sa.Column("message_snapshot", sa.JSON()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_shares_chat_id", "chat_shares", ["chat_id"], unique=True)
    op.create_index("ix_chat_shares_user_id", "chat_shares", ["user_id"])
    op.create_index("ix_chat_shares_token", "chat_shares", ["token"], unique=True)
    op.create_index("ix_chat_shares_visibility", "chat_shares", ["visibility"])


def downgrade():
    op.drop_index("ix_chat_shares_visibility", table_name="chat_shares")
    op.drop_index("ix_chat_shares_token", table_name="chat_shares")
    op.drop_index("ix_chat_shares_user_id", table_name="chat_shares")
    op.drop_index("ix_chat_shares_chat_id", table_name="chat_shares")
    op.drop_table("chat_shares")

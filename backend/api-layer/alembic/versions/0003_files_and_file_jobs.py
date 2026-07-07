"""Add files and file_jobs tables for image upload metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_files"
down_revision = "0002_api_logs"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "files",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("original_name", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("public_url", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_files_user_id", "files", ["user_id"])
    op.create_index("ix_files_object_key", "files", ["object_key"], unique=True)
    op.create_index("ix_files_status", "files", ["status"])
    op.create_index("ix_files_user_status", "files", ["user_id", "status"])

    op.create_table(
        "file_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("file_id", uuid, sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("payload_json", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_file_jobs_file_id", "file_jobs", ["file_id"])
    op.create_index("ix_file_jobs_job_type", "file_jobs", ["job_type"])
    op.create_index("ix_file_jobs_status", "file_jobs", ["status"])


def downgrade():
    op.drop_table("file_jobs")
    op.drop_table("files")

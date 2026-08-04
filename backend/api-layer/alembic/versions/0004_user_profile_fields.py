"""Add persisted user profile fields."""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_profile_fields"
down_revision = "0003_files"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("nickname", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("address", sa.String(512), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "address")
    op.drop_column("users", "phone")
    op.drop_column("users", "nickname")

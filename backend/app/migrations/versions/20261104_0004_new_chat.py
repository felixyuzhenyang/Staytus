"""Persist a clean conversation and independent assistant-update visibility."""
import sqlalchemy as sa
from alembic import op

revision = "20261104_0004"
down_revision = "20261104_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("hide_assistant_updates", sa.Boolean(),
        nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("conversations", "hide_assistant_updates")

"""Optional structured planning facts; existing accounts retain unknown defaults."""
from alembic import op
import sqlalchemy as sa

revision = "20261103_0002"
down_revision = "20261103_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_profiles", sa.Column("planning_details", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("user_profiles", "planning_details")

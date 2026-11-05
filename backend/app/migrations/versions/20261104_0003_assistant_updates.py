"""Add proactive assistant outbox and independent user settings."""
import sqlalchemy as sa
from alembic import op

revision = "20261104_0003"
down_revision = "20261103_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_preferences", sa.Column("assistant_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("notification_preferences", sa.Column("assistant_language", sa.String(8), nullable=False, server_default="en"))
    op.create_table("assistant_updates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(64), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("batch_key", sa.String(120), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False), sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False), sa.Column("model_id", sa.String(160)),
        sa.Column("language", sa.String(8), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(64)), sa.Column("claimed_at", sa.DateTime()),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False), sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("generated_at", sa.DateTime()),
        sa.Column("read_at", sa.DateTime()), sa.UniqueConstraint("account_id", "batch_key"))
    for column in ("account_id", "profile_id", "state"):
        op.create_index(f"ix_assistant_updates_{column}", "assistant_updates", [column])
    op.create_table("assistant_update_events",
        sa.Column("notice_id", sa.String(64), sa.ForeignKey("reminder_inbox.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("profile_version", sa.Integer(), primary_key=True),
        sa.Column("update_id", sa.String(64), sa.ForeignKey("assistant_updates.id", ondelete="CASCADE"), nullable=False))
    op.create_index("ix_assistant_update_events_update_id", "assistant_update_events", ["update_id"])


def downgrade():
    op.drop_table("assistant_update_events")
    op.drop_table("assistant_updates")
    op.drop_column("notification_preferences", "assistant_language")
    op.drop_column("notification_preferences", "assistant_enabled")

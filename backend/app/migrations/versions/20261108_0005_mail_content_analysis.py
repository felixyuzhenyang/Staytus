"""Add explicit email-content analysis consent and encrypted summary storage."""
import sqlalchemy as sa
from alembic import op

revision = "20261108_0005"
down_revision = "20261104_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_agent_permissions", sa.Column("content_analysis_enabled", sa.Boolean(),
        nullable=False, server_default=sa.false()))
    op.add_column("mail_agent_permissions", sa.Column("content_analysis_updated_at", sa.DateTime(), nullable=True))
    op.create_table("mail_message_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(64), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("connection_id", sa.String(), sa.ForeignKey("provider_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_result", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "provider", "connection_id", "message_hash"))
    op.create_index("ix_mail_message_analyses_account_id", "mail_message_analyses", ["account_id"])
    op.create_index("ix_mail_message_analyses_profile_id", "mail_message_analyses", ["profile_id"])
    op.create_index("ix_mail_message_analyses_expires_at", "mail_message_analyses", ["expires_at"])


def downgrade():
    op.drop_table("mail_message_analyses")
    op.drop_column("mail_agent_permissions", "content_analysis_updated_at")
    op.drop_column("mail_agent_permissions", "content_analysis_enabled")

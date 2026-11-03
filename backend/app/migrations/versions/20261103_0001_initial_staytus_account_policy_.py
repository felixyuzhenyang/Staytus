"""Initial Staytus account policy connector and reminder schema

Revision ID: 20261103_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


revision = '20261103_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Extension creation belongs to this explicit privileged migration, never API startup.
    if op.get_context().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('accounts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_accounts_email'), ['email'], unique=True)

    op.create_table('policy_sources',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('allowed_host', sa.String(length=100), nullable=False),
    sa.Column('freshness_days', sa.Integer(), nullable=False),
    sa.Column('auto_fetch_enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('conversations',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('thread_id', sa.String(), nullable=True),
    sa.Column('history', sa.JSON(), nullable=False),
    sa.Column('busy_until', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversations_account_id'), ['account_id'], unique=False)

    op.create_table('fetch_attempt_log',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('source_id', sa.String(length=64), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['policy_sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mail_agent_permissions',
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('account_id', 'provider')
    )
    op.create_table('mail_monitor_preferences',
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('connection_id', sa.String(length=64), nullable=True),
    sa.Column('timezone', sa.String(length=100), nullable=False),
    sa.Column('check_hour', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('next_check_at', sa.DateTime(), nullable=True),
    sa.Column('last_check_at', sa.DateTime(), nullable=True),
    sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('last_error_code', sa.String(length=80), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('lease_token', sa.String(length=64), nullable=True),
    sa.Column('lease_until', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', 'provider')
    )
    op.create_table('mail_monitor_seen',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('connection_id', sa.String(length=64), nullable=False),
    sa.Column('message_hash', sa.String(length=64), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'provider', 'connection_id', 'message_hash')
    )
    with op.batch_alter_table('mail_monitor_seen', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mail_monitor_seen_account_id'), ['account_id'], unique=False)

    op.create_table('notification_preferences',
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('in_app_enabled', sa.Boolean(), nullable=False),
    sa.Column('popup_enabled', sa.Boolean(), nullable=False),
    sa.Column('email_enabled', sa.Boolean(), nullable=False),
    sa.Column('timezone', sa.String(length=100), nullable=False),
    sa.Column('digest_hour', sa.Integer(), nullable=False),
    sa.Column('digest_weekday', sa.Integer(), nullable=False),
    sa.Column('digest_monthday', sa.Integer(), nullable=False),
    sa.Column('scheduled_frequency', sa.String(length=16), nullable=False),
    sa.Column('lead_days', sa.Integer(), nullable=False),
    sa.Column('email_provider', sa.String(length=20), nullable=True),
    sa.Column('email_connection_id', sa.String(length=64), nullable=True),
    sa.Column('email_recipient', sa.String(length=320), nullable=True),
    sa.Column('next_email_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id')
    )
    op.create_table('policy_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('source_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('reviewed', sa.Boolean(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('fixture', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.Column('visa_types', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['policy_sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('provider_connections',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('encrypted_tokens', sa.Text(), nullable=False),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('last_sync_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'provider')
    )
    op.create_table('source_capture_state',
    sa.Column('source_id', sa.String(length=64), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('last_success_at', sa.DateTime(), nullable=True),
    sa.Column('final_url', sa.Text(), nullable=True),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('robots_status', sa.String(length=64), nullable=False),
    sa.Column('last_error', sa.String(length=200), nullable=True),
    sa.Column('etag', sa.Text(), nullable=True),
    sa.Column('last_modified', sa.Text(), nullable=True),
    sa.Column('latest_version_id', sa.String(length=64), nullable=True),
    sa.Column('retrieval_mode', sa.String(length=64), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['policy_sources.id'], ),
    sa.PrimaryKeyConstraint('source_id')
    )
    op.create_table('source_refresh_requests',
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('source_scope', sa.String(length=64), nullable=False),
    sa.Column('requested_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('account_id', 'source_scope')
    )
    op.create_table('user_profiles',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('school', sa.String(length=100), nullable=False),
    sa.Column('status_type', sa.String(length=32), nullable=False),
    sa.Column('program_start', sa.Date(), nullable=False),
    sa.Column('program_end', sa.Date(), nullable=False),
    sa.Column('graduation_date', sa.Date(), nullable=True),
    sa.Column('travel_date', sa.Date(), nullable=True),
    sa.Column('travel_signature_date', sa.Date(), nullable=True),
    sa.Column('notification_frequency', sa.String(length=16), nullable=False),
    sa.Column('nationality', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('synthetic', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id')
    )
    op.create_table('approval_requests',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('receipt', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('audit_events',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('correlation_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('auth_sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=True),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_sessions_account_id'), ['account_id'], unique=False)

    op.create_table('notification_deliveries',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('dedup_key', sa.String(length=180), nullable=False),
    sa.Column('recipient', sa.String(length=320), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('connection_id', sa.String(length=64), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
    sa.Column('claimed_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('error_code', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'dedup_key')
    )
    with op.batch_alter_table('notification_deliveries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_deliveries_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_deliveries_status'), ['status'], unique=False)

    op.create_table('notification_queue',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('policy_chunks',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('policy_version_id', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', sa.JSON(), nullable=True),
    sa.Column('vector', pgvector.sqlalchemy.vector.VECTOR().with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('embedding_model', sa.String(length=100), nullable=True),
    sa.Column('superseded', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['policy_version_id'], ['policy_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('policy_snapshot_metadata',
    sa.Column('policy_version_id', sa.String(length=64), nullable=False),
    sa.Column('requested_url', sa.Text(), nullable=False),
    sa.Column('final_url', sa.Text(), nullable=False),
    sa.Column('captured_at', sa.DateTime(), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=False),
    sa.Column('embedding_model', sa.String(length=160), nullable=True),
    sa.Column('embedding_dimension', sa.Integer(), nullable=True),
    sa.Column('index_status', sa.String(length=64), nullable=False),
    sa.Column('classification', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['policy_version_id'], ['policy_versions.id'], ),
    sa.PrimaryKeyConstraint('policy_version_id')
    )
    op.create_table('reminder_inbox',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('dedup_key', sa.String(length=240), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.Column('popup_seen_at', sa.DateTime(), nullable=True),
    sa.Column('superseded_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('profile_id', 'dedup_key')
    )
    with op.batch_alter_table('reminder_inbox', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reminder_inbox_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reminder_inbox_profile_id'), ['profile_id'], unique=False)

    op.create_table('rule_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('school', sa.String(length=32), nullable=False),
    sa.Column('preparation_days', sa.Integer(), nullable=False),
    sa.Column('policy_version_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('reviewed_by', sa.String(length=64), nullable=False),
    sa.Column('effective_from', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['policy_version_id'], ['policy_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('deadline_results',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('profile_id', sa.String(length=64), nullable=False),
    sa.Column('workflow', sa.String(length=64), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('rule_version_id', sa.String(length=64), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ),
    sa.ForeignKeyConstraint(['rule_version_id'], ['rule_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('profile_id', 'workflow', 'profile_version', 'rule_version_id')
    )
    op.create_table('notification_delivery_items',
    sa.Column('notice_id', sa.String(length=64), nullable=False),
    sa.Column('delivery_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['delivery_id'], ['notification_deliveries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['notice_id'], ['reminder_inbox.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('notice_id')
    )
    with op.batch_alter_table('notification_delivery_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_delivery_items_delivery_id'), ['delivery_id'], unique=False)

    op.create_table('oauth_attempts',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('verifier', sa.Text(), nullable=False),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['auth_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('oauth_attempts')
    with op.batch_alter_table('notification_delivery_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_delivery_items_delivery_id'))

    op.drop_table('notification_delivery_items')
    op.drop_table('deadline_results')
    op.drop_table('rule_versions')
    with op.batch_alter_table('reminder_inbox', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reminder_inbox_profile_id'))
        batch_op.drop_index(batch_op.f('ix_reminder_inbox_account_id'))

    op.drop_table('reminder_inbox')
    op.drop_table('policy_snapshot_metadata')
    op.drop_table('policy_chunks')
    op.drop_table('notification_queue')
    with op.batch_alter_table('notification_deliveries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_deliveries_status'))
        batch_op.drop_index(batch_op.f('ix_notification_deliveries_account_id'))

    op.drop_table('notification_deliveries')
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_sessions_account_id'))

    op.drop_table('auth_sessions')
    op.drop_table('audit_events')
    op.drop_table('approval_requests')
    op.drop_table('user_profiles')
    op.drop_table('source_refresh_requests')
    op.drop_table('source_capture_state')
    op.drop_table('provider_connections')
    op.drop_table('policy_versions')
    op.drop_table('notification_preferences')
    with op.batch_alter_table('mail_monitor_seen', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mail_monitor_seen_account_id'))

    op.drop_table('mail_monitor_seen')
    op.drop_table('mail_monitor_preferences')
    op.drop_table('mail_agent_permissions')
    op.drop_table('fetch_attempt_log')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_account_id'))

    op.drop_table('conversations')
    op.drop_table('policy_sources')
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accounts_email'))

    op.drop_table('accounts')
    # ### end Alembic commands ###

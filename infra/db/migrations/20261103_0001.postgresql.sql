-- Generated from Alembic revision 20261103_0001; review only, apply with database_cli.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 20261103_0001

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE accounts (
    id VARCHAR(64) NOT NULL,
    email VARCHAR(320) NOT NULL,
    name VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_accounts_email ON accounts (email);

CREATE TABLE policy_sources (
    id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    url TEXT NOT NULL,
    allowed_host VARCHAR(100) NOT NULL,
    freshness_days INTEGER NOT NULL,
    auto_fetch_enabled BOOLEAN NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE conversations (
    id VARCHAR NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR,
    history JSON NOT NULL,
    busy_until TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE INDEX ix_conversations_account_id ON conversations (account_id);

CREATE TABLE fetch_attempt_log (
    id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    success BOOLEAN NOT NULL,
    detail TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(source_id) REFERENCES policy_sources (id)
);

CREATE TABLE mail_agent_permissions (
    account_id VARCHAR(64) NOT NULL,
    provider VARCHAR NOT NULL,
    enabled BOOLEAN NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (account_id, provider),
    FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE TABLE mail_monitor_preferences (
    account_id VARCHAR(64) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL,
    connection_id VARCHAR(64),
    timezone VARCHAR(100) NOT NULL,
    check_hour INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    next_check_at TIMESTAMP WITHOUT TIME ZONE,
    last_check_at TIMESTAMP WITHOUT TIME ZONE,
    last_attempt_at TIMESTAMP WITHOUT TIME ZONE,
    last_error_code VARCHAR(80),
    failure_count INTEGER NOT NULL,
    lease_token VARCHAR(64),
    lease_until TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (account_id, provider),
    FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE
);

CREATE TABLE mail_monitor_seen (
    id VARCHAR(64) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    connection_id VARCHAR(64) NOT NULL,
    message_hash VARCHAR(64) NOT NULL,
    first_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    UNIQUE (account_id, provider, connection_id, message_hash)
);

CREATE INDEX ix_mail_monitor_seen_account_id ON mail_monitor_seen (account_id);

CREATE TABLE notification_preferences (
    account_id VARCHAR(64) NOT NULL,
    in_app_enabled BOOLEAN NOT NULL,
    popup_enabled BOOLEAN NOT NULL,
    email_enabled BOOLEAN NOT NULL,
    timezone VARCHAR(100) NOT NULL,
    digest_hour INTEGER NOT NULL,
    digest_weekday INTEGER NOT NULL,
    digest_monthday INTEGER NOT NULL,
    scheduled_frequency VARCHAR(16) NOT NULL,
    lead_days INTEGER NOT NULL,
    email_provider VARCHAR(20),
    email_connection_id VARCHAR(64),
    email_recipient VARCHAR(320),
    next_email_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (account_id),
    FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE
);

CREATE TABLE policy_versions (
    id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(40) NOT NULL,
    reviewed BOOLEAN NOT NULL,
    version INTEGER NOT NULL,
    fixture BOOLEAN NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    verified_at TIMESTAMP WITHOUT TIME ZONE,
    visa_types JSON NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(source_id) REFERENCES policy_sources (id)
);

CREATE TABLE provider_connections (
    id VARCHAR NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    provider VARCHAR NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    scopes JSON NOT NULL,
    last_sync_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id),
    UNIQUE (account_id, provider)
);

CREATE TABLE source_capture_state (
    source_id VARCHAR(64) NOT NULL,
    last_attempt_at TIMESTAMP WITHOUT TIME ZONE,
    last_success_at TIMESTAMP WITHOUT TIME ZONE,
    final_url TEXT,
    http_status INTEGER,
    robots_status VARCHAR(64) NOT NULL,
    last_error VARCHAR(200),
    etag TEXT,
    last_modified TEXT,
    latest_version_id VARCHAR(64),
    retrieval_mode VARCHAR(64) NOT NULL,
    chunk_count INTEGER NOT NULL,
    PRIMARY KEY (source_id),
    FOREIGN KEY(source_id) REFERENCES policy_sources (id)
);

CREATE TABLE source_refresh_requests (
    account_id VARCHAR(64) NOT NULL,
    source_scope VARCHAR(64) NOT NULL,
    requested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (account_id, source_scope),
    FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE TABLE user_profiles (
    id VARCHAR(64) NOT NULL,
    account_id VARCHAR(64),
    name VARCHAR(100) NOT NULL,
    school VARCHAR(100) NOT NULL,
    status_type VARCHAR(32) NOT NULL,
    program_start DATE NOT NULL,
    program_end DATE NOT NULL,
    graduation_date DATE,
    travel_date DATE,
    travel_signature_date DATE,
    notification_frequency VARCHAR(16) NOT NULL,
    nationality VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL,
    email VARCHAR(320),
    synthetic BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id),
    UNIQUE (account_id)
);

CREATE TABLE approval_requests (
    id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    profile_version INTEGER NOT NULL,
    payload JSON NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    receipt JSON,
    PRIMARY KEY (id),
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id)
);

CREATE TABLE audit_events (
    id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    action VARCHAR(100) NOT NULL,
    detail JSON NOT NULL,
    correlation_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id)
);

CREATE TABLE auth_sessions (
    id VARCHAR(64) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64),
    role VARCHAR(16) NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id),
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id),
    UNIQUE (token_hash)
);

CREATE INDEX ix_auth_sessions_account_id ON auth_sessions (account_id);

CREATE TABLE notification_deliveries (
    id VARCHAR(64) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    dedup_key VARCHAR(180) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    connection_id VARCHAR(64) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(24) NOT NULL,
    attempts INTEGER NOT NULL,
    next_attempt_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    claimed_at TIMESTAMP WITHOUT TIME ZONE,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    error_code VARCHAR(80),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id) ON DELETE CASCADE,
    UNIQUE (account_id, dedup_key)
);

CREATE INDEX ix_notification_deliveries_account_id ON notification_deliveries (account_id);

CREATE INDEX ix_notification_deliveries_status ON notification_deliveries (status);

CREATE TABLE notification_queue (
    id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    data JSON NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id)
);

CREATE TABLE policy_chunks (
    id VARCHAR(64) NOT NULL,
    policy_version_id VARCHAR(64) NOT NULL,
    text TEXT NOT NULL,
    embedding JSON,
    vector VECTOR,
    embedding_model VARCHAR(100),
    superseded BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_versions (id)
);

CREATE TABLE policy_snapshot_metadata (
    policy_version_id VARCHAR(64) NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    captured_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    http_status INTEGER NOT NULL,
    embedding_model VARCHAR(160),
    embedding_dimension INTEGER,
    index_status VARCHAR(64) NOT NULL,
    classification JSON NOT NULL,
    PRIMARY KEY (policy_version_id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_versions (id)
);

CREATE TABLE reminder_inbox (
    id VARCHAR(64) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    dedup_key VARCHAR(240) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    data JSON NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    read_at TIMESTAMP WITHOUT TIME ZONE,
    popup_seen_at TIMESTAMP WITHOUT TIME ZONE,
    superseded_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE,
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id) ON DELETE CASCADE,
    UNIQUE (profile_id, dedup_key)
);

CREATE INDEX ix_reminder_inbox_account_id ON reminder_inbox (account_id);

CREATE INDEX ix_reminder_inbox_profile_id ON reminder_inbox (profile_id);

CREATE TABLE rule_versions (
    id VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL,
    school VARCHAR(32) NOT NULL,
    preparation_days INTEGER NOT NULL,
    policy_version_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    reviewed_by VARCHAR(64) NOT NULL,
    effective_from TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_versions (id)
);

CREATE TABLE deadline_results (
    id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    workflow VARCHAR(64) NOT NULL,
    profile_version INTEGER NOT NULL,
    rule_version_id VARCHAR(64) NOT NULL,
    result JSON NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(profile_id) REFERENCES user_profiles (id),
    FOREIGN KEY(rule_version_id) REFERENCES rule_versions (id),
    UNIQUE (profile_id, workflow, profile_version, rule_version_id)
);

CREATE TABLE notification_delivery_items (
    notice_id VARCHAR(64) NOT NULL,
    delivery_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (notice_id),
    FOREIGN KEY(delivery_id) REFERENCES notification_deliveries (id) ON DELETE CASCADE,
    FOREIGN KEY(notice_id) REFERENCES reminder_inbox (id) ON DELETE CASCADE
);

CREATE INDEX ix_notification_delivery_items_delivery_id ON notification_delivery_items (delivery_id);

CREATE TABLE oauth_attempts (
    id VARCHAR NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    provider VARCHAR NOT NULL,
    verifier TEXT NOT NULL,
    scopes JSON NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES accounts (id),
    FOREIGN KEY(session_id) REFERENCES auth_sessions (id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('20261103_0001') RETURNING alembic_version.version_num;

COMMIT;

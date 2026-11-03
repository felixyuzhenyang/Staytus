#!/bin/sh
set -eu
# Only runs when initializing a new Compose volume. Never echo credentials.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set="runtime_password=$STAYTUS_RUNTIME_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE staytus_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'runtime_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO staytus_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO staytus_runtime;
SQL

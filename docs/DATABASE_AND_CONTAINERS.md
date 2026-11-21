# PostgreSQL, Migrations, and Container Setup (2026-11-03)

This guide records the database migration and local container setup as of November 3, 2026. The deployment status below refers to that stage. See the [Vercel operations guide](../infra/vercel/README.md) for the later public deployment.

## Supabase Hosting and Database Migration

- The project used Supabase Free with PostgreSQL 17 in the US East region. No paid IPv4 option or plan upgrade was purchased. The connection used the IPv4 **Session pooler** shown in the dashboard, with `sslmode=verify-full` and the project's private CA bundle. Supabase enforced SSL.
- `backend/.env` was switched to the cloud `staytus_runtime` role shared by the main API and tool gateway. This role cannot create databases or roles, bypass row-level security, create permanent tables, or modify the migration revision. IBM and OAuth settings, signing secrets, and token encryption settings stayed in place. Recovery of the expired temporary gateway address was logged separately.
- The original Supabase `postgres` administrator password was used only for initialization. The administrator connection is kept in the private `.local/supabase/admin.env` file. `migration.env` uses the separate `staytus_owner` role, and `runtime.env` stores the runtime connection. All three files use mode `0600` and are kept out of Git, the frontend, model inputs, and Docker images. The one-time local page used to hand off the configuration was stopped after use, and the original handoff file was removed. Local and cloud roles with the same names use different credentials.
- The cloud database was initialized with Alembic baseline `20261103_0001`, pgvector, and 25 application tables. Before migrating data, we verified shared API and gateway access with two accounts, rejection of forged ownership, and persistence after restart. We then stopped writes to the local application database, took a backup, and imported 266 records and 98 total policy chunks from the PostgreSQL source, comparing each value. The old SQLite database was preserved separately.
- The Supabase Data API was disabled. The `anon`, `authenticated`, and `service_role` roles had no grants on the application tables. Staytus continued to use its own accounts and backend ownership checks, with database credentials kept out of the frontend. Automatic migrations tied to GitHub branches were disabled. Alembic remained the only authority for schema revisions.
- The cloud application backup is a private SQLite archive labeled with its Alembic revision. We used `import-sqlite` to restore it into a fresh local PostgreSQL database, checked the data field by field, and then removed the temporary restore database. The archive covers 25 application tables. Supabase Auth, Storage, and managed point-in-time recovery fall outside its scope. The private verification report is at `.local/supabase/cloud-backup-restore-verification.json`.
- The bundled local `pg_dump` was built without SSL support, so it could not back up the cloud database directly. The official container client download also timed out. We used the verified TLS-enabled driver to create a portable application archive. A full PostgreSQL dump from before the migration was retained separately. A standard TLS-capable `pg_dump` and automated backups could be configured later. An empty dump from a failed run is unusable.
- At this stage, the frontend, API, gateway, and scheduled jobs still ran locally. Public deployment, the temporary HTTPS tool tunnel, live OAuth checks, independent scheduling, and safeguards for public accounts were tracked separately.
- After migration, the main Live agent passed two-account verification and the browser completed an end-to-end chat through the backend-for-frontend (BFF). Test data was cleaned up. Chat and the existing policy, reminder, and mailbox-check settings were restored, and all three local services were healthy. An expired temporary tunnel was restored within the original authorization, and the same Draft and Live connections were updated. No new IBM roles or keys were created, and the tools were not reimported.

## Earlier Local Database and Container Setup

- In this earlier phase, the private development configuration moved from SQLite to a real PostgreSQL database. The main backend and tool gateway shared `DATABASE_URL`.
- Docker and a system PostgreSQL installation were initially unavailable, so a removable PostgreSQL runtime was installed in the ignored `.local/postgres-runtime/` directory. It ran PostgreSQL 18.6 and listened only at `127.0.0.1:55432`. This instance had no TLS and was restricted to local use. A cloud database requires managed hosting and certificate verification.
- Data lived in `.local/postgres/data/`, with no service installed to launch at boot. `backend/.env` stored the limited runtime connection, and `.local/postgres/admin.env` stored a separate migration connection. Both used mode `0600`. Existing IBM and OAuth keys were unchanged.
- We migrated 25 application tables, 266 records, and 98 total policy chunks, including historical versions. Of those chunks, 87 had previously been current. We verified values field by field. pgvector uses `float32`, so the comparison allowed small, explicitly bounded differences in vectors. The original SQLite file was left intact, and a separate pre-migration SQLite backup was retained.
- The legacy database contained an empty `rule_change_proposals` table, which stayed in SQLite and was excluded from the new schema. If the table contains records, the migration rejects it. The legacy `retrieval_mode` field had a declared length of 24, compared with 64 on the target. The migration verified that no values were truncated. Other unknown schema differences are rejected.
- We created a PostgreSQL dump, restored it to a new temporary database, compared every value in every table, and deleted the temporary database. Backups, credentials, and runtime reports remained under `.local/` and outside Git.
- Live checks with two synthetic accounts confirmed isolation between the separate API and gateway processes, rejection of forged ownership, and session persistence across a gateway restart. The synthetic accounts were cleaned up afterward.
- No IBM-managed PostgreSQL database, Code Engine app, domain, or new IBM credential was created during this phase. Cloud resources and a live HTTPS connection were deferred.
- Docker Desktop 4.98.0 was installed later. The user accepted the terms and selected the free Personal plan. Both the frontend and backend `linux/amd64` images built locally and started in temporary containers with external networking disabled. The backend startup check used a synthetic, temporary SQLite database. Cloud PostgreSQL and Orchestrate were outside that check. CI had not been pushed or run, and the app had not yet been deployed publicly at this stage.

## Running Locally

For the machine already configured with the private Supabase connection, run:

```sh
make database-check
make dev
```

The app opens at http://127.0.0.1:3000. Supabase hosts the database, so the local PostgreSQL instance does not need to start first. Shutting down the computer still stops locally running web, API, and gateway services and their background scheduling. The following commands start the retained local PostgreSQL instance and check and run the app using its existing configuration. Starting the instance alone does not switch the app to it.

```sh
make database-local
make database-check
make dev
```

For a rollback, stop writes to the cloud database, review any cloud-side changes, and decide how to cut over before changing the connection. The older local copy is not kept in sync with the cloud. Retain the local data directory.

Other developers can use PostgreSQL through Docker Compose or install the optional local runtime:

```sh
uv pip install --python backend/.venv/bin/python --target .local/postgres-runtime 'embedded-postgres==18.6.3'
make database-local
```

`scripts/local_postgres.py start` sets up the local instance and its private configuration and leaves `backend/.env` in place. For a new setup, use the URL from `.local/postgres/admin.env` for migrations and the URL from `runtime.env` for the runtime configuration. Keep the actual connection values out of Git and chat.

## Versioned Schema Upgrades

Baseline `20261103_0001` defines 25 application tables and the Alembic version table. At this stage, revision `20261103_0002` added only the `planning_details` JSON column to `user_profiles`, with an empty object as the default. Existing profiles gained no inferred application facts. Migration definitions live under `backend/app/migrations/versions/`, and generated SQL for review lives under `infra/db/migrations/`. The SQL contains no connection details, personal data, or secrets. Explicit adoption of a legacy SQLite database checks the full schema before upgrading from a matching historical revision. Unknown differences are rejected.

At startup, the API and gateway only check the schema revision. `create_all`, DDL, and extension creation belong to migration. First run the following with the migration account:

```sh
cd backend
.venv/bin/python -m app.database_cli --env-file ../.local/postgres/admin.env upgrade
.venv/bin/python ../scripts/local_postgres.py grant-runtime
.venv/bin/python -m app.database_cli check
```

`upgrade` can be rerun and uses a transaction-level advisory lock. Cloud PostgreSQL must have pgvector preinstalled or allow the migration role to create it. Existing databases without a revision are not stamped automatically.

`adopt-sqlite` is only for a backed-up legacy SQLite database whose schema exactly matches the baseline. For the earlier SQLite transfer, we used a read-only snapshot with `import-sqlite`:

```sh
.venv/bin/python -m app.database_cli --env-file ../.local/postgres/admin.env import-sqlite \
  --sqlite-path ../.local/backups/YOUR_SNAPSHOT.db --report ../.local/import-report.json
```

The destination must be migrated and empty. Stop the API, gateway, and background jobs first. The importer locks application tables and uses one transaction. A failure rolls back the entire import. Existing records are neither merged nor overwritten. After a successful import, do not run it against the now-populated database.

The Supabase migration read from a snapshot of the active PostgreSQL database. The old SQLite file was not reused. The source connection and target migration settings were stored in separate private files. The following records the completed operation and must not be rerun against a populated database.

```sh
cd backend
.venv/bin/python -m app.database_cli --env-file ../.local/supabase/migration.env import-postgres \
  --source-env-file ../.local/postgres/admin.env --report ../.local/supabase/import-verification.json
```

Both databases must be PostgreSQL and on the current revision. The source is read in a repeatable-read, read-only transaction. The target must be empty. The importer locks all application tables and compares values field by field before committing. Locks and statements have timeouts, and a failure rolls back all inserts. The source is left intact and existing destination records are protected. The migration included a write freeze, backup, and checks of TLS, roles, and shared access. Run the same checks when restoring to a new database.

Create a new revision for each schema change and keep published revisions intact. Review the generated DDL, verify it in a separate test database, and run the migration as a separate deployment step. A downgrade can delete data and is unsuitable as a general production recovery mechanism.

## Database Roles and Shared Secrets

- `staytus_owner` handles local migrations and backups. In the cloud, use a dedicated developer or migration role supported by the provider and keep it separate from the API and gateway credentials.
- `staytus_runtime` can read and write application tables and read the revision table. Verification confirmed that it cannot create tables or update the revision table.
- The API and gateway must share the existing `CONTEXT_SECRET`, `ORCHESTRATE_TOOL_KEY`, and `CONNECTOR_TOKEN_KEY`. Preserve these values during a database copy to keep existing signatures and encrypted data usable.

The migration job only needs database configuration. If `DATABASE_RUNTIME_ROLE` is set, `upgrade` grants the existing non-superuser role its required privileges and revokes write access to the revision table.

## Containers

Build both Dockerfiles from the repository root. Docker does not allow `COPY ../config` to cross the build context boundary.

```sh
make images
```

- The backend image installs locked dependencies and includes migrations. It reads `/app/config` at runtime and runs as a non-root user. One image supports the `api`, `gateway`, `migrate`, and `check` roles and honors the platform's `PORT`.
- The frontend uses a multi-stage build that copies the standalone output, static assets, and public directory. It runs as a non-root user. Configure `BACKEND_URL` and `APP_ORIGIN` at runtime. A production instance without a backend URL returns HTTP 503 and has no localhost fallback.
- The root `.dockerignore` uses an allowlist that excludes `.env`, databases, backups, `.local`, Bob conversations, and local dependencies.
- `backend/.env.production.example` and `frontend/.env.production.example` are templates for platform configuration. Replace the placeholders with actual platform values before deployment. Production database connections require Psycopg 3, `sslmode=verify-full`, and a trusted CA. The loopback-only local PostgreSQL instance does not use TLS.

For Docker Compose, copy `.env.compose.example` to the ignored `.local/compose.env` file, set distinct passwords, and run:

```sh
docker compose --env-file .local/compose.env --profile app up --build
```

Compose checks database health and runs the migration before starting the API, gateway, and frontend. The published ports bind to loopback by default. The production frontend uses Secure cookies, so full browser and OAuth verification requires a local HTTPS proxy or a cloud HTTPS endpoint. Compose disables the three background workers. Independent scheduling was planned for the next phase. `make dev` uses the worker settings in the private backend configuration.

## Verification and Recovery

```sh
make test
make build
backend/.venv/bin/python scripts/verify_shared_database.py
backend/.venv/bin/python scripts/local_postgres.py backup
backend/.venv/bin/python scripts/local_postgres.py restore-check
```

Set `STAYTUS_TEST_DATABASE_URL` for the PostgreSQL test suite. It only accepts database names matching `staytus_test*`, and each fixture uses its own schema. Never point the test suite at the application database. Unit tests can still use SQLite. Live IBM and OAuth integrations require separate verification.

Backup files contain private data and use mode `0600`. A restore check creates a separate temporary database with a random name and leaves the running database intact. For a real restore, stop writes, restore and verify a fresh database, and then switch the connection. Keep the application version, database revision, and original token encryption key compatible.

The next cloud deployment plan at this stage was to reuse Supabase and the limited runtime role, mount the trusted CA and store the private connection in platform secrets, deploy the API and gateway, set up stable HTTPS and the Orchestrate connection, repeat two-account Live checks, and verify the frontend and OAuth callbacks. Cloud containers need the mounted CA path instead of the absolute path from the local machine. Recheck certificate validation after updating it. Public registration, production OAuth verification, account recovery, shared rate limiting, independent background scheduling, and ongoing operations were tracked separately.

## No-Paid-Services Constraint

The user chose **Supabase Free managed PostgreSQL** on November 3, 2026, to minimize costs. The project was created and the data migrated. Local Docker builds used the Personal plan without paid cloud builds. No paid IBM PostgreSQL instance was created, and upgrades to paid plans were not automatic.

On the pricing check date, Supabase's Free plan listed 500 MB of database storage, up to two active projects, and pausing after one week of inactivity. The local database was about 11 MB, which provided a preliminary capacity estimate. Measure cloud system overhead, indexes, growth, connection counts, and traffic separately. Continuous availability is not guaranteed on the free plan. IBM model and Orchestrate costs and future compute hosting costs require separate checks.

Staytus retained SQLAlchemy, Psycopg, Alembic, and its own account system. The Free project setup, TLS certificate, Session pooler, migration and limited runtime roles, pgvector schema and `search_path`, migration transactions, and cross-account isolation were verified. Database passwords and connection strings stay in private backend configuration, outside the browser and Git.

We verified Supabase with synthetic data first. We took a backup and stopped writes to the source database before importing existing data. We also verified recovery from the application-level backup. See the [verification guide](VERIFICATION.md) for how to check the Orchestrate Live integration. Monitor free-tier capacity, pause rules, recovery readiness, and compute usage before making any plan changes.

Pricing checked November 3, 2026. [Docker](https://www.docker.com/pricing/), [IBM PostgreSQL](https://cloud.ibm.com/docs/databases-for-postgresql?topic=databases-for-postgresql-pricing), [Supabase](https://supabase.com/pricing), [Neon](https://neon.com/pricing).

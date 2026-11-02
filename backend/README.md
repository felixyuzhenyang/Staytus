# Staytus backend

Run from this directory:

```sh
cp .env.example .env
uv sync --extra dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

`GET /health` checks the process; `/docs` exposes the application API. Startup creates `staytus-app.db` and synchronizes the configured official-source directory. It creates no sample accounts or fictional policies. The previous `staytus.db` remains untouched. Local SQLite requires no Docker.

## Accounts and onboarding

The frontend signs users up through `POST /api/v1/auth/register` with an email, a name and a password of at least 12 characters. Registration returns an account session with `needs_onboarding: true`. `POST /api/v1/profile` saves the authenticated account's school, F-1/J-1 category, nationality and program dates. Profile-dependent endpoints return `409 profile_required` until onboarding is complete. `PATCH /api/v1/profile` updates only that account's profile.

Passwords use salted scrypt; the database stores only hashes of random session tokens. Signing in rotates the account's previous session. The frontend server keeps its bearer token in an HttpOnly cookie. Accounts cannot assign themselves reviewer permissions or choose another student's profile. `/auth/demo`, the profile picker API and the fictional policy replay are absent from the product.

The local identity service has a per-process sign-in attempt limit. Email verification, password recovery, institutional SSO, a distributed rate limiter and revisioned database upgrades are not implemented. Those are deployment work before opening registration to a public audience.

## Modules

| Module | Responsibility |
|---|---|
| `config.py`, `db.py`, `models.py` | Environment settings, database transactions and core schema |
| `identity.py`, `auth.py` | Registration/login, account-owned profiles, opaque sessions and signed tool capabilities |
| `schemas.py` | Strict API validation and approved-action payloads |
| `rules.py` | Penn adapter, public-only fallback and deterministic planning preferences |
| `services.py`, `api.py` | Personal dashboard, approvals, calendar export and audit records |
| `chat.py`, `chat_models.py` | Account-owned conversations and the real Orchestrate chat route |
| `source_registry.py`, `policy_models.py` | YAML source registry, capture state and snapshot metadata |
| `ingestion.py`, `retrieval.py`, `policy_pipeline.py`, `policy_routes.py` | Fetching, chunk indexing, retrieval, refresh scheduling and source status API |
| `tools.py` | Twelve authenticated read/proposal tools exposed to Orchestrate |
| `integrations/` | IBM runtime clients, mailbox OAuth and approved provider drafts |
| `tests/support.py`, `tests/scenarios.py` | Synthetic regression fixtures and fictional replay harness, loaded only by tests |

## Chat, retrieval and scheduling

`POST /api/v1/chat` calls the configured IBM Orchestrate runtime. Each conversation belongs to the signed-in account; provider thread IDs are maintained on the server. The backend supplies the current profile, school-filtered official-source excerpts and a signed user capability. An unconfigured runtime returns 503, and a provider failure returns 502. There is no scripted local answer as a fallback.

Set `ORCHESTRATE_SERVICE_URL`, the deployed `ORCHESTRATE_AGENT_ID` and server-side credentials. Set `ORCHESTRATE_CONTEXT_VERIFIED=true` only after verifying secure user-context transport in the actual tenant. Application startup and account/profile features work while IBM configuration is absent. Mock-transport tests do not prove tenant connectivity.

Official-source URLs and polling intervals come from `../config/sources.yaml`. The application lifespan starts a polling worker when `POLICY_WORKER_ENABLED=true`. It captures permitted public pages, detects changed content and creates relevant in-app notifications. It does not read a user's private Penn portal or automatically activate a changed legal rule. Source status shows capture timestamps and fetch failures; a fresh capture is not a verification that a policy is legally in effect. A separate worker can be run with:

```sh
uv run python ../scripts/policy_worker.py --once
```

For a deployment using the separate worker, disable the API's lifespan worker. Polling locks are process-local; run one scheduler rather than starting one per API worker. Scheduled notifications are in-app; automatic outbound email delivery is not implemented.

Keyword retrieval works without model credentials. With a valid watsonx.ai project, endpoint and embedding model, capture/retrieval can use real embeddings. Responses identify the mode actually used. Pending snapshots remain explicitly unreviewed; synthetic fixtures are excluded from product retrieval. Penn planning offsets come from `../config/schools/penn.yaml` and are product preferences, not legal filing windows. Profiles from other schools can access public federal information, but receive no invented school deadlines, adviser directory or portal integration.

## Approvals and tool permissions

Orchestrate tools require both `X-Tool-Key` and a short-lived signed `X-Staytus-Context`. The backend resolves the capability to the registered account's session and profile; a model-supplied identifier never grants access. Final approve/reject endpoints require the user's bearer session and are absent from the tool list. Configure independent random `CONTEXT_SECRET` and `ORCHESTRATE_TOOL_KEY` values for shared deployments. The automatically generated development context secret changes on restart and is not shared across processes.

Approval flow is `PROPOSED → PREVIEWED → EXECUTING → SUCCEEDED`, with `REJECTED`, `EXPIRED` and `FAILED_UNCONFIRMED` terminal states. Before execution, the backend checks ownership, expiry, the exact payload hash, the profile version and an atomic single-use claim.

- A calendar approval prepares a real `.ics` file for download/import; it does not claim to have written to Google or Outlook Calendar.
- A profile-update approval changes the current user's stored profile.
- An email approval creates a real draft through a connected provider with draft permission. It does not send mail. If a provider response is lost, the approval becomes `FAILED_UNCONFIRMED`; check the mailbox before creating another preview.
- Penn application submission is unavailable. No mocked success receipt is produced.

## Mailbox OAuth setup

Register a Google or Microsoft OAuth application, add its client credentials to `.env` and generate a persistent encryption key:

```sh
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Save that value as `CONNECTOR_TOKEN_KEY`. Keep it stable while encrypted provider tokens exist. Users explicitly choose `mail_read` or `mail_draft`; provider or institution consent restrictions can still prevent access. The app never asks for an email or university password.

The callback must pass through the frontend proxy, which attaches the original HttpOnly-session-derived authorization header. With the default local configuration, register these redirect URIs in the provider application:

```text
http://127.0.0.1:3000/api/backend/connections/google/callback
http://127.0.0.1:3000/api/backend/connections/microsoft/callback
```

Keep the browser's host consistent with `FRONTEND_URL` and `OAUTH_CALLBACK_BASE` (`127.0.0.1` and `localhost` have different cookies). Use HTTPS URLs for deployment. The callback binds PKCE and a one-time state to the exact initiating login session. Logging out, signing in again or disconnecting invalidates pending authorization attempts. Provider tokens are encrypted server-side; API responses never expose them. Mail reading returns recent matching message metadata/snippets, and does not send mailbox content to an LLM automatically.

## Database lifecycle and validation

`Base.metadata.create_all()` at API startup bootstraps all registered tables in a fresh development database. It does not modify existing tables. Keep backups and add Alembic revisions before applying schema changes to a deployed database. PostgreSQL uses `postgresql+psycopg://...`; enabling its optional vector extension requires database permission. PostgreSQL behavior is not verified by the SQLite test suite.

```sh
uv run pytest -q
uv run python ../scripts/export_openapi_3_0.py
```

Tests cover account/onboarding isolation, hashed credentials and sessions, tool capabilities, school/category filtering, planning math, capture/retrieval, approval integrity/single-use, OAuth state/session/concurrency, scope restrictions, real draft request contracts and account-owned chat. Provider transports and runtime replies are faked only inside tests; live IBM/OAuth access needs separate validation with the configured accounts.

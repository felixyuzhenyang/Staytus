# Staytus

International student and scholar planning assistant. The application uses real accounts and public-source capture. Product chat has one path: the authenticated backend calls an IBM watsonx Orchestrate agent. There is no keyword or demo-answer fallback.

The public application is deployed at **https://mystaytus.vercel.app** on Vercel Hobby: Next.js frontend, privately bound FastAPI API and authenticated tool gateway share Supabase PostgreSQL. Two synthetic public users completed registration, profile onboarding, hybrid policy retrieval and real IBM Live chat; cross-account conversation access was rejected. Actual browser login/dashboard/Chinese chat also passed with a matching owned tool audit. The old temporary gateway tunnel is retired. All 13 Python tools remain imported and published on the existing Staytus Live agent; earlier bounded Live cases exercised all 13 interfaces. These checks do not establish comprehensive answer quality or legal accuracy.

Independent watsonx.ai embeddings, structured generation and hybrid retrieval are live-tested. Google client credentials, production callback, Gmail/Calendar APIs, minimum scopes and designated test user are configured. Personal Gmail consent and an actual inbox check passed with one new matching message. Separate Calendar consent also passed: its actual primary-calendar API returned200 in a read-only field-limited probe, and an offline refresh credential is present. Daily recurring reads and assistant-preview sharing remain off. Google remains External/Testing; actual approved calendar writes and broader public verification remain separate. Microsoft credentials remain absent and Outlook was deferred after the Penn-managed Entra portal denied access. Direct iCloud needs a personally created Apple app-specific credential and a chosen calendar. No real provider write is claimed. Penn private portals are not connected. See [Vercel operations](infra/vercel/README.md) for deployment and remaining release work.

## Run

Requires Node 20.9+, Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```sh
make install
make migrate
make dev
```

Open http://127.0.0.1:3000; API documentation is http://127.0.0.1:8000/docs. Create an account, complete your profile and enter your own workspace. Unsupported universities can use federal public-source information; only Penn has a configured school adapter.

Fresh installations default to SQLite and need an explicit `make migrate` before startup. Copy `backend/.env.example` to `backend/.env` first. Existing unversioned databases are never silently stamped or imported. The current operator database is hosted on Supabase Free PostgreSQL, using a certificate-verified TLS Session pooler and a limited runtime role shared by API and gateway. The original local PostgreSQL/SQLite and private backups are preserved. On this configured computer run `make database-check` then `make dev`; starting the fallback local database is no longer required for the application. Synthetic scenarios remain in tests. Never commit secrets or personal records; see [database/container operations](docs/DATABASE_AND_CONTAINERS.md).

## Implemented behavior

- Registration/login, hashed passwords and sessions, profile onboarding/editing and account isolation.
- Independent dashboard/chat/policy/approval/profile/connections/updates/audit components.
- Scheduled, bounded official-source capture, history, actual text chunks, citations and explicit freshness/error states. Captures remain pending review; no captured page automatically establishes current law.
- Status-specific preparation checklists cover extension, travel/reentry, completion/OPT and distinct J-1 student/scholar workflows. They expose missing-information questions and source capture/review states in the dashboard and chat/action-plan grounding. They do not determine eligibility or automatically calculate legal filing windows.
- One shared chat/API/tool retrieval entry, optional watsonx.ai embeddings and explicit keyword fallback. Regional model discovery, bounded bilingual probes and saved-corpus reindexing have separate operator commands.
- Server-to-Orchestrate runtime HTTP, private conversation threads, per-turn signed tool context and an authenticated tool gateway.
- Exact-content approvals bound to the current profile and connected account, calendar `.ics` export with alarms, Google/Outlook adapters, direct iCloud CalDAV discovery/owned-calendar selection and approved event creation, plus OAuth-authorized email drafts. iCloud credentials are encrypted server-side, are not granular OAuth scopes, and never go to the model. Agent-proposed actions require final user approval. School-application submission is not implemented.
- Google/Microsoft linking, encrypted provider tokens, selected recent official-message reads, separate Agent-preview permission, draft permission and calendar-write scopes. Connections reports exact callback and developer setup requirements. Registered OAuth applications and personal consent are still required.
- Separately opted-in daily read-only inbox monitoring with timezone/hour, manual checks, binding to the verified connection, hashed-message deduplication and private count notices. Checks return at most20 matches from the recent30day inbox window, with a five-minute manual cooldown. They do not store bodies/subjects/snippets, add mail to public RAG, send it to a model, send email or mark messages read. A real manual Gmail check passed; recurring live monitoring remains off and unexercised.
- Durable reminder inbox and visible-page popups; timezone-aware daily/weekly/monthly scheduling and optional SMTP digests. The user deferred sending, so email remains off and no real digest email was sent. Mailbox reading/in-app notices do not require SMTP.

Actual source verification on November3 attempted23registered official topic pages:15captured and8returnedHTTP403. Some Penn public pages now captured successfully; remaining blocked pages stay visibly unavailable and are not replaced by fabricated content. The87active chunks all have real768-dimensional Granite embeddings. Four bilingual F-1/J-1 topic checks returned category-appropriate official hybrid results with pending-review flags; this is a smoke evaluation, not proof of comprehensive legal accuracy. Large-chunk embedding uses an explicit model input-truncation parameter while preserving full stored text. Public deployment registers 25 daily cron jobs for the 23 sources, reminders and opted-in mailbox checks. Authenticated manual dispatch of one policy job, reminders and mail checks passed. Hobby triggers are daily with up to an hour of timing variation; they do not provide minute-level scheduling. Cloud entrypoints disable local lifespan threads, and this computer's worker flags are disabled to avoid duplicate scheduling. In-app popups require an open page; device background push is not implemented.

Google Cloud project Staytus (`staytus-513614`) and external Testing branding exist. The user approved creation of `staytus-local-web`, production secret storage, the public callback, Gmail/Calendar APIs, minimum read/owned-calendar scopes and designated test user; these settings are configured. Personal Gmail/Calendar grants, an actual inbox check and a field-limited Calendar API read passed. Actual event creation and broader public-app verification remain separate gates. Microsoft credentials remain missing, and direct iCloud has only mocked/security verification so far. Public web hosting does not complete provider OAuth verification.

## Code map

| Path | Responsibility |
| --- | --- |
| `frontend/app/page.tsx` | Thin login/onboarding/workspace gate |
| `frontend/components/`, `hooks/`, `lib/` | Independent views, session/request state and types |
| `frontend/app/api/backend/[...path]/route.ts` | Same-origin proxy, HttpOnly cookie, OAuth callback |
| `backend/app/identity.py`, `auth.py` | Accounts, sessions, ownership and signed capabilities |
| `backend/app/chat.py`, `chat_models.py` | Single real chat route and account-owned provider threads |
| `backend/app/integrations/orchestrate_runtime.py` | IBM IAM and Orchestrate runtime HTTP |
| `backend/app/integrations/connectors.py` | OAuth, verified mailbox identity, selected reads, approved drafts/calendar writes |
| `backend/app/integrations/icloud_calendar.py` | Encrypted Apple app-specific credential, bounded CalDAV discovery and approval-bound event creation |
| `backend/app/mail_monitor.py`, `mail_monitor_models.py` | Separate daily-read consent, timezone schedule, manual inbox checks and hashed dedup state |
| `backend/app/notification_models.py`, `notifications.py` | Reminder preferences/inbox, scheduling and consent-bound SMTP outbox |
| `backend/app/source_registry.py`, `ingestion.py`, `retrieval.py`, `policy_pipeline.py` | Capture, versions, retrieval and scheduler |
| `backend/app/rules.py`, `workflow_guidance.py`, `services.py` | Deterministic planning, evidence-aware personal checklists, approvals and audit |
| `backend/app/tools.py`, `orchestrate/python_tools.py` | Server-scoped tools and IBM runtime wrappers |
| `backend/app/tool_gateway.py` | Separate minimal server for authorized HTTPS tool callbacks |
| `backend/app/migrations/`, `database_cli.py`, `database_transfer.py` | Versioned DDL, explicit upgrades/checks and verified SQLite-to-PostgreSQL transfer |
| `scripts/check_watsonx_connection.py`, `reindex_policy_embeddings.py` | Explicit model discovery/probe and saved-corpus embedding |
| `scripts/orchestrate_setup.py` | Offline bundle preparation, SDK validation and explicit cloud stages |
| `config/` | Actual official-source registry and school configuration |
| `backend/tests/` | Isolated synthetic scenarios and security/HTTP checks |
| `CHANGELOG.md` | Continuing implementation and verification log |

Read [current architecture](docs/ARCHITECTURE.md), [feature status](FEATURES.md), [policy pipeline](docs/POLICY_PIPELINE.md), [Orchestrate setup](docs/ORCHESTRATE_SETUP.md), [model checks](docs/research/MODEL_RETRIEVAL_UNIFICATION.md), [email setup](docs/EMAIL_CONNECTIONS.md) and [reminders/calendars](docs/REMINDERS_AND_CALENDARS.md).

## Verify and deploy

```sh
make test
make build
```

Tests use isolated databases and mocked provider transports. They do not prove a live IBM or email connection. Separate ignored operator reports record actual tenant validation. A fresh installation keeps chat gated until its own configuration and secure context have been verified; no credentials or passing gate are shipped in source control.

SQLite remains available for fresh lightweight development. Supabase hosting, verified TLS, pgvector, transactional transfer, limited runtime privileges, cloud-data backup/restore and two-process/two-account isolation are now verified. API/gateway startup only checks the Alembic revision. Both container definitions use the repository root and exclude private data; actual linux/amd64 Docker builds and isolated startup checks pass locally (see docs/VERIFICATION.md). The application/gateway still run locally; database hosting is separate from public application deployment. Before public production, add verified-email/reset or SSO, distributed limits, independent scheduling, retention/deletion and operational monitoring. New accounts cannot become reviewers through a checkbox. For privileged cloud migrations use `make migrate MIGRATION_ENV=../.local/supabase/migration.env` on this computer. Supabase Data API and GitHub integration are not enabled; Alembic remains the schema authority.

## IBM Bob provenance

Planning and prior code review came from actual Bob sessions. Codex implemented the product migration and runtime code. A subsequent Bob Agent session produced approved, applied preflight/CLI/UUID-verifier changes and regression tests. Codex then independently hardened metadata handling, corrected tenant context propagation, simplified wrapper transport and performed authorized cloud imports, Live publication and synthetic runtime validation. Detailed Bob conversations remain local-only; the final repository will contain only the course-required per-member consumption-summary screenshots under `bob_sessions/consumption_summaries/`. Subsequent cloud and debugging work is summarized in CHANGELOG.

# Staytus

International student and scholar planning assistant. The application uses real accounts and public-source capture. Product chat has one path: the authenticated backend calls an IBM watsonx Orchestrate agent. There is no keyword or demo-answer fallback.

The public application is deployed at **https://mystaytus.vercel.app** on Vercel Hobby: Next.js frontend, privately bound FastAPI API and authenticated tool gateway share Supabase PostgreSQL. Two synthetic public users completed registration, profile onboarding, hybrid policy retrieval and real IBM Live chat; cross-account conversation access was rejected. Actual browser login/dashboard/Chinese chat also passed with a matching owned tool audit. The old temporary gateway tunnel is retired. All 13 Python tools remain imported and published on the existing Staytus Live agent; earlier bounded Live cases exercised all 13 interfaces. These checks do not establish comprehensive answer quality or legal accuracy.

Independent watsonx.ai embeddings, structured generation and hybrid retrieval are live-tested. Google client credentials, production callback, Gmail/Calendar APIs, minimum scopes and designated test user are configured. Personal Gmail consent and an actual inbox check passed with one new matching message. Separate Calendar consent also passed: its actual primary-calendar API returned200 in a read-only field-limited probe, and an offline refresh credential is present. Daily recurring reads are enabled for the consenting Google account and its actual background-check path passed; assistant-preview sharing remains off. Google remains External/Testing; actual approved calendar writes and broader public verification remain separate. Microsoft credentials remain absent and Outlook was deferred after the Penn-managed Entra portal denied access. Direct iCloud needs a personally created Apple app-specific credential and a chosen calendar. No real calendar event or user-mailbox draft/send is claimed. System reminder email now uses the original Brevo SMTP key with STARTTLS after the user disabled SMTP IP blocking. A real owner-requested SMTP test reached Gmail in SPAM with display name Staytus; removing the personal address prefix still requires a verified product mailbox. The restricted HTTPS API key remains an unselected alternative. Penn private portals are not connected. See [Vercel operations](infra/vercel/README.md) for deployment and remaining release work.

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

- Registration/login, hashed passwords and sessions, profile onboarding/editing and account isolation. Onboarding, Profile and guided travel planning share a searchable country/region selector with local English/Chinese/code/alias matching and keyboard navigation. Nationality is a single choice; travel destinations support multiple removable selections. Search text is never submitted as a country.
- Optional structured OPT/EAD, J-1 training/scholar, extension, admission and travel details with conditional forms, stage-aware checklists and record-conflict checks. Application progress changes internal preparation targets in the existing reminder pipeline. Guided Assistant forms generate real LLM/RAG personal plans with temporary scenario facts, restored conversation history and approval-gated calendar reminders. See [personal workflows](docs/PERSONAL_WORKFLOWS.md); formal legal windows remain separate work.
- Proactive, event-triggered watsonx.ai messages stored for the next visit, without a user question or active login. Daily generation uses saved profile facts, scoped official evidence and actual planning/source-change events. Includes language/on-off settings, unread/read state, manual event checks and durable deduplication/retry limits. No template fallback, mailbox sharing or automatic action execution. See [proactive messages](docs/PROACTIVE_ASSISTANT.md).
- Independent dashboard/chat/policy/approval/profile/connections/updates/audit components.
- **New chat** starts an independent IBM topic and persists the empty state across reloads. Previous chat records stay saved. **Refresh data** reloads data without clearing the conversation. Planning/policy shortcuts remain available, and **Assistant updates** opens all saved proactive messages in a paginated view on the same page; new chats hide inline updates without deleting or marking them read.
- Scheduled, bounded official-source capture, history, actual text chunks, citations and explicit freshness/error states. Captures remain pending review; no captured page automatically establishes current law.
- Status-specific preparation checklists cover extension, travel/reentry, completion/OPT and distinct J-1 student/scholar workflows. They expose missing-information questions and source capture/review states in the dashboard and chat/action-plan grounding. They do not determine eligibility or automatically calculate legal filing windows.
- One shared chat/API/tool retrieval entry, optional watsonx.ai embeddings and explicit keyword fallback. Regional model discovery, bounded bilingual probes and saved-corpus reindexing have separate operator commands.
- Server-to-Orchestrate runtime HTTP, private conversation threads, per-turn signed tool context and an authenticated tool gateway.
- Exact-content approvals bound to the current profile and connected account, calendar `.ics` export with alarms, Google/Outlook adapters, direct iCloud CalDAV discovery/owned-calendar selection and approved event creation, plus OAuth-authorized email drafts. iCloud credentials are encrypted server-side, are not granular OAuth scopes, and never go to the model. Agent-proposed actions require final user approval. School-application submission is not implemented.
- Google/Microsoft linking, encrypted provider tokens, selected recent official-message reads, separate Agent-preview permission, draft permission and calendar-write scopes. Connections reports exact callback and developer setup requirements. Registered OAuth applications and personal consent are still required.
- Separately opted-in daily read-only inbox monitoring with timezone/hour, manual checks, binding to the verified connection, hashed-message deduplication and private count notices. Checks return at most20 matches from the recent30day inbox window, with a five-minute manual cooldown. They do not store bodies/subjects/snippets, add mail to public RAG, send it to a model, send email or mark messages read. Real manual and explicitly opted-in background-path Gmail checks passed for the current account; other accounts remain default-off.
- Durable reminder inbox and visible-page popups; opt-in daily/weekly/monthly digests through Brevo SMTP or an explicitly selected HTTPS API alternative. The current account enabled a daily subscription; a fixed-content, owner-only test passed Brevo acceptance and Gmail receipt, currently in SPAM. Natural scheduled delivery and longer-term inbox placement still need observation. Mailbox reading/in-app notices are independent of the sender. See [Brevo email setup](docs/BREVO_EMAIL.md).

Actual source verification on November3 attempted23registered official topic pages:15captured and8returnedHTTP403. Some Penn public pages now captured successfully; remaining blocked pages stay visibly unavailable and are not replaced by fabricated content. The87active chunks all have real768-dimensional Granite embeddings. Four bilingual F-1/J-1 topic checks returned category-appropriate official hybrid results with pending-review flags; this is a smoke evaluation, not proof of comprehensive legal accuracy. Large-chunk embedding uses an explicit model input-truncation parameter while preserving full stored text. Public deployment now registers26daily cron jobs for the23sources, reminders, opted-in mailbox checks and proactive assistant generation. Authenticated manual dispatch of one policy job, reminders and mail checks passed. Hobby triggers are daily with up to an hour of timing variation; they do not provide minute-level scheduling. Cloud entrypoints disable local lifespan threads, and this computer's worker flags are disabled to avoid duplicate scheduling. In-app popups require an open page; persisted proactive messages are available on return, and device background push is not implemented.

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

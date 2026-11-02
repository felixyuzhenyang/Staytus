# Staytus

International student and scholar planning assistant. The application uses real accounts and public-source capture. Product chat has one path: the authenticated backend calls an IBM watsonx Orchestrate agent. There is no keyword or demo-answer fallback.

The local application works; external connections have separate readiness states. All13Python tools are imported, bound to the backend connection and published on the existing Staytus Live agent. Four bounded Live cases exercised all13tools with17invocations, including owned reads/planning, exact unexecuted proposals, mailbox-permission denial and a second-account workflow. Two-account context/audit checks, the local Next.js → FastAPI → Live → gateway round trip and visual browser chat also passed. Real chat is enabled in private local configuration. Independent watsonx.ai multilingual embeddings, structured generation and public-corpus hybrid retrieval are live-tested. Google/Microsoft email/calendar still need application credentials and personal consent; no real provider write is claimed. Penn private portals are not connected.

## Run

Requires Node 20.9+, Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```sh
make install
make dev
```

Open http://127.0.0.1:3000; API documentation is http://127.0.0.1:8000/docs. Create an account, complete your profile and enter your own workspace. Unsupported universities can use federal public-source information; only Penn has a configured school adapter.

The new database is `backend/staytus-app.db`, ignored by Git. The historical `staytus.db` is preserved and is not loaded or migrated automatically. Synthetic scenarios live in tests, outside the product entry. Copy `backend/.env.example` to `backend/.env` for server configuration; never commit secrets or personal records.

## Implemented behavior

- Registration/login, hashed passwords and sessions, profile onboarding/editing and account isolation.
- Independent dashboard/chat/policy/approval/profile/connections/updates/audit components.
- Scheduled, bounded official-source capture, history, actual text chunks, citations and explicit freshness/error states. Captures remain pending review; no captured page automatically establishes current law.
- One shared chat/API/tool retrieval entry, optional watsonx.ai embeddings and explicit keyword fallback. Regional model discovery, bounded bilingual probes and saved-corpus reindexing have separate operator commands.
- Server-to-Orchestrate runtime HTTP, private conversation threads, per-turn signed tool context and an authenticated tool gateway.
- Exact-content approvals bound to the current profile and connected account, calendar `.ics` export with alarms, Google/Outlook calendar adapters and OAuth-authorized email draft creation. Agent-proposed actions require final user approval. School-application submission is not implemented.
- Google/Microsoft linking, encrypted provider tokens, selected recent official-message reads, separate Agent-preview permission, draft permission and calendar-write scopes. Connections reports exact callback and developer setup requirements. Registered OAuth applications and personal consent are still required.
- Durable reminder inbox and visible-page popups; timezone-aware daily/weekly/monthly scheduling and optional SMTP digests. Email is off by default and requires a configured sender plus explicit consent to a provider-verified linked recipient. No real digest email has been sent.

Actual source verification on November 1 captured USCIS, DHS Study in States and DOS BridgeUSA. Their five current chunks have real 768-dimensional Granite embeddings; a Chinese query returned hybrid results with citations and pending-review flags. Penn ISSS homepage/travel/OPT returned HTTP403 and remain visibly blocked. Source and reminder workers require the backend to keep running; in-app popups require an open page. Device background push is not implemented.

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
| `backend/app/notification_models.py`, `notifications.py` | Reminder preferences/inbox, scheduling and consent-bound SMTP outbox |
| `backend/app/source_registry.py`, `ingestion.py`, `retrieval.py`, `policy_pipeline.py` | Capture, versions, retrieval and scheduler |
| `backend/app/rules.py`, `services.py` | Deterministic planning, approvals and audit |
| `backend/app/tools.py`, `orchestrate/python_tools.py` | Server-scoped tools and IBM runtime wrappers |
| `backend/app/tool_gateway.py` | Separate minimal server for authorized HTTPS tool callbacks |
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

SQLite is for local development. PostgreSQL/pgvector models, a development Compose service and Code Engine instructions exist; PostgreSQL/deployment have not been validated here. Before public production, add verified-email/reset or SSO, distributed limits, versioned migrations, retention/deletion and operational monitoring. New accounts cannot become reviewers through a checkbox.

## IBM Bob provenance

Planning and prior code review came from actual Bob sessions. Codex implemented the product migration and runtime code. A subsequent Bob Agent session produced approved, applied preflight/CLI/UUID-verifier changes and regression tests. Codex then independently hardened metadata handling, corrected tenant context propagation, simplified wrapper transport and performed authorized cloud imports, Live publication and synthetic runtime validation. Detailed Bob conversations remain local-only; the final repository will contain only the course-required per-member consumption-summary screenshots under `bob_sessions/consumption_summaries/`. Subsequent cloud and debugging work is summarized in CHANGELOG.

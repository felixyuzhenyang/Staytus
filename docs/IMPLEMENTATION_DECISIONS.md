# Implementation decisions and corrections

The original two plans and Unified Project Plan remain preserved. This file records implementation choices where those plans were contradictory or needed a local development path.

## November 8 Orchestrate history-item guard

The previous 64,000-character limit on one Orchestrate history message was an application-side validation guard, not a discovered IBM model or API limit. It rejected a lossless server-supplied grounding message of roughly 69,000 characters before any network request. The per-item guard is now 100,000 characters after synthetic, non-personal 69,367-, 99,000- and exact 100,000-character requests were accepted by the configured IBM Orchestrate agent. The separate 256,000-character aggregate history guard remains unchanged. This revision does not truncate, summarize or compact policy excerpts, profile context, planning data or assistant updates; compaction remains a separate future design if real requests exceed the new bound or the provider's token budget.

## November 3 cloud database choice and funding audit

The user selected Supabase Free, with no automatic paid upgrade, and completed project/password creation. Hosting is now active: certificate-verified TLS over the free Session pooler, separate owner/runtime roles, Alembic baseline, atomic25table/266row/98chunk transfer, dual-account API/gateway verification and a cloud application archive restored into new PostgreSQL. Keep existing backend identity/business services and psycopg/SQLAlchemy/Alembic; Supabase Data API is disabled and neither Supabase Auth nor GitHub branching is adopted. Original local databases remain intact; public compute deployment is separate. See `DATABASE_AND_CONTAINERS.md`.

The logged-in course account is `3131681 - watsonx`. Promotions/discount/manual-credit lists showed no entries; subscription balance and account-wide usage were explicitly unauthorized. Therefore an overall credit balance, expiry or PostgreSQL eligibility was not established. The $250 database banner is a new-customer offer, not evidence of an applied credit. The resource list contains existing `watsonx-Hackathon Cloudant`, a different database service, and showed no PostgreSQL instance. The local Guide describes preprovisioned course services, no new-instance creation and account closure at program end; do not assume unrestricted PostgreSQL or Code Engine funding/provisioning.

## November 3 shared database and container preparation

The tool gateway is a database-backed application, not a stateless relay. It validates sessions and reads/writes owned business state, so it cannot be deployed against an independent copy of local SQLite. The operator database is now real project-local PostgreSQL shared by API/gateway; cloud-hosted PostgreSQL is the next provisioning step. Original SQLite is unchanged, with a separate migration-before backup.

Versioned Alembic DDL runs explicitly before web processes. Runtime startup checks revision and refuses drift in version; it does not create tables/extensions. Migration configuration is separate from runtime/model secret validation, allowing a narrowly credentialed migration Job. Shared runtime signing/tool/token secrets must remain stable. Data transfer locks an empty target, verifies values and rolls back on failure. Only two measured legacy differences are tolerated; nonempty removed history is never silently discarded.

Both images use repository-root build contexts, not `COPY ../config`; configuration is explicitly mounted/copied via STAYTUS_CONFIG_DIR. One backend image supports API/gateway/migrate/check roles. No cloud resource was created and no actual Docker image was built locally; native installed-package/standalone verification and locally executed PostgreSQL tests are separate from future image/cloud validation. Detailed evidence and commands are in `DATABASE_AND_CONTAINERS.md` and `VERIFICATION.md`.

## November 1 product migration — current decisions

The numbered initial-prototype decisions below are historical. Current behavior replaces two chat paths with one backend-mediated Orchestrate runtime. Keyword chat, demo login, persona selection and replay are outside the product path. Real accounts/onboarding and OAuth provider code are implemented. A separate database preserves prototype data. Source scheduling and actual federal snapshots are implemented. The main Orchestrate Live profile/shared transport and account isolation now have real synthetic validation, including the local application HTTP path; private Penn access and live mailbox OAuth still need their own permissions/consent. See `ARCHITECTURE.md` and `../CHANGELOG.md`.

Official IBM OpenAPI verifies request-body `context` for Cloud Chat Completions; ADK2.19.1 verifies `AgentRun.request_context.get`. The signed capability must be resent each turn and kept out of model messages. Documented transport does not replace tenant end-to-end verification. The obsolete widget branch is archived.

### Tenant context-switch correction

An actual fixed-marker comparison corrected the initial configuration assumption: a Python tool executed with `context_access_enabled: false` but could not read the request marker; the same tool with the switch `true` and `context_variables: []` returned the marker successfully. New source/prepared definitions and validation use the latter combination. The empty model allowlist remains mandatory; no capability is declared or interpolated in a model prompt. IBM's [context documentation](https://developer.watson-orchestrate.ibm.com/conversation/context_variables) distinguishes the switch, the per-variable allowlist and prompt interpolation. The full signed-capability/backend-audit test remains the production gate, and is not replaced by this harmless marker test.

## November 2 reminders and connected calendars

- **Google/Outlook first.** The user chose provider calendar synchronization. Separate calendar scopes and approved event adapters are implemented. Apple Calendar can display those provider accounts. Direct iCloud/CalDAV and native EventKit are distinct integrations and remain deferred; a browser does not gain native calendar permission by running on an Apple device.
- **Preview binds the destination.** Email/remote-calendar approval hashes include server-derived connection identity. Relinking requires a new preview. The atomic claim checks the current database profile owner/version and approval hash to prevent stale-session execution.
- **Scheduling is not device push.** The backend worker persists notices/outbox and schedules timezone-aware digests. The visible web page polls for in-app popups. OS/background push is not implemented, and shutting down the local backend stops scheduled work.
- **Sender is separate from mailbox access.** Optional SMTP delivery uses an operator-configured sender. Recipient consent is bound to a provider-verified mailbox and current connection, not to arbitrary signup text. Email defaults off; uncertain deliveries are not silently retried. This does not grant the Agent unrestricted email-send permission.
- **Live proof is bounded.** Four real Live cases exercised all13tools, including correct denial and unexecuted preview results. A proposal-only recheck passed after destination binding changed. No real calendar/mail write or OAuth authorization is inferred from those checks. Google/Microsoft application registration and personal consent remain prerequisites; no new credential was created in this iteration.

## November 3 business expansion

The November3 iteration adds topic-specific captures (23registered/15captured/87embedded chunks), evidence-aware category workflows, independently opted-in daily inbox checks and direct iCloud CalDAV linking. Workflow guidance remains advisory with no automatic eligibility/legal-date inference. iCloud uses a dedicated Apple app-specific password because supported-app Apple Account authorization is not assumed available; it is not a granular OAuth grant. Monitor consent is separate from assistant-preview permission and no SMTP/send capability is enabled. See `DATA_STORAGE_AND_RAG.md` and the November3 CHANGELOG entry; SQLite remains the current local database.

## Initial prototype decisions (superseded where stated above)

1. **Eight statuses.** The vocabulary contains eight values; “seven” in the plans was a counting error.
2. **Local scaffold before tenant validation.** Tenant spikes gate live IBM enablement. They do not prevent building provider-independent components and contract tests now.
3. **SQLite development; PostgreSQL deployment.** No Docker or cloud database is required to open the local demo. Models include pgvector-compatible columns. Production database behavior still requires verification.
4. **Deterministic local chat is labelled.** It drives the real profile/rule/approval services for demo purposes, without pretending to be IBM inference. The signed embedded-chat path is a separately configured integration.
5. **Secure context needs two credentials.** An Orchestrate service key alone cannot select any profile. A five-minute signed capability derived from an existing backend session is also required. Context is injected through signed chat JWT/AgentRun, never an LLM function parameter.
6. **No model-callable final approval.** Only the authenticated application UI can approve/execute. The exported tool schema excludes final writes and admin routes.
7. **No automatic fallback bypassing Orchestrate.** Failed IBM integration should be debugged/escalated. watsonx.ai is an optional provider for ingestion, not a covert replacement for the course's agent runtime.
8. **No invented OPT policy changes.** Demo B changes an internal preparation buffer, with visible fictional labels. Demo fixtures never claim fresh official verification.
9. **Operational integration remains explicit.** Production identity, external OAuth, scheduling, RLS, migrations and retention need additional implementation and validation. Course account administrator access is not assumed.
10. **Honest Bob evidence.** Planning came from Bob; this initial implementation came from Codex. Subsequent Bob feature work and authentic screenshots must be retained for course submission.


## 2026-11-03 — Brevo HTTPS delivery and daily monitoring

- Production sends opted-in system reminders through a restricted Brevo transactional-email API key. The existing SMTP key is active but IP-blocked; SMTP IP protection and the pre-existing API security switch were preserved. SMTP is an explicit alternative, never an automatic fallback.
- Keep the new key only in approved backend `.env` and Vercel Production; release artifacts contain no new key copy. The current verified account enabled daily read-only monitoring and reminder subscription separately; assistant-preview sharing stayed off.
- Provider acceptance and actual Gmail receipt were verified separately. The real test reached SPAM, so record that outcome and do not claim verified INBOX placement. The first natural scheduled batch remains to be observed. See `BREVO_EMAIL.md` for verification and deployment timing.


## 2026-11-03 — User-selected SMTP transport and sender identity

- The user chose the original SMTP key and personally disabled SMTP IP blocking after action-time confirmation. Production now selects smtp with STARTTLS; HTTPS remains an explicit alternative with no automatic fallback. A new real SMTP test was received by Gmail in SPAM, with its application-generated Message-ID.
- Brevo sender display name is Staytus. The existing verified From address still derives from a personal mailbox because the user has no product mailbox. Complete address anonymization requires a new owned, verified product mailbox or authenticated sending domain; renaming a display name does not provide that ownership.

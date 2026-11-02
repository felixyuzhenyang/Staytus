# Staytus — Architecture & Implementation Plan

**Status:** Draft for review  
**Team:** 2-person IBM SkillsBuild AI Experiential Learning Lab  
**Scope:** F-1 / J-1 students and J-1 scholars at University of Pennsylvania — prototype with extensible multi-university adapter architecture  
**Constraint:** Planning only; no code has been written yet.

---

## Top-Level Overview

Staytus is a personalized AI agent that helps international students and scholars understand and act on their immigration-status obligations. It is **not** a chatbot wrapping a static document set. The design combines:

1. A **structured user profile** (school, visa type, dates, employment, travel) driving deterministic deadline and eligibility rules.  
2. A **versioned policy store** continuously ingested from authoritative sources (USCIS, DHS/SEVP, DOS, Penn ISSS).  
3. A **watsonx Orchestrate agent** that orchestrates read tools, deterministic rule calls, and — with explicit user approval — write actions (email drafts, calendar events, form prefills).  
4. A **custom backend** (running on IBM Cloud Code Engine) that owns user data, rule execution, vector retrieval, and all state; the LLM never directly touches persistent writes.  
5. An **ingestion pipeline** that monitors sources for changes, records versions, and flags affected user profiles.

The MVP demonstrates a complete end-to-end loop: profile → deterministic deadlines → conversational assistant → retrieval-backed answer with citations → escalation path. All data in the demo uses **synthetic student records and mock integrations**.

---

## Question-by-Question Architecture Answers

### Q1 — IBM Bob's Role in Development

**Bob is the primary development and planning tool throughout the project.**

| Bob Activity | Artifact to Preserve |
|---|---|
| Plan mode: architecture decisions and phased plans | Plan `.md` files committed to the repo |
| Plan mode: per-feature design discussions | Feature-specific plan files in `/docs/plans/` |
| Agent mode: implementing backend routes, rule engine, ingestion workers, schema migrations | Git commit messages referencing the Bob session goal |
| Agent mode: writing OpenAPI specs for Orchestrate tool import | The OpenAPI YAML files in `/orchestrate/tools/` |
| Ask mode: researching IBM platform behavior, verifying Orchestrate limitations | Notes in `/docs/research/` |
| Agent mode: writing unit/integration tests for rule engine and ingestion | Test files in `/tests/` |

**Evidence preservation protocol:**
- Every significant Bob planning session produces or updates a plan file committed with a descriptive commit message like `docs: add staytus ingestion-worker plan via Bob`.
- Non-trivial implementation sessions are captured via Bob-generated PR descriptions (using the `create_pr_workflow`).
- A `/docs/bob-usage-log.md` file records date, mode, task description, and key decisions for each session. This serves as course evidence.

---

### Q2 — IBM Cloud's Exact Role

IBM Cloud is the **hosting and managed-services layer** for all custom-built components. It is not a separate product from watsonx; the IBM Cloud account that provides watsonx services also hosts the backend.

**Components that run on IBM Cloud:**

| Component | Recommended IBM Cloud Service | Rationale |
|---|---|---|
| Backend API (Node.js or Python FastAPI) | **IBM Cloud Code Engine** (application) | Fully managed, serverless container runtime; scales to zero; no Kubernetes cluster overhead for a 2-person team |
| Ingestion / monitoring workers | **IBM Cloud Code Engine** (batch jobs) | Scheduled or event-triggered batch jobs; same container registry |
| User profile + policy metadata database | **IBM Cloud Databases for PostgreSQL** | Managed PostgreSQL; schema migrations; row-level security; JSON columns for flexible profile fields |
| Vector store for policy embeddings | **IBM Cloud Databases for Elasticsearch** (or self-hosted pgvector extension on the PostgreSQL instance) | Semantic search over policy chunks; pgvector is simpler to start |
| Secrets (API keys, OAuth tokens) | **IBM Cloud Secrets Manager** | Auto-rotation; backend reads secrets at runtime rather than baking them into env vars |
| Container images | **IBM Cloud Container Registry** | Private registry for Code Engine to pull images |
| Audit + application logs | **IBM Cloud Logs** | Central log sink; required for the audit trail described in Q9 |

**Necessary for prototype:**
- Code Engine (backend + workers)
- Cloud Databases for PostgreSQL (profiles, policy metadata, audit log)
- Container Registry (image storage)
- IBM Cloud IAM (service IDs and API keys for service-to-service auth)

**Optional / phase 2:**
- Cloud Secrets Manager (can start with IAM API keys stored as Code Engine environment secrets)
- Cloud Databases for Elasticsearch (can start with pgvector)
- IBM Cloud Logs (can start with Code Engine built-in log streaming)

---

### Q3 — watsonx Orchestrate's Exact Role

**Orchestrate is the primary agent runtime and control plane.** It hosts:

1. **The Staytus Agent definition** — system prompt / instructions, persona, escalation instructions, safety guardrails.
2. **Registered tools** — each tool is an OpenAPI operation imported into Orchestrate pointing to an endpoint on the backend API.
3. **Agent Lab / Builder UI** — used during development to iterate on the agent prompt, add tools, and test conversations.
4. **Conversation history** — Orchestrate manages turn-by-turn context within a session.
5. **Agent endpoint** — Orchestrate exposes an API (and optionally a web-chat widget) that the frontend calls.

**What lives in Orchestrate:**
- System prompt with agent personality, scope, escalation rules, and citation requirements
- Tool registrations (OpenAPI specs imported from `/orchestrate/tools/`)
- Agent-level guardrails (do-not-give-legal-advice instruction)
- The model selection (which foundation model backs the agent)

**What does NOT live in Orchestrate:**
- User profile data (stays in PostgreSQL, accessed only through backend tools)
- Policy text and embeddings (stay in the vector store, accessed through backend tools)
- Rule execution (deterministic deadline math stays in the backend rule engine)
- Approval state and audit logs (backend-owned, not LLM-owned)
- Any credentials beyond the IAM API key Orchestrate uses to call the backend

**Confirmed behavior:** The watsonx.ai Agent Lab beta is ending August 2026. The canonical agent builder going forward is watsonx Orchestrate Agent Lab / builder. The prototype should be built against Orchestrate, not the watsonx.ai Agent Lab.

---

### Q4 — watsonx.ai's Exact Role

**Orchestrate already provides model access for the conversational agent.** You do not need a separate watsonx.ai service call just to run the agent's reasoning loop.

**When watsonx.ai credentials ARE needed separately:**

| Use Case | Why Orchestrate Alone Doesn't Cover It |
|---|---|
| Generating dense embeddings for policy chunks during ingestion | Ingestion workers run outside Orchestrate; they call the watsonx.ai embedding API directly |
| Re-ranking retrieved policy passages | A backend re-rank call against `watsonx.ai` REST API (`/ml/v1/text/rerank`) |
| Classification of ingested policy changes (e.g., "proposed vs. effective", "which user types affected") | A targeted generation call from the ingestion worker |
| Evaluating agent response quality offline | watsonx.ai evaluation APIs or watsonx.governance integration |
| Fine-tuning or prompt template management (phase 3+) | watsonx.ai project / deployment space |

**Credential pattern:** The ingestion worker and the backend rule-engine-adjacent summarization calls use an IBM Cloud IAM API key scoped to a watsonx.ai project. The Orchestrate agent uses its own internal model binding and does not need a separate API key in the backend code.

**Key API endpoints used directly:**
- `POST /ml/v1/text/embeddings` — vectorize policy text chunks
- `POST /ml/v1/text/generation` — classification/extraction in ingestion workers
- `POST /ml/v1/text/rerank` — rerank retrieved passages before returning to agent

---

### Q5 — Component Diagram and Data Flows

#### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  User's Browser                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  React SPA (Next.js)                                          │   │
│  │  • Dashboard  • Profile editor  • Action plans  • Chat panel  │   │
│  └──────────────┬───────────────────────────────────────────────┘   │
└─────────────────│───────────────────────────────────────────────────┘
                  │ HTTPS (JWT)
                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  IBM Cloud Code Engine                                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Backend API  (FastAPI or Node/Express)                         │ │
│  │  • /auth  • /profile  • /deadlines  • /policy-search           │ │
│  │  • /agent-proxy  • /approvals  • /audit                        │ │
│  │                                                                 │ │
│  │  Rule Engine Module (pure Python/JS, deterministic)            │ │
│  │  School Adapter Layer  (UPenn adapter → future: generic)       │ │
│  └────────┬──────────────────────────────┬───────────────────────┘ │
│            │                              │                          │
│  ┌─────────▼──────────┐     ┌────────────▼──────────────────────┐ │
│  │  Ingestion Workers  │     │  PostgreSQL (Cloud Databases)      │ │
│  │  (Code Engine jobs) │     │  • user_profiles  • audit_log      │ │
│  │  • Fetch sources    │     │  • policy_versions  • deadlines    │ │
│  │  • Diff & classify  │     │  • approvals  • school_adapters    │ │
│  │  • Embed & store    │     │  (pgvector extension for vectors)  │ │
│  └────────┬────────────┘     └───────────────────────────────────┘ │
└───────────│─────────────────────────────────────────────────────────┘
            │ IAM API key
            ▼
┌───────────────────────────────────┐
│  watsonx.ai (IBM Cloud SaaS)       │
│  • Embeddings API                  │
│  • Generation API (classification) │
│  • Rerank API                      │
└───────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  watsonx Orchestrate (SaaS)                                        │
│  • Staytus Agent (system prompt, tools, model binding)             │
│  • Registered tools → call Backend API endpoints                   │
│  • Web chat embed or REST API endpoint                             │
└───────────────────────────┬───────────────────────────────────────┘
                            │ OpenAPI tool calls (IAM-authenticated)
                            ▼
                  Backend API  (same Code Engine app above)

┌──────────────────────────────────────────────────────────────────┐
│  External Sources (public, read-only)                             │
│  USCIS.gov  •  DHS/SEVP SEVIS  •  DOS travel.state.gov          │
│  Penn ISSS website  •  Federal Register RSS                       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  External Write Targets (Phase 2, explicit user consent only)    │
│  Google Calendar API  •  Gmail API  •  Penn ISSS portal (mock)   │
└──────────────────────────────────────────────────────────────────┘
```

#### Data Flow 1 — Student asks "When is my OPT application deadline?"

1. User types query in the React chat panel.
2. Frontend sends the message to the **backend `/agent-proxy` endpoint** with the user's JWT.
3. Backend validates the JWT, looks up the user's session token, and forwards the message to the **Orchestrate agent REST API** with a context header containing the `user_id`.
4. Orchestrate decides to call the `get_deadline_calculation` tool.
5. Orchestrate calls the backend's `GET /deadlines?user_id=<id>&deadline_type=OPT_application` endpoint.
6. Backend's **Rule Engine** reads the user profile (PostgreSQL), looks up the applicable UPenn school adapter rule, and computes the deterministic OPT application window.
7. Backend returns `{ deadline: "2025-03-15", rule_ref: "SEVP-8CFR214.2f11", policy_version: "v2024-11" }`.
8. Orchestrate calls `search_policy` tool to retrieve the relevant USCIS policy chunk for citation.
9. Backend runs a vector similarity search (pgvector) against the policy store, returns top-3 passages.
10. Orchestrate composes the final response citing the deadline, its basis, and the policy passage.
11. Response flows back through the backend proxy to the frontend.
12. Backend writes an `audit_log` row for the interaction.

#### Data Flow 2 — Policy change detected and user notified

1. Ingestion worker (Code Engine batch job, scheduled every 6 hours) fetches the Penn ISSS "Deadlines" page and the USCIS SEVIS page.
2. Worker computes a SHA-256 diff against the last stored version.
3. If diff detected: worker calls watsonx.ai generation API to classify the change as *proposed* or *effective* and extract the affected visa categories and key dates.
4. Worker saves a new `policy_version` row in PostgreSQL with the raw text, parsed metadata, and classification.
5. Worker queries the `user_profiles` table for users affected (e.g., all active F-1 students with OPT pending).
6. For each affected user, worker writes a `pending_notification` row.
7. Next time the affected user opens their dashboard, the frontend fetches notifications from `GET /notifications` and surfaces the change with a "What does this mean for me?" prompt.
8. User can ask the Orchestrate agent that question; the agent's `search_policy` tool will return the new policy version with its version metadata.

---

### Q6 — Technology Stack and Repository Structure

#### Recommended Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | **Next.js 14 (React)** with TypeScript | App Router for dashboard + API routes; easy IBM Cloud Code Engine deployment; good ecosystem |
| Backend API | **FastAPI (Python 3.11)** | Python-native watsonx SDK; excellent OpenAPI auto-generation for Orchestrate import; async support |
| Structured DB | **PostgreSQL 15** via IBM Cloud Databases for PostgreSQL + **pgvector** extension | One managed service for both relational profile data and vector embeddings; reduces moving parts |
| Rule Engine | **Pure Python module** within the backend | Zero dependencies on LLM; fully unit-testable; school-adapter pattern via Python ABC |
| Ingestion Workers | **Python scripts** packaged as Code Engine batch jobs | Same language as backend; share model code; scheduled via Code Engine job triggers |
| Orchestrate Integration | **OpenAPI 3.0 YAML files** imported into Orchestrate as skills/tools | Canonical integration path for Orchestrate custom tools |
| Auth (users) | **Auth0 or IBM App ID** (app-level JWT) | Social login + Penn edu SSO later; issues JWTs the backend validates |
| Secrets | **IBM Cloud Secrets Manager** | Runtime secret injection; avoid baking credentials into container images |
| Observability | **IBM Cloud Logs** + Code Engine built-in metrics | Centralized log shipping |
| CI/CD | **GitHub Actions** → IBM Cloud Container Registry → Code Engine deployment trigger | Simple two-person workflow |

#### Repository Structure

```
staytus/
├── frontend/                    # Next.js app
│   ├── app/
│   │   ├── dashboard/
│   │   ├── profile/
│   │   └── chat/
│   ├── components/
│   └── lib/
│       └── api-client.ts        # Typed calls to backend
│
├── backend/                     # FastAPI app
│   ├── main.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── profile.py
│   │   ├── deadlines.py
│   │   ├── policy_search.py
│   │   ├── agent_proxy.py
│   │   ├── approvals.py
│   │   └── audit.py
│   ├── rules/                   # Deterministic rule engine
│   │   ├── base_adapter.py      # Abstract school adapter
│   │   ├── upenn_adapter.py     # UPenn F-1 / J-1 rules
│   │   └── deadline_engine.py
│   ├── ingestion/               # Workers (also run as Code Engine jobs)
│   │   ├── sources/
│   │   │   ├── uscis_fetcher.py
│   │   │   ├── penn_isss_fetcher.py
│   │   │   └── dos_fetcher.py
│   │   ├── differ.py
│   │   ├── classifier.py        # Calls watsonx.ai
│   │   └── embedder.py          # Calls watsonx.ai embeddings
│   ├── models/                  # SQLAlchemy models
│   └── tests/
│
├── orchestrate/                 # Orchestrate configuration
│   ├── tools/
│   │   ├── get_profile.yaml
│   │   ├── get_deadlines.yaml
│   │   ├── search_policy.yaml
│   │   ├── create_approval.yaml
│   │   └── draft_email.yaml
│   └── agent_prompt.md          # System prompt / instructions
│
├── infra/                       # Deployment config
│   ├── code-engine/
│   │   ├── backend-app.yaml
│   │   └── ingestion-jobs.yaml
│   └── db/
│       └── migrations/
│
└── docs/
    ├── plans/                   # Bob plan files
    ├── research/                # IBM platform research notes
    └── bob-usage-log.md
```

---

### Q7 — Initial Agent Topology

**Recommendation: Start with a single Orchestrate agent with permission-scoped tools.**

**Rationale for one agent:**
- Orchestrate's Trial/Agent Builder tier may limit the number of concurrent agent configurations available in a course account. One agent avoids hitting limits.
- A single agent with well-structured tools and a carefully written system prompt is sufficient for the MVP's scope.
- Two-person teams can maintain a single agent prompt without merge conflicts on agent configurations.
- Orchestrate's tool-calling model already provides natural task decomposition within a single conversation.

**What justifies adding sub-agents later:**

| Trigger | Sub-agent to add |
|---|---|
| Email/calendar integration has a distinct auth flow and consent model that the main agent should not see | "Communication sub-agent" scoped to email/calendar tools only |
| Multi-university support with school-specific policy reasoning that needs different system prompts | Per-school "policy sub-agent" variants |
| Policy change impact analysis runs long-context chains that should not interfere with user conversations | "Policy analyst sub-agent" triggered by backend, not user conversation |

**Trade-offs of multiple agents now:** Additional complexity in routing, harder to debug in the Orchestrate UI during early development, potential trial-tier limitations on number of agents.

---

### Q8 — Tool / API Inventory

Tools are OpenAPI operations imported into Orchestrate as skills. Each tool calls the backend API.

#### Read-Only Tools (agent may call freely)

| Tool | Endpoint | Input | Output |
|---|---|---|---|
| `get_user_profile` | `GET /profile` | user_id (injected by proxy, not user-supplied) | Structured profile object |
| `get_deadlines` | `GET /deadlines` | user_id, deadline_types[] | List of deadlines with dates, rule references, policy versions |
| `search_policy` | `POST /policy-search` | query_text, visa_type, school, top_k | List of policy passages with source, URL, version date, citation key |
| `get_policy_version` | `GET /policy/{id}` | policy_id | Full policy record with version history |
| `get_notifications` | `GET /notifications` | user_id | List of pending change notifications for this user |
| `check_travel_eligibility` | `POST /rules/travel` | user_id, departure_date, return_date, destination | Eligibility result, required steps, travel signature expiry |
| `get_action_plan` | `GET /action-plan` | user_id, goal (e.g. "apply_OPT") | Ordered task list with deadlines and forms |

#### Proposal-Only Tools (agent may generate but must surface to user for review before any write)

| Tool | Endpoint | Input | Output |
|---|---|---|---|
| `draft_email` | `POST /drafts/email` | template_type, recipient_type, user_id, context | Draft text; stored as pending approval, never sent |
| `draft_calendar_event` | `POST /drafts/calendar` | title, description, date, user_id | Event JSON; stored as pending approval |
| `prefill_form` | `POST /drafts/form` | form_type, user_id | Prefilled form JSON; stored as pending approval |

#### Controlled-Write Tools (require explicit user approval; backend enforces, not prompt)

| Tool | Endpoint | Approval Gate |
|---|---|---|
| `submit_email_draft` | `POST /approvals/{id}/approve` | User must click "Send" in the dashboard UI; backend checks approval state |
| `submit_calendar_event` | `POST /approvals/{id}/approve` | Same approval flow |
| `update_profile` | `PATCH /profile` | User submits profile form; not LLM-initiated |

**Important constraint:** The agent never calls a controlled-write tool directly. The draft tools create approval records. The user acts on those records via the frontend. The backend validates approval state before any external write. This is enforced in backend middleware, not the LLM prompt.

---

### Q9 — Security, Auth, and Privacy

#### User Authentication
- **Auth mechanism:** IBM App ID (or Auth0) issues JWTs to authenticated users.
- The frontend passes the JWT in `Authorization: Bearer` headers to the backend.
- The backend validates the JWT signature and expiry on every request.
- This is enforced in backend middleware; the LLM never sees the raw token.

#### Service-to-Service Authentication (Backend ↔ Orchestrate)
- Orchestrate calls backend tool endpoints using an IBM Cloud IAM API key scoped to a service ID.
- The backend validates the IAM token on the `Authorization` header for every inbound tool call from Orchestrate.
- **SPIKE REQUIRED:** Verify exactly how Orchestrate passes credentials when calling registered OpenAPI tool endpoints in the course tenant. Options are: IAM bearer token in header, API key in header, or OAuth2 client credentials. This must be tested before building the tool endpoints.

#### Passing User Identity to Tools
- The frontend sends the user's message to the backend `/agent-proxy` endpoint, which prepends a `user_id` context injection into the Orchestrate conversation (as a system message or custom context field).
- **SPIKE REQUIRED:** Verify the exact mechanism for injecting per-user context into an Orchestrate agent session. This may be done via a `context` parameter in the Orchestrate message API or via a custom HTTP header that Orchestrate forwards to tool calls.
- The backend `/agent-proxy` adds the `user_id` to all outbound tool calls as a signed header that backend endpoints trust.
- **Critical rule:** The LLM must never self-report a user_id. The user_id is always injected by server-side code.

#### Secrets Handling
- Watsonx.ai API key, Orchestrate API key, database credentials, and OAuth refresh tokens are stored in **IBM Cloud Secrets Manager**.
- Code Engine applications are configured to read secrets at startup, not baked into images.
- No secrets appear in the Git repository or in log output (structured logging with secret scrubbing).

#### Human-in-the-Loop Approval
- Any write action (email send, calendar add, form submit) goes through the approval flow:
  1. Agent calls a draft tool → backend creates an `approval_requests` record with status `pending`.
  2. Agent response contains a reference to the pending approval (not the action itself).
  3. Frontend renders the draft with a "Review and Approve" UI.
  4. Only after user clicks "Approve" does the backend call the actual external API (Google, Penn portal).
  5. Backend marks the approval record `approved` and writes the audit log.
- **This is enforced in backend code.** External write endpoints check for an approved `approval_request_id` as a required parameter.

#### Audit Logging
- Every agent conversation turn, every tool call, every profile read, every approval state change is written to the `audit_log` table in PostgreSQL.
- Schema: `{ event_id, user_id, event_type, tool_name, input_hash, output_hash, timestamp, session_id }`.
- PII in tool inputs/outputs is hashed (SHA-256) before storing; only the hash is logged, not the raw value.
- IBM Cloud Logs is the centralized destination for all structured logs from Code Engine.

#### Privacy Controls
- User profiles are stored in a PostgreSQL table with row-level security: users can only SELECT/UPDATE their own rows.
- Vector search queries are parameterized; results include only policy text (no other user data).
- Email/calendar OAuth tokens (phase 2) are stored encrypted in a separate `user_integrations` table; the application backend uses them only with the specific user's session active.
- For the course demo: all data is synthetic. No real PII is stored.

#### What Must Be Enforced in Code, Not Prompts
1. User identity injection (never from LLM output)
2. Approval check before any external write
3. JWT validation on every request
4. Row-level security on profile reads
5. Secret never logged or returned in API responses
6. Write tool endpoints reject calls without a valid `approval_request_id`

---

### Q10 — Policy Ingestion, Versioning, and Change Detection

#### Ingestion Architecture

```
Source Fetcher  →  Differ  →  Classifier (watsonx.ai)  →  Chunker  →  Embedder (watsonx.ai)  →  Policy Store (PostgreSQL + pgvector)
                                                                                                    ↓
                                                                                          Affected User Finder  →  notification_queue
```

#### Source Configuration

Each source is described by a record in a `policy_sources` table:
- `source_id`, `name`, `url`, `fetch_strategy` (HTML scrape / RSS / JSON API), `school_adapter`, `visa_categories[]`, `check_interval_hours`, `last_fetched_at`, `last_hash`

#### Versioning Schema

The `policy_versions` table stores:
- `version_id`, `source_id`, `fetched_at`, `raw_content_hash`, `raw_content` (stored in object storage or as text), `parsed_sections` (JSONB), `classification` (`proposed` | `effective` | `rescinded`), `effective_date`, `affected_visa_types[]`, `diff_summary`, `reviewed_by` (null until human-reviewed), `reviewed_at`

When the differ detects a change:
1. A new `policy_version` row is created. The previous version remains immutable.
2. The classification step (watsonx.ai generation call with a structured extraction prompt) populates `classification`, `effective_date`, and `affected_visa_types`.
3. If `classification == "proposed"`, the version is flagged with a `requires_review = true` field to surface to human review.
4. A human reviewer (team member) can mark the version `reviewed_by = reviewer_id` in an admin panel.

#### Retrieval

- Policy text is chunked (512-token chunks with 64-token overlap).
- Each chunk is embedded using watsonx.ai embeddings and stored as a `policy_chunks` row with `(chunk_id, version_id, chunk_text, embedding vector, section_path)`.
- At query time: the backend embeds the user query, runs `pgvector` similarity search, applies a filter on `visa_type` and `school`, and returns the top-k chunks.
- Chunks include `version_id` and `source_url` for citation.
- When a new version is indexed, old chunks for the same source are not deleted; they are marked `superseded = true`. This preserves version history for citation.

#### Deterministic Rule Updates

- The rule engine reads its parameters from a `rule_parameters` table (e.g., OPT application window = 90 days before graduation).
- When an ingested policy change affects a rule parameter (detected by the classifier), a `rule_change_proposals` record is created.
- A team member reviews and applies the parameter update via the admin panel.
- After the update, a backend job re-computes `user_deadlines` for all affected profiles and marks stale cached deadlines for recalculation.

#### Affected User Recalculation

- The `user_deadlines` table caches computed deadlines per user.
- After any policy version or rule parameter update, a Code Engine batch job queries affected user profiles and re-runs the rule engine for each, updating or invalidating cached deadlines.
- Affected users receive a notification (see Data Flow 2 above).

---

### Q11 — MVP and Later Phases

#### MVP Scope

**Goal:** A working end-to-end loop that demonstrates profile → deadline calculation → conversational retrieval → escalation. All data is synthetic.

**MVP Components:**
1. React dashboard with profile display, deadline list, and embedded Orchestrate chat panel.
2. FastAPI backend with `profile`, `deadlines`, `policy_search`, and `agent_proxy` routes.
3. UPenn F-1 rule adapter (3-5 key deadline rules: OPT application window, travel signature expiry, grace period, I-20 end date, CPT eligibility check).
4. PostgreSQL with synthetic F-1 student profiles, 3-5 synthetic J-1 records, pre-loaded policy chunks from USCIS and Penn ISSS (manually ingested for MVP).
5. Orchestrate agent with the four read-only tools and a well-crafted system prompt including escalation instructions.
6. Basic audit log.

**MVP Acceptance Criteria:**
- A synthetic F-1 student with a profile can log in and see their 3 nearest deadlines with dates.
- The agent correctly answers "When must I apply for OPT?" with a citation and the correct date for this student's graduation date.
- The agent correctly answers "Can I travel to Canada next week?" based on travel signature expiry in the profile.
- The agent answers a policy question ("What is the 5-month rule?") with a retrieved passage from the policy store and a cited source URL and version date.
- The agent responds with an appropriate escalation message to a question it cannot answer ("Can I do H-1B without sponsorship?").
- All rule calculations are unit-tested and pass independently of the LLM.

**Three-Minute Demo Story:**
1. (0:00–0:30) Log in as "Mei Lin", a synthetic Penn F-1 student. Dashboard shows her profile and three upcoming deadlines.
2. (0:30–1:00) Ask the chat: "When do I need to submit my OPT application?" Agent responds with the specific deadline, the citation (USCIS 8 CFR 274a.12), and explains the calculation from her graduation date.
3. (1:00–1:45) Ask: "I'm planning to visit Canada over spring break — is my travel signature still valid?" Agent checks the travel signature field in her profile, calculates days remaining, and advises what to do if it expires.
4. (1:45–2:30) Ask: "What happens if I miss the OPT deadline?" Agent retrieves the relevant policy chunk from the store, cites the Penn ISSS page, and explains the consequence. It then says: "For your specific situation, I recommend confirming this with Penn ISSS directly" with the ISSS contact link.
5. (2:30–3:00) Show the policy version history panel — a "change detected" badge next to a Penn ISSS deadline showing it was last updated, with what changed.

#### Phase 2

- Full ingestion pipeline (automated fetchers, differ, classifier, embedder workers on schedule).
- J-1 scholar rule adapter.
- Email draft tool (Gmail mock integration with approval flow).
- Calendar event drafting.
- Travel reminder notifications.
- Admin panel for policy version review and rule parameter updates.

#### Phase 3

- Real OAuth connections to Gmail / Google Calendar (with explicit consent flow).
- Automated affected-user recalculation after policy changes.
- Multi-university adapter (second school).
- watsonx.governance integration for agent monitoring and evaluation.

---

### Q12 — Technical Spikes (Run Before Heavy Coding)

These are prioritized experiments that must be resolved before building dependent components.

| # | Spike | Question to Answer | Time-box |
|---|---|---|---|
| 1 | **Orchestrate tool import / OpenAPI compatibility** | Can the Orchestrate Agent Builder in the course tenant import an OpenAPI 3.0 YAML? What field names, security scheme names, and server URL formats does it require? Are there known limitations (no request body schemas with `$ref` nesting deeper than 2 levels, etc.)? | 1 day |
| 2 | **Orchestrate-to-backend authentication** | When Orchestrate calls a registered tool endpoint, what credential does it pass? Is it an IBM Cloud IAM bearer token, a static API key header, or something else? Can the backend verify it cryptographically? | 1 day |
| 3 | **User context injection into Orchestrate sessions** | How do you pass a `user_id` into an Orchestrate agent session such that tool calls receive it? Options: pre-pended system message, a `context` parameter in the Orchestrate messages API, a custom header Orchestrate forwards to tool calls. Must be confirmed in the actual course tenant. | 1 day |
| 4 | **Orchestrate web chat embed or API integration** | Does the course tenant's Orchestrate instance support the web chat embed widget for external web pages? Or must the frontend use the Orchestrate REST API directly? What are the CORS and authentication requirements for embedding? | Half day |
| 5 | **Code Engine deployment from container registry** | Can the IBM Cloud course account deploy a Code Engine application from IBM Cloud Container Registry without a paid plan upgrade? What are the egress/ingress limitations? | Half day |
| 6 | **watsonx.ai embeddings model availability** | Which embedding models are available in the course watsonx.ai project (e.g., `ibm/slate-125m-english-rtrvr`)? What are the token limits and rate limits? | Half day |
| 7 | **Orchestrate Draft → Live promotion** | What is the exact workflow to take an agent from a "draft" state in the Agent Builder to a "live" published state? What changes break after publishing that require creating a new draft? | Half day |

---

### Q13 — Assumptions, Risks, and Mitigations

#### Confirmed Platform Facts
- watsonx.ai Agent Lab beta ends August 2026; Orchestrate is the canonical agent builder (documented).
- Orchestrate requires IAM API key + URL + Auth URL for external platform connections (documented).
- watsonx.ai REST API supports `/ml/v1/text/embeddings`, `/ml/v1/text/generation`, and `/ml/v1/text/rerank` (documented).
- IBM Cloud Secrets Manager supports automatic rotation of IAM credentials (documented).
- IBM Cloud Code Engine supports scheduled batch jobs and containerized applications (documented).
- IBM Cloud Databases for PostgreSQL is a managed service available on IBM Cloud (documented).

#### Assumptions Requiring Verification in the Course Tenant

| Assumption | Risk if Wrong | Verification Method |
|---|---|---|
| The course Orchestrate Trial tenant allows importing custom OpenAPI specs as tools | Cannot use Orchestrate as the agent runtime | Spike #1: try importing a minimal OpenAPI YAML |
| Orchestrate passes an IAM bearer token to tool endpoints | Cannot verify inbound tool calls | Spike #2: deploy a logging endpoint; inspect headers |
| The course watsonx.ai project has embedding models available | Cannot embed policy text without an alternative | Spike #6: check Project → Models list |
| The course IBM Cloud account can create a Code Engine project | Cannot host the backend | Check account entitlements in IBM Cloud console |
| IBM App ID is available in the course account | Must use a different auth provider | Check Catalog → IBM App ID |
| pgvector extension is available on IBM Cloud Databases for PostgreSQL | Need Elasticsearch or external vector store | Check PostgreSQL version and extension list |

#### Major Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Orchestrate course tenant has tool import limitations that block the architecture | Medium | High | Spike #1 first; fallback: use watsonx.ai agent API directly from backend, bypass Orchestrate for tool routing |
| Policy source websites change structure, breaking scrapers | High | Medium | Use hash-based content detection, not XPath; log failures and alert; manual re-run is acceptable for demo |
| Immigration policy changes rapidly; prototype gives stale information | Medium | High | Prominent "information current as of [date]" disclaimer; manual ingestion trigger in admin panel; clear escalation to ISSS |
| LLM hallucinates a deadline or eligibility decision | Medium | High | All deadline answers must come from the deterministic rule engine tool, not LLM generation; citation is mandatory in system prompt |
| Course account quota prevents provisioning multiple services | Medium | Medium | Prioritize Code Engine + PostgreSQL; defer Elasticsearch (use pgvector); defer Secrets Manager (use env secrets) |
| Two-person team scope creep | High | Medium | Strict phase boundaries; MVP first; phase 2 only after MVP acceptance criteria pass |

---

## Sub-Tasks for Implementation

### Sub-Task 1 — Run Technical Spikes
**Intent:** Resolve platform unknowns before any feature code is written.  
**Expected Outcomes:** Written notes in `/docs/research/` answering each of the 7 spike questions.  
**Todo:**
- [ ] Deploy a minimal "echo" FastAPI endpoint to Code Engine (validates deployment path)
- [ ] Create a minimal OpenAPI 3.0 YAML and attempt import into Orchestrate Agent Builder
- [ ] Log all inbound HTTP headers when Orchestrate calls the tool endpoint
- [ ] Test user context injection by prepending a system message in an Orchestrate session
- [ ] Verify web chat embed or REST API access from a static HTML page
- [ ] List available embedding models in the course watsonx.ai project
- [ ] Test Orchestrate Draft → Live promotion with the echo tool
**Status:** `[ ] pending`

### Sub-Task 2 — Database Schema and Migrations
**Intent:** Define and migrate the PostgreSQL schema for all core tables.  
**Expected Outcomes:** Migration files in `/infra/db/migrations/`; all tables created in dev database; pgvector extension enabled.  
**Todo:**
- [ ] Create `user_profiles` table with all F-1 / J-1 profile fields
- [ ] Create `policy_sources`, `policy_versions`, `policy_chunks` (with vector column) tables
- [ ] Create `user_deadlines`, `audit_log`, `approval_requests`, `notification_queue` tables
- [ ] Enable pgvector extension; add HNSW index on `policy_chunks.embedding`
- [ ] Create `rule_parameters` and `school_adapters` tables
- [ ] Insert synthetic UPenn F-1 and J-1 student records (5 profiles)
**Status:** `[ ] pending`

### Sub-Task 3 — Backend API Foundation
**Intent:** Build the FastAPI backend with auth, profile, and deadline routes.  
**Expected Outcomes:** Running Code Engine application with health check, JWT validation middleware, profile CRUD, and working deadline calculation for UPenn F-1 rules.  
**Todo:**
- [ ] Scaffold FastAPI project structure as per `/backend/` layout above
- [ ] Implement JWT validation middleware (IBM App ID or Auth0)
- [ ] Implement `GET /profile` and `PATCH /profile` routes
- [ ] Implement the UPenn F-1 rule adapter (OPT window, travel signature, I-20 expiry, grace period)
- [ ] Implement `GET /deadlines` route calling the rule engine
- [ ] Unit test all rule engine methods (no LLM involved)
- [ ] Containerize and deploy to Code Engine
**Status:** `[ ] pending`

### Sub-Task 4 — Policy Ingestion (Manual / Seeded)
**Intent:** Manually ingest Penn ISSS and USCIS policy content into the vector store for MVP demo.  
**Expected Outcomes:** 50–100 policy chunks in `policy_chunks` table with embeddings; `policy_search` endpoint returns relevant passages for test queries.  
**Todo:**
- [ ] Write ingestion script that takes a URL, fetches text, chunks it, calls watsonx.ai embeddings, and inserts into DB
- [ ] Manually run script for: Penn ISSS F-1 deadlines page, USCIS OPT page, USCIS F-1 status page, Penn ISSS J-1 page
- [ ] Implement `POST /policy-search` endpoint with pgvector similarity search
- [ ] Validate search quality with 5 representative queries
**Status:** `[ ] pending`

### Sub-Task 5 — Orchestrate Agent Configuration
**Intent:** Register the four MVP read-only tools in Orchestrate and write the system prompt.  
**Expected Outcomes:** A working Orchestrate agent that calls the backend tools, answers deadline and policy questions correctly, and escalates appropriately.  
**Todo:**
- [ ] Write OpenAPI YAML files for: `get_user_profile`, `get_deadlines`, `search_policy`, `check_travel_eligibility`
- [ ] Import tools into Orchestrate Agent Builder
- [ ] Write the system prompt (persona, scope, citation requirement, escalation instruction)
- [ ] Configure model binding in Orchestrate
- [ ] Test the agent against the MVP acceptance criteria questions
- [ ] Promote agent from Draft to Live
**Status:** `[ ] pending`

### Sub-Task 6 — Frontend Dashboard and Chat Panel
**Intent:** Build the React dashboard with profile display, deadline list, notification feed, and embedded Orchestrate chat.  
**Expected Outcomes:** A logged-in synthetic student sees their deadlines and can chat with the agent; responses appear in the chat panel with citations.  
**Todo:**
- [ ] Scaffold Next.js project with TypeScript and Tailwind CSS
- [ ] Implement login page (IBM App ID / Auth0 redirect)
- [ ] Build profile view component
- [ ] Build deadline list component with urgency indicators
- [ ] Build notification feed component
- [ ] Integrate Orchestrate chat (embed widget or REST API via backend proxy)
- [ ] Build approval review panel (for phase 2 write actions; scaffold only in MVP)
- [ ] Deploy frontend to Code Engine
**Status:** `[ ] pending`

### Sub-Task 7 — Audit Logging and Escalation
**Intent:** Ensure every agent interaction is logged and escalation paths are functional.  
**Expected Outcomes:** Audit log table populated after every tool call; escalation responses include Penn ISSS contact information; no PII appears in logs.  
**Todo:**
- [ ] Implement audit log middleware in backend
- [ ] Add escalation phrases and Penn ISSS contact to system prompt
- [ ] Test that ambiguous questions trigger escalation, not hallucination
- [ ] Verify no PII appears in IBM Cloud Logs output
**Status:** `[ ] pending`

### Sub-Task 8 — Demo Preparation
**Intent:** Prepare the three-minute demo using synthetic data.  
**Expected Outcomes:** Rehearsed demo flow works end-to-end; synthetic student profiles cover all demo questions; screenshots/recording captured.  
**Todo:**
- [ ] Finalize synthetic student profile for "Mei Lin" covering all demo questions
- [ ] Run through the three-minute demo story and fix any gaps
- [ ] Capture a video recording or screenshots for submission evidence
- [ ] Commit all Bob plan files and research notes to `/docs/`
- [ ] Update `/docs/bob-usage-log.md` with all sessions
**Status:** `[ ] pending`

---

## Open Questions for Team Decision

1. **Auth provider:** IBM App ID is available in IBM Cloud and integrates with IAM, but requires a paid instance beyond the Lite plan. Auth0 has a generous free tier. Which is available in the course account? This must be confirmed before Sub-Task 3.

2. **Orchestrate chat integration method:** If the Orchestrate web chat widget cannot be embedded in an external domain (CORS restriction), the frontend must call the Orchestrate REST API through the backend proxy. Spike #4 resolves this.

3. **PostgreSQL vs. Elasticsearch for vectors:** pgvector is simpler to start. Only switch to IBM Cloud Databases for Elasticsearch if pgvector performance is unacceptable for the demo scale (it won't be with <10,000 chunks).

4. **Ingestion automation timeline:** For the MVP demo, manual ingestion is sufficient. Automated scheduled workers are Phase 2. Confirm this scope boundary is acceptable.

5. **J-1 scholar rules for MVP:** The brief mentions F-1, J-1 students, and J-1 scholars. Is it acceptable to implement only F-1 rules in the MVP and demonstrate the adapter extensibility pattern with a skeleton J-1 adapter? This reduces MVP scope significantly.

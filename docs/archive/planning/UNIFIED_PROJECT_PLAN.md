# Staytus — Unified Project Plan

**Synthesized from:** Plan A (PROJECT_PLAN_FOR_IBM_BOB.md) and Plan B (staytus-architecture-plan.md)  
**Status:** Proposed — awaiting team review  
**Team:** 2-person IBM SkillsBuild AI Experiential Learning Lab  
**Scope:** Penn F-1 / J-1 students and J-1 scholars; extensible adapter architecture  
**Constraint:** No code has been written; this is architecture and planning only.

---

## Part 1 — Executive Comparison

### Where the two plans are fundamentally aligned

Both plans share the same core architecture philosophy and agree on:

- **Orchestrate as the agent runtime, not the whole application.** The backend owns profiles, deadlines, rules, approvals, and audit logs; Orchestrate calls them through narrow OpenAPI tools.
- **A single primary Orchestrate agent** for the initial prototype — no multi-agent network without a justified need.
- **Deterministic rule engine in the backend.** Dates and eligibility computations are performed by code, never by the LLM.
- **Three-tier tool categorization.** Read-only tools the agent can call freely; proposal-only tools that produce previews; controlled-write tools that require backend-enforced approval.
- **FastAPI (Python) backend and Next.js (TypeScript) frontend.** Both plans converge on this stack.
- **PostgreSQL + pgvector** as the unified data and vector store.
- **Human-in-the-loop approval before any external write.** Enforced in backend code, not in a prompt.
- **Source authority and versioning.** Policy content is versioned, reviewed by a human, and labelled with a controlled status vocabulary before it can influence deadlines.
- **Technical spikes before coding.** Both plans flag Orchestrate OpenAPI compatibility, authentication between Orchestrate and the backend, and user-context propagation as must-resolve-first items.
- **Synthetic data for the demo.** No real PII, no real immigration documents, no real submissions.

### Where they take meaningfully different approaches

| Topic | Plan A position | Plan B position |
|---|---|---|
| Tenant verification | Detailed: exact account ID, region (ca-tor), Orchestrate plan (Trial), confirmed UI areas, and explicit flag that the current user lacks IAM admin rights | Abstract: lists generic services without verified tenant state |
| Hosting strategy | Pragmatic: prefers IBM Code Engine but explicitly names Render/Railway as fallback if Code Engine is blocked by account restrictions | Dogmatic: assumes Code Engine is available; no fallback |
| Auth provider | Supabase Auth or Auth.js as primary; does not name IBM App ID because App ID availability in the course account is unconfirmed | IBM App ID as primary; Auth0 as fallback |
| Demo stories | Two distinct stories: Demo A (program-extension planning with approval) and Demo B (policy-change impact replay) — both fully scripted | One story (OPT deadline + travel) — simpler but misses the policy-change replay required by the product brief |
| Policy status vocabulary | Seven distinct, controlled labels covering proposed, enjoined, superseded, unverified | Two labels: proposed and effective |
| Approval state machine | Explicitly defined PROPOSED → PREVIEWED → APPROVED/REJECTED → EXECUTING → SUCCEEDED/FAILED/EXPIRED with content-specific approval token carrying a payload hash | Approval record with pending/approved states; no expiry or payload-hash binding described |
| Orchestrate Knowledge | Explicitly addressed: useful for stable help docs but backend retrieval preferred for dynamic policy because it can expose version metadata and review status | Not mentioned |
| Source terms of use | Called out as a risk; SOURCES.md planned | Not mentioned |
| Evaluation dataset | 20–30 structured test cases covering edge conditions, escalation, and policy-status discrimination | Not present |
| Repository structure | `bob_sessions/` folder with screenshot evidence protocol; `fixtures/` for demo data; `evals/` for test cases | `docs/bob-usage-log.md` only; no dedicated session evidence folder |
| Frontend hosting | Vercel or equivalent as simple public deployment (Code Engine not mandated for frontend) | Code Engine for both frontend and backend |
| OpenAPI 3.1 vs 3.0 issue | Explicitly noted: FastAPI emits 3.1 by default; a validated 3.0 export must be maintained separately for Orchestrate compatibility | Mentioned as a spike item but not resolved |
| Background worker approach | Python scheduled commands initially; no Code Engine job dependency stated | Code Engine batch jobs required |
| Proposal tool for profile updates | `propose_profile_update` and `confirm_profile_update` — model may propose, user approves; important for demo | Profile update only via user form; no LLM-proposed update path |

---

## Part 2 — Strong Shared Conclusions (Preserve in Unified Plan)

| # | Conclusion | Evidence in both plans |
|---|---|---|
| 1 | Orchestrate is the agent runtime; all business logic and security enforcement live in the backend | Both plans state this explicitly as the primary architecture principle |
| 2 | One primary Orchestrate agent; no multi-agent network without demonstrated need | Both plans recommend this and give the same rationale |
| 3 | FastAPI (Python) + Next.js (TypeScript) + PostgreSQL + pgvector | Identical stack recommendation |
| 4 | Deterministic rule engine in backend; LLM never calculates dates | Identical |
| 5 | Three-category tool model: read-only / proposal / controlled-write | Identical structure; Plan A adds more tools |
| 6 | Backend enforces approval gate before any external write | Identical; both flag this as code, not prompt |
| 7 | Policy content is versioned, immutable after creation, and requires human review before influencing deadlines | Identical |
| 8 | Phase 0 / technical spikes before any production code | Both plans list the same critical spikes |
| 9 | Synthetic data only for course demo | Identical constraint |
| 10 | Audit log records every tool call, approval, and result | Identical |
| 11 | LLM must never self-report or infer the user identity — server side only | Identical security requirement |
| 12 | `escalate_to_isss` or equivalent tool for ambiguous/high-risk questions | Both plans include this |
| 13 | School adapter interface to support future universities | Both plans include this |
| 14 | IBM Bob as primary development tool with committed evidence | Both plans include this |

---

## Part 3 — Unique Valuable Contributions from Plan A

1. **Verified tenant facts.** Account `3131681 - watsonx`, region `ca-tor`, plan Trial, confirmed `Create agent` access, confirmed UI areas (Agents, Tools, Knowledge, Controls, Connections, Credentials, Optimization, Observability). Also confirmed: the user lacks IAM admin rights. This is the single most important grounding fact missing from Plan B. Any architectural claim about "just provision Code Engine" must be treated as unverified.

2. **Hosting pragmatism.** Plan A explicitly acknowledges the course account may block Code Engine provisioning and names Render/Railway as a fallback. This is honest and operationally necessary. Plan B's assumption that Code Engine is available is overconfident given confirmed limited IAM rights.

3. **Two distinct, fully scripted demo stories** that match the product brief. Demo A (program-extension planning through approval) and Demo B (policy-change impact replay with old/new comparison) together satisfy the evaluator's "end-to-end agent" requirement better than Plan B's single story.

4. **Seven-label policy status vocabulary.** `current_effective`, `announced_future`, `proposed`, `under_comment`, `detected_pending_review`, `postponed_or_enjoined`, `superseded`, `unverified_report`. This is not academic — it directly addresses the core product problem of distinguishing proposed and enjoined rules from currently effective ones. Plan B's binary `proposed`/`effective` is insufficient for realistic immigration scenarios.

5. **Content-specific approval token with payload hash and expiry.** Plan A's approval state machine binds approval to a specific preview payload hash and includes an EXPIRED state. Plan B's approval record lacks expiry and payload binding, meaning a user could approve a preview that was subsequently changed by the agent before execution.

6. **`propose_profile_update` and `confirm_profile_update` tools.** These allow the LLM to identify a profile field that needs updating (e.g., a graduation date mentioned in chat) and propose it for user confirmation rather than silently ignoring it. This is an important product capability and a necessary demonstration of safe write behavior.

7. **`get_school_adapter` tool.** Exposing the school adapter as a readable tool means the agent can explain what Penn-specific procedures apply vs. what is federal, which is a distinct feature not covered by Plan B's tool list.

8. **Orchestrate Knowledge addressed explicitly.** Plan A gives a precise position: useful for stable help/FAQ content but not appropriate as the primary policy store because it cannot expose review status and version metadata. This prevents a common mistake of uploading policy PDFs into Orchestrate Knowledge and treating them as authoritative.

9. **`execute_mock_submission` tool.** For the demo, a mock submission that produces a verifiable receipt and audit event is more compelling than just generating a preview. Plan B has no equivalent.

10. **Evaluation dataset (20–30 cases).** Plan A defines structured evaluation cases covering policy-status discrimination, escalation, date boundary cases, and unsafe requests. This is required to validate the agent before Demo Day.

11. **OpenAPI 3.1 vs. 3.0 problem explicitly resolved.** Plan A requires maintaining a validated Orchestrate-compatible OpenAPI 3.0 export alongside the native FastAPI schema, plus contract tests comparing them.

12. **Source terms of use as a risk.** Scraping government websites may have terms of service implications. Plan A adds SOURCES.md and flags this explicitly. Plan B ignores it.

13. **`SubscriptionPreference` and `AdvisorContact` data model entities.** Notification preferences and verified advisor contacts are part of the product promise but missing from Plan B's data model.

14. **`bob_sessions/` folder with screenshot evidence protocol.** Per-session summary, screenshot, and `bob_sessions/README.md` entry. This is more actionable for course evidence than Plan B's single log file.

15. **Zero-friction demo mode.** Plan A requires that evaluators can complete the demo without creating a real account. This is operationally critical and explicitly listed as an auth requirement.

---

## Part 4 — Unique Valuable Contributions from Plan B

1. **IBM documentation-grounded watsonx.ai API details.** Plan B cites documented API endpoints (`/ml/v1/text/embeddings`, `/ml/v1/text/generation`, `/ml/v1/text/rerank`) and confirms watsonx.ai Agent Lab beta end date (August 2026). These are concrete facts from IBM documentation that Plan A left unspecified.

2. **Explicit watsonx.ai role for ingestion workers.** Plan B clearly separates Orchestrate (conversational agent) from watsonx.ai (embedding, classification, reranking in workers). Plan A acknowledges this pattern but is less explicit about which API endpoints the workers call.

3. **SHA-256 content hash diffing in ingestion workers.** Plan B specifies the content-hash-based change detection mechanism concretely, including storing `raw_content_hash` per version. Plan A describes the pattern but does not specify the hash algorithm.

4. **`superseded = true` flag on old policy chunks.** When a new version is indexed, old chunks are marked superseded rather than deleted. This ensures version-specific citations remain answerable. Plan A's data model implies this but does not state it.

5. **pgvector HNSW index.** Plan B explicitly calls for an HNSW index on the embedding column for query performance. Plan A does not address indexing.

6. **Concrete "Mei Lin" synthetic profile persona.** A named, scripted demo persona makes demo preparation concrete and reproducible.

7. **Ingestion worker → watsonx.ai classification → `rule_change_proposals` pathway.** Plan B makes explicit that a detected change may warrant a `rule_change_proposals` record, triggering team review before any rule parameter is updated. Plan A describes the concept but Plan B makes the database record explicit.

8. **`rule_parameters` table** as a named entity separate from the rule logic. Rule parameters that can change (e.g., "OPT application window = 90 days") are stored in a database table, allowing updates without code changes.

9. **Q&A format for the 13 original questions.** The structured Q&A format of Plan B makes it directly useful as a reference document during implementation. Plan A's richness is sometimes difficult to navigate.

10. **Spike time-boxing.** Plan B assigns explicit time-box estimates to each spike, which helps a two-person team plan their first week.

---

## Part 5 — Contradiction and Decision Table

| # | Topic | Plan A | Plan B | Why It Matters | Evidence / Spike Needed | Recommended Decision |
|---|---|---|---|---|---|---|
| C1 | Backend hosting | IBM Code Engine preferred; explicitly names Render/Railway as a fallback if Code Engine is blocked by course account restrictions | IBM Code Engine assumed; no fallback mentioned | The course account has limited IAM rights; Code Engine provisioning may be blocked | Verify in IBM Cloud console whether the course account can create a Code Engine project | **Adopt Plan A's position.** Prefer Code Engine; document Render/Railway as the explicit fallback. Do not block the prototype on a hosting question. |
| C2 | Auth provider | Supabase Auth or Auth.js; App ID not named because availability is unconfirmed | IBM App ID primary; Auth0 secondary | App ID may not be available in Trial course account; Supabase Auth is not IBM-managed | Check IBM Cloud Catalog in the course account for App ID availability | **Use Auth.js (NextAuth) for the demo frontend.** This is zero-dependency on IBM account rights. If real IBM App ID is available, add it as an optional integration. Do not block the prototype on an unconfirmed IBM service. |
| C3 | Policy status vocabulary | Seven labels including `postponed_or_enjoined` and `unverified_report` | Two labels: proposed / effective | Immigration policy is frequently enjoined by courts; failing to distinguish this from "current effective" would give dangerous guidance | No spike needed; this is a design decision | **Adopt Plan A's seven-label vocabulary.** The richer vocabulary is a core product differentiator and a safety requirement, not over-engineering. |
| C4 | Approval token design | Content-specific one-time token with payload hash and EXPIRY state | Approval record with pending/approved; no expiry or payload binding | Without payload hash binding, a malicious or confused agent could approve one action and execute a different one | No spike needed; this is a security design decision | **Adopt Plan A's approval token design.** Payload hash binding and expiry are required security properties. |
| C5 | `propose_profile_update` tool | Yes — agent may propose a profile update; user must confirm | No LLM-proposed updates; profile only via user form | The product brief explicitly states the system should be able to identify relevant information from messages | No spike needed | **Adopt Plan A's tool.** This is an important product feature and demonstrates safe LLM-assisted write behavior. Keep the user-confirmation requirement. |
| C6 | OpenAPI version management | Explicitly requires maintaining a validated OpenAPI 3.0 export separately from native FastAPI 3.1, plus contract tests | Listed as a spike item but not resolved into a requirement | If Orchestrate tool import only supports OpenAPI 3.0 (unconfirmed), a FastAPI 3.1 default will silently produce incompatible schemas | Spike #1 (Orchestrate tool import test) | **Adopt Plan A's requirement.** Maintain a validated 3.0 export from day 1. The export script belongs in `/scripts/export_openapi_3_0.py`. |
| C7 | Frontend hosting | Vercel or equivalent for simple public deployment | Code Engine for both frontend and backend | A two-person team with limited IAM rights should not over-couple the frontend to the IBM Cloud account | Verify whether Code Engine is accessible first | **Use Vercel for the frontend in the prototype.** It is public, free, requires no IBM provisioning, and is easier for evaluators to access. Use Code Engine (or fallback) for the backend only. |
| C8 | Demo stories | Two stories: Demo A (program-extension + approval) and Demo B (policy-change impact replay) | One story (OPT + travel + escalation) | The product brief explicitly describes policy-change monitoring and impact analysis. A single OPT story does not demonstrate this capability | No spike needed | **Adopt Plan A's two demo stories.** However, Demo A should be the primary three-minute story; Demo B can be a 90-second extension or a secondary demo track. |
| C9 | Evaluation dataset | 20–30 structured eval cases defined | Not present | Without evaluation cases, there is no reproducible way to validate agent quality before Demo Day | No spike needed | **Adopt Plan A's evaluation dataset requirement.** Create the dataset in `evals/` during Phase 2. |
| C10 | Agent Lab / watsonx.ai lab note | Does not mention the beta ending | States watsonx.ai Agent Lab beta ends August 2026 and Orchestrate is the replacement | Course tenant already uses Orchestrate; this is confirmed. The note is accurate but not a decision point | None | **Retain Plan B's documentation note** for clarity in the research folder. No architecture change needed since both plans target Orchestrate. |
| C11 | Ingestion worker scheduling | "Scheduled Python commands initially" — no Code Engine dependency | Code Engine batch jobs required | If Code Engine is unavailable, Plan B's ingestion workers have no home | Confirm Code Engine availability | **Plan A's position is safer.** Use a simple cron-triggered script locally or on the backend process first; migrate to Code Engine batch jobs when deployment is confirmed. |
| C12 | Bob evidence format | `bob_sessions/` folder, screenshots, per-session README entry | `docs/bob-usage-log.md` text file | The `bob_sessions/` approach with screenshots is more credible course evidence | None needed | **Adopt Plan A's `bob_sessions/` folder structure.** Also retain Plan B's log file as a machine-readable index. |

---

## Part 6 — Gap Analysis

The following important requirements or risks are inadequately covered or absent in **both** plans:

### G1 — Legal-risk boundary is under-defined
Both plans say "not legal advice" and "escalate to ISSS" but do not specify: (a) what specific question categories always escalate regardless of retrieved evidence; (b) what the agent says when a question touches litigation (e.g., an enjoined rule); (c) whether the agent may ever give a definitive answer about whether a user is in status. A **legal-risk taxonomy** should be defined during design, not discovered during the demo.

**Recommendation:** Add a `legal_risk_categories` classification to the system prompt and to the evaluation dataset. Categories should include: status-determination questions, court-enjoined-rule questions, SEVIS termination questions, and questions about other people's status.

### G2 — Source governance / terms of use
Plan A mentions SOURCES.md; Plan B does not mention it at all. Neither plan specifies whether scraping government websites complies with their terms of service, whether cached content requires attribution, or how to handle a website that blocks scrapers (e.g., Cloudflare protection on some USCIS subpages).

**Recommendation:** Create SOURCES.md before ingestion development. Each source entry should include: URL, authority, fetch method, terms of use status (checked/unchecked), last human review date, and any known scraping restrictions.

### G3 — Policy freshness staleness UX
Both plans discuss versioning but neither specifies what the UI shows when a policy version is more than N days old without a refresh. Users making time-sensitive decisions need to see "Last verified: 3 days ago" not just a version timestamp.

**Recommendation:** Add a `source_freshness_warning_days` configuration per source. The dashboard and every policy citation should show an orange warning if the source has not been successfully fetched within that threshold.

### G4 — Failure recovery for ingestion workers
Neither plan addresses what happens when an ingestion worker fails: network error, changed HTML structure, watsonx.ai rate limit, or malformed response. A failed worker that silently produces no update is worse than a failed worker that alerts the team.

**Recommendation:** Workers must write a `fetch_attempt_log` record on every run (success or failure). The admin panel must surface the last successful fetch and any consecutive failures. Manual retry must be possible from the admin panel.

### G5 — Demo reliability under live conditions
Neither plan specifies what happens during the demo if Orchestrate is slow, watsonx.ai hits a rate limit, or the backend throws an error. A live demo with a loading spinner and a timeout is a course failure.

**Recommendation:** The demo must use a "demo fast path" mode: pre-computed deadline results are cached in the database; if the LLM call times out, the dashboard can still show correct deadlines from the cache. The Orchestrate agent chat is a live integration, but the dashboard must never depend on a live LLM call for its correctness.

### G6 — Identity and user-context propagation — the "how" is unresolved
Both plans identify user-context propagation to Orchestrate tool calls as a critical spike but neither resolves it to a concrete mechanism. The two options (prepended system message injected by the backend proxy; custom HTTP header forwarded by Orchestrate to tools) have materially different security implications.

**Recommendation:** Spike #3 must produce a documented, implemented pattern — not just a hypothesis. The pattern must be reviewed against OWASP prompt injection guidance before being adopted. A system message that includes `[SYSTEM: user_id=X]` is vulnerable to prompt injection unless the backend's tool endpoints independently verify user_id from the session, not from Orchestrate's message content.

**Key security requirement:** The backend tool endpoint must derive `user_id` from the authenticated session established by the backend `/agent-proxy`, not from any Orchestrate-forwarded message field. The Orchestrate message content is untrusted input.

### G7 — Data retention and deletion
Neither plan defines how long user profile data, audit logs, policy versions, or approval records are retained, or what happens when a user requests deletion. For a prototype this is lower priority, but the architecture must not make deletion impossible (e.g., by embedding user identifiers in vector embeddings).

**Recommendation:** The data model must support user account deletion by design: audit records become anonymized, not deleted; vector embeddings must not contain user data; OAuth tokens are deleted on revocation.

### G8 — Accessibility
Neither plan mentions accessibility (WCAG compliance, keyboard navigation, screen reader support). For a course submission that may be evaluated by IBM, accessibility is a professional obligation.

**Recommendation:** Use shadcn/ui components (Plan A recommends Tailwind + shadcn/ui) which are built on Radix UI primitives and have good accessibility by default. Add a brief accessibility statement to the README.

### G9 — Deployment portability / course account expiry
Plan A notes the course account expiry risk in the risk register. Neither plan defines a concrete portability strategy. If the course Orchestrate tenant expires, the agent configuration is lost unless exported.

**Recommendation:** Export Orchestrate agent configuration (instructions, tool definitions, model settings) to version-controlled files in `/orchestrate/agent/` after every significant change. The backend must remain independently runnable without Orchestrate by supporting a direct API mode for the agent call (see fallback architecture in the IBM platform verification matrix below).

### G10 — Observability correlation across systems
Both plans mention audit logs and IBM Cloud Logs but neither specifies how to correlate a user-visible conversation turn with the specific Orchestrate trace, backend tool call sequence, and database operation. Without a shared correlation ID, debugging a wrong answer in the demo is very difficult.

**Recommendation:** Generate a `conversation_turn_id` in the frontend on every user message. This ID must propagate through: frontend → backend `/agent-proxy` → Orchestrate session context → tool call headers → database audit records. IBM Cloud Logs and Orchestrate AgentOps both receive this ID.

### G11 — FERPA / FERPA-adjacent considerations
Neither plan mentions FERPA. While the demo uses synthetic data, the product description implies it could eventually connect to university systems that store education records. Any real deployment would have FERPA implications. The plan should acknowledge this explicitly and defer real student-record integration to a phase that includes institutional review.

**Recommendation:** Add a note in the product scope: "Any integration with real student records or university systems that contain education records requires institutional FERPA compliance review. This prototype uses only synthetic data and is explicitly scoped to avoid real education records."

---

## Part 7 — IBM Platform Verification Matrix

### 7A — Documented and Reasonably Confirmed

| Claim | Evidence |
|---|---|
| watsonx.ai Agent Lab beta ends August 2026; Orchestrate Agent Builder is the replacement | IBM documentation retrieved during research |
| watsonx.ai REST API supports `/ml/v1/text/embeddings`, `/ml/v1/text/generation`, `/ml/v1/text/rerank` | IBM documentation |
| watsonx.ai programmatic access requires IAM API key → IAM bearer token | IBM documentation |
| IBM Cloud Secrets Manager supports automatic IAM credential rotation | IBM documentation |
| IBM Cloud Code Engine supports containerized apps and scheduled batch jobs | IBM documentation |
| IBM Cloud Databases for PostgreSQL is a managed service on IBM Cloud | IBM documentation |
| Course Orchestrate tenant is confirmed at region `ca-tor`, plan Trial | Plan A verified in live account |
| Orchestrate UI areas confirmed: Agents, Agentic workflows, Tools, Knowledge, Controls, Connections, Credentials, Optimization, Observability | Plan A verified in live account |
| `Create agent` access is confirmed in the course tenant | Plan A verified in live account |

### 7B — Edition-, Region-, Role-, or Tenant-Specific Claims

| Claim | Why It May Vary | What to Check |
|---|---|---|
| Orchestrate Trial plan supports custom OpenAPI tool import | Trial plan feature set may differ from paid plans; some connectors are plan-restricted | Spike #1 |
| Orchestrate tool endpoint receives IAM bearer token from Orchestrate | Authentication mechanism for outbound tool calls is implementation-dependent; may differ between regions or plans | Spike #2 |
| Orchestrate supports passing per-user context to tool calls via a `context` API parameter | This is an API design feature that may not be exposed in Trial | Spike #3 |
| Orchestrate web chat embed widget can be embedded in an external domain | CORS and embedding policies may restrict this to internal IBM Cloud domains | Spike #4 |
| IBM Cloud Code Engine project can be created in the course account | Course accounts with limited IAM rights may be unable to provision new services | Check IBM Cloud console → Resource list → Code Engine |
| IBM App ID is available in the course catalog | App ID is a paid service; Trial accounts may not have access | Check IBM Cloud Catalog in the course account |
| pgvector extension is available on the course PostgreSQL instance | Depends on PostgreSQL version and managed service offering level | Check available extensions on the PostgreSQL instance |
| watsonx.ai embedding models (e.g., `ibm/slate-125m-english-rtrvr`) are available in the course project | Available models depend on the project region and plan | Check Project → Manage → Models in the course watsonx.ai Studio |
| Orchestrate AgentOps / Observability metrics are available in Trial | Observability is listed in the confirmed UI areas but depth of metrics in Trial is unknown | Explore the Observability tab in the course tenant |
| Code Engine scheduled jobs are available without paid plan | Scheduling may require a paid tier | Check Code Engine → Jobs in the course account |

### 7C — Must-Test Spikes with Fallback Architecture

| Spike | Expected Evidence | Pass Criteria | Fail Criteria | Fallback Architecture |
|---|---|---|---|---|
| **S1: Orchestrate OpenAPI tool import** | Import a minimal OpenAPI 3.0 YAML (`get_demo_profile` with one parameter and one response) into Orchestrate Agent Builder and invoke it from Orchestrate Chat | Tool is imported, appears in agent tool list, and can be called from Chat with a returned response | Import fails, tool does not appear, or call returns an error | Use watsonx.ai agent API directly from the backend as the agent reasoning loop; wrap it in a thin FastAPI router; Orchestrate becomes optional for the demo |
| **S2: Orchestrate-to-backend auth** | Deploy a logging FastAPI endpoint that returns all inbound HTTP headers; invoke it as an Orchestrate tool; inspect the log | Headers contain a verifiable credential (IAM bearer token, API key, or other) that the backend can validate | No credential is passed; headers show only Orchestrate's internal origin | Accept any valid inbound call from a fixed IP range OR use a shared secret API key in the OpenAPI security scheme that Orchestrate sends as a header |
| **S3: User context propagation** | Test three patterns: (a) inject `user_id` as a pre-conversation system message via the backend proxy; (b) pass `user_id` in an Orchestrate `context` parameter if available; (c) have the backend proxy sign the session and verify independently of Orchestrate | Pattern that safely delivers `user_id` to the tool endpoint without the user being able to forge it | No safe pattern available | Backend proxy always resolves `user_id` from its own session; tool endpoints ignore any `user_id` in the Orchestrate message body and look it up from the session ID in the Authorization header |
| **S4: Orchestrate chat integration** | Embed the Orchestrate chat widget in a static HTML page hosted on a different domain; verify messages work | Widget loads, user can send messages, responses appear | CORS error or widget does not load on external domains | Use Orchestrate REST API directly from the Next.js frontend via a backend proxy; the backend proxy validates the user JWT and calls the Orchestrate messages API with a service IAM token |
| **S5: Code Engine availability** | Attempt to create a Code Engine project in the course IBM Cloud account | Project is created and an application can be deployed | Account lacks permissions to create Code Engine projects | Host the backend on Render (free tier) or Railway; deploy ingestion workers as GitHub Actions scheduled workflows |
| **S6: watsonx.ai embedding models** | List available models in the course watsonx.ai Studio project; attempt to call `/ml/v1/text/embeddings` with `ibm/slate-125m-english-rtrvr` | API returns a valid embedding vector | Model not available or API call returns 403 | Use an alternative embedding approach: OpenAI `text-embedding-3-small` with team API key (course-only); or pre-embed content with a local `sentence-transformers` model and store in pgvector without a live embedding API |
| **S7: Orchestrate Draft → Live** | Create a simple draft agent, publish to Live, verify the Live agent is callable via the Live endpoint; then modify the draft and verify the Live endpoint is unchanged | Draft and Live are distinct; Live remains stable after draft changes | Draft and Live are the same; publishing is irreversible or breaks tool bindings | Keep the agent in Draft for the demo; use the Draft API endpoint; document this in the demo notes |

---

## Part 8 — Unified Target Architecture

### Component Ownership

| Component | Technology | Hosted On | Owned By |
|---|---|---|---|
| Frontend web app | Next.js 14 + TypeScript + Tailwind + shadcn/ui | Vercel (primary) or Code Engine (if available) | Application team |
| Backend API + tool gateway | FastAPI (Python 3.11) + Pydantic | IBM Code Engine app (or Render/Railway fallback) | Application team |
| Deterministic rule engine | Pure Python module within backend | Same as backend | Application team |
| School adapter layer | Python ABC pattern; `upenn_adapter.py` first | Same as backend | Application team |
| PostgreSQL + pgvector | IBM Cloud Databases for PostgreSQL (or Supabase) | IBM Cloud (or Supabase fallback) | Application team |
| Ingestion workers | Python scripts, initially run as scheduled commands | Same as backend (or GitHub Actions scheduled) | Application team |
| watsonx Orchestrate agent | Orchestrate Agent Builder, Draft → Live | IBM watsonx Orchestrate SaaS (ca-tor) | Orchestrate (agent definition, model, tool registration) |
| watsonx.ai embedding/generation | watsonx.ai REST API | IBM Cloud SaaS | IBM (API); Application team (calls from workers) |
| Secrets | Environment variables → IBM Cloud Secrets Manager | IBM Cloud | Application team |
| Observability | IBM Cloud Logs + Orchestrate AgentOps | IBM Cloud | Both |
| Source content (read-only) | Public government and university websites | External | External authorities |
| Email/calendar (Phase 5) | Microsoft Graph or Google OAuth | External SaaS | User (consent required) |

### Final Agent Topology

**Phase 0–3 (MVP and through Demo Day):** One primary Orchestrate agent.

**Agent name:** Staytus International Student Navigator  
**System prompt responsibilities:** Persona, scope, citation requirement, policy-status labelling, escalation triggers, not-legal-advice disclaimer, and explicit instruction to use `calculate_deadline` for all date questions and `search_official_policy` before answering any policy question.  
**Model:** Tenant-provided Orchestrate/watsonx model (no BYOK required).

**Sub-agent trigger conditions (Phase 4+):**
- If email/calendar OAuth tools require a separate consent context that the primary agent should not access → Communication sub-agent.
- If school-specific policy reasoning requires a distinct system prompt per institution → School-specific policy sub-agent.
- Never add sub-agents for technical appearance.

### Tool Categories

#### Read-Only (agent calls freely)
| Tool | Backend Endpoint | Notes |
|---|---|---|
| `get_student_profile` | `POST /tools/get_student_profile` | Returns redacted profile; excludes OAuth tokens |
| `get_school_adapter` | `POST /tools/get_school_adapter` | Returns Penn-specific workflows, contacts, portal links |
| `search_official_policy` | `POST /tools/search_official_policy` | Hybrid retrieval; filters by authority and policy status; returns citation metadata |
| `get_policy_version_and_status` | `POST /tools/get_policy_version_and_status` | Returns a specific version with full status vocabulary label |
| `calculate_deadline` | `POST /tools/calculate_deadline` | Returns deterministic result + calculation trace |
| `list_action_tasks` | `POST /tools/list_action_tasks` | Returns personalized task list for a workflow |
| `get_policy_changes_for_profile` | `POST /tools/get_policy_changes_for_profile` | Returns relevant recent changes for this profile |
| `escalate_to_isss` | `POST /tools/escalate_to_isss` | Returns verified ISSS contacts and a checklist; sends no data automatically |

#### Proposal-Only (agent creates a preview; no external write occurs)
| Tool | Backend Endpoint | Notes |
|---|---|---|
| `propose_profile_update` | `POST /tools/propose_profile_update` | Creates a `PROPOSED` approval record; agent presents to user |
| `build_action_plan` | `POST /tools/build_action_plan` | Returns a structured task list; no write |
| `create_email_preview` | `POST /tools/create_email_preview` | Creates a `PROPOSED` approval record with email content |
| `create_calendar_preview` | `POST /tools/create_calendar_preview` | Creates a `PROPOSED` approval record with event content |

#### Controlled-Write (user acts via UI; backend enforces token validation)
| Tool | Backend Endpoint | Approval Requirement |
|---|---|---|
| `confirm_profile_update` | `POST /tools/confirm_profile_update` | Valid approval token; payload hash matches |
| `save_email_draft` | `POST /tools/save_email_draft` | Valid approval token; payload hash matches |
| `create_calendar_event` | `POST /tools/create_calendar_event` | Valid approval token; payload hash matches |
| `execute_mock_submission` | `POST /tools/execute_mock_submission` | Valid approval token; produces mock receipt and audit event |

### Trust Boundaries

```
UNTRUSTED                     BACKEND BOUNDARY               TRUSTED
┌──────────────┐              ┌───────────────────┐         ┌──────────────────┐
│ User browser │─── JWT ─────▶│ /api/* routes     │         │ PostgreSQL       │
│              │              │ (validates JWT)    │────────▶│ (row-level sec.) │
└──────────────┘              │                   │         └──────────────────┘
                              │ /agent-proxy       │
┌──────────────┐              │ (injects user_id   │         ┌──────────────────┐
│ Orchestrate  │─ IAM token ─▶│  into session;     │────────▶│ Rule Engine      │
│ (tool calls) │              │  validates IAM)    │         │ (no LLM calls)   │
└──────────────┘              │                   │         └──────────────────┘
                              │ /tools/* routes   │
                              │ (validates IAM;    │
                              │  resolves user_id  │
                              │  from session,     │
                              │  NOT from message) │
                              └───────────────────┘
```

**Critical trust rule:** Tool endpoints at `/tools/*` resolve `user_id` from the authenticated backend session established by `/agent-proxy`. They never trust a `user_id` value present in the Orchestrate message body or tool call parameters. This defends against prompt injection attacks that attempt to impersonate another user.

### Approval State Machine

```
PROPOSED
  → agent calls a proposal tool; backend creates ApprovalRequest with:
    - approval_id
    - user_id
    - tool_name
    - preview_content (exact text/JSON the user will see)
    - input_payload_hash (SHA-256 of the tool input)
    - target_resource
    - expires_at (15 minutes from creation)
    - status: PROPOSED

PREVIEWED
  → frontend renders the preview to the user; status updated to PREVIEWED

APPROVED (terminal success path)
  → user clicks "Approve" in the UI
  → frontend sends approval_id to POST /approvals/{id}/confirm
  → backend checks: user_id matches, status == PREVIEWED, not expired, payload_hash unchanged
  → backend sets status = APPROVED
  → backend calls external API (email/calendar/mock)
  → backend sets status = SUCCEEDED or FAILED
  → audit event written

REJECTED (terminal rejection path)
  → user clicks "Reject" in the UI
  → status = REJECTED; audit event written

EXPIRED (terminal expiry path)
  → backend job checks for PROPOSED/PREVIEWED records past expires_at
  → sets status = EXPIRED; no external action taken
```

### Policy Version Pipeline

```
Source Registry (policy_sources table)
  ↓ scheduled fetch (every 6 hours; manual trigger available)
Source Fetcher (per-source strategy: HTML scrape / RSS / JSON)
  ↓ SHA-256 hash comparison with last version
Change Detector
  ↓ if changed: create immutable PolicyVersion (status: detected_pending_review)
watsonx.ai Classifier
  ↓ classify: current_effective / announced_future / proposed / under_comment /
               detected_pending_review / postponed_or_enjoined / superseded / unverified_report
  ↓ extract: affected_visa_types[], effective_date, diff_summary
Review Queue (admin panel)
  ↓ team member reviews: old text vs new text, extracted metadata, proposed rule changes
  ↓ approves / rejects / edits
PolicyVersion.status = approved status label; ReviewDecision created
  ↓ if rule parameters changed: RuleVersion created
Affected User Finder
  ↓ query user_profiles for affected users
  ↓ re-run rule engine for each affected profile
  ↓ compare old DeadlineResult vs new DeadlineResult
  ↓ write notification_queue records
  ↓ frontend surfaces notifications on next user visit
```

**Safety rule:** An unreviewed PolicyVersion (status `detected_pending_review`) can appear as a notification badge on the dashboard ("A change was detected — pending review") but must not alter any user's deadlines or action tasks until a ReviewDecision is made.

### End-to-End Data Flow 1: Program-Extension Planning (Demo A)

1. User selects synthetic profile "Mei Lin" (F-1, Penn, program end 2027-05-15).
2. Dashboard loads — backend calls rule engine deterministically for the top 3 deadlines; results are cached in `user_deadlines`.
3. User asks: "What do I need to do to extend my F-1 program?"
4. Frontend sends message to `POST /agent-proxy` with JWT.
5. Backend validates JWT, establishes session with `user_id = mei_lin_id`, injects `user_id` into Orchestrate session context, forwards to Orchestrate.
6. Orchestrate agent calls `get_student_profile` → backend returns redacted profile including program end date.
7. Orchestrate agent calls `get_school_adapter` → backend returns Penn-specific F-1 extension workflow and required documents.
8. Orchestrate agent calls `calculate_deadline(workflow="program_extension", ...)` → backend rule engine returns `{ recommended_start: 2027-03-16, deadline: 2027-05-01, rule_version: "PENN_F1_EXT_v1.2", policy_version_id: "pv-2024-11-01" }`.
9. Orchestrate agent calls `search_official_policy(query="F-1 program extension requirements", school="penn", status_filter=["current_effective"])` → backend returns top-3 Penn ISSS and USCIS passages with citation metadata.
10. Orchestrate composes response: action plan with the calculated dates, cited sources, required documents, and ISSS contact.
11. Response flows back through backend proxy to frontend; frontend renders source cards and calculation trace.
12. User asks: "Can you create a reminder for March 16?"
13. Orchestrate calls `create_calendar_preview(title="Start F-1 extension preparation", date="2027-03-16", ...)` → backend creates `ApprovalRequest` (status: PROPOSED).
14. Frontend renders preview modal with exact event details.
15. User clicks "Approve" → backend validates approval token, calls Google Calendar mock, writes audit event.
16. Backend writes 4 `AuditEvent` records: profile read, policy search, deadline calculation, calendar approval.

### End-to-End Data Flow 2: Policy-Change Impact Replay (Demo B)

1. Ingestion worker runs (manual trigger for demo).
2. Worker fetches Penn ISSS F-1 deadlines page; SHA-256 hash differs from last stored version.
3. Worker creates new `PolicyVersion` (status: `detected_pending_review`).
4. Worker calls watsonx.ai to classify: returns `{ classification: "announced_future", effective_date: "2027-06-01", affected_visa_types: ["F-1"], diff_summary: "OPT application window changed from 90 to 120 days before graduation" }`.
5. Worker creates `rule_change_proposals` record for the `OPT_APPLICATION_WINDOW` parameter.
6. Team member opens admin panel → Review Queue → sees old text vs new text, extracted diff.
7. Team member approves → new `RuleVersion("OPT_WINDOW_v1.3")` created with `days_before_graduation = 120`.
8. Backend job re-runs rule engine for all F-1 profiles with OPT plans.
9. Mei Lin's cached deadline changes from 2027-02-14 to 2027-01-15.
10. Notification written to `notification_queue`.
11. Mei Lin opens dashboard → notification badge appears: "Your OPT preparation deadline changed from Feb 14 to Jan 15 due to a Penn ISSS policy update."
12. Mei Lin asks: "Why did my deadline change?" → Orchestrate agent calls `get_policy_changes_for_profile` → backend returns the new PolicyVersion with old/new text and the RuleVersion changelog.
13. Agent explains the change, cites the Penn ISSS source with old and new version dates, and offers to update her calendar event.

---

## Part 9 — Consolidated Implementation Roadmap

### Phase 0 — Technical Validation (run before any production code)

**Objective:** Remove all integration uncertainty.

**Tasks:**
- Open the project in IBM Bob and review this unified plan.
- Create `AGENTS.md` after review.
- Initialize version control with README and `.env.example`.
- In Orchestrate, create a temporary sandbox agent.
- Implement a minimal FastAPI `get_demo_profile` endpoint.
- Export/import an Orchestrate-compatible OpenAPI 3.0 YAML.
- Run Spikes S1–S7 and document results in `/docs/research/`.
- Record verified tenant constraints (Code Engine available yes/no; App ID available yes/no; embedding models confirmed; chat integration method confirmed).

**Dependencies:** None.

**Acceptance Criteria:**
- Bob can read and reason about the local repository.
- One Orchestrate agent can call one deployed test tool.
- User context propagation mechanism is chosen and documented.
- All 7 spike questions have written answers.
- All fallback architectural decisions are committed.

### Phase 1 — Foundation and Synthetic Data

**Tasks:**
- Frontend skeleton: Next.js + TypeScript, Tailwind, shadcn/ui.
- Backend skeleton: FastAPI, Pydantic, middleware, health check.
- Database schema: all core tables including `policy_sources`, `policy_versions`, `policy_chunks`, `user_profiles`, `rule_parameters`, `rule_versions`, `deadline_results`, `approval_requests`, `audit_events`.
- pgvector extension and HNSW index.
- Seed synthetic Penn F-1 and J-1 profiles (at minimum: "Mei Lin" for Demo A, one J-1 student, one J-1 scholar).
- `penn.yaml` school adapter configuration.
- `sources.yaml` with allowlisted source list.
- SOURCES.md with terms-of-use notes.
- Demo profile selector and profile edit page.
- Audit event foundation.
- Bob evidence: `bob_sessions/` folder initialized with first session.

**Dependencies:** Phase 0 complete; hosting decision made.

**Acceptance Criteria:**
- Application runs locally and in preview deployment.
- Frontend loads synthetic profiles from backend.
- Profile editing is validated and persisted.
- No secrets or real personal data are committed.

### Phase 2 — Policy Retrieval and Deadline Engine

**Tasks:**
- Ingest a small reviewed set of Penn ISSS and USCIS official pages (manually, script-driven).
- Save immutable PolicyVersions with seven-label status vocabulary.
- Chunk and embed reviewed content with watsonx.ai embeddings (or fallback).
- Implement hybrid retrieval: structured filter + keyword + pgvector similarity.
- Implement one production-quality deterministic deadline workflow: program extension + travel-signature validity.
- Implement `RuleVersion` and `DeadlineResult` tables with calculation trace.
- Expose Orchestrate read-only tools via validated OpenAPI 3.0.
- Evaluation dataset: 20 cases covering F-1/J-1, policy status discrimination, escalation.
- Unit tests for all rule engine methods.

**Dependencies:** Phase 1 complete; Spike S6 (embedding model) resolved.

**Acceptance Criteria:**
- Same profile + RuleVersion always produces the same deadline.
- Every policy answer displays an official citation with source URL and version date.
- Proposed/pending policy cannot be cited as currently effective.
- Orchestrate can call policy and deadline tools from the deployed backend.
- 20 eval cases are defined and 80% pass against the initial agent.

### Phase 3 — Dashboard, Chat, and Action Previews (MVP / Demo A complete)

**Tasks:**
- Status dashboard with deadline cards, source badges, status badges, and calculation traces.
- Orchestrate chat integration (widget embed or REST API proxy — method from Spike S4).
- Tool-progress and citation cards visible in chat.
- Approval state machine: PROPOSED → PREVIEWED → APPROVED/REJECTED/EXPIRED.
- Content-specific approval token with payload hash and expiry.
- Email and calendar preview tools.
- `.ics` download.
- `execute_mock_submission` tool and mock receipt.
- Audit timeline page.
- `escalate_to_isss` tool with verified Penn ISSS contacts.
- `propose_profile_update` / `confirm_profile_update` tools.
- Demo A rehearsal and clean-browser smoke test.

**Dependencies:** Phase 2 complete; Spikes S2, S3, S4 resolved.

**Acceptance Criteria (= MVP Definition of Done):**
- Demo A runs end-to-end without error.
- No external write occurs without approval.
- Approval token expires and payload-hash mismatch is rejected.
- User can inspect source and calculation trace.
- Audit timeline shows all events.
- Public prototype link works in a clean browser session.
- Evaluation dataset at 80% pass rate.
- `bob_sessions/` has at least 5 documented sessions.

### Phase 4 — Policy-Change Review and Impact Replay (Demo B complete)

**Tasks:**
- Scheduled/manual ingestion command.
- Hash/diff and candidate extraction.
- watsonx.ai classification of changes.
- Review queue admin page (old text vs new text, approve/reject).
- `RuleVersion` creation after review.
- `DeadlineResult` recalculation for affected profiles.
- Old/new task comparison and notification generation.
- Dashboard notification feed.
- `get_policy_changes_for_profile` tool.
- Replay fixture and script for Demo B.
- Policy freshness staleness warning (configurable threshold per source).
- Fetch attempt log and consecutive failure alerting.

**Dependencies:** Phase 3 complete; Spike S6 resolved; admin panel scaffolded.

**Acceptance Criteria:**
- Demo B runs end-to-end without error.
- An unreviewed change never alters deadlines.
- Old and new deadline versions and their sources are auditable.
- Review queue is usable by a team member without developer assistance.

### Phase 5 — Controlled Real Integrations (if time and permissions allow)

**Tasks:**
- Microsoft Graph or Google OAuth for a dedicated test account.
- Save an approved email to Drafts (test account only).
- Create an approved calendar event (test account only).
- Connection pause and revoke UI.
- Document administrative consent limitations for Microsoft tenant.

**Dependencies:** Phase 3 complete; external OAuth consent flows confirmed.

**Note:** This phase must not block Demo Day. If OAuth integration is incomplete, Demo A and B with mock actions are sufficient.

### Phase 6 — Deployment, Evaluation, and Submission

**Tasks:**
- Deploy public frontend (Vercel) and backend (Code Engine or fallback).
- Promote Orchestrate agent to Live; document Live endpoint.
- Export Orchestrate agent configuration to version-controlled files.
- Seed stable demo data.
- Run full evaluation set; target 90% pass rate.
- Verify no secrets or PII are exposed in logs or responses.
- Complete README, SOURCES.md, FEATURES.md, and architecture documentation.
- Organize `bob_sessions/` evidence with screenshots.
- Rehearse and record three-minute demo video.
- Clean-browser smoke test from a device that has never visited the app.
- Verify prototype from evaluator perspective.

---

## Part 10 — Decisions for the Team vs. Decisions for Spikes

### Decisions the team must make (cannot be resolved by testing alone)

| Decision | Options | Recommended Default | Rationale |
|---|---|---|---|
| Primary demo story for three-minute slot | Demo A only / Demo A + Demo B extension | Demo A as primary; Demo B as 90-second extension | Demo A is complete and compelling; Demo B adds differentiation but requires Phase 4 |
| J-1 rules scope for MVP | F-1 rules only with skeleton J-1 adapter / F-1 + J-1 rules both | F-1 rules only with skeleton J-1 adapter | Two-person team; shipping F-1 properly is better than both poorly |
| Source terms of use for scraping | Proceed with scraping / use only officially licensed feeds / use only manual ingest | Manual ingest for MVP; research terms before automation | Conservative; avoids legal risk during prototype |
| Policy status vocabulary depth | Seven-label (Plan A) / two-label (Plan B) | Seven-label | Required for correct behavior on enjoined rules |
| FERPA acknowledgement | Add explicit disclaimer / ignore for prototype | Add explicit disclaimer in README and PRODUCT_SCOPE.md | Minimal effort; professional obligation |

### Decisions that technical testing (spikes) will resolve

| Decision | Resolved By |
|---|---|
| Backend hosting: Code Engine vs. Render/Railway | Spike S5 |
| Auth provider: Auth.js vs. IBM App ID vs. Supabase Auth | Spike S5 (code engine availability confirms platform) + App ID availability check |
| Orchestrate chat: embed widget vs. REST API proxy | Spike S4 |
| User context propagation mechanism | Spike S3 |
| Embedding model: watsonx.ai vs. local/alternative | Spike S6 |
| OpenAPI 3.0 vs. 3.1 format required by Orchestrate | Spike S1 |
| Orchestrate Draft vs. Live endpoint for demo | Spike S7 |

---

## Part 11 — Final Recommendation

### What the unified plan should look like

The unified plan should use **Plan A as the primary source for product depth, security design, and operational detail**, and **Plan B as the primary source for IBM documentation grounding, platform-specific API details, and ingestion worker specifics**. Plan A is more complete by a significant margin and was written with knowledge of the actual course tenant; Plan B should not be treated as authoritative simply because it was generated more recently.

### What to retain from Plan A (unchanged or minimally revised)

- Product definition, service modes, and non-goals (Section 4–5)
- Both demo stories (Section 6) — critical for course evaluation
- Full functional requirements (Section 7)
- Architecture principles (Section 8) — especially the ten principles verbatim
- Nine-label Orchestrate ownership boundary table (Section 9.1)
- Seven-label policy status vocabulary (Section 12.1)
- Full tool list including `get_school_adapter`, `propose_profile_update`, `confirm_profile_update`, `execute_mock_submission`, `escalate_to_isss` (Section 10.3)
- Content-specific approval token with payload hash and EXPIRY state (Section 16.4)
- Complete data model with all 16 entities (Section 14)
- Full 15-endpoint API surface (Section 15)
- Testing and evaluation framework including 20–30 eval cases (Section 21)
- Six-phase implementation plan with exit criteria (Section 20)
- 25-point Definition of Done (Section 25)
- `bob_sessions/` evidence format with screenshots (Section 3.1)
- Risk register (Section 24) — add Gap Analysis items G1–G11

### What to retain from Plan B (as addenda or revisions to Plan A content)

- watsonx.ai API endpoint specifics (`/ml/v1/text/embeddings`, etc.) — add to Section 9 equivalent
- Agent Lab beta end-date note — add to research notes
- SHA-256 hash specification for content diffing
- `superseded = true` flag on old policy chunks
- pgvector HNSW index specification
- `rule_parameters` table as an explicitly named entity
- `rule_change_proposals` as the link between classifier output and team review
- Seven-spike matrix with time-box estimates (retain and expand with fallback architectures)
- IBM Cloud service availability pragmatism — revise Plan A's hosting section to acknowledge fallbacks

### What to revise

- **Plan A's hosting section:** add explicit fallbacks (Render/Railway for backend; Vercel confirmed for frontend)
- **Plan A's auth section:** add Auth.js as the primary demo option; IBM App ID as an optional IBM integration if available
- **Plan A's ingestion timing:** clarify that manual ingestion is sufficient for MVP; scheduled workers are Phase 4
- **Plan B's policy status vocabulary:** replace with Plan A's seven-label vocabulary
- **Plan B's approval record:** add payload hash binding and EXPIRED state from Plan A
- **Both plans' user-context propagation:** adopt the security rule that tool endpoints derive `user_id` from the backend session, never from Orchestrate message content

### What to defer

- Real OAuth integrations (Phase 5; should not block Demo Day)
- Multi-university adapter (Phase 4+ for non-Penn schools)
- watsonx.governance integration (Phase 6 or post-course)
- Sub-agents (Phase 4+; only if demonstrated need arises)

### What to reject

- Plan B's recommendation to use "watsonx.ai agent API directly from backend, bypass Orchestrate for tool routing" as a fallback: **this fallback is wrong for this course because Orchestrate being central is a course requirement.** If Orchestrate tool import fails, the correct fallback is to troubleshoot Orchestrate compatibility, not to bypass Orchestrate. The only scenario where bypassing Orchestrate is acceptable is if the course tenant has definitively confirmed that custom tool import is not available in the Trial plan.
- Plan B's IBM App ID as the primary auth recommendation: premature given confirmed limited IAM rights in the course account.
- Plan B's assumption that Code Engine is always available: overstated confidence given unconfirmed provisioning rights.

---

## Appendix: Repository Structure (Unified)

```
staytus/
├── AGENTS.md
├── README.md
├── PRODUCT_SCOPE.md
├── SOURCES.md
├── FEATURES.md
├── UNIFIED_PROJECT_PLAN.md
├── .env.example
│
├── bob_sessions/
│   ├── README.md               # index of all sessions
│   └── screenshots/            # per-session screenshots
│
├── frontend/                   # Next.js 14 + TypeScript
│   ├── app/
│   │   ├── dashboard/
│   │   ├── profile/
│   │   ├── chat/
│   │   ├── approvals/
│   │   ├── policy-updates/
│   │   ├── admin/              # review queue (team only)
│   │   └── audit/
│   ├── components/
│   └── lib/api-client.ts
│
├── backend/
│   ├── app/
│   │   ├── api/                # /api/v1/* application routes
│   │   ├── tools/              # /tools/* Orchestrate-facing routes
│   │   ├── auth/               # JWT validation, session management
│   │   ├── models/             # SQLAlchemy + Pydantic models
│   │   ├── services/           # business logic layer
│   │   ├── rules/              # deterministic rule engine
│   │   │   ├── base_adapter.py
│   │   │   ├── upenn_adapter.py
│   │   │   └── deadline_engine.py
│   │   ├── retrieval/          # hybrid search logic
│   │   ├── ingestion/          # workers + scripts
│   │   │   ├── sources/
│   │   │   ├── differ.py
│   │   │   ├── classifier.py
│   │   │   └── embedder.py
│   │   ├── approvals/          # approval state machine
│   │   ├── connectors/         # Phase 5: email/calendar clients
│   │   └── audit/
│   ├── migrations/
│   └── tests/
│
├── orchestrate/
│   ├── agent/
│   │   ├── instructions.md     # system prompt, version-controlled
│   │   └── agent_config.yaml   # model, tools, settings export
│   └── tools/
│       ├── openapi.yaml        # validated OpenAPI 3.0 export
│       └── tool_notes.md       # known Orchestrate compatibility notes
│
├── config/
│   ├── sources.yaml
│   └── schools/
│       └── penn.yaml
│
├── fixtures/
│   ├── profiles/               # synthetic student profiles
│   ├── policies/               # pre-ingested policy fixtures for demo
│   └── policy_replay/          # Demo B replay snapshot
│
├── scripts/
│   ├── export_openapi_3_0.py   # generates validated 3.0 from FastAPI
│   ├── ingest_sources.py
│   ├── seed_demo_data.py
│   └── replay_policy_change.py
│
├── evals/
│   ├── policy_questions.json   # 20–30 evaluation cases
│   ├── deadline_cases.json
│   └── approval_cases.json
│
├── docs/
│   ├── research/               # spike results and IBM platform notes
│   └── bob-usage-log.md        # machine-readable session index
│
└── infra/
    ├── code-engine/            # Code Engine deployment manifests
    └── db/migrations/
```

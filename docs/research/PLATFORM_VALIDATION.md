# Platform evidence and unresolved tenant checks

Updated 2026-11-01. Documentation research is not a successful course-tenant test.
The user previously verified dashboard/Builder access to a Toronto Orchestrate
Trial. Provisioning rights, model availability, tool import, app integration,
and actual Live invocation have not been verified by this implementation.

## Corrections to the planning documents

- There are **eight** policy labels in the plan's enumerated vocabulary.
- The S1 fallback table contradicts Part 11. Keep Orchestrate central; troubleshoot
  its tool import or escalate to the course administrator. Do not silently replace
  the agent with direct watsonx.ai calls.
- A source IP range is not sufficient tool authentication. Do not expose inbound
  headers for debugging; they can contain credentials. Log only presence/status.
- IAM authenticates access to the IBM Cloud service API. The application's tool
  API needs its own configured credential and per-session authorization; do not
  assume an outbound Orchestrate tool call automatically carries valid IAM.
- A contextual `user_id` in a system message is not proof of user identity.
  Staytus tools require a signed server-issued context and validate its session.
- The plan's example OPT window changes and dates are fictional. They must never
  be presented as actual Penn/USCIS changes. The implementation replays only an
  explicitly fictional internal preparation-buffer change.
- Auth.js does not itself implement an identity provider or institutional login.
  This iteration uses an explicit synthetic-profile demo session. Real auth is a
  separate deployment task; selecting a school or EDU address grants no access.
- Publishing is an agent lifecycle operation; it does not deploy the frontend,
  FastAPI server, database, or scheduled workers.

## Documented platform behavior

| Component | Documented role | Implementation implication |
|---|---|---|
| IBM Cloud | Hosts managed services and service access policies | Code Engine/database availability depends on actual account entitlements |
| Orchestrate | Native agents, callable tools, connections and application channels | Agent YAML/tools are committed; runtime tenant configuration remains separate |
| Orchestrate connections | API key, key-value, bearer/OAuth; team/member identities | Service credentials belong in connections; per-user authorization remains enforced by backend |
| IBM Cloud Orchestrate API | IAM token authentication for service APIs | Copy the tenant service endpoint and agent UUID, then test actual request shape |
| Embedded chat | Signed client JWT and configurable session context | A server-minted context claim can be consumed by Python `AgentRun` tools |
| watsonx.ai | Separate model generation/embedding/reranking APIs | Workers may call these with appropriate project/space credentials; separate from Orchestrate's internal model binding |

References checked:

- [IBM Cloud Orchestrate authentication](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=api-getting-started)
- [OpenAPI imports](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=tools-importing-from-openapi)
- [Connection binding and Live validation](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=credentials-binding-deploying-connections)
- [Authentication types](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=credentials-authentication-types-overview)
- [JWT context in Python tools](https://developer.ibm.com/tutorials/context-variables-watsonx-orchestrate/)
- [Embedded chat security](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=applications-securing-embedded-chat)
- [watsonx.ai REST API](https://cloud.ibm.com/docs/apis/watsonx-ai)
- [watsonx.ai quick start](https://www.ibm.com/watsonx/developer/get-started/quick-start)

The signed-capability design strengthens the tutorial's identifier-only example.
It still needs a live S3 test to establish that this tenant's chosen channel and
ADK runtime inject the signed JWT claim into `AgentRun.request_context` without
converting it into an LLM-provided argument.

## Seven required live spikes

All status entries below are **PENDING**. No credential or live resource has been
created automatically. Store screenshots and sanitized request/response evidence
under `bob_sessions/` after testing; never record keys, full headers, or tokens.

| Spike | Status | Small test and evidence | Pass condition | Failure behavior |
|---|---|---|---|---|
| S1 Tools | PENDING | Import one read tool; show its successful response in Draft | Correct schema/tool invocation | Fix import or Python wrapper compatibility; ask course admin if unsupported |
| S2 Service auth | PENDING | Invoke once with valid configured key and once without | Missing/invalid key is rejected; no secret logs | Keep endpoint closed; adjust connection configuration |
| S3 User context | PENDING | Two signed browser sessions, tampered/expired context, prompt asking for another profile | Sessions remain isolated; invalid capability gets 401 | Disable personalized live tools; no shared static student context |
| S4 Web/API channel | PENDING | Copy embed config or complete endpoint; test CORS/JWT/refresh and a full turn | Agent response and user-scoped tool work end to end | Keep labelled local demo; investigate supported channel |
| S5 Hosting | PENDING | Verify Code Engine and PostgreSQL permissions; deploy tiny health endpoint | Actual entitlement, TLS, health, persistence | Use approved alternative hosting; retain IBM Orchestrate runtime |
| S6 Model/embeddings | PENDING | List actual models; request one embedding with project/space IAM | Vector dimensions known and permitted model succeeds | Use explicit keyword demo retrieval; never claim vector RAG is active |
| S7 Draft/Live | PENDING | Deploy to Live and test its credential bindings; edit Draft separately | Live flow remains stable and correct | Keep Draft labelled development-only; resolve before public release |

## Release gates beyond code

Real identity/OAuth, institutional consent, production secret management, account
expiry, privacy review, RLS under the actual database role, and source-fetch terms
must be resolved for real student use. Local deterministic fixtures and mock
receipts are evidence of application behavior, not proof of IBM deployment.

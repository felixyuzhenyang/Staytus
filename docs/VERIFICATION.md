# Current verification — November 2, 2026 (America/New_York)

## Automated checks

| Check | Actual result |
| --- | --- |
| `make test` | 401 backend tests passed, including tool/workflow verification, connector-target/profile-version approval binding, calendar providers and notification delivery controls; TypeScript passed; OpenAPI 3.0.3 validated 13 read/proposal operations; real provider credentials blanked for the fixture-based suite |
| `npm run build` | Passed after final frontend changes, Next16.4.3 |
| IBM runtime/chat | Existing main Staytus Agent published with 13 tools; all 13 tool interfaces covered by 4 bounded Live cases/17 tool calls, including expected mail-permission denial; fresh two-principal main-Agent Live proof passed after tunnel restoration; real Chinese browser chat called the profile tool once |
| OAuth/security | PKCE, session/state binding, encrypted tokens, exact separate mail/calendar scopes, bounded renewal, Agent-preview permission, cross-account denial, immutable connector target and current-profile approval claims tested; provider transports mocked, not a real mailbox/calendar authorization |
| Reminders | Worker, account-owned inbox/popup, timezone preferences, durable opt-in email outbox and SMTP transport implemented/security-tested; synthetic browser popup/settings passed; real SMTP is unconfigured and no real reminder email was sent |
| Calendar | Synthetic browser approval/export produced a real `.ics` with `VALARM` 1440 minutes; Google/Microsoft write transports and target-binding guards tested with mocks; no real remote calendar was changed |
| Offline readiness script | Orchestrate and independent watsonx.ai URL/project/key/models configured; OAuth app credentials absent; private local context gate enabled after matching main-Agent Live evidence |
| SDK and context | Actual ADK2.19.1 import/serialization/mock forwarding passed;13 cloud imports/bindings verified; isolated Draft/Live and main-Agent Live two-account profile/audit proofs passed |
| Orchestrate connection | User completed the connection wizard; Draft and Live credential-entry flags and key-value/team compatibility verified through metadata; this is not successful tool execution |
| Narrow gateway | Authorized temporary HTTPS edge and loopback health 200, private routes 404, unauthorized tool 401; no browser/login/OAuth/final-approval interface exposed |
| Model readiness | Real regional catalog, Granite embedding and structured chat-generation probes passed; five current chunks indexed at 768 dimensions; real Chinese hybrid retrieval returned official citations |

The sole test warning is an upstream Starlette/httpx TestClient deprecation. Tests use isolated databases and synthetic scenarios. The old embed route is absent; its source and earlier report are archived.

## Actual browser flows

- Latest synthetic QA: reminder inbox/popup appeared, preferences saved with timezone `America/New_York`, and Google Calendar displayed missing-configuration/scope information. A calendar preview was approved and its actual `.ics` included a display alarm 1440 minutes before the event. A real Chinese chat reply used Orchestrate and invoked `get_student_profile` exactly once, confirmed by the owned backend audit. The QA account was logged out and all synthetic rows/local QA credentials were removed. Evidence: `docs/evidence/reminder-inbox-synthetic.png`, `calendar-target-synthetic.png`, `chat-after-calendar-reminder-integration.png`.
- The popup is an in-app feature that requires an open page. Native OS notifications/background push have not been implemented. Email reminders remain off by default and require configured SMTP, a verified connected target mailbox and explicit user opt-in.

Earlier browser coverage, retained as history:

- Real existing test-account login → session restoration → first-use profile onboarding → personal dashboard.
- Profile restoration after reload; cross-origin mutations rejected; tokens redacted from browser JSON; HttpOnly/SameSite cookie; logout/reload returns to login.
- Calendar preview → exact-content approval → `SUCCEEDED` / `file_export` receipt and actual `.ics` endpoint.
- Chat with no IBM configuration returns503 and a visible error, without any invented assistant answer.
- Connections describes actual missing OAuth deployment credentials; no user's mailbox was connected.
- Second-iteration browser check: a clearly synthetic QA account completed registration/onboarding, Microsoft setup displayed the exact callback and missing client settings, and chat showed the missing-IBM error with no generated answer. Signed out after checking.
- Policy library shows six real-source statuses, fresh federal captures and explicit Penn failures.
- Actual Staytus Orchestrate Agent created and later updated/published on the same UUID, with the existing internal name and Staytus display name preserved. UI shows 13 tools and Live. A separate local HTTP smoke verified the Next.js cookie proxy, actual backend chat and Live tool callback using disposable synthetic accounts; no real browser user's session was replaced.

## Actual Live business-tool coverage

`scripts/verify_orchestrate_tools.py` completed 4 bounded model requests against the existing published main Agent, covering 13 unique tool interfaces and 17 tool invocations:

| Case | Actual verified result |
| --- | --- |
| Eight read/planning/handoff tools | School metadata, cited non-fixture policy search/version status, deterministic planning dates, owned tasks/notifications, adviser handoff without sending, and action plan all matched actual backend responses/audits |
| Proposal tools | Profile update, email and export-calendar previews produced exact owned `PROPOSED` rows without execution; an optional profile call made 4 tool calls in this case |
| Mail permission denial | Inert synthetic provider connection plus disabled Agent-preview permission returned `tool_permission_required`; no provider credentials could be used and no real mailbox was read |
| Second-account multistep workflow | Profile → public policy search → planning-date calculation → calendar preview ran in the reviewed order, with separate ownership and no other-account changes |

All returned proposal IDs/content and successful tool audits matched the database; the denied mail request correctly produced no committed successful-read audit. Temporary notifications, approvals, provider placeholders, sessions, profiles and accounts were cleaned up. Report: `.local/orchestrate-business-tools-result.json`. This is actual Live integration coverage using synthetic data, not an evaluation of legal completeness or real provider permissions.

After approval hardening, a separate one-request proposal-only Live check passed against the updated gateway, including its optional profile call (4 tool calls). Email/remote-calendar payloads bind a server-derived `_connector_target` inside the content hash; an absent connection is explicitly bound and cannot silently switch after a later connection. Export calendars have no remote target. The verifier checks normalized business fields, full hash, displayed target and current profile version and rejects model-forged targets. Report: `.local/orchestrate-business-proposals-bound-target.json`. The earlier full report remains historical proof of the original batch; this recheck covers the changed proposal contract.

## Actual public-source results

All six sources in the registered YAML were attempted. Cleaner v2 snapshots of USCIS Students, DHS Study in States and DOS BridgeUSA total five current main-text chunks. They are non-fixture, pending-review captures. Three Penn ISSS pages returned HTTP 403. Those errors are persisted and shown; no login/challenge bypass or synthetic replacement occurred. No captured policy auto-activated a legal rule.

After the user created/downloaded `staytus-watsonx-ai`, its JSON was read without printing the key and configured server-side only. Real IBM IAM/catalog checks succeeded. Selected available `ibm/granite-embedding-278m-multilingual` and `ibm/granite-4-h-small`. Embedding/structured-generation checks passed using fixed public text. The related English/Chinese pair ranked above an unrelated sentence (0.95551 vs 0.43618); this is a tiny smoke check, not a general benchmark. Granite 4 generation now uses the documented chat endpoint; the legacy endpoint's empty response was not counted as success.

Reindexing existing captures completed for three sources/five chunks with zero failures; no recrawl, personal-profile input or review/rule change occurred. A fixed Chinese query with a synthetic F-1 category returned USCIS and DHS hybrid results, both marked review_required. Current vectors are 768-dimensional; historical 11 chunks remain superseded and unembedded. Safe reports are in ignored `.local/watsonx-*.json` files.

## IBM and Bob boundaries

Official Cloud REST/context schemas and ADK2.19.1 source were inspected; the implemented protocol uses `/v1/orchestrate`, separate per-turn context and the thread header. Actual two-principal tenant identity propagation passed and was repeated successfully after the temporary callback was restored.

Cloud UI confirms existing Runtime/Studio services in Dallas and Orchestrate in Toronto. Orchestrate's exact API URL was saved locally. Studio's signed-in home shows the course account and two existing projects. Staytus now uses the existing `watsonx Hackathon Sandbox` project, whose existing Runtime association was verified. Independent watsonx.ai authentication/inference/indexing passed as described above. Its key is not reused for Orchestrate authoring. Source/newly prepared Agent configurations enable the context switch while keeping the model allowlist empty, following the actual fixed-marker comparison described below.

User approved creation of `staytus-local-runtime` / `WO User`, local-only API-key storage, and the third-party model terms/test. Real IAM/Draft inference succeeded. Runtime-key connection management initially returned403. The user subsequently created `staytus-local-authoring` / Writer; it was stored only in private backend configuration, authenticated, and used in the separately bound `staytus-authoring` SDK environment. The runtime and watsonx.ai keys were preserved.

The authorized temporary Cloudflare edge exposes only the independent gateway. An earlier automatic review rejected copying Draft to Live because the then-current authorization was interpreted as Draft-only. The user later explicitly requested Live setup and completed the visible connection wizard. Fresh metadata confirms both environments have credentials entered with compatible key-value/team settings; gateway health is good. No additional access grant is inferred from those metadata flags.

The actual completed synthetic model call initially encountered an incorrect thread-read prefix. Correcting the read-only URL to `/v1/orchestrate/threads/{id}/messages` recovered the existing assistant response without another inference submission. The verifier now requires actual assistant output, not user/tool echoes or `run.result`. Internal Agent `name` and UI `display_name` are checked separately.

Bob Agent task attempts are recorded honestly under `bob_sessions/2026-11-01-runtime-implementation/` and `2026-11-01-healthcheck-attempt/`. Native input/screenshot state was inconsistent; no verified Bob implementation file was produced. Current runtime and readiness script are Codex work.

The subsequent bounded provider-setup task and actual inconsistent UI evidence are in `bob_sessions/2026-11-01-provider-setup-attempt/`; it is also not credited as completed Bob implementation.

A later actual Agent session is recorded in `bob_sessions/2026-11-01-orchestrate-toolchain/`. Corrected preflight/CLI/verifier/test edits were approved and applied, with exact Bob-applied snapshots preserved. Codex then hardened metadata/identity handling and the test harness. After Writer access was established, Codex imported all 13 business tools and confirmed their exact backend connection bindings. The isolated `StaytusContextProbe` Draft agent references only the profile tool.

Earlier controlled WO User Draft attempts, including retries after Finish and dependency pinning, reached `get_student_profile` but returned `Error getting Python tool status`. Those failed attempts supplied no passing isolation proof; their temporary accounts were removed. A transient Writer diagnostic also failed, without replacing the product runtime identity. The following later corrections and passing reports supersede that failure state.

A separate constant-only/no-connection diagnostic returned an actual `STAYTUS_RUNTIME_OK` tool response. Thus simple tenant Python execution works; a blanket platform-outage claim is unsupported. Further operator-only probes isolate imports/dependencies from connection/context handling. Read-only transient status GETs now retry with bounds, while uncertain inference POSTs never resubmit automatically. Safe results remain in ignored `.local/` files, without capabilities or credentials.

The no-extra-dependency AgentRun diagnostic executed with the original context switch off but returned `STAYTUS_DIAGNOSTIC_CONTEXT_MISSING`. With only that switch changed to true and the model allowlist still empty, the actual tool returned `STAYTUS_RUNTIME_OK`. Source/preparation/probe/preflight checks now require enabled tool context and an empty model allowlist. The isolated profile probe was updated and its signed two-account test rerun. A separate dependency/import diagnostic stayed running for over five minutes; its cancellation endpoint returned404, so cancellation was not claimed and no result from that request was treated as passing proof.

Further isolated tools verified delivery of the existing backend connection fields and an actual standard-library HTTPS GET from IBM to the approved narrow gateway. The full dependency-based profile tool still timed out after the context fix; the precise provider-side failure is not established. The thin business wrapper now uses standard-library HTTPS with both credentials, redirects disabled, bounded timeout/response size and no retries. Ten transport regressions and the actual SDK decorator/context mock passed before updating the same 13 business tools. Full owned-profile/audit proof remains separate from these diagnostics.

The corrected full bridge then passed isolated Draft and published Live two-account tests. Published releases use pinned `{tool_id, version_label}` references, unlike Draft UUID strings; the verifier now accepts only the observed strict Live shape and rejects unknown/duplicate identities or invalid versions. The existing main Agent was independently read back on its original UUID, then published using matching Live probe evidence. Its own Live two-principal test also passed exact profile JSON, separate threads, one owned audit each and no cross-account audit. All temporary rows were cleaned up. Private reports: `.local/context-draft.json`, `.local/context-live.json`, `.local/context-product-live.json`.

Only after the main-Agent proof was reviewed was `ORCHESTRATE_CONTEXT_VERIFIED=true` written to private mode0600 backend configuration; source defaults and example configuration remain false. The final real local application HTTP smoke returned 200 and `mode: orchestrate`, with the exact owned-profile result, a corresponding tool audit, the other synthetic account untouched and synthetic conversations/accounts cleaned up. Report: `.local/product-bff-live-smoke.json`. Runtime/authoring/watsonx.ai keys and permissions were preserved; no new credential was needed. Screenshot: `docs/evidence/orchestrate-staytus-live-13-tools.png`.

During the later business-tool work, the former temporary callback returned 530 before any model call or synthetic record creation. The narrow gateway and tunnel were restored, the approved callback URL was updated in private configuration and both existing Draft/Live bindings were refreshed. No service/signing secret or IBM runtime/authoring role was changed. The context gate stayed false until a fresh main-Agent two-account Live proof passed on the new binding; `.local/context-product-live.json` now records that current proof. Public app deployment remains deferred.

Google/Microsoft OAuth app credentials are still absent. The Google registration console requires the user's MFA; the Microsoft portal attempt timed out. No completed app registration, real mailbox consent, provider read/draft/calendar write or reminder email is claimed. Configuration and exact permission requirements are exposed in the application; mock/security tests cover the prepared provider paths.

## Not yet validated or implemented

- Real consenting Google/Microsoft OAuth, mailbox read/draft and remote calendar writes. The 13 Orchestrate interfaces are Live-tested, but mail coverage intentionally verifies denial, and calendar coverage creates previews/export files only.
- Real SMTP delivery after operator configuration and verified-mailbox user opt-in. Worker/outbox/UI implementation is present; delivery is off by default. In-app popups require an open page; native OS/background push remains unimplemented.
- Broader policy coverage and applicability/answer-quality evaluation beyond the small actual public corpus and fixed synthetic workflows.
- Penn private portal reads/submissions and user-directed mail sending; Penn work is deferred. Three Penn public sources remain blocked403.
- Public cloud deployment, PostgreSQL behavior/migrations, production SSO/verified-email reset, distributed limits, retention/deletion and operational monitoring.

Earlier QA screenshots are ignored under `output/verification/2026-11-01/` and `output/verification/2026-11-01-connections/`. Non-secret screenshots of the saved Draft/Live connection and imported tool list are in `docs/evidence/`. Credential values are excluded from retained evidence. Safe credential/model/gateway checks and synthetic diagnostic reports are ignored under `.local/`. Historic prototype data remains separate in `staytus.db`; new application state is in `staytus-app.db`. The application itself remains local; only the user-approved temporary tool edge was started.

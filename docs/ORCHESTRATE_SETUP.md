# Remote Orchestrate setup — version-checked preparation

The official IBM ADK2.19.1 is installed in ignored `.local/orchestrate-adk`, separately from the application environment. Its package metadata supports Python3.11–3.14; the local environment uses3.13.9. Remote imports do not require the Docker-based local Developer Edition.

`scripts/orchestrate_setup.py` defaults to an offline check. It does not read `backend/.env` unless `--env-file` is explicitly passed, and it never prints credential values. It can prepare reviewed assets, verify the actual installed SDK, and execute a specifically selected authorized cloud step.

## Offline verification

From the repository root:

```sh
backend/.venv/bin/python scripts/orchestrate_setup.py
.local/orchestrate-adk/bin/python scripts/orchestrate_setup.py --check-adk
```

The actual SDK successfully imports all 13 current Python wrappers, including `read_recent_official_messages`; each has the `context` AgentRun binding and the `staytus_backend` key-value connection expectation. The check also executes the actual SDK decorator/context parser against a mock HTTP bridge and verifies capability forwarding. This command establishes local serialization only; separate actual tenant two-account tests and the bounded business-tool checks below have now passed. A fresh deployment still needs its own proof rather than treating SDK import as runtime validation.

The source and newly prepared agents use `context_access_enabled: true` and `context_variables: []`. A controlled tenant comparison found that the former `false` setting produced an executed Python tool with the fixed request marker missing; `true` with an empty allowlist delivered that marker. This corrects the earlier assumption that leaving the switch off would still deliver tool context in this tenant. IBM documents that unlisted variables are not available to the native agent or injected into its prompt ([context configuration](https://developer.watson-orchestrate.ibm.com/conversation/context_variables)). The model allowlist must remain empty and a signed capability must never be interpolated into instructions, descriptions or guidelines. Local bundle and cloud-Agent checks require this exact configuration. Marker delivery alone does not prove an owned-profile callback or two-account isolation.

## Prepare a connection-test Agent

Use the exact model ID available in the tenant. The following model passed the authorized tool-free Draft inference check; this does not establish a tool-enabled deployment:

```sh
.local/orchestrate-adk/bin/python scripts/orchestrate_setup.py \
  --prepare --chat-only --agent-name Staytus \
  --model-id groq/openai/gpt-oss-120b \
  --bundle-dir .local/orchestrate-chat-only
```

Preparation writes only reviewed Agent/tool/requirements/connection assets and a hash manifest. It copies no `.env`, database, student profile, mailbox content or service key. Chat-only Agent instructions explicitly state that tools are not connected. Preparation alone does not call a model or accept a model license.

For full tools, repeat without `--chat-only`, using a different bundle folder. The prepared YAML uses the current wrapper names automatically and does not modify the source Agent YAML or the existing cloud draft. Re-prepare if any asset changes; the apply path rejects a mismatched artifact hash.

## Real cloud operations — explicit steps only

First obtain the exact service-instance URL and an authorized key. IBM maps `WO User` to the runtime user role, `Writer` to Builder, and `Manager` to administrator. The current role guide gives Builder connection management, agent/tool building and testing/deployment capabilities. Prefer a separate authoring credential with `Writer` scoped to this one Orchestrate instance, while the application's runtime credential remains `WO User`. Never broaden the runtime key silently.

IBM's documentation is inconsistent at a finer level: the current Builder role guide includes adding connection credentials, while the separate IBM Cloud IAM action table still maps `credentials.write` and `release.write` to `Manager`. Therefore `Writer` is the documented minimum authoring role, not a guarantee that every credential/deployment API is enabled in a particular tenant. If a specific authorized action remains denied, identify it and resolve that requirement separately; do not automatically escalate to Manager. See [current role guide](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=users-roles-watsonx-orchestrate), [IBM Cloud IAM actions](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=users-managing-cloud) and [Builder connection prerequisites](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=servers-configuring-mcp-server-connections).

Use these server-side variable names in an explicitly selected env file:

- `ORCHESTRATE_SERVICE_URL`: exact service-instance URL, not dashboard host.
- `ORCHESTRATE_API_KEY`: runtime credential, normally `WO User`; unchanged by setup.
- `ORCHESTRATE_AUTHORING_API_KEY`: optional, separate authoring credential preferred by every explicit setup stage. If absent, setup falls back to `ORCHESTRATE_API_KEY` and does not claim that runtime permission is sufficient.
- `ORCHESTRATE_BACKEND_URL`: approved public HTTPS base host for cloud tool callbacks, with no `/tools` suffix.
- `ORCHESTRATE_TOOL_KEY`: independent random backend service key.
- `ORCHESTRATE_CONTEXT_VERIFIED`: remains false until actual secure-context testing passes.

After reviewing the prepared files and receiving any required action-time permissions, the operator can select a single stage:

```sh
.local/orchestrate-adk/bin/python scripts/orchestrate_setup.py \
  --env-file backend/.env --bundle-dir .local/orchestrate-chat-only \
  --environment-name staytus-authoring --apply activate --confirm-cloud-changes
```

The stage choices are:

| Stage | Operation |
| --- | --- |
| `activate` | Register/activate the project CLI environment and authenticate to the selected instance |
| `connection` | Import `staytus_backend` and provide HTTPS URL/tool key for `--connection-environment draft`, `live` or `both` |
| `tools` | Import the prepared Python file with requirements and connection binding; needs `--allow-update` |
| `agent` | Import the reviewed prepared Agent; needs `--allow-update` because same-name assets can be updated |
| `deploy` | Publish the prepared Agent by its exact name; tool-enabled bundles need matching synthetic evidence via `--context-test-report` plus `--confirm-context-tested` |

Every real stage requires `--confirm-cloud-changes`; flags are operator controls and do not replace user/account authorization. Do not run all stages blindly. First complete a no-personal-data chat test, then use the staged synthetic procedure below. `ORCHESTRATE_CONTEXT_VERIFIED` is a product-routing gate and is not a prerequisite for running controlled verification.

Use the distinct SDK environment `--environment-name staytus-authoring` for authoring stages. ADK2.19.1 can reuse a still-valid cached token and ignore a newly supplied API key. The launcher refuses an environment whose cached identity is unknown or bound to another selected key; choosing the authoring variable alone is insufficient. It records only a one-way credential/tenant fingerprint and source label in ignored `.local/orchestrate-cli/credential-bindings.json` after successful activation. No raw API key is saved there. Older SDK caches without this binding must use a fresh distinct environment; they are not silently trusted, deleted or overwritten. A changed authoring key also needs a fresh environment when an older cached identity exists. The application runtime and synthetic verifier keep using `ORCHESTRATE_API_KEY` and never consume the authoring key.

An independent authoring key is a permission-separation choice, not a requirement to have three differently named IBM keys. IAM identity and roles determine access, not the key's label. The existing watsonx.ai user key is authorized here only for model calls; it is not reused for Orchestrate setup. Bob can edit local code without any authoring key. The user created the instance-scoped `staytus-local-authoring` Writer credential; it is saved only in private backend configuration and its authoring authentication has passed. Writer scope is not limited to one local project folder. The product runtime identity remains WO User.

Current cloud setup: all 13 Python wrappers are imported, bound to the backend connection and published on the existing Staytus Agent. Isolated Draft/Live and main-Agent two-account identity/audit tests passed. Four bounded Live business cases now cover 13 unique tool interfaces and 17 tool calls, including expected mailbox denial and a second-account multistep planning/calendar-preview workflow. A separate proposal-only recheck passed after connector-target/profile-version hardening. Real OAuth/provider delivery remains unverified: tool invocation and preview creation do not prove a connected mailbox or remote calendar write.

The earlier Next.js → API → Live → tool profile smoke returned 200, and latest synthetic browser QA also passed a real Chinese profile-tool chat with one matching audit. Its reminder popup/preferences and approved calendar export with a 1440-minute alarm passed; QA records/credentials were removed after logout. Final local checks passed 401 backend tests, TypeScript, 13-operation OpenAPI validation and production build. See `VERIFICATION.md` for the exact scope and evidence.

The former temporary callback later returned 530 before any model request or test-account creation. The gateway/tunnel were restored, only the callback URL was changed in private configuration, and both existing Draft/Live bindings were refreshed. Runtime/service/signing credentials and roles were preserved. The local context gate stayed false until a fresh main-Agent Live two-account proof passed for the new binding; current proof is `.local/context-product-live.json`. The tunnel is still temporary and must remain running. A changed URL, key, model or artifact needs matching new evidence.

Earlier Python-tool-status failures and timeouts were superseded by the corrected context switch plus standard-library HTTPS bridge; the exact provider-side dependency failure was not proven. The extra-requirements file is empty; ADK import adds its own versioned SDK. Do not change package versions speculatively after a passing report, since that invalidates the reviewed artifact.

The existing product Agent has a different internal `name` and human-facing `display_name`. Its prepared bundle preserves the exact internal slug and display name Staytus; blindly importing a new Agent named only Staytus could create a duplicate. Published tool references pin `tool_id` and integer `version_label`, while Draft holds UUID strings. The controlled verifier handles these shapes separately and still resolves every UUID through independently fetched metadata.

## Read-only tool-chain preflight

After reviewing this command, an operator can inspect configuration and cloud metadata:

```sh
backend/.venv/bin/python scripts/orchestrate_setup.py \
  --env-file backend/.env --bundle-dir .local/orchestrate-context-probe \
  --preflight --preflight-gateway
```

This is explicit opt-in networking: IAM authentication, metadata GETs and optional gateway health only. It cannot be combined with prepare, SDK checks or apply stages. Without `--preflight`, setup remains offline. It never reads connection credential values, imports tools, publishes an Agent, invokes a model, or enables product chat.

The report separates local blockers, authentication, forbidden metadata (`403`), genuinely missing resources (`404`), and unknown/malformed evidence. Draft/Live credential-entry flags prove only that values were entered, not their validity. Tool bindings must point to the exact connection UUID. Agent tools are UUID references; names are resolved through actual tool metadata and checked for missing, extra, conflicting and duplicate identities. Agent definition checks describe Draft only; a Live version number does not verify its contents. `personalized_context_verified` remains false until the separate synthetic procedure is reviewed.

## Staged synthetic Draft → Live verification

The separate `scripts/verify_orchestrate_context.py` bypasses the product chat route only for an explicit integration test. Its default is offline and does not read an env file, create an account or call IBM. Actual testing requires both `--live` and `--confirm-synthetic-test`; `--target draft` still means an actual cloud call when `--live` is supplied. The test may consume model quota. Do not start it until the model terms, cloud access and narrow HTTPS callback have been approved/configured.

Prepare a separate one-tool agent, leaving the product Draft unchanged:

```sh
.local/orchestrate-adk/bin/python scripts/orchestrate_setup.py \
  --prepare --context-probe --agent-name StaytusContextProbe \
  --model-id groq/openai/gpt-oss-120b \
  --bundle-dir .local/orchestrate-context-probe
```

After authorized `connection`, `tools` and `agent` imports for that bundle, obtain its actual UUID. Use that UUID explicitly; never substitute the current product Agent ID. The test discovers the actual environment UUID using the official `GET /v1/orchestrate/agents/{agent_id}/environment` response. It sends the Draft request through `POST /v1/orchestrate/runs` with `environment_id` and `context` as separate top-level fields, then polls the returned run ID. It does not assume that `environment_id: "draft"` is interchangeable with the returned UUID. The published Chat Completions contract has no Draft selector.

For **IBM Cloud**, final thread messages are read from `{service-instance-url}/v1/orchestrate/threads/{thread_id}/messages`. The shorter `/v1/threads/...` path in the Developer Edition OpenAPI is for the local server and is not the Cloud URL. This distinction is explicit in installed ADK2.19.1 `ibm_watsonx_orchestrate_clients/common/base_client.py:235–243`: `BaseWXOClient` appends `/v1/orchestrate` for Cloud and `/v1` locally; `threads/threads_client.py:18–26` then adds `/threads/{id}/messages`.

The response is an array, with the SDK also accepting a top-level `data` array. The verifier reads only the latest message whose role is `assistant`, extracts its text blocks and requires the exact JSON profile result requested by the prompt. A completed run, an empty/loosely typed `run.result`, a user-message echo, a tool-output message or an unsupported `data.messages` wrapper cannot count as a successful model answer. A thread-read failure stops the check without resubmitting the inference request. A generic no-tool smoke test should follow the same Cloud path and assistant-only rule.

```sh
backend/.venv/bin/python scripts/verify_orchestrate_context.py \
  --env-file backend/.env --bundle-dir .local/orchestrate-context-probe \
  --agent-id '<actual-probe-uuid>' --target draft \
  --live --confirm-synthetic-test --report .local/context-draft.json
```

The script checks the exact requested Draft agent/environment UUID and selected cloud name/model/tool/context configuration, plus the approved gateway's health, private-route absence and unauthenticated denial. A cloud agent can have an internal `name` slug and a human-facing `display_name`; either must exactly match the reviewed manifest name, and neither substitutes for the UUID check. It creates two disposable, visibly synthetic profiles in the existing database with `example.invalid` emails, disabled notifications and unusable passwords. Each gets an independent signed server context and a separate cloud thread. The profile UUIDs never enter the prompt. Both an actual assistant JSON response identifying the owned profile and exactly one corresponding backend audit are required, with no audit for the other principal. Reports additionally require two distinct verified assistant threads. Temporary sessions, audit rows, profiles and accounts are removed afterward. The script performs no migrations, mailbox authorization, email send, calendar write or application submission. A failure never enables product routing. If cleanup itself fails because an unexpected related record exists, inspect synthetic records privately; the script deliberately refuses broad deletion.

A passing Draft report permits publishing **only the isolated one-tool probe**, with the product gate still false:

```sh
.local/orchestrate-adk/bin/python scripts/orchestrate_setup.py \
  --env-file backend/.env --bundle-dir .local/orchestrate-context-probe \
  --environment-name staytus-authoring \
  --apply deploy --confirm-cloud-changes --confirm-context-tested \
  --context-test-report .local/context-draft.json
```

Configure the corresponding `live` backend connection first. Then repeat the synthetic test with `--target live --report .local/context-live.json`. This selects the actual published version and uses the application's existing Chat Completions transport, outside the product route. The test never sets `ORCHESTRATE_CONTEXT_VERIFIED`.

After the Live probe passes, a reviewed full Agent bundle with the same model and unchanged bridge assets can be imported/deployed using `--context-test-report .local/context-live.json`. Reports expire after 24 hours and are bound to the tenant, HTTPS callback, signing/service configuration, model, agent identity and hashes of the tested bundle. Changing Python wrappers, requirements, connections or secrets requires repeating the test. A report file is local operator evidence, not an attestation from IBM; review its provenance rather than accepting a supplied report from an untrusted source.

Finally repeat `--target live` against the **full bundle and full published Agent UUID**, using a new report path. Review that result before enabling `ORCHESTRATE_CONTEXT_VERIFIED` yourself. A profile-tool pass verifies authenticated forwarding and isolation; it does not certify all 13 business operations, OAuth permissions or policy accuracy. Those keep their own integration checks. No script automatically changes the product flag.

The script uses a small version-pinned launcher adapter to keep ADK config and IAM-token cache under `.local/orchestrate-cli` with private file permissions. It never changes `HOME`, edits installed SDK files or prints the raw API key in a subprocess argument. The official CLI normally initializes `~/.config/orchestrate`; one initial help check created an empty default file, without credentials. The project launcher avoids subsequent writes there. SDK authentication cache contains a short-lived IAM token/expiry, not the original API key.

## Bounded Live business-tool verification

`scripts/verify_orchestrate_tools.py` defaults to offline instructions. Actual requests require the reviewed existing main-Agent UUID, an explicit env file, `--live` and `--confirm-synthetic-test`:

```sh
backend/.venv/bin/python scripts/verify_orchestrate_tools.py \
  --env-file backend/.env --bundle-dir .local/orchestrate-prepared \
  --agent-id '<actual-existing-main-agent-uuid>' \
  --live --confirm-synthetic-test \
  --report .local/orchestrate-business-tools-result.json
```

The fixed full suite makes at most 4 model requests: eight read/planning/handoff tools; three proposal tools; explicit mailbox permission denial; and a second-account profile → policy → planning date → calendar-preview sequence. All 4 cases passed with 13 unique tools/17 invocations. Actual assistant tool traces, non-fixture policy provenance, deterministic internal planning dates, owned notifications/tasks, exact unexecuted proposal rows and backend audits are checked; another account must remain untouched. An inert synthetic mailbox placeholder is introduced only for the denial case, without usable tokens or any provider access. Cleanup deletes only invocation-owned records. Private report paths are operator evidence and contain no raw context or credentials.

After a changed proposal contract, `--case proposal_tools` permits one independent request with a separate report. That recheck passed in `.local/orchestrate-business-proposals-bound-target.json`, with 4 tool calls including the optional profile read. Proposal semantics now compare normalized business fields separately from the server-owned `_connector_target`, while checking the full payload hash, displayed target and profile version. A missing email connection binds explicit null identity fields; later connecting/relinking cannot silently change that target. Export calendars have no remote target. Client/model-supplied target bindings are rejected. Final approval/execution stays outside the Agent tool surface.

These results establish tool integration using synthetic accounts, not exhaustive policy accuracy or real provider consent. Google/Microsoft client IDs/secrets are still absent; Google console MFA requires the user and a Microsoft portal attempt timed out. Real OAuth reads, provider draft/calendar writes and SMTP delivery still need their own authorized tests. Reminder worker/UI/outbox/SMTP code exists, but email is off by default and real SMTP is not configured or used. In-app popups need an open page; there is no native OS/background push. Penn portal integration and public app deployment remain deferred.

## Narrow callback server, separate from the private app

`backend/app/tool_gateway.py` provides a separate ASGI app containing only `/health` and the authenticated `/tools/*` operations. It has no login/profile/approval execution/email connection routes, docs, OpenAPI endpoint, CORS browser interface, schema migration or policy worker.

Start the ordinary application first so its database schema and account records exist. Then, from `backend/`, the separate gateway can be started on loopback:

```sh
.venv/bin/python -m uvicorn app.tool_gateway:app \
  --host 127.0.0.1 --port 8001 --no-access-log
```

Both processes must run from the same backend directory and use the same explicitly configured database, `ORCHESTRATE_TOOL_KEY` and `CONTEXT_SECRET`. Gateway startup refuses missing/short/shared secrets and refuses a mismatch with the effective application settings; it does not accept the app's generated fallback as an explicit signing configuration. Each secret must be independently random and at least 32 characters.

An eventual approved HTTPS deployment/tunnel should terminate at this narrow server, not the ordinary app's3000/8000ports. No public listener, tunnel, DNS or cloud resource was started by adding this app. Publication or new persistent access remains a separate decision. The backend connection URL must use the approved HTTPS base host for this gateway.

Local TestClient verification covers exact-route absence404, missing/wrong service authentication401, missing/tampered signed context401, a valid own-profile response, identity-spoofing422, strong explicit startup settings and no-store/correlation headers. It does not establish public network reachability or cloud-to-gateway integration.

## Exact official CLI equivalents

These command shapes were verified from installed2.19.1source/help. They are reference commands, not an executed deployment:

```sh
orchestrate env add --name staytus-cloud --url '<exact-service-instance-url>'
orchestrate env activate staytus-cloud
orchestrate connections import --file orchestrate/connections.yaml
orchestrate tools import --kind python --file orchestrate/python_tools.py \
  --requirements-file orchestrate/requirements.txt --app-id staytus_backend --safe
orchestrate agents import --file '<prepared-agent.yaml>' --safe
orchestrate agents deploy --name '<prepared-agent-internal-name>'
```

Use the SDK/script secure credential path or tenant connection UI for connection key values. Avoid putting the backend tool key directly on a shell command line. Draft preview uses draft connections; deployed Agents need complete live bindings. Publishing a draft and verifying HTTP request construction do not prove tool reachability or user isolation.

Primary references: [official package](https://pypi.org/project/ibm-watsonx-orchestrate/2.19.1/), [IBM ADK development](https://developer.ibm.com/learningpaths/get-started-watsonx-orchestrate/develop-agents-adk/), [connection bindings](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=credentials-binding-deploying-connections), [deployment](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=agents-deploying), [Runs API](https://developer.watson-orchestrate.ibm.com/apis/orchestrate-agent/chat-with-orchestrate-assistant), [context variables and Python-tool access](https://developer.watson-orchestrate.ibm.com/conversation/context_variables), [official OpenAPI](https://developer.watson-orchestrate.ibm.com/apis/server_openapi.json).

# Connect Staytus to watsonx Orchestrate

Product chat uses the custom Staytus UI and backend REST client. The previous widget/JWT implementation is archived and is no longer mounted. The backend never supplies keyword/demo answers when IBM is unavailable.

## Actual tenant state — November 1

A Staytus **draft** was created in the existing Toronto tenant, ID `271c9439-fb87-4c86-88cd-b2e5919833e9`. Name, description and behavioral instructions were entered. Tools have not been imported, a version has not been deployed, and no real request from the local application has passed. The tenant's model selector is administrator-locked to `groq/openai/gpt-oss-120b`; the UI displays a third-party license notice. Creating a draft is not a completed integration.

IBM Cloud Manage displayed “您无权查看凭证”; its service-credentials tab subsequently showed an empty list and an enabled Create credential form. A `staytus-local-runtime` / `WO User` form was prepared but not submitted pending explicit permission to create persistent service access. Do not infer credential-creation permission solely from an enabled button.

## Protocol verified against primary sources

- Cloud endpoint: exact service-instance URL + `/v1/orchestrate/{agent_id}/chat/completions`.
- Body: `messages`, `stream:false`, separate `context` dictionary.
- Subsequent turns: `X-IBM-THREAD-ID` header, using the returned `thread_id` stored by our backend.
- Resend context every turn. Put signed `staytus_context` only in run context, never model messages or an LLM-supplied argument.
- Python tools read `AgentRun.request_context.get('staytus_context')`. The wrapper passes that capability plus the independent service key to the backend, which resolves the actual signed-in account.

These facts are supported by the [official OpenAPI](https://developer.watson-orchestrate.ibm.com/apis/server_openapi.json), [context documentation](https://developer.watson-orchestrate.ibm.com/conversation/context_variables), and inspected official ADK2.19.1 source. Tenant-specific context propagation and callback authentication still require a live test.

## Connection steps

1. Obtain an authorized service API key and the exact service-instance URL. Store only on the backend in `.env`. Never copy the dashboard host as an inference URL or infer a tenant URL from a CRN.
2. Deploy the backend to an authorized HTTPS host reachable by IBM. Localhost cannot receive calls from the cloud agent. Do not expose a development server or its database without a deliberate deployment decision.
3. Create `staytus_backend` key-value connection with `backend_url` (base host, without `/tools`) and `tool_key`. The short-lived user capability is not a static connection credential.
4. In an isolated authorized ADK environment, check the installed version and `orchestrate tools import --help`; import `python_tools.py` with `requirements.txt` bound to that connection. The 12 operation names match `tools/openapi.yaml`.
5. Choose the actual available model in the agent YAML, import/attach tools and declare `staytus_context` as runtime context. Do not interpolate the capability in agent instructions. Keep final approval/execute/admin operations outside the exported tool set.
6. Test in Draft: valid service authentication without user context must fail; a valid signed user context must return only that account's profile. Test two separate accounts, expired/tampered context, and identity-spoofing text. Never log capability values.
7. Deploy a tested version and copy its actual agent UUID/environment. Set `ORCHESTRATE_SERVICE_URL`, `ORCHESTRATE_AGENT_ID`, `ORCHESTRATE_API_KEY` (or short-lived server-only bearer), and only after verification `ORCHESTRATE_CONTEXT_VERIFIED=true`.
8. Start the local app and complete one browser question → IBM model → authenticated tool → cited answer/proposal. Approve a local calendar export in Staytus, inspect its receipt, then test a consenting mailbox separately.

## Model roles

Orchestrate runs the deployed conversational agent using its selected model. It does not require every student to paste a model API key. `watsonx.ai` credentials are separate and optional here: they generate policy embeddings (and provide a classification client). They do not replace the agent runtime when Orchestrate fails.

## Verification

```sh
cd backend
.venv/bin/python -m pytest -q tests/test_orchestrate_runtime.py tests/test_chat.py
.venv/bin/python ../scripts/export_openapi_3_0.py --check
```

MockTransport tests check real request construction, IAM expiry/401 refresh, account-owned threads, per-turn context and safe failure behavior. They do not establish a live IBM connection. Record successful live tests and safe receipts in `CHANGELOG.md` and the current verification document.

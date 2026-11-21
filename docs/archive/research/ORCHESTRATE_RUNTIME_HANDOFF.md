# Orchestrate runtime handoff — November 1

Implementation author: Codex. Bob Agent was attempted with a bounded task but did not produce verified application code. See the actual attempts in `bob_sessions/`.

## Verified protocol

- Official OpenAPI: https://developer.watson-orchestrate.ibm.com/apis/server_openapi.json
- Context contract: https://developer.watson-orchestrate.ibm.com/conversation/context_variables
- Source inspection: official ADK and client wheels2.19.1, downloaded without installation/execution.

Cloud service instance URL appends `/v1/orchestrate/{agent_id}/chat/completions`. Requests have messages, `stream:false`, separate context; thread reuse is `X-IBM-THREAD-ID`. Replies contain choices and `thread_id`. Context must be resent each turn. ADK `AgentRun.request_context.get` reads the runtime value; model prompt interpolation is not used for the signed capability.

The misleading Cloud `/api/v1` generalization in an earlier runtime reference is not used. We followed the actual Cloud OpenAPI and client base URL construction.

## Implemented and tested

`OrchestrateRuntime` validates instance URL/UUIDs, keeps provider credentials server-side, caches IAM tokens with expiry margin, refreshes once on an authentication401, and does not retry uncertain timeouts,429or5xx. Errors exclude response bodies/credentials. Chat route owns conversation/thread identity and resends a signed session capability.

The focused tests include a real adapter + authenticated chat route over MockTransport, two-turn reuse and validation of the signed capability against the backend tool gateway. This is transport/integration code verification, not a live IBM service test.

## Still not verified live

Actual API-key permission, deployed Agent version, callback connection, cloud-to-backend HTTPS reachability, model/license use, per-user context propagation and cross-account isolation. The created Staytus draft has no attached tools or deployed version yet. `ORCHESTRATE_CONTEXT_VERIFIED` remains false until those tests pass.

Run the offline readiness script from backend:

```sh
.venv/bin/python ../scripts/check_ibm_connection.py
```

`--live` intentionally requires a deliberate explicit flag; it performs one generic no-student-data request and does not prove personalized tool access. It was not run during this turn.

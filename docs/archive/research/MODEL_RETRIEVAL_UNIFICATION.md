# Model and retrieval integration — November 1, 2026

This batch is Codex implementation. No real watsonx.ai credential, model or student record was used by these tests. Live account/project configuration is a separate step.

## One retrieval entry point

`retrieval.retrieve_for_profile()` is shared by chat grounding, the policy API and Orchestrate's policy-search tool. It obtains the same optional embedding client and always filters by the server-owned profile's school/status. Each returned item reports keyword, hybrid or an explicit embedding-unavailable fallback; reviewed/effective state is separate.

Chinese keyword text no longer degenerates into an unrelated full-corpus result. Cross-language semantic retrieval still requires a suitable selected embedding model and an indexed corpus.

## Independent model capabilities

`policy_pipeline.optional_policy_models()` allows an embedding model, generation model or both. Retrieval requests only embedding capability. Source capture can compare changed text with a generation-only configuration; it no longer incorrectly depends on an embedding-model selection. First captures have no previous text to compare. Model suggestions remain pending review and do not activate legal rules.

Server model defaults are blank. Example IDs are not asserted to be region/project-entitled. `WATSONX_API_VERSION` is now actually used by the client.

## Provider transport and discovery

The watsonx.ai client validates the HTTPS IBM regional host and API version, uses bounded requests, caches IAM tokens across client instances and refreshes once on401. It does not blindly retry timeouts, redirects,429or5xx. Errors and readiness output exclude credentials/project IDs. `WatsonxConfig` hides its API key in repr.

Discovery reads the real regional `/ml/v1/foundation_model_specs` catalog with `function_embedding` or `function_text_generation` filters. Multilingual recommendations use returned language/label/description metadata, not guessed IDs. Catalog presence does not prove inference permission. Lifecycle metadata is included for inspection; operators must review it before selecting a model.

Primary documentation:

- https://cloud.ibm.com/docs/apis/watsonx-ai
- https://www.ibm.com/docs/en/watsonx/saas?topic=generation-text-embeddings
- https://ibm.github.io/watsonx-ai-python-sdk/

## Operator commands

Run from `backend/` after configuring the correct region/project credential on the server:

```sh
.venv/bin/python ../scripts/check_watsonx_connection.py
.venv/bin/python ../scripts/check_watsonx_connection.py --catalog
```

The first command is offline; the second authenticates and reads model metadata without inference. Select actual model IDs in `.env`; discovery does not modify settings automatically.

An explicit quota-using probe is:

```sh
.venv/bin/python ../scripts/check_watsonx_connection.py --live
```

It embeds three fixed English/Chinese public test sentences and reports whether the related cross-language pair ranks above an unrelated pair. It also checks a structured generation response to a simple office-hours text change. This is a small relevance/format smoke check, not a general quality benchmark or legal evaluation. No student profile, mailbox or signed capability is sent.

Connectivity flags remain separate from `multilingual_probe_passed` and `quality_probe_passed`. A successful model request with inverted, tied or unrelated embeddings still reports successful connectivity, but fails the quality sanity gate. The explicit `--live` command then returns nonzero; it cannot silently report overall success merely because HTTP requests succeeded.

To embed saved official snapshots without fetching the websites again:

```sh
.venv/bin/python ../scripts/reindex_policy_embeddings.py
.venv/bin/python ../scripts/reindex_policy_embeddings.py --run
```

Default reports offline state. `--run` makes real model calls on the saved public corpus and updates chunk vectors/model/dimension. It preserves source capture time, policy version/review status and legal rules. Actual document/query embeddings must use the same selected model.

## Verification

Focused verification:56 tests passed across unification, original integration, chat and policy pipeline suites. A full backend run passed191 tests before the last reindex case was added; the root task performs final combined validation after parallel work. Ruff F checks passed.

Tests use MockTransport and isolate model configuration so a developer's real `.env` cannot accidentally trigger quota-using model requests in the normal fixture-based suite. Real regional catalog, entitlement, embedding quality and generation behavior must still be tested with authorized service configuration.

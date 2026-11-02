# Public policy capture and retrieval

`config/sources.yaml` is the runtime allowlist. `sync_source_registry()` upserts it at startup and before a refresh; it does not seed policy summaries or student accounts. `config/schools/penn.yaml` supplies Penn directory links and explicitly internal planning buffers.

The capture path is:

```text
registered source -> robots check -> bounded HTTPS fetch -> normalized text/hash
  -> immutable pending PolicyVersion -> overlapping PolicyChunks -> optional IBM embeddings
  -> versioned source citations -> profile-relevant in-app source-change notification
```

Capture accepts no model- or browser-provided URL. Every redirect and resolved destination must remain on registered public HTTPS hosts. Cross-origin redirects require a separate registry entry. Requests have connect/read limits, a wall-clock budget, byte limits and redirect limits. A robots disallow, explicit restriction, access block or transport failure remains visible in the fetch log; a block is not bypassed. These DNS checks are defense in depth for a fixed administrator-owned allowlist, rather than a general-purpose arbitrary-URL crawler.

`PolicySnapshot` records final URL, capture time, HTTP status, embedding model/dimension and index status. `SourceCapture` records each source's latest attempt, successful fetch, error, robots state, chunk count and freshness. Fresh retrieval time does not certify that a policy is legally effective. All new captures are `detected_pending_review`, never auto-activated `RuleVersion` records. Historical snapshots and reviewed evidence remain available.

`search_snapshots()` is the single retrieval implementation used by the app and agent tools. It searches real chunks, returns version/capture/citation metadata, excludes fixtures in the product and applies status/school filters. `include_pending=True` allows informational raw snapshots; the default agent-tool search returns reviewed `current_effective` evidence only. Agent instructions should explicitly request pending snapshots when answering informational source questions and disclose their review status. The exact-version tool can resolve historical citations.

When `WATSONX_URL`, `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` and `WATSONX_EMBEDDING_MODEL` are configured, the server requests embeddings. Model/dimension are persisted; only matching vectors participate in cosine ranking. Without credentials, or on a provider failure, real source captures and keyword retrieval still work and report their mode. A later capture can add embeddings to unchanged content without replacing its citation IDs. Classification is advisory and cannot publish a rule. The HTML extractor prioritizes main/article content and excludes site navigation, global headers, footers and executable text. Ranking currently runs in process over this small corpus; database-native vector indexing and more dedicated per-site parsers remain future scaling work.

Authenticated endpoints:

- `GET /api/v1/sources`: public-source operational status, with no credentials or private student data.
- `POST /api/v1/policies/refresh`: `{}` or `{"source_id":"penn-isss"}`; no arbitrary URL. Manual requests have account and source cooldowns, and a three-source batch bound. The response identifies errors and deferred sources.

The API lifespan can run the polling worker. The worker checks per-source intervals from YAML; notification preference `off`, visa category and school determine subscription relevance. Initial capture and unchanged content create no source-change notification. Notifications say that a source changed and awaits review; they do not claim that a student's legal deadline changed. Delivery here is in-app; OAuth email/calendar actions are separate integrations.

From `backend/`:

```sh
.venv/bin/python ../scripts/ingest_sources.py --force
.venv/bin/python ../scripts/ingest_sources.py --source penn-isss
.venv/bin/python ../scripts/policy_worker.py --once
```

`--force` is a maintainer CLI option, not exposed by the user refresh endpoint. The capture CLI exits nonzero if any source fails, while committing successes and descriptive failures. Production should run one polling worker; the current in-process batch lock is not a distributed work queue.

Live verification on 2026-11-02 01:01 UTC populated the current local `staytus-app.db`: USCIS Students and Exchange Visitors (5 chunks), DHS Study in the States (4), and DOS BridgeUSA Current Participants (2). All are genuine pending snapshots in keyword mode. The three Penn URLs returned HTTP 403; their failure states are stored and displayed. No blocked Penn page was fabricated or treated as current evidence.

After improving main/article extraction, a full recapture at 01:05–01:06 UTC stored cleaner v2 baselines: USCIS (2 chunks), DHS (2), DOS (1). Earlier captures remain historical. This new normalization baseline does not establish that immigration policy changed.

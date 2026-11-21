# Public policy capture and retrieval

## Registered sources

[config/sources.yaml](../config/sources.yaml) is the runtime allowlist. It contains 23 public pages, all enabled for scheduled capture in the checked-in configuration. Each entry records the URL, allowed hosts, authority, applicable categories, polling interval, and freshness threshold. `sync_source_registry()` loads the registry on startup and before capture.

| Publisher | Registered pages | Coverage |
| --- | ---: | --- |
| Penn International Student and Scholar Services (ISSS) | 13 | Travel and reentry, OPT and STEM OPT, program extensions, processing times, I-94, policy updates, and academic training or scholar procedures. |
| U.S. Citizenship and Immigration Services (USCIS) | 4 | Students and exchange visitors, OPT, STEM OPT, and student employment. |
| U.S. Department of Homeland Security, Study in the States | 2 | General F-1 information and maintaining student status. |
| U.S. Department of State, BridgeUSA | 4 | Current J-1 participants, extensions, college and university students, and research scholars. |

[Penn's school configuration](../config/schools/penn.yaml) links each planning workflow to relevant sources and defines internal preparation buffers. It also provides the iPenn portal link for users to follow. Private student records and university submissions require separate institutional authorization. Synthetic fixtures are labeled and excluded from product retrieval.

## Capture and review

1. The capture worker checks the registered URL and robots policy before making a bounded HTTPS request. Redirects and resolved destinations must satisfy the registered public-host restrictions. When access fails or is restricted, Staytus records the result and leaves it visible in **Official source checks**.
2. The parser extracts the main page text and normalizes it for comparison. The first capture or a changed text hash creates a new `PolicyVersion` with status `detected_pending_review`. The system retains historical snapshots, splits captured text into overlapping chunks, and adds watsonx.ai embeddings when configured.
3. `PolicySnapshot` records the source URL, capture time, HTTP status, and indexing metadata. `SourceCapture` tracks the last attempt, last successful capture, freshness, and errors. **Policy Updates** can surface a change to users whose school, status category, and preferences make it relevant.
4. A capture or optional model classification supplies evidence for review. Before applying a rule, the reviewer checks the issuing authority, effective date, legal status, and applicability. Capture freshness describes when the page was retrieved. Rule activation is a separate step.

When adding a source, record the exact page and publisher, check permitted use and robots rules, and choose a capture schedule and freshness threshold. Keep version and citation information so readers can trace guidance back to the source. Use **Official source checks** in the app for capture outcomes, which can change between runs.

## Retrieval and citations

`search_snapshots()` is shared by the application and Agent tools. It filters results by school and status category, then combines keyword scores and cosine similarity when the stored and query embeddings match. If embeddings are unavailable, the retrieval response identifies the keyword mode. Ranking runs in the backend process. Citations include the source URL, version, capture time, and review status. Exact-version lookups support historical citations, and a later capture can add embeddings to unchanged content while retaining its citation IDs.

The default policy tool search returns reviewed `current_effective` evidence. Informational searches can explicitly include pending snapshots, which stay labeled as awaiting review. Policy excerpts and account-owned profile data enter the assistant's context separately.

## Scheduling and maintenance

The checked-in [Vercel configuration](../vercel.json) schedules a daily job for each enabled source. The production handler authenticates the scheduler and uses a PostgreSQL transaction lock to prevent concurrent execution of the same job. Local deployments can use the polling worker, which uses each source's configured interval.

- `GET /api/v1/sources` returns capture, freshness, and review status to signed-in users.
- `POST /api/v1/policies/refresh` refreshes registered sources, optionally scoped by `source_id`. The endpoint applies cooldowns and processes up to 3 sources per request.

Run these maintenance commands from `backend/`:

```sh
uv run python ../scripts/ingest_sources.py --source penn-isss
uv run python ../scripts/ingest_sources.py --force
uv run python ../scripts/policy_worker.py --once
```

`--force` is a maintainer CLI option. Failures are recorded with successful captures, and the capture CLI returns a nonzero exit status if any source fails. See the [verification guide](VERIFICATION.md) and [full changelog](CHANGELOG_FULL.md) for checks and dated results.

# Vercel production operations

Current URL: **https://mystaytus.vercel.app**. Existing project `staytus`, Hobby, team `felixyuzhenyangs-projects`. This is the active deployment target; Code Engine remains unavailable under the course account's current project-creation permission.

## Runtime boundary

- `web`: Next.js, including same-origin `/api/backend/*` BFF and server-side session cookie handling.
- `api`: private FastAPI service reached by the web service binding, sharing the existing limited Supabase PostgreSQL role.
- `gateway`: health plus `/tools/*`, requiring both the independent tool key and a short-lived signed user context.
- `/internal/jobs/*`: 26 daily jobs protected by the separate production cron secret, including proactive assistant generation. PostgreSQL transaction advisory locks prevent concurrent duplicate runs. Application state/outcomes provide durable deduplication where supported; a lock is not a guarantee against every sequential repeat.

`vercel.json` routes the three services. Both Python entrypoints load public configuration and relocate a packaged public trust bundle while retaining `sslmode=verify-full`. They do not run migrations or background threads. Connections use NullPool rather than retaining a connection per warm function. The Supabase Data API remains disabled; user access remains through backend ownership checks.

Vercel Hobby cron jobs run daily and may vary by up to an hour. This deployment does not provide minute-level alerts or native background push. Source/reminder/mail work no longer requires the developer computer to remain awake. Real mailbox reads still require separate consent; SMTP/send remains off. Free quotas, Supabase availability and existing IBM service entitlements remain dependencies.

## Updating the code

The domain is reused for later deployments; no domain registration is needed for a feature update. The current deployment came from an allowlisted local source stage, not a GitHub integration. No commit or push was created as part of publication.

1. Change and inspect the repository code; run `make test && make build`.
2. Prepare a fresh stage with `backend/.venv/bin/python scripts/prepare_vercel_settings.py`. Inspect `.local/vercel/deployment-review.json` and the source manifest. The stage excludes private env/database/Bob artifacts; never deploy the complete raw workspace.
3. This preparation deliberately resets the context gate in the private Production values to false. Upload only approved runtime values with `backend/.venv/bin/python scripts/vercel_operator.py upload-env --confirm-production-release`, then deploy the stage with its `deploy` action. Owner and Writer keys must never enter Vercel runtime secrets or source.
4. Verify public health/denial boundaries and the existing IBM callback binding. For gateway/identity/context changes, run the controlled two-account Live probe and review the matching evidence before enabling `ORCHESTRATE_CONTEXT_VERIFIED`. A change to a Vercel environment variable requires another deployment to take effect. Do not invent a passed report or enable chat merely because a build succeeded.
5. Exercise the public BFF workflow with `scripts/verify_public_deployment.py --live --confirm-synthetic-test`; it uses fictional accounts and exact-row cleanup. With `--keep-ui-fixture`, perform visual QA, sign out, then run `--cleanup-fixture` with the same live confirmation flags. Keep reports/screenshots private and log the actual result in `CHANGELOG.md`.

The operator CLI is `.local/vercel-cli/node_modules/.bin/vercel`. Credentials are passed on stdin; private operator output is0600 under `.local/vercel`. Do not print environment values or use them in command-line arguments. Existing production variables contain only runtime configuration; migrations remain explicit, separately authorized owner operations. Review schema compatibility before a release; rolling back application code does not roll back database migrations.

## Remaining release work

Google's public callback, APIs, minimum scopes and test user are configured. Personal Gmail/Calendar grants, an actual inbox check and a read-only primary Calendar API200 probe passed; actual approved event creation remains untested. Google remains External/Testing and has not completed public/restricted-scope verification. Daily mailbox monitoring and assistant-preview sharing remain off. Microsoft credentials are absent; actual iCloud authorization is pending. Verified email, password recovery, shared login-rate limits, privacy/retention operations, operational monitoring and broader answer-quality evaluation remain before broad public use. Penn private-portal access and school-application submission remain unimplemented.

November3 actual verification: public two-account onboarding/hybrid retrieval/IBM chat and cross-account denial; browser Chinese chat with a matching tool audit; 25 enabled daily cron definitions and three successful authenticated job dispatches; Live tool calls after local tunnel shutdown. See `../../docs/VERIFICATION.md` for the evidence boundaries.

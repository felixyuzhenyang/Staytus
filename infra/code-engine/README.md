# IBM Cloud deployment handoff

> Current active deployment: https://mystaytus.vercel.app on Vercel Hobby. See [Vercel operations](../vercel/README.md). The Code Engine access findings and steps below remain historical/alternative-platform guidance.

Supabase PostgreSQL/TLS, migration, application-archive restore and independent API/gateway cloud verification now pass. See `docs/DATABASE_AND_CONTAINERS.md`. Web/API/gateway compute remains local; no public application deployment was performed.

## Current account blocker (2026-11-03)

The user authorized only a free empty Code Engine project: `staytus`, Washington DC (`us-east`), resource group `Default`, in the existing course account. Submission failed with transaction `codeengine-ui-a41db41e`; a refreshed list still showed no projects. Captured console details show an inner HTTP502 `internal` error (100010), with an outer UI wrapper status400, at `2026-11-03T18:49:37.128Z`. The transaction identifier alone does not diagnose the cause.

Read-only IAM inspection found no direct user policies. The course access group grants Code Engine **platform Viewer + service Manager**, and Default resource-group Viewer; the Public Access group has no listed policies. The inspected Code Engine action list does not grant `resource-controller.instance.create`. [IBM's Code Engine IAM table](https://cloud.ibm.com/docs/codeengine?topic=codeengine-iam) distinguishes project creation (platform Editor/Administrator) from managing project contents (service Manager/Writer). The course Guide also says needed instances are preprovisioned and users cannot create new instances. A missing project-creation permission is confirmed; it is not proof that the observed502 was an IAM403.

Repair through the course account administrator: preferably have them create the empty project, then use the existing service Manager permission for approved work inside it. Alternatively, if course rules allow, request a platform Editor grant scoped to Code Engine and the intended resource group. Do not request global Administrator or repurpose the watsonx.ai API key. If an adequately authorized administrator still sees the error, give IBM support the transaction identifier, UTC time, region and resource group for backend investigation. Application/build spending and public exposure still require their own configuration/cost review. Nothing has been publicly deployed.

## Deployment steps after access is resolved

1. Run backend tests and the OpenAPI contract check.
2. From the repository root build `docker build -f backend/Dockerfile -t staytus-backend .` and `docker build -f frontend/Dockerfile -t staytus-frontend .`. Root build context is required for `config/`; private files are excluded by an allowlist. Actual image builds still require Docker/CI or an authorized Code Engine source build.
3. Push the image to a registry you are authorized to use.
4. Reuse the configured Supabase Free PostgreSQL, separate migration/runtime roles and `sslmode=verify-full`. Mount its trusted CA bundle and replace the developer-machine certificate path in the connection URL. Keep Data API disabled and database credentials server-only. A cloud gateway must share this database rather than a separate SQLite/local snapshot. No IBM paid database is assumed.
5. Run an explicit migration Job from the backend image with argument `migrate` and the migration-owner URL. Set `DATABASE_RUNTIME_ROLE` for explicit runtime grants. Migration configuration does not require runtime/model keys. Enable pgvector only with authorized database privileges. If importing existing records, stop writes, use an empty migrated target, verify the transfer and restore, and retain encryption/signing keys. API/gateway startup will not run DDL.
6. Configure secrets as environment references, not Docker build arguments. Copy the complete backend environment schema, not frontend public variables.
7. Create API and gateway applications from the same image with arguments `api` and `gateway`; set target `PORT`. Both share the limited-runtime database URL plus explicit context/tool/token secrets. Use production configuration templates and disable lifespan workers until independent scheduling is configured. Start with a controlled test deployment; production identity, provider verification and operations remain required before broad release.
8. Export/import the Orchestrate tools, set the backend HTTPS server URL and configure service credentials. Validate user-context forwarding before enabling personalized tools.
9. Deploy the frontend separately; set server-only BACKEND_URL to the backend URL.
10. Test from a clean browser, including cross-user isolation and approval expiry.

Do not create resources, API keys or billable services automatically. Supabase database hosting is configured; Code Engine/public application deployment still needs its own authorization, cost and readiness checks.

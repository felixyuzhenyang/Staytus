# Staytus web app

Next.js App Router, React, and TypeScript. The product uses real account registration, profile onboarding, and a single assistant connected through the backend to IBM watsonx Orchestrate. An unavailable integration is reported as unavailable; there is no deterministic chat fallback.

```sh
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The FastAPI backend defaults to `http://127.0.0.1:8000`; override `BACKEND_URL` in `.env.local` if needed. No IBM or email provider secrets belong in `NEXT_PUBLIC_*` variables.

## Structure

- `app/page.tsx`: session restoration, sign-in, onboarding, and workspace gates.
- `hooks/useSession.ts`: account session lifecycle and sign-out.
- `hooks/useWorkspace.ts`: typed API requests, view data, the active conversation, and action approvals. Requests are aborted on navigation or account teardown.
- `components/`: independent screens for the dashboard, chat, policies, approvals, profile, source updates, activity, connections, and reviewer records. Shared shell, forms, dialog, and UI elements live here too.
- `lib/types.ts`: shared API shapes and display helpers.
- `lib/api-client.ts`: fetch wrapper with structured API errors.
- `app/api/backend/[...path]/route.ts`: same-origin API proxy. Keeps the backend session in an HttpOnly cookie, adds authorization server-side, redacts access tokens from registration/login responses, rejects cross-origin mutations, and revokes the session at sign-out.
- `app/globals.css`: Morandi blue and dusty red responsive design system.

## User flow and capabilities

Create an account → enter school/category/program dates → use a personal workspace. Penn is the first school with a procedure adapter; other schools can use public sources without implying access to their private portals. Email is optional and connects through explicit Google/Microsoft OAuth. Provider setup is required before Connect becomes available. Messages remain read only in the current interface. Calendar actions export an approved `.ics` file; they do not imply a live calendar integration.

Chat posts only to the real `/chat` endpoint and displays an integration error if Orchestrate is not configured or fails. Connections is a service status and authorization screen, not a second chat experience. Reviewer navigation appears only when the authenticated server session has the reviewer role; users cannot grant that role to themselves.

The workspace mounts separately for each account. Conversation state, cached responses, approval previews, and requests are cleared with that workspace. Pending responses from an old account cannot populate a new account's screens.

`npm run typecheck` checks TypeScript. `npm run build` verifies the production bundle. Backend tests cover account isolation, policy review, and action approval boundaries.

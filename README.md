# Staytus

[Open the live Staytus application](https://mystaytus.vercel.app/)

Staytus is a RAG-based AI planning assistant for international students and scholars. It brings official immigration guidance together with each user's profile to help them prepare for international travel, work authorization, program extensions, and other status-related milestones. The initial release provides Penn-specific planning for F-1 students and J-1 students and scholars at the University of Pennsylvania. Users at other schools can still browse applicable federal guidance.

The project grew out of our team's experience as international students. Guidance about travel and employment can be spread across university and government websites, and a policy announcement may still require students to determine whether it is effective and relevant to their own plans. Staytus organizes those sources and turns the user's saved dates and application stage into a clearer set of questions, preparation steps, and reminders.

Staytus retrieves relevant passages from selected Penn and U.S. government sources through its RAG pipeline. IBM watsonx Orchestrate runs the conversational assistant, while watsonx.ai provides policy-search embeddings and bounded background summaries. A backend planning harness defines the core workflow steps and calculates preparation dates before validating any contextual additions selected by the model. Vercel hosts the Next.js frontend, FastAPI backend, and authenticated tool gateway. Supabase PostgreSQL stores account, profile, conversation, policy, and reminder data.

## Features

- **Profile, Overview, and personalized planning.** Users save their immigration category, program dates, travel plans, and application stage, then update those details as their circumstances change. The Overview brings together upcoming preparation dates, recent policy changes, and priority checklists based on the saved profile.
- **Policy retrieval and monitoring.** The Policy Library organizes university and government guidance by issuing authority. Staytus checks a defined set of official pages, versions detected changes, and displays each source's freshness, capture status, and review status. Retrieved passages retain links to their original sources.
- **AI assistant and visual timelines.** Users can ask questions in natural language or begin with a guided form for travel, OPT/EAD, extensions, and supported J-1 workflows. Planning responses can include a brief explanation followed by a visual timeline. Each step can be expanded to show how the date was calculated, which information still needs confirmation, and which official sources support the guidance.
- **Proactive updates and reminders.** Relevant policy changes and approaching preparation dates can create private Assistant Updates that remain available when the user returns. Users can also opt in to scheduled email digests and choose their preferred notification frequency.
- **Email and calendar connections.** With separate user permission, Staytus can monitor a connected Gmail inbox for relevant notices and use watsonx.ai to summarize matching messages. Users can export reminders as `.ics` files or review a proposed connected-calendar event before approving it. Integration availability and provider requirements are documented separately.

Personalized tools resolve the account from the signed-in session, and connected services require the user's corresponding authorization. Staytus asks for final approval before writing a calendar event. Its timelines and checklists provide planning support, while official deadlines and individual eligibility still need confirmation from the relevant university or government authority.

See [Features and integration availability](FEATURES.md) and the [policy pipeline](docs/POLICY_PIPELINE.md) for details.

## Repository structure

| Path | Purpose |
| --- | --- |
| `frontend/` | Next.js web interface and API proxy |
| `backend/` | FastAPI services, policy retrieval, planning rules, and tests |
| `config/` | Official-source registry and school settings |
| `orchestrate/` | IBM agent configuration and tool definitions |
| `infra/` | Vercel deployment and database setup |
| `scripts/` | Development, validation, and maintenance commands |
| `docs/` | Architecture, setup guides, and project history |
| `bob_sessions/` | IBM Bob course-evidence guidance and approved summary artifacts |

See the [architecture guide](docs/ARCHITECTURE.md), [release milestones](CHANGELOG.md), and [full changelog](docs/CHANGELOG_FULL.md).

## Local development

The public link above is the normal entry point for users. This section is for contributors who want to run the source code locally, inspect the implementation, or develop a change. Local development requires Node.js 20.9 or later, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/).

Run these commands from the repository root:

```sh
test -f backend/.env || cp backend/.env.example backend/.env
make install
make migrate
make dev
```

The first command creates a local development configuration when one does not already exist. `make install` installs the frontend and backend dependencies, `make migrate` prepares the local database schema, and `make dev` starts the application services. A fresh local configuration uses SQLite, so contributors can inspect the basic account, profile, policy, and interface flows without connecting to the production database.

Open [the local application](http://127.0.0.1:3000). FastAPI documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). IBM, Google, Microsoft, Brevo, Supabase, and production deployment features require their own developer configuration and credentials. Those credentials are intentionally absent from the repository. See the [database and container guide](docs/DATABASE_AND_CONTAINERS.md), [Orchestrate setup](docs/ORCHESTRATE_SETUP.md), and [email connections guide](docs/EMAIL_CONNECTIONS.md) when working on those integrations.

Before submitting a code change, run:

```sh
make test
make build
```

`make test` runs the backend tests, frontend type checking, and the OpenAPI tool-contract check. `make build` creates the Next.js production bundle. These checks cover the repository code and contracts. Live provider access is verified separately because it depends on configured external accounts. See the [verification guide](docs/VERIFICATION.md) and [Vercel operations guide](infra/vercel/README.md).

## IBM Bob usage

We used IBM Bob's Plan mode to compare architecture proposals and clarify how the web application, backend, and Orchestrate agent should divide responsibilities. We also used Agent mode for targeted code reviews and selected changes to the Orchestrate tool-chain and workspace interface. Proposed edits were reviewed and tested before integration.

The [Bob sessions guide](bob_sessions/README.md) explains which course evidence may be included in the repository. Detailed prompts, conversations, diffs, and recordings are kept in the local `bob_sessions/` folder and excluded from Git. Only the course-required team-member consumption-summary images are intended for the tracked evidence folder.

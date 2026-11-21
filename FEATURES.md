# Staytus features

Penn-specific planning supports F-1 students, J-1 students, and J-1 scholars. Users at other schools can access applicable federal sources.

| Area | What Staytus supports | Availability and limits |
| --- | --- | --- |
| Account and Overview | Sign-in, editable profiles, upcoming preparation dates, relevant checklists, and policy updates. | Verified-email sign-up and password recovery remain pending. |
| My Assistant | watsonx Orchestrate chat, saved conversations, New chat, and planning shortcuts for travel, OPT/EAD, extensions, and J-1 workflows. | The checked-in [tool contract](orchestrate/tools/openapi.yaml) defines 14 operations. Personalized tools are scoped to the signed-in account. |
| Planning timelines | Guided forms and chat produce visual timelines with expandable date explanations and citations. The backend defines the core steps and allows up to 3 validated contextual additions. Missing facts are marked **To confirm**. | Preparation targets help users plan. Official deadlines and individual eligibility require confirmation from the appropriate authority. |
| Policy Library and Policy Updates | The [source registry](config/sources.yaml) lists 23 public pages. Staytus captures and versions source text, uses keyword and vector retrieval, and shows citations, freshness, and review status. | Each new snapshot starts pending review. See **Official source checks** in the app for the latest capture results. |
| Proactive updates and reminders | Relevant changes and upcoming preparation dates can generate private Assistant Updates and in-app reminders. Users can opt in to Brevo email digests. | In-app popups appear while the site is open. Scheduled delivery depends on service configuration and user preferences. |
| Email | Gmail and Microsoft OAuth, optional daily monitoring for relevant messages, and separately consented watsonx.ai content summaries. Encrypted summaries expire after 90 days. | Gmail reading and one matching-body summary passed documented live checks. The deployment notes record Google OAuth in Testing. Microsoft is configured. Penn administrator approval and an end-to-end Outlook mailbox test remain pending. |
| Calendar | Approved `.ics` export and adapters for Google Calendar, Outlook, and iCloud. Connected-provider writes require user approval. | Google consent and read-only access passed documented checks. Live event creation and Outlook/iCloud authorization remain pending. |
| Deployment | Vercel hosts the web app, API, and tool gateway with shared Supabase PostgreSQL. The checked-in [deployment configuration](vercel.json) defines 26 daily jobs, including 23 source jobs and 3 jobs for reminders, mailbox monitoring, and proactive updates. | Provider-backed features require configured services and the relevant user permissions. |

Penn private-portal workflows remain manual. Staytus links users to the appropriate university office or portal.

See the [verification guide](docs/VERIFICATION.md) and [Vercel operations notes](infra/vercel/README.md) for provider checks and deployment details.

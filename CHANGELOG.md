# Staytus changelog

This page highlights major project milestones. See the [full changelog](docs/CHANGELOG_FULL.md) for the complete dated implementation and verification history.

## 2026-11-09 — Adaptive planning timelines

- Kept the core timeline under backend control and allowed the model to suggest up to three validated, situation-specific steps.

## 2026-11-08 — Visual planning, policy browsing, and email summaries

- Added visual timelines to guided and free-text planning, with expandable date explanations and source links.
- Grouped the Policy Library by issuing authority and improved navigation and readability.
- Added separately consented summaries of matching email content and published the corresponding Orchestrate tool.

## 2026-11-04 — Proactive assistant and chat controls

- Added proactive assistant messages with a separate update history, unread status, and preferences.
- Added New chat and persistent planning and policy shortcuts.

## 2026-11-03 — Public deployment and scheduled workflows

- Deployed the web app, API, and tool gateway to Vercel with shared Supabase PostgreSQL and versioned migrations.
- Added guided personal planning, opt-in mailbox monitoring, and Brevo reminder delivery. Verified initial Gmail authorization and read-only Google Calendar access.

## 2026-11-01 to 2026-11-02 — Core application and IBM integration

- Built account onboarding, a personal workspace, and a policy pipeline for registered official public sources.
- Connected the conversational assistant to watsonx Orchestrate, added account-scoped tools and user approvals, and enabled watsonx.ai embeddings for hybrid retrieval.

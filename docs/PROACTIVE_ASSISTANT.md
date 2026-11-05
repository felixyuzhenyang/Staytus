# Proactive assistant messages

The Assistant can receive model-written messages without a user question or an active login session. A daily cloud job turns relevant saved planning/source-change events into a private generation outbox; a separate text-only watsonx.ai call writes the summary. The browser later reads the saved result. Normal interactive chat still calls Orchestrate.

## Flow and limits

1. Synchronize the existing reminder inbox for enabled accounts. Only `planning` and `policy_update` events from the last7days qualify. Mail-monitor notices, mailbox previews and private Penn portals are excluded.
2. Reserve up to5new events per account/profile version, at most one batch per local calendar day. Event reservations and a unique daily key prevent concurrent or repeated runs from duplicating messages. Read reminders are still eligible for an assistant explanation if they have not already been reserved.
3. Combine the saved structured profile, current internal preparation targets, scoped RAG excerpts and, for a policy-change event, bounded old/current official-source excerpts. No email address, account identifiers, document numbers, user credentials or mailbox bodies are supplied. The model writes `title`, `summary`, `why_it_matters`, `next_steps` and `questions`; source links are attached by the server.
4. Validate the model's JSON, language, length and selected timing/action claims. Unsupported individual next steps/questions can be omitted, with an explicit note shown to the user; retained text remains model-written. Invalid core content gets at most one model correction. Provider failure or still-invalid output produces no template message. Retry failed batches after at least6hours, at most3attempts. The daily host schedule may mean a retry happens the following day. Expired10minute claims can recover; unique claim tokens prevent an older worker from publishing over a newer one. These checks do not verify every factual/legal claim.
5. Recheck account/profile ownership, profile version, current preferences and event validity before publication. Changed or superseded inputs invalidate generation. Saved older messages remain inspectable with an outdated label when their facts/preferences change.
6. Save successful results independently of the active chat conversation. No fake user question, impersonation session or model tool capability is minted. The generation client has no calendar/email/application tools. Users still use the normal chat and approval flows for further actions.

The first implementation processes up to3messages per job run to bound free-tier time/model usage. A larger user population needs more scheduled capacity or a dedicated queue consumer; it is not an unlimited broadcast service. Empty batches make no generation call. This does not verify legal eligibility or current-law accuracy: a captured page change remains an unreviewed change until checked.

## Settings and experience

In **Your assistant → Proactive assistant updates**, choose English or Chinese, disable further generation, or select **Check for assistant updates**. The check uses only actual eligible events and shares the same daily deduplication and retry budget; it does not fabricate a sample message. In-app reminders and a reminder frequency other than Off must also be enabled.

On return, **Your assistant** displays an unread count and a clearly labelled **Updates from your assistant** section. Messages include the trigger explanation, personal relevance, proposed next steps, unresolved facts, source references and creation date. **Mark as read** persists per account. **Discuss this update** sends a user-requested follow-up with the update context to Orchestrate. While visible, the browser checks for newly saved messages every30seconds; it never calls the LLM merely to display them.

**New chat** creates a clean conversation and hides inline proactive cards in that conversation, including after reload. It never deletes messages, marks them read, disables generation or changes subscriptions. The permanent **Assistant updates** button opens a history view inside the same Assistant page, with preferences, an account-wide unread count and **Load older updates**. The API uses a stable timestamp/ID cursor in owned20-message pages, allowing access beyond the recent20shown inline. History is newest-first; **Back to chat** restores the current conversation, and **Discuss this update** returns to it. Guided forms and **Latest policy sources** remain available before and after sending messages.

These messages are stored under the account in Supabase. Email digests remain a separate existing reminder channel; no new mailbox-read permission or system-email send behavior is introduced by this feature. Creating a proactive message does not create a calendar event or submit an application.

## Deployment and verification

Additive Alembic revision `20261104_0003` adds `assistant_updates`, event reservations and two preference fields. Existing accounts, profile facts and reminder preferences are retained. The limited runtime role receives access to the new tables; the owner credential remains local. A private, read-only pre-migration logical snapshot is retained; restoring that new snapshot was not tested this round.

Vercel now registers26daily jobs, including `/internal/jobs/assistant` at `0 16 * * *` UTC, protected by the existing cron secret and PostgreSQL advisory lock. Hobby jobs can vary within an hour. This daily job is independent of the browser and developer computer. A local installation can run the same generator through the existing reminder worker.

`scripts/verify_proactive_updates.py --live --confirm-synthetic-test` creates only fictional accounts, logs them out, runs the real configured model path scoped to those accounts and verifies saved messages on return, zero user chat turns, deduplication and account isolation. It removes exact test records afterwards. `--keep-ui-fixture` permits browser QA; follow with `--cleanup-fixture`. Reports and screenshots remain ignored/private. An explicit background-path test is distinct from observing the first naturally scheduled cron run.

# Reminders and connected calendars

Staytus now has a durable account-owned reminder inbox, notification preferences and opt-in email digest outbox with Brevo HTTPS and optional SMTP transports. The policy capture worker still owns public-source checking. The reminder worker consumes captured update notices and deterministic planning targets; it does not turn a newly captured page into an effective legal rule.

## What works without a mailbox

- Policy-source checks continue on their configured schedule while the backend runs.
- Upcoming/today/past preparation targets and relevant source updates enter the user's inbox with durable deduplication.
- The header bell polls while the page is open, shows unread counts, and presents an in-app popup. Read and popup acknowledgements survive reloads.
- Settings support daily, weekly, monthly or off, a timezone, digest hour/day and preparation lead time. A month-day31 schedule clamps to the end of short months.
- Calendar previews can still export an approved `.ics` file, including the selected display alarm and correctly folded Unicode text.

The current popup is an application popup, not an operating-system push service. It does not run after the page closes. The public deployment runs capture, mailbox and reminder jobs in Vercel daily batches backed by Supabase. Closing this webpage or sleeping the development computer does not stop those cloud jobs. A selected hour is the earliest eligible time; exact minute-level delivery is not promised.

## Connected calendar writes

In Connections, a user can request Google or Microsoft calendar access independently of mailbox reading and drafting. After configuration and personal provider consent, the planning screen lets the user select a calendar target and alarm, inspect the exact preview, then approve one event creation. The target account is bound to that preview; reconnecting to a different account requires a new preview. No attendees or invitations are added. Uncertain provider writes are terminal for that approval and are not automatically repeated.

Google/Outlook events are written to the connected primary/default provider calendar. They appear in Apple Calendar when the same Google/Microsoft account is enabled on the iPhone or Mac. This is provider synchronization, not native EventKit access.

The action result shows a readable summary with the reminder, date, alert and destination. A calendar-file export is labelled **Ready to download** and still requires download/import; only a confirmed provider write is labelled **Added to calendar**. An uncertain result warns the user to check their calendar before preparing another reminder. The UI does not display raw execution-receipt JSON or provider event identifiers. Full receipts and audit records remain on the backend, and approval/duplicate-execution controls are unchanged.

A direct **iCloud Calendar** connection is now implemented using CalDAV and a dedicated Apple app-specific password. Apple Account two-factor authentication and password creation must be completed personally by the user; never enter the primary Apple password in Staytus. App-specific credentials are not granular OAuth scopes and may allow broader iCloud access. Staytus encrypts this credential server-side and restricts its adapter to fixed Apple calendar hosts, owned writable calendars and approved event creation. Multiple calendars require a selection; changing accounts/calendars invalidates old previews. No invitations or two-way synchronization are added. The adapter has mocked/security coverage, but no real Apple Account was connected or changed. Native EventKit access remains a separate future native-app task.

See [Apple calendar accounts](https://support.apple.com/guide/iphone/change-calendar-settings-iphc37be2016/ios), [Google event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), and [Microsoft event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0).

## Daily read-only inbox checks

Gmail/Outlook monitoring is separate from sending reminders. A verified read-authorized connection lets the user check the inbox on demand; recurring daily checks require a separate default-off opt-in, timezone and local hour. The consent binds to the current connection; relinking or revocation stops background access until renewed. Manual attempts have a five-minute cooldown. The public cloud job runs independently of this page; local development still requires a running backend.

The monitor checks a bounded recent30day inbox window and returns at most20 matching official-topic messages; it does not promise exhaustive coverage. It persists only hashed message IDs, schedule/check status and generic private count notices. It does not save message bodies/subjects/snippets, add mail to the policy RAG, share it with a model, send anything or mark messages read. The existing separately authorized Agent-preview tool remains independent. Personal Google authorization, a manual check and an explicitly opted-in background-path check passed for the current account. Other accounts remain default-off. Microsoft remains unconfigured/deferred.

## Opt-in email delivery

The current public deployment selects the original Brevo SMTP key with STARTTLS after the user disabled its IP blocking. The restricted HTTPS API remains an explicit alternative. Real user-requested API and SMTP tests were accepted by Brevo and received by the linked Gmail account in SPAM; this does not prove INBOX placement or multi-day scheduled reliability. The current account's daily subscription is enabled, with the earliest digest time10:00America/New_York. See [Brevo setup and verification](BREVO_EMAIL.md).

Delivery needs an operator-configured sender plus explicit opt-in to the user's provider-verified mailbox. Arbitrary signup/profile email text is not a verified recipient. Reconnection, recipient changes or revoked consent invalidate the saved binding. No Gmail send permission is needed to receive system reminders.

Queued messages use durable claims and bounded retries only after definitive rejection; an ambiguous result is recorded as unknown and is not silently resent. Recipient/connection, profile state and notice freshness are rechecked before delivery. The owner-only test button sends a fixed non-sensitive message, cannot choose another recipient or custom content, is rate-limited and leaves other queued deliveries untouched. Mailbox reading and in-app notices are independent of email sending.

## Remaining integration checks

The current Google client, production callback, personal Gmail and Calendar grants are configured. Read-only Gmail/Calendar checks passed; an actual approved calendar event remains to be tested. Google is still External/Testing. Microsoft developer registration and personal Outlook authorization remain deferred. iCloud needs a personally created app-specific credential and a chosen calendar.

The first naturally scheduled digest and longer-term schedule reliability remain to be observed. The initial Brevo test reached SPAM, so sender-domain authentication and broader inbox-placement work remain before general public email use. Device background push and Penn private-portal submission are not implemented. System reminders do not add authority to activate unreviewed legal rules.

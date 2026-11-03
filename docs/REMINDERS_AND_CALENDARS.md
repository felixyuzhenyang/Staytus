# Reminders and connected calendars

Staytus now has a durable account-owned reminder inbox, notification preferences and optional email digest outbox. The policy capture worker still owns public-source checking. The reminder worker consumes captured update notices and deterministic planning targets; it does not turn a newly captured page into an effective legal rule.

## What works without a mailbox

- Policy-source checks continue on their configured schedule while the backend runs.
- Upcoming/today/past preparation targets and relevant source updates enter the user's inbox with durable deduplication.
- The header bell polls while the page is open, shows unread counts, and presents an in-app popup. Read and popup acknowledgements survive reloads.
- Settings support daily, weekly, monthly or off, a timezone, digest hour/day and preparation lead time. A month-day31 schedule clamps to the end of short months.
- Calendar previews can still export an approved `.ics` file, including the selected display alarm and correctly folded Unicode text.

The current popup is an application popup, not an operating-system push service. It does not run after the page closes. Both capture and reminder workers require a running backend; shutting down the development computer stops them. Public hosting is a later deployment task.

## Connected calendar writes

In Connections, a user can request Google or Microsoft calendar access independently of mailbox reading and drafting. After configuration and personal provider consent, the planning screen lets the user select a calendar target and alarm, inspect the exact preview, then approve one event creation. The target account is bound to that preview; reconnecting to a different account requires a new preview. No attendees or invitations are added. Uncertain provider writes are terminal for that approval and are not automatically repeated.

Google/Outlook events are written to the connected primary/default provider calendar. They appear in Apple Calendar when the same Google/Microsoft account is enabled on the iPhone or Mac. This is provider synchronization, not native EventKit access.

A direct **iCloud Calendar** connection is now implemented using CalDAV and a dedicated Apple app-specific password. Apple Account two-factor authentication and password creation must be completed personally by the user; never enter the primary Apple password in Staytus. App-specific credentials are not granular OAuth scopes and may allow broader iCloud access. Staytus encrypts this credential server-side and restricts its adapter to fixed Apple calendar hosts, owned writable calendars and approved event creation. Multiple calendars require a selection; changing accounts/calendars invalidates old previews. No invitations or two-way synchronization are added. The adapter has mocked/security coverage, but no real Apple Account was connected or changed. Native EventKit access remains a separate future native-app task.

See [Apple calendar accounts](https://support.apple.com/guide/iphone/change-calendar-settings-iphc37be2016/ios), [Google event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), and [Microsoft event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0).

## Daily read-only inbox checks

Gmail/Outlook monitoring is separate from sending reminders. A verified read-authorized connection lets the user check the inbox on demand; recurring daily checks require a separate default-off opt-in, timezone and local hour. The consent binds to the current connection; relinking or revocation stops background access until renewed. Manual attempts have a five-minute cooldown. The backend must remain running.

The monitor checks a bounded recent30day inbox window and returns at most20 matching official-topic messages; it does not promise exhaustive coverage. It persists only hashed message IDs, schedule/check status and generic private count notices. It does not save message bodies/subjects/snippets, add mail to the policy RAG, share it with a model, send anything or mark messages read. The existing separately authorized Agent-preview tool remains independent. Real mailbox authorization and testing are still pending.

## Optional email delivery (deferred)

Email is off by default. It needs both:

1. An operator-configured deployment sender (SMTP over TLS), with these private backend settings: `NOTIFICATION_EMAIL_ENABLED`, `NOTIFICATION_SMTP_HOST`, `NOTIFICATION_SMTP_PORT`, `NOTIFICATION_SMTP_SECURITY`, `NOTIFICATION_SMTP_USERNAME`, `NOTIFICATION_SMTP_PASSWORD`, `NOTIFICATION_FROM_EMAIL`.
2. A user's explicit delivery opt-in to their provider-verified connected mailbox. Arbitrary signup/profile email text is not a verified recipient. Reconnection, recipient changes or revoked consent invalidate the saved binding.

The deployment sender is separate from a user's read/draft OAuth permission. Queued messages use durable claims and bounded retries only after safe, definitive rejection; an ambiguous send is recorded as unknown and is not silently resent. Recipient/connection, profile state and notice freshness are rechecked before delivery. The user deferred sending: SMTP remains disabled and no real reminder email was sent. Reading a mailbox and producing in-app notices do not require SMTP.

## Before real-user testing

The token-encryption key and newly approved Google Web client credentials are configured; Microsoft credentials are not. Google project Staytus (`staytus-513614`) and branding/external Testing preparation exist; the user completed the policy step and approved Web client creation. Credentials were saved privately, while API enablement/test-user registration and personal authorization remain pending. Microsoft configuration remains missing. The exact preparation is in [EMAIL_CONNECTIONS.md](EMAIL_CONNECTIONS.md). Google/Microsoft registrations and personal consent are prerequisites for real mailbox/calendar tests. Direct iCloud uses its separate personally created app-specific credential and calendar selection. No provider authorization or live write has been completed by these code changes.

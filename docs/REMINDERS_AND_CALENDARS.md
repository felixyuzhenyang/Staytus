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

Events are written to the connected primary/default provider calendar. They appear in Apple Calendar when the same Google/Microsoft account is enabled on the iPhone or Mac. This is provider synchronization, not native EventKit access or direct iCloud writing. iCloud authorization/CalDAV or a native EventKit app requires separate implementation and device verification; it is deferred in this iteration.

See [Apple calendar accounts](https://support.apple.com/guide/iphone/change-calendar-settings-iphc37be2016/ios), [Google event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), and [Microsoft event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0).

## Optional email delivery

Email is off by default. It needs both:

1. An operator-configured deployment sender (SMTP over TLS), with these private backend settings: `NOTIFICATION_EMAIL_ENABLED`, `NOTIFICATION_SMTP_HOST`, `NOTIFICATION_SMTP_PORT`, `NOTIFICATION_SMTP_SECURITY`, `NOTIFICATION_SMTP_USERNAME`, `NOTIFICATION_SMTP_PASSWORD`, `NOTIFICATION_FROM_EMAIL`.
2. A user's explicit delivery opt-in to their provider-verified connected mailbox. Arbitrary signup/profile email text is not a verified recipient. Reconnection, recipient changes or revoked consent invalidate the saved binding.

The deployment sender is separate from a user's read/draft OAuth permission. Queued messages use durable claims and bounded retries only after safe, definitive rejection; an ambiguous send is recorded as unknown and is not silently resent. Recipient/connection, profile state and notice freshness are rechecked before delivery. No real SMTP delivery or personal calendar/mail operation occurred during development tests.

## Before real-user testing

The token-encryption key is already configured, but Google/Microsoft OAuth client IDs and secrets are not. The exact provider registration preparation is in [EMAIL_CONNECTIONS.md](EMAIL_CONNECTIONS.md). Until those external developer registrations and user consent are complete, connected mail/calendar operations correctly remain unavailable. SMTP configuration is an additional prerequisite for actual scheduled email delivery.

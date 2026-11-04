# Brevo system reminder delivery

Production now uses the original Brevo SMTP key, selected explicitly with `NOTIFICATION_EMAIL_TRANSPORT=smtp`, on port587 with STARTTLS. The restricted HTTPS API transport remains available as an explicitly selected alternative; there is no automatic fallback.

## Credentials and permissions

The original SMTP attempt returned525 under IP blocking. After the user requested SMTP and personally disabled its IP blocking at the final confirmation, a fresh certificate-verified STARTTLS login returned235. The same key was reused; the API IP-security switch was not changed. Vercel uses changing outbound IPs, so the selected SMTP configuration no longer depends on a fixed-IP allowlist.

The unselected alternative API key `staytus-production-email-api` uses Restricted access: **Transactional email — All**, with every other resource set to None. Brevo requires this resource level to send; it also permits transactional template/log management. It is not a send-only permission or full-account access. Read-only live checks returned200 for transactional statistics and403 for the ungranted account resource. The key has the provider's one-year expiry; Brevo also applies an inactivity expiry policy.

Sender credentials are saved only in approved `backend/.env` and Vercel Production. Release preparation excludes it from local release-value JSON and source uploads; the operator reads it into memory and passes it over stdin to the cloud secret store. Do not commit it, expose it in screenshots or use it as an SMTP password.

Server settings:

```dotenv
NOTIFICATION_EMAIL_ENABLED=true
NOTIFICATION_EMAIL_TRANSPORT=smtp
NOTIFICATION_SMTP_HOST=smtp-relay.brevo.com
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_SECURITY=starttls
NOTIFICATION_SMTP_USERNAME=
NOTIFICATION_SMTP_PASSWORD=
NOTIFICATION_FROM_EMAIL=
```

The From address must be a verified Brevo sender. The account's verified sender display name is now Staytus, matching the application header. The user has no product mailbox, so the verified personal address remains. Brevo rewrites it through a relay domain while retaining its personal local part. Changing From name alone cannot remove that part; complete address branding requires an owned, verified product mailbox or an authenticated sending domain. Both the initial API test and the later SMTP test reached Gmail in SPAM; sender-domain authentication and broader inbox-placement tests remain release work.

## User subscription and testing

Recipients are derived from the signed-in account's provider-verified mailbox and are bound to its connection ID. Users separately opt in under the header bell → Reminder settings → Email me scheduled digests. Reading a Gmail inbox, receiving system reminders and sharing previews with the IBM agent are independent permissions. No Gmail send/draft scope is required to receive these system emails.

After saving a subscription, reopen settings and select **Send me a test email**. The endpoint accepts no custom recipient or content, sends only one fixed, non-sensitive message to the current recipient and has a five-minute per-account cooldown. It dispatches only that test delivery, leaving unrelated queued messages untouched.

`SENT` means the mail service accepted the message; it does not prove INBOX placement or that the user read it. Brevo receipts are recorded in the account's audit. Missing/uncertain responses remain UNKNOWN and are not silently resent. Definitive rejections have bounded retry behavior. Revocation, relinking and changed content invalidate unsent deliveries.

## Daily execution

The public Vercel project has25enabled daily jobs:23policy-source checks, mailbox monitoring and reminders. The mailbox batch is scheduled at14:00UTC and the reminder/email batch at15:00UTC. In the current New York winter timezone these correspond to09:00and10:00before host scheduling variation; daylight saving and user settings can change the delay. A user's selected hour is the earliest eligible time, not an exact appointment.

The current consenting account has daily background reads enabled in America/New_York and email digests eligible from10:00. A precisely scoped immediate background-path test passed and scheduled its next check for November4at09:00NewYork. The first naturally scheduled digest remains to be observed. Both cloud jobs passed authenticated manual dispatch, and unauthenticated access returned401.

Digests contain eligible unread, unsuperseded reminders. A quiet day may produce no email. Captured page changes remain pending review; activating delivery does not implement complete personal-impact analysis or activate legal rules. Closing the webpage does not stop cloud checks or email delivery; only in-app popups require an open page.

## Verification records

Ignored `.local/brevo/` contains credential-free summaries for API authentication/resource denial, Production configuration, current-account monitoring, cloud job configuration/dispatch and actual Gmail test receipt. The live test was requested from the authenticated public UI, not an operator-created login session. Gmail metadata confirmed the API test's delivery header and the later SMTP test's application-generated Message-ID, with Staytus display name and SPAM label; no mail labels were changed or private message content exported.

Code checks:500backend tests passed/3PostgreSQL-only skips, TypeScript,13-tool OpenAPI validation and production build passed. These checks do not establish multi-day schedule reliability, comprehensive policy accuracy or delivery to other users' inboxes.

References: [Brevo API permissions](https://help.brevo.com/hc/en-us/articles/40158277171474-About-API-key-permissions), [transactional email API](https://developers.brevo.com/docs/send-a-transactional-email).

Latest SMTP validation:32targeted tests passed; the same runtime source from the preceding500-test release was redeployed with SMTP configuration and a real SMTP test was received. No new key was created for this switch.

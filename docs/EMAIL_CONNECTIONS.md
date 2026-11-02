# Email connection setup and real-user test

Staytus uses OAuth authorization-code + PKCE through its same-origin server proxy. The user signs in at Google/Microsoft; Staytus never collects the mailbox password. The implemented integration supports personal Gmail/Microsoft accounts and eligible school-managed accounts. A school administrator may restrict third-party consent even when the user can sign in normally.

## Developer configuration

OAuth is a protocol, not a ready-made application registration. Each deployment needs a registered OAuth application with a client ID, server-side secret, allowed redirect URL, requested delegated scopes and test-user/consent settings.

The live Connections screen reports the **exact configured callback**, missing environment variable names and configuration errors without revealing credentials. Register that callback exactly. The default is:

```text
http://127.0.0.1:3000/api/backend/connections/google/callback
http://127.0.0.1:3000/api/backend/connections/microsoft/callback
```

Set these only on the backend:

```text
CONNECTOR_TOKEN_KEY=<stable Fernet key; encrypts saved provider tokens>
GOOGLE_CLIENT_ID=<registered Web client ID>
GOOGLE_CLIENT_SECRET=<registered Web client secret>
MICROSOFT_CLIENT_ID=<registered Web application ID>
MICROSOFT_CLIENT_SECRET=<registered Web application secret>
MICROSOFT_TENANT=common
OAUTH_CALLBACK_BASE=http://127.0.0.1:3000/api/backend
FRONTEND_URL=http://127.0.0.1:3000
```

Keep the browser origin, FRONTEND_URL and OAUTH_CALLBACK_BASE origin identical. A localhost session cookie does not transfer to127.0.0.1, or vice versa. The UI now detects this mismatch before opening an authorization page.

OAuth callback query strings contain short-lived authorization codes and state. Next development logs exclude these callback paths; the dev and Docker backend launchers disable Uvicorn access logs. In production, configure every reverse proxy, CDN and hosting access logger to omit callback query strings (especially `code` and `state`) and redact Authorization/Cookie headers. Application log settings do not control those upstream logs.

### Google

1. Use a project you are authorized to manage; enable Gmail API.
2. Configure the OAuth consent screen and choose the appropriate audience. For an external app in Testing, add the real test email under test users.
3. Create a **Web application** OAuth client and register the exact Google callback above.
4. Save client ID/secret on the backend. Request `gmail.readonly` first; draft creation is a later separate authorization for `gmail.compose`.
5. Gmail read/compose scopes can require provider verification before broad public release. A working test-user flow is not public-app verification.

Primary source: [Google Web server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

### Microsoft

1. Register a **Web** application in Microsoft Entra. The backend exchanges the code; this is not a browser-only SPA token exchange.
2. Choose supported accounts deliberately: school/work accounts, personal accounts, or both. `common` works only with a compatible registration/audience.
3. Register the exact Microsoft callback and add **delegated** `User.Read` (signed-in basic mailbox identity) and `Mail.Read`; add `Mail.ReadWrite` only for drafts and `Calendars.ReadWrite` only when the user chooses calendar linking. Do not add organization-wide application mailbox/calendar access.
4. Save the application ID and server secret. The user signs in and consents; school policy can require administrator approval.
5. The Microsoft portal textbox does not accept an HTTP127.0.0.1 redirect directly; Microsoft documents adding it through the application manifest. Alternatively use `http://localhost:3000` consistently for FRONTEND_URL, callback base and browser sign-in. Production requires HTTPS.

Primary sources: [Entra app registration](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app), [redirect restrictions](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url), [authorization-code + PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

## Test with an existing real mailbox

After developer setup, the user can use the mailbox they already own; they do not need a new Staytus-specific email account.

1. Sign into Staytus on the configured browser origin and complete the profile.
2. Open Connections → Connect Google/Microsoft. Review the provider permissions and personally finish any password/MFA/consent steps.
3. Return to Staytus and confirm the provider/scopes are visible. Select **Check messages**. Only bounded recent official-topic metadata/short previews are returned, without attachments or full bodies.
4. If the user wants the cloud Agent to inspect matching previews, separately enable **Allow assistant to read matching email previews**. OAuth connection alone never enables this.
5. Once Orchestrate is deployed, ask it to check recent relevant email. The read-only tool uses the signed-in principal, never a model-supplied account ID. It returns at most10previews, each at most500characters, and marks them untrusted data rather than official policy authority.
6. To test drafts, choose **Enable email drafts**, complete the separate provider grant, and approve one exact draft in Staytus. Verify it in the actual provider mailbox. No send endpoint is implemented.
7. Turning off Agent access preserves manual mailbox reads. Relinking or disconnecting resets Agent access. Disconnect removes local tokens/pending authorizations; provider account settings can revoke provider-wide consent too.

## Implemented safety and current limits

- One account-scoped read service powers both the UI and authenticated Agent tool.
- PKCE and one-time state are bound to the original Staytus login session; tokens are encrypted server-side.
- Exact known scope checks, token refresh and one read-only401 retry are implemented. Reduced permissions stop the request before message retrieval.
- Current relevance filtering covers Penn and selected federal sender domains/topics; it is not every university's directory.
- Mail previews are not persisted into the policy corpus or silently included in normal chat grounding. Agent access requires a separate user choice.
- An enabled configuration screen is not a successful live connection. A real user must complete provider authorization; school/provider restrictions must be resolved through their normal approval process.

## Preparation audit before the first real mailbox test

The current private local configuration has a valid `CONNECTOR_TOKEN_KEY`. Google and Microsoft client IDs and secrets have not yet been supplied. Thus the remaining external developer steps are still necessary: choose/create an authorized Google Cloud or Entra application, register the exact callback, enable the relevant provider APIs, set its audience/test users/delegated permissions and save the client ID/secret privately on the backend. Only then can the user finish sign-in, MFA and consent. Entering an email address alone is insufficient. No OAuth application or persistent provider access was created by this code update.

For Google, enable Gmail API for mail and **Google Calendar API** for calendar writes in the same authorized project. Calendar linking requests `https://www.googleapis.com/auth/calendar.events.owned`, which permits events in calendars the user owns; Staytus writes only the user's primary calendar. Microsoft calendar linking requests delegated `Calendars.ReadWrite` plus offline renewal. It does not require application-wide calendar access. Calendar-only linking requests no mailbox read or draft scopes. Incremental linking retains already granted known permissions; the consent page remains the place where the user approves the requested combination.

Primary references: [Google Calendar event insertion and scopes](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), [Microsoft calendar event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0).

## Verified mailbox identity for reminder delivery

An arbitrary address typed at Staytus registration is not verified. After a mailbox grant, Staytus attempts to resolve the authenticated provider mailbox using [Gmail users.getProfile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile) or [Graph /me with delegated User.Read](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0). Only a valid bare provider-returned address is stored as identity inside the already encrypted token payload. No token or private identity is placed in the policy corpus or sent to a model by this lookup.

`verified_connected_email(db, account_id, provider)` performs no network and returns only `{email, provider, connection_id}` when a linked, known mail-read grant and encrypted identity exist. Legacy/unverified records, calendar-only grants, missing encryption access and reduced mail-read permission return no identity. A fresh OAuth callback rotates the connection binding even for the same address; notification delivery must recheck its recorded address/provider/connection binding. Disconnection removes the binding. Token renewal preserves that identity while the known read grant remains. Reminder-delivery consent is separate from Agent-preview sharing and from permission to create drafts. SMTP delivery, if configured, uses a deployment sender rather than mailbox send permission.

## Direct calendar writes and Apple devices

After explicit calendar authorization, an exact-content calendar proposal may select `provider: google` or `provider: microsoft`. The backend approval executor calls `execute_calendar` only for the current profile's claimed `EXECUTING` approval. It creates one all-day reminder in the authorized user's primary/default calendar, with no attendees or invitations. The approved fields include provider, title, date, description and reminder minutes. Google uses a deterministic event ID; Microsoft uses a deterministic transaction ID. An uncertain write is not retried automatically and the approval becomes `FAILED_UNCONFIRMED` for manual checking. `.ics` export remains available when provider is `export`; linking a mail account alone does not permit calendar writes.

Email and remote-calendar proposals additionally receive a server-owned `_connector_target` containing the chosen provider, current connection binding and a safe account label. This metadata is included in the approval hash; clients and models cannot supply it through the strict proposal schema. Relinking an account rotates its binding, so an old preview cannot write to a newly linked mailbox/calendar. A preview created before linking requires a fresh proposal after connection, and historical remote previews without a binding fail closed. The approval claim atomically rechecks current database profile ownership/version and stored hash, rather than relying on a stale ORM object. The UI displays the readable `target_account` label while keeping private binding fields out of the editable business content.

These provider events can be displayed by Apple Calendar when the user has added the same Google/Microsoft account to the device. A web page does not get native EventKit access merely because it runs on iOS/macOS. For an Apple-specific path:

- A user-enabled calendar subscription can display a maintained read-only feed across devices; it needs a reachable feed URL, explicit subscription and privacy-protected access. Apple controls refresh timing. See [Apple calendar subscriptions](https://support.apple.com/en-la/102301).
- A future native iOS/macOS app can request the appropriate EventKit permission or show EventKit's event editor. This requires native code, platform declarations and device testing, not merely a backend OAuth scope. See [Apple EventKit access](https://developer.apple.com/documentation/eventkit/accessing-the-event-store).

Calendar event transport is verified with synthetic provider responses, including ownership/scope denial, no invitations, no repeat approval and terminal uncertain-write handling. No real user's calendar, Gmail or Microsoft mailbox was changed in these tests. Provider consent, calendar appearance/reminder timing and school restrictions still require a real-user test.

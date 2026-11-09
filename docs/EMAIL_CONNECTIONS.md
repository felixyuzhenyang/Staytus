# Email connection setup and real-user test

Staytus uses OAuth authorization-code + PKCE through its same-origin server proxy. The user signs in at Google/Microsoft; Staytus never collects the mailbox password. The implemented integration supports personal Gmail/Microsoft accounts and eligible school-managed accounts. A school administrator may restrict third-party consent even when the user can sign in normally.

## Opt-in matching email-content summaries — November 8

Mailbox OAuth and Staytus content analysis are separate permissions. A delegated `gmail.readonly` or `Mail.Read` grant lets the backend perform bounded reads, but it does not authorize sending message bodies to a model. The signed-in user must separately enable **Allow Staytus to analyze matching email content** for the current provider connection. Disabling that choice deletes the provider's retained summaries; relinking or disconnecting also invalidates the consent and connection binding.

Staytus first filters recent inbox metadata by registered official domains and international-student topics. Only matching messages proceed to a second, bounded inline-body read. At most five messages are analyzed in one batch. Attachments and named or remote MIME parts are excluded, provider responses are streamed under a byte limit, and extracted text is bounded before it reaches IBM watsonx.ai. Email fields are labelled as untrusted data: the generation instructions prohibit following embedded requests, opening links, calling tools, changing permissions or treating an email as verified immigration policy. The backend then validates the strict structured response, requires human confirmation, and requires normalized action dates to match exact date evidence quoted from the same message.

Raw bodies and attachments are never written to the database or returned to Watson Orchestrate. Staytus stores only an encrypted structured summary containing bounded message metadata, a concise summary and relevance explanation, proposed actions/questions, and short quoted date evidence. Current-profile and current-connection checks guard reads; records expire after 90 days and the daily mail job physically deletes expired rows. Turning content analysis off deletes them immediately. The current cache is also scoped to connection, profile version, model and expiry.

Daily inbox monitoring remains a third, independent opt-in. It checks a bounded recent inbox window without sending, deleting or marking messages read. When both daily monitoring and content analysis are enabled, newly detected matches are summarized in batches of five; later messages remain queued for a future run. The user receives an account-owned count notice and can review encrypted summaries in Connections while verifying important details in the original mailbox. If content analysis is off, the monitor creates only the existing count notice and does not share message bodies with watsonx.ai.

The implementation, migration, provider doubles, adversarial-email validation, retention, consent-race and account-isolation paths have synthetic automated coverage. The fourteenth Orchestrate tool, `summarize_recent_official_messages`, is imported and published; a bounded main-Agent Live test verified that both mail tools deny a synthetic account without the required permissions. The Google mailbox owner then enabled the separate application consent and one real matching body completed the same bounded watsonx.ai summary path. The first model response needed the allowed JSON-format correction pass; the second produced a validated encrypted summary, and the public API returned200. No attachment, raw body or provider token entered the retained result.

## Microsoft developer setup — November4

Registered the Staytus Web application in the developer's personal Default Directory, outside PennO365. Its audience supports organizational and personal Microsoft accounts, the production callback below is registered, and only delegated `User.Read`, `Mail.Read` and `offline_access` are declared. No organization-wide mailbox access or tenant-wide admin consent was granted. The developer personally created `staytus-production-web` with a November4,2028 expiration; its value is stored only in backend `.env` and Vercel Production. Rotate it before expiry without changing the application ID.

The existing production source was redeployed with `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` and `MICROSOFT_TENANT=common`. Live synthetic tests passed the configured callback/client ID, S256 PKCE, minimal scopes, account-bound cancellation and replay rejection; test accounts were removed. The live Connections page displays Ready to connect. A real Penn mailbox attempt returned `AADSTS90095` and Need approval before a token exchange; no school approval request was submitted. Real provider consent, credential/token exchange and inbox reads remain unverified, including for personal Outlook accounts. The user must obtain the school administrator's approval for this mailbox or test an eligible personal Outlook mailbox. Developer setup in a personal directory does not override the school's consent policy. Calendar/draft grants are not part of this initial read-only setup.

The user opted to retain this setup and defer school approval. Resume from Connections → Microsoft / Outlook → Connect email when ready; no developer registration needs to be repeated solely because this authorization attempt was abandoned.

## Current public-domain setup — November3

The public frontend, privately bound API and stable tool gateway are deployed at https://mystaytus.vercel.app. Its backend uses the existing encrypted-token key and approved production OAuth client secret. The developer configures these once per deployment; end users only sign into Staytus and separately authorize their chosen provider. A Staytus login email may be Outlook while the linked mailbox is Gmail; the two identities do not have to match.

The existing Google Web client now has both the production callback below and its original local callback. The designated test user and only `gmail.readonly` / `calendar.events.owned` scopes were saved; Gmail and Google Calendar APIs display enabled. Public pre-consent HTTP tests passed PKCE, exact callbacks, scope separation, account binding, cancellation and replay rejection, with exact synthetic cleanup. The user personally completed Gmail consent and an actual inbox check returned1new matching message. Separate calendar consent subsequently passed; the UI displays Calendar writing enabled while retaining Gmail Read only. An exactly scoped live check confirmed the encrypted token, matching verified mailbox, offline refresh credential and primary Calendar events API200 with only its resource-kind field returned. No event details were requested and no event was created. Message content was not copied into reports or chat. Daily recurring checks and assistant-preview sharing remain off; real approved event creation remains a separate test.

Google currently remains External/Testing. [Google documents a seven-day refresh-token lifetime for this configuration](https://developers.google.com/identity/protocols/oauth2#expiration), except basic identity-only requests. A stable public application URL does not change that state. Broad release requires completing branding/homepage/privacy-policy/domain and scope verification steps as applicable; server-side Gmail read uses a restricted scope and may require a security assessment unless an exception applies. [Google verification requirements and testing exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification). Do not describe a successful designated-test-user connection as approval for arbitrary public users.

Microsoft is configured once for the deployment through the Staytus application in the developer's personal Default Directory. Its `common` tenant endpoint supports organizational and personal Microsoft accounts, and the server holds the production client credential. End users do not create an Azure application; each user clicks **Connect email** and grants delegated `Mail.Read` and `offline_access` for their own mailbox. The Penn-managed mailbox returned `AADSTS90095` / Need approval, so that specific organization still requires an administrator to approve Staytus. No tenant-wide or application-level mailbox permission was requested, and a personal Outlook mailbox has not yet completed the live consent/read test.

## Developer configuration

OAuth is a protocol, not a ready-made application registration. Each deployment needs a registered OAuth application with a client ID, server-side secret, allowed redirect URL, requested delegated scopes and test-user/consent settings.

The live Connections screen reports the **exact configured callback**, missing environment variable names and configuration errors without revealing credentials. Register that callback exactly. Current production callbacks are:

```text
https://mystaytus.vercel.app/api/backend/connections/google/callback
https://mystaytus.vercel.app/api/backend/connections/microsoft/callback
```

Both production callbacks are now registered; the November4 Microsoft section distinguishes developer setup from pending real-user consent. Local development defaults remain:

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
5. With the existing Live Orchestrate connection, ask it to check recent relevant email only if that separate Agent-preview toggle is enabled. The read-only tool uses the signed-in principal, never a model-supplied account ID. It returns at most10previews, each at most500characters, and marks them untrusted data rather than official policy authority.
6. To request private body summaries, separately enable **Allow Staytus to analyze matching email content**. Review the disclosure before consenting. The summary tool remains denied when this toggle is off even if preview access is on. Verify any returned dates or actions in the original message; a summary is not a policy determination.
7. To test drafts, choose **Enable email drafts**, complete the separate provider grant, and approve one exact draft in Staytus. Verify it in the actual provider mailbox. No send endpoint is implemented.
8. Turning off Agent access preserves manual mailbox reads. Turning off content analysis deletes retained summaries. Relinking or disconnecting resets both choices. Disconnect removes local tokens/pending authorizations; provider account settings can revoke provider-wide consent too.

## Implemented safety and current limits

- One account-scoped read service powers both the UI and authenticated Agent tool.
- PKCE and one-time state are bound to the original Staytus login session; tokens are encrypted server-side.
- Exact known scope checks, token refresh and one read-only401 retry are implemented. Reduced permissions stop the request before message retrieval.
- Current relevance filtering covers Penn and selected federal sender domains/topics; it is not every university's directory.
- Mail previews are not persisted into the policy corpus or silently included in normal chat grounding. Agent access requires a separate user choice.
- Matching inline body text reaches watsonx.ai only after the separate content-analysis choice. Attachments and raw bodies are not retained; encrypted structured summaries are current-profile scoped and physically deleted after90days or immediately when consent is withdrawn.
- An enabled configuration screen is not a successful live connection. A real user must complete provider authorization; school/provider restrictions must be resolved through their normal approval process.

## Earlier preparation audit, before the public-domain configuration

This historical audit recorded a valid local `CONNECTOR_TOKEN_KEY`. On November3, the Google Cloud project **Staytus** (`staytus-513614`) was created and its branding/external Testing setup was prepared. The user completed the policy step and explicitly approved creating Web client `staytus-local-web` with the exact local callback. Its client ID/secret were initially saved only in mode0600 backend `.env`; at that time, APIs/test-user/personal consent and Microsoft setup remained incomplete. The current public-domain configuration above supersedes those earlier setup gaps; personal consent remains separately verified.

Remaining developer steps include completing the Google consent configuration, enabling the relevant provider APIs, registering the Web client's exact callback and test users, or completing the equivalent authorized Entra registration. Save client IDs/secrets privately on the backend. Only then can the user finish mailbox sign-in, MFA and delegated consent. Entering an email address alone is insufficient. Creating a Cloud project is not the same as creating an OAuth client or authorizing a mailbox.

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

## Separate daily read-only inbox monitoring

Connections now includes **Read-only inbox monitoring** for Gmail and Outlook. After a verified mailbox read connection exists, a user may press **Check inbox now**, or separately enable **Allow a daily background inbox check** and select an IANA timezone and hour. Background reading defaults off. It is independent of sharing previews with the cloud Agent, creating drafts or sending email. No SMTP service is needed for reading and in-app notices; SMTP remains disabled in the current configuration.

The authenticated API is `GET/PATCH /api/v1/mail-monitor/{google|microsoft}` and `POST /api/v1/mail-monitor/{provider}/check`. A PATCH contains `{enabled, timezone, check_hour}`. Manual checking can run with background monitoring off; attempts are limited to one per five minutes. The worker requires a running backend and checks only opted-in account/connection bindings. Relinking or revocation requires renewed consent. A durable lease prevents concurrent checks; a changed consent/binding discards results after the provider response.

Checks use the existing bounded read service, restricted to the inbox and recent30days: Gmail uses `in:inbox`; Microsoft uses the inbox-folder messages endpoint. At most20 matching messages are returned, so this is not a complete mailbox archive or a guarantee that every important email was found. Sender/topic filtering currently covers Penn and selected federal sources. See [Gmail inbox filtering](https://developers.google.com/workspace/gmail/api/guides/list-messages) and [Microsoft mail folders/messages](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0).

Persistent monitoring state contains the connection binding, schedule, status and hashed message IDs for deduplication. Newly detected messages create a private in-app count notice, explicitly marked untrusted. With content analysis disabled, message bodies, snippets and subjects are not saved by the monitor or sent to a model; manual short previews are returned to the signed-in UI only. With the separate content-analysis choice enabled, matching inline body text is sent to watsonx.ai in batches of five and only the encrypted structured summary described above is retained. Nothing is added to the public policy corpus. No send, mark-read or delete operation is implemented by the monitor. Synthetic monitor/security paths passed, and the same underlying analysis path passed one real owner-invoked Gmail summary; the first naturally scheduled body-summary batch remains to be observed.

## Direct iCloud calendar connection

Staytus now includes an iCloud CalDAV adapter and connection UI. This is code and mocked-transport verification, not a live Apple Account connection. The user must personally enable Apple Account two-factor authentication and create a dedicated, independently revocable **app-specific password** following [Apple's official instructions](https://support.apple.com/en-us/102654). Staytus never asks for the primary Apple Account password. Apple app-specific credentials are not granular Google/Microsoft-style OAuth grants and may permit broader iCloud access; Staytus restricts its implementation to calendar discovery and approved event creation.

`POST /api/v1/connections/icloud/link` uses the Apple Account email and app-specific password to discover only owned writable event calendars on fixed Apple HTTPS hosts. The credential and provider locations are encrypted server-side. If several calendars are found, the user must select one with `PATCH /api/v1/connections/icloud/calendar`. Changing the selected calendar or relinking rotates the approval binding. The UI never receives the password back, and neither the credential nor provider URLs are passed to the model.

An exact-content calendar preview may choose `provider: icloud`. Final authenticated approval rechecks the owned writable calendar and performs one conditional event-creation PUT, without attendees/invitations. Discovery and creation share a bounded operation budget; an uncertain write is not automatically retried. Disconnect deletes the local credential; the user can also revoke its app-specific password in Apple Account settings. The adapter provides approved event creation, not two-way calendar synchronization, native EventKit access, mailbox reading or school-portal authorization. Actual Apple consent, event appearance and device reminder timing still need a real-user test.

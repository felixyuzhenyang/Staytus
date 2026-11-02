"use client";
import { ArrowRight, Check, Mail } from "lucide-react";
import type { Connection, OAuthCapability } from "@/lib/types";
import { date } from "@/lib/types";
import { Badge } from "./ui";
import { canReadMail, canWriteCalendar } from "@/lib/calendar";

type Provider = "google" | "microsoft";
type Props = {
  provider: Provider; connection?: Connection; busy: boolean;
  onConnect: (provider: Provider, capability?: OAuthCapability) => Promise<void>;
  onDisconnect: (provider: Provider) => Promise<void>;
  onReadMail: (provider: Provider) => Promise<void>;
  onAgentAccess: (provider: Provider, enabled: boolean) => Promise<void>;
};

export default function EmailProviderCard({ provider, connection, busy, onConnect, onDisconnect, onReadMail, onAgentAccess }: Props) {
  const connected = connection?.connected === true;
  const available = connection?.configured === true || connected;
  const scopes = connection?.scopes || [];
  const readsEnabled = canReadMail(connection);
  const calendarEnabled = canWriteCalendar(connection);
  const draftsEnabled = scopes.some(scope => scope === "https://www.googleapis.com/auth/gmail.compose"
    || scope === "https://www.googleapis.com/auth/gmail.modify" || scope === "https://mail.google.com/"
    || scope === "https://graph.microsoft.com/Mail.ReadWrite");
  return <div className="email-provider">
    <div className="provider-row">
      <span className="tile-icon small"><Mail size={19} /></span>
      <div>
        <h3>{provider === "google" ? "Google / Gmail" : "Microsoft / Outlook"}</h3>
        <p>{connected ? connection?.email || "Account connected" : available ? "Sign in with the account you want to connect, then review its permissions." : "Email sign-in is not enabled on this deployment yet. Developer setup is required."}</p>
        {connection?.last_sync_at && <small>Last checked {date(connection.last_sync_at)}</small>}
        {connected && readsEnabled && !draftsEnabled && <p className="scope-note">{provider === "google"
          ? "Drafts need Gmail compose permission, which also permits sending. Staytus creates drafts only and has no send action."
          : "Drafts need additional mailbox write permission. Staytus creates drafts for you to review and send yourself."}</p>}
      </div>
      <Badge tone={connected ? "green" : available ? "blue" : "neutral"}>{connected ? <><Check size={11} />{calendarEnabled && !readsEnabled ? "Calendar connected" : draftsEnabled ? "Drafts enabled" : "Read only"}</> : available ? "Ready to connect" : "Setup needed"}</Badge>
      {connected ? <div className="provider-actions">
        {readsEnabled ? <button className="button secondary compact" disabled={busy} onClick={() => void onReadMail(provider)}>Check messages</button> : <button className="button secondary compact" disabled={busy} onClick={() => void onConnect(provider, "mail_read")}>Enable email reading</button>}
        {readsEnabled && !draftsEnabled && <button className="button secondary compact" disabled={busy} onClick={() => void onConnect(provider, "mail_draft")}>Enable email drafts</button>}
        {!calendarEnabled && <button className="button secondary compact" disabled={busy} onClick={() => void onConnect(provider, "calendar_write")}>Enable calendar writing</button>}
        {calendarEnabled && <Badge tone="green">Calendar writing enabled</Badge>}
        <button className="text-button" disabled={busy} onClick={() => void onDisconnect(provider)}>Disconnect</button>
      </div> : <div className="provider-actions"><button className="button secondary compact" disabled={busy || !available} onClick={() => void onConnect(provider, "mail_read")}>Connect email <ArrowRight size={13} /></button><button className="button secondary compact" disabled={busy || !available} onClick={() => void onConnect(provider, "calendar_write")}>Connect calendar</button></div>}
    </div>
    {connected && readsEnabled && <label className="agent-mail-choice">
      <input type="checkbox" checked={connection?.agent_access === true} disabled={busy} onChange={event => void onAgentAccess(provider, event.target.checked)} />
      <span><strong>Allow assistant to read matching email previews</strong><small>When you ask, the IBM agent can receive recent matching subjects, senders, dates and short previews. Full bodies and attachments are excluded. You can turn this off separately from your mailbox connection.</small></span>
    </label>}
    {connection?.setup && <details className="email-setup">
      <summary>{available ? "Developer connection settings" : "Set up email sign-in"}</summary>
      <p>{provider === "google"
        ? "Create a Web OAuth client in your Google Cloud project, enable Gmail API and Google Calendar API for the capabilities you want, configure the consent screen, and add your email as a test user while the app is in Testing."
        : "Register a Web application in Microsoft Entra with delegated User.Read and Mail.Read for email, Mail.ReadWrite for drafts, and Calendars.ReadWrite for calendar writing. Choose supported account types and check whether your school requires administrator consent."}</p>
      <p>Register this exact redirect URI:</p><code>{connection.setup.callback_uri || "Configure a valid server callback URL"}</code>
      {provider === "microsoft" && connection.setup.callback_uri?.startsWith("http://127.0.0.1") && <p>Microsoft's portal may require adding an HTTP 127.0.0.1 callback in the application manifest. Alternatively use localhost consistently for the app, callback and FRONTEND_URL, then sign in again at that address.</p>}
      {!!connection.setup.missing.length && <p>Server settings still needed: {connection.setup.missing.join(", ")}</p>}
      {!!connection.setup.errors.length && <p>{connection.setup.errors.join(". ")}</p>}
      <p>Keep client secrets on the backend. Once setup is complete, refresh this page and use Connect; your existing email account can be the test account.</p>
      <a href={provider === "google" ? "https://developers.google.com/identity/protocols/oauth2/web-server" : "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"} target="_blank" rel="noreferrer">Official setup instructions <ArrowRight size={12} /></a>
    </details>}
  </div>;
}

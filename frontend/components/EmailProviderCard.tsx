"use client";
import { Mail } from "lucide-react";
import type { Connection, OAuthCapability } from "@/lib/types";
import { canReadMail, canWriteCalendar } from "@/lib/calendar";
import { Badge } from "./ui";
import MailboxMonitorCard from "./MailboxMonitorCard";

type Provider = "google" | "microsoft";
type Props = {
  provider: Provider;
  connection?: Connection;
  busy: boolean;
  onConnect: (provider: Provider, capability: OAuthCapability) => Promise<void>;
  onDisconnect: (provider: Provider) => Promise<void>;
  onReadMail: (provider: Provider) => Promise<void>;
  onAgentAccess: (provider: Provider, enabled: boolean) => Promise<void>;
  onContentAnalysis: (provider: Provider, enabled: boolean) => Promise<void>;
  onAnalyzeMail: (provider: Provider) => Promise<void>;
  onSessionExpired?: () => void;
};

export default function EmailProviderCard({
  provider, connection, busy, onConnect, onDisconnect, onReadMail,
  onAgentAccess, onContentAnalysis, onAnalyzeMail, onSessionExpired,
}: Props) {
  const label = provider === "google" ? "Gmail" : "Outlook";
  const connected = connection?.connected === true;
  const available = !!(connection?.configured || connected);
  const readsEnabled = canReadMail(connection);
  const calendarEnabled = canWriteCalendar(connection);
  const draftsEnabled = connected && (connection?.scopes || []).some(scope => [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://mail.google.com/",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "Mail.ReadWrite",
  ].includes(scope));
  const canDisconnect = connected && (readsEnabled || draftsEnabled || !calendarEnabled);

  return <div>
    <div className="provider-row">
      <span className="tile-icon small"><Mail size={19} /></span>
      <div>
        <h3>{label}</h3>
        {readsEnabled && connection?.email && <p>{connection.email}</p>}
        {canDisconnect && calendarEnabled && <p>Disconnecting this account also removes calendar access.</p>}
      </div>
      <Badge tone={readsEnabled || draftsEnabled ? "green" : "neutral"}>
        {draftsEnabled ? "Drafts enabled" : readsEnabled ? "Read only" : available ? "Not connected" : "Unavailable"}
      </Badge>
      <div className="provider-actions">
        {!readsEnabled && <button type="button" className="button secondary compact" disabled={busy || !available} aria-label={`Connect ${label} email`} onClick={() => void onConnect(provider, "mail_read")}>Connect</button>}
        {canDisconnect && <button type="button" className="text-button" disabled={busy} aria-label={`Disconnect ${label} account`} onClick={() => void onDisconnect(provider)}>Disconnect account</button>}
      </div>
    </div>
    {readsEnabled && <details className="connection-disclosure">
      <summary>Manage {label} permissions and checks</summary>
      <div className="connection-details">
        <label className="agent-mail-choice">
          <input type="checkbox" checked={connection?.agent_access === true} disabled={busy} onChange={event => void onAgentAccess(provider, event.target.checked)} />
          <span><strong>Share matching email previews with the assistant</strong><small>When you ask, the IBM agent can receive matching subjects, senders, dates and short previews. Full bodies and attachments are excluded.</small></span>
        </label>
        <label className="agent-mail-choice">
          <input type="checkbox" checked={connection?.content_analysis_enabled === true} disabled={busy} onChange={event => void onContentAnalysis(provider, event.target.checked)} />
          <span><strong>Summarize matching email content</strong><small>Selected text from matching international-student emails is sent to IBM watsonx.ai when requested or during enabled daily checks. Raw bodies and attachments are not saved. Encrypted summaries expire after 90 days or are removed when you turn this off.</small></span>
        </label>
        <MailboxMonitorCard provider={provider} connection={connection} onSessionExpired={onSessionExpired} />
        <div className="provider-actions connection-actions">
          <button type="button" className="button secondary compact" disabled={busy} onClick={() => void onReadMail(provider)}>Check messages</button>
          {connection?.content_analysis_enabled && <button type="button" className="button secondary compact" disabled={busy} onClick={() => void onAnalyzeMail(provider)}>Analyze matching emails</button>}
        </div>
        {!draftsEnabled && <details className="connection-disclosure">
          <summary>Email drafts</summary>
          <div className="connection-details">
            <p className="muted">{provider === "google"
              ? "Google’s compose permission also allows sending. Staytus only creates drafts for you to review."
              : "Outlook requires additional mailbox write access. Staytus only creates drafts for you to review."}</p>
            <div className="provider-actions connection-actions"><button type="button" className="button secondary compact" disabled={busy} onClick={() => void onConnect(provider, "mail_draft")}>Enable email drafts</button></div>
          </div>
        </details>}
      </div>
    </details>}
  </div>;
}

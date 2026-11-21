"use client";
import { CalendarDays, Mail } from "lucide-react";
import type { Connection, MailAnalysis, MailMessage, OAuthCapability } from "@/lib/types";
import { date } from "@/lib/types";
import { canWriteCalendar } from "@/lib/calendar";
import { Badge } from "./ui";
import EmailProviderCard from "./EmailProviderCard";
import ICloudCalendarCard from "./ICloudCalendarCard";

const providers = ["google", "microsoft"] as const;
type Provider = (typeof providers)[number];
type Props = {
  connections: Connection[];
  messages: MailMessage[];
  analyses: MailAnalysis[];
  mailboxLoaded: boolean;
  busy: boolean;
  onConnect: (provider: Provider, capability: OAuthCapability) => Promise<void>;
  onDisconnect: (provider: Provider) => Promise<void>;
  onReadMail: (provider: Provider) => Promise<void>;
  onAgentAccess: (provider: Provider, enabled: boolean) => Promise<void>;
  onContentAnalysis: (provider: Provider, enabled: boolean) => Promise<void>;
  onAnalyzeMail: (provider: Provider) => Promise<void>;
  onUpdated: () => void;
  onSessionExpired?: () => void;
};

export default function ConnectionsPanel({
  connections, messages, analyses, mailboxLoaded, busy, onConnect, onDisconnect,
  onReadMail, onAgentAccess, onContentAnalysis, onAnalyzeMail, onUpdated, onSessionExpired,
}: Props) {
  return <>
    <section className="panel connection-settings" aria-labelledby="connection-email-heading">
      <div className="section-heading inside"><h2 id="connection-email-heading"><Mail size={18} /> Email</h2></div>
      <p className="muted">Connect an inbox to check for relevant notices. Assistant access and daily checks are optional.</p>
      <div className="provider-list">
        {providers.map(provider => <EmailProviderCard
          key={provider}
          provider={provider}
          connection={connections.find(item => item.provider === provider)}
          busy={busy}
          onConnect={onConnect}
          onDisconnect={onDisconnect}
          onReadMail={onReadMail}
          onAgentAccess={onAgentAccess}
          onContentAnalysis={onContentAnalysis}
          onAnalyzeMail={onAnalyzeMail}
          onSessionExpired={onSessionExpired}
        />)}
      </div>
      {(mailboxLoaded || analyses.length > 0) && <details className="connection-disclosure email-activity">
        <summary>Recent email activity</summary>
        <div className="connection-details">
          {mailboxLoaded && <div>
            <h3>Recent messages</h3>
            {messages.length === 0 && <p role="status" className="muted">No matching messages were found.</p>}
            {messages.map(message => <article className="mail-message" key={message.id}>
              <span className="eyebrow">{date(message.received_at)}</span>
              <h4>{message.subject || "(No subject)"}</h4>
              <small>{message.from}</small>
              <p>{message.snippet}</p>
            </article>)}
          </div>}
          {analyses.length > 0 && <div>
            <h3>Private email summaries</h3>
            <p className="muted">Confirm dates and required actions in the original email and official sources.</p>
            {analyses.map(item => <article className="mail-message mail-analysis" key={item.id}>
              <span className="eyebrow">{date(item.received_at)} · {item.provider === "google" ? "Gmail" : "Outlook"}</span>
              <h4>{item.subject || "(No subject)"}</h4>
              <small>{item.from}</small>
              <p><strong>Summary:</strong> {item.analysis.summary}</p>
              <p><strong>Why it may matter:</strong> {item.analysis.why_relevant}</p>
              {item.analysis.action_items.length > 0 && <>
                <h5>Possible next steps</h5>
                <ul>{item.analysis.action_items.map((action, index) => <li key={index}>
                  {action.text}{action.due_date ? ` · ${date(action.due_date)}` : ""}
                  {action.needs_confirmation ? " · Confirm in the original email" : ""}
                </li>)}</ul>
              </>}
              {item.analysis.dates.length > 0 && <details><summary>Dates mentioned</summary>
                <ul>{item.analysis.dates.map((mentioned, index) => <li key={index}>
                  <strong>{mentioned.date_text}</strong> — {mentioned.meaning}
                  <small className="mail-quote">Source wording: “{mentioned.exact_quote}”</small>
                </li>)}</ul>
              </details>}
              {item.analysis.questions_to_confirm.length > 0 && <details><summary>Questions to confirm</summary>
                <ul>{item.analysis.questions_to_confirm.map((question, index) => <li key={index}>{question}</li>)}</ul>
              </details>}
              <small>Raw email bodies and attachments are not retained. Summary expires {date(item.expires_at)}.</small>
            </article>)}
          </div>}
        </div>
      </details>}
    </section>

    <section className="panel connection-settings" aria-labelledby="connection-calendars-heading">
      <div className="section-heading inside"><h2 id="connection-calendars-heading"><CalendarDays size={18} /> Calendars</h2></div>
      <p className="muted">Connect a calendar for reminders you approve. You can also download a calendar file without connecting.</p>
      <div className="provider-list">
        {providers.map(provider => {
          const connection = connections.find(item => item.provider === provider);
          const connected = canWriteCalendar(connection);
          const available = !!(connection?.configured || connection?.connected);
          const label = provider === "google" ? "Google Calendar" : "Outlook Calendar";
          return <div className="provider-row" key={provider}>
            <span className="tile-icon small"><CalendarDays size={19} /></span>
            <div>
              <h3>{label}</h3>
              {connected && <p>Disconnecting this account also removes any email access for it.</p>}
            </div>
            <Badge tone={connected ? "green" : "neutral"}>{connected ? "Connected" : available ? "Not connected" : "Unavailable"}</Badge>
            <div className="provider-actions">
              {connected
                ? <button type="button" className="text-button" disabled={busy} aria-label={`Disconnect ${label} account`} onClick={() => void onDisconnect(provider)}>Disconnect account</button>
                : <button type="button" className="button secondary compact" disabled={busy || !available} aria-label={`Connect ${label}`} onClick={() => void onConnect(provider, "calendar_write")}>Connect</button>}
            </div>
          </div>;
        })}
        <ICloudCalendarCard onUpdated={onUpdated} onSessionExpired={onSessionExpired} />
      </div>
    </section>
  </>;
}

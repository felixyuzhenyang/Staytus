"use client";
import { CalendarDays, Globe2, Link2, Mail, Sparkles } from "lucide-react";
import type { Connection, MailMessage, OAuthCapability } from "@/lib/types";
import { date } from "@/lib/types";
import { Badge, Empty } from "./ui";
import EmailProviderCard from "./EmailProviderCard";

function integrationStatus(value: unknown): { ready: boolean; text: string } {
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    if (item.configured === true && item.secure_context_verified === true) return { ready: true, text: "Chat enabled" };
    const ready = item.available === true || item.verified === true || item.live_verified === true || item.status === "connected" || item.status === "ready";
    return { ready, text: ready ? "Available" : item.configured === true ? "Configured" : "Not connected" };
  }
  return { ready: false, text: "Not connected" };
}

export default function ConnectionsPanel({ connections, integrations, messages, mailboxLoaded, busy, onConnect, onDisconnect, onReadMail, onAgentAccess }: { connections: Connection[]; integrations: Record<string, unknown>; messages: MailMessage[]; mailboxLoaded: boolean; busy: boolean; onConnect: (provider: "google" | "microsoft", capability?: OAuthCapability) => Promise<void>; onDisconnect: (provider: "google" | "microsoft") => Promise<void>; onReadMail: (provider: "google" | "microsoft") => Promise<void>; onAgentAccess: (provider: "google" | "microsoft", enabled: boolean) => Promise<void> }) {
  const orchestrate = integrationStatus(integrations.orchestrate);
  const watson = integrationStatus(integrations.watsonx || integrations.watsonx_ai);
  return <>
    <div className="connection-grid"><section className="panel connection-card"><span className="tile-icon"><Sparkles size={24} /></span><h2>IBM watsonx Orchestrate</h2><p>Powers your assistant's conversation and routes tools through the server. Chat is available only when the real service is connected.</p><Badge tone={orchestrate.ready ? "green" : "amber"}>{orchestrate.text}</Badge></section><section className="panel connection-card"><span className="tile-icon"><Globe2 size={24} /></span><h2>watsonx.ai</h2><p>Supports model services for source analysis and retrieval when configured. Connection keys stay on the server.</p><Badge tone={watson.ready ? "green" : "amber"}>{watson.text}</Badge></section><section className="panel connection-card"><span className="tile-icon"><CalendarDays size={24} /></span><h2>Calendar reminders</h2><p>Connect Google or Outlook Calendar below, then preview and approve reminders before Staytus creates them. Events sync to Apple Calendar when that account is enabled on your device. Calendar file export is also available.</p><Badge tone="blue">Separate calendar permission</Badge></section></div>
    <section className="panel connection-settings"><div className="section-heading inside"><h2><Mail size={18} /> Your email and calendar connections</h2><Badge>Optional</Badge></div><p className="muted">Connect only the account you want Staytus to access. The provider will show the requested permissions before you approve them.</p>
      <div className="provider-list">{(["google", "microsoft"] as const).map(provider => <EmailProviderCard key={provider} provider={provider} connection={connections.find(item => item.provider === provider)} busy={busy} onConnect={onConnect} onDisconnect={onDisconnect} onReadMail={onReadMail} onAgentAccess={onAgentAccess} />)}</div><div className="note"><Link2 size={18} /><p>Connecting email does not grant access to Penn's authenticated ISSS portal. School portal actions remain unavailable until a supported connection exists.</p></div>
    </section>
    {mailboxLoaded && <section className="panel mailbox-panel"><div className="section-heading inside"><h2>Recent messages</h2><Badge>Read only</Badge></div>{messages.map(message => <article className="mail-message" key={message.id}><span className="eyebrow">{date(message.received_at)}</span><h3>{message.subject || "(No subject)"}</h3><small>{message.from}</small><p>{message.snippet}</p></article>)}{!messages.length && <Empty icon={Mail} title="No messages returned" text="No matching messages were returned by the connected provider." />}</section>}
    <details className="panel config-status"><summary>Service connection details</summary><pre>{JSON.stringify({ integrations, connections }, null, 2)}</pre></details>
  </>;
}

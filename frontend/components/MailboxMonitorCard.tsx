"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { Connection, MailMessage } from "@/lib/types";
import { canReadMail } from "@/lib/calendar";
import { date } from "@/lib/types";
import { ErrorNotice } from "./ui";

type Monitor = { enabled: boolean; consent_current: boolean; connected: boolean; timezone: string; check_hour: number; next_check_at?: string | null; last_check_at?: string | null; last_error_code?: string | null };
type Check = { new_relevant_count: number; messages: MailMessage[]; checked_at: string; partial_window?: boolean };

export default function MailboxMonitorCard({ provider, connection, onSessionExpired }: {
  provider: "google" | "microsoft"; connection?: Connection; onSessionExpired?: () => void;
}) {
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [zone, setZone] = useState("UTC");
  const [hour, setHour] = useState(9);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Check | null>(null);
  const lifecycle = useRef<AbortController | null>(null);
  const expired = useRef(onSessionExpired); expired.current = onSessionExpired;
  const ready = canReadMail(connection);
  function fail(value: unknown, signal?: AbortSignal) {
    if (signal?.aborted) return;
    if (value instanceof ApiError && value.status === 401) expired.current?.();
    else setError(value instanceof Error ? value.message : "Unable to check mailbox settings.");
  }
  useEffect(() => {
    const controller = new AbortController(); lifecycle.current = controller;
    setMonitor(null); setResult(null); setError(""); setBusy(false);
    void api<Monitor>(`mail-monitor/${provider}`, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      setMonitor(value); setZone(value.timezone); setHour(value.check_hour);
    }).catch(value => fail(value, controller.signal));
    return () => controller.abort();
  }, [provider, connection?.connected, connection?.connection_id, connection?.last_sync_at]);
  async function save(enabled: boolean) {
    const signal = lifecycle.current?.signal;
    if (!signal || busy) return;
    setBusy(true); setError("");
    try {
      const value = await api<Monitor>(`mail-monitor/${provider}`, { method: "PATCH", body: JSON.stringify({ enabled, timezone: zone, check_hour: hour }), signal });
      if (!signal.aborted) setMonitor(value);
    } catch (value) { fail(value, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  async function check() {
    const signal = lifecycle.current?.signal;
    if (!signal || busy) return;
    setBusy(true); setError("");
    try {
      const value = await api<Check>(`mail-monitor/${provider}/check`, { method: "POST", signal });
      if (!signal.aborted) setResult(value);
    } catch (value) { fail(value, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  return <div className="connection-monitor">
    <ErrorNotice message={error} />
    {!ready && <p className="scope-note">Connect this mailbox with reading permission above before enabling checks.</p>}
    <label className="agent-mail-choice"><input type="checkbox" checked={!!monitor?.enabled && !!monitor?.consent_current} disabled={!ready || !monitor || busy} onChange={event => void save(event.target.checked)} /><span><strong>Allow a daily background inbox check</strong><small>Read-only checks create private notices for new matches. Staytus saves check status and message fingerprints. Relinking requires renewed consent.</small></span></label>
    <div className="form-grid"><label>Check timezone<input value={zone} disabled={busy} onChange={event => setZone(event.target.value)} placeholder="America/New_York" /></label><label>Hour in that timezone<select value={hour} disabled={busy} onChange={event => setHour(Number(event.target.value))}>{Array.from({ length: 24 }, (_, index) => <option key={index} value={index}>{String(index).padStart(2, "0")}:00</option>)}</select></label></div>
    <div className="provider-actions connection-actions"><button className="button secondary compact" disabled={!ready || !monitor || busy} onClick={() => void save(!!monitor?.enabled && !!monitor?.consent_current)}>Save check schedule</button><button className="text-button" disabled={busy} onClick={() => setZone(Intl.DateTimeFormat().resolvedOptions().timeZone)}>Use device timezone</button><button className="button secondary compact" disabled={!ready || busy} onClick={() => void check()}>Check inbox now</button></div>
    {monitor?.next_check_at && <p className="muted">Next scheduled check: {new Date(monitor.next_check_at).toLocaleString()} (displayed in your device timezone).</p>}
    {monitor?.last_check_at && <p className="muted">Last checked: {date(monitor.last_check_at)}</p>}
    {monitor?.last_error_code && <p className="muted">The last scheduled check encountered a problem. Try checking now.</p>}
    <small>Daily checks run at or after the selected hour and cover a limited window of recent messages.</small>
    {result && <div role="status">
      <p>{result.new_relevant_count === 0 ? "No new matching messages were found." : `${result.new_relevant_count} new matching ${result.new_relevant_count === 1 ? "message" : "messages"} found.`}{result.partial_window ? " The provider returned a limited set of recent messages." : ""}</p>
      {result.messages.length > 0 && <details className="connection-disclosure">
        <summary>View inbox check results</summary>
        <p className="muted">Verify important information in the original message.</p>
        {result.messages.map(message => <article className="mail-message" key={message.id}><h4>{message.subject || "(No subject)"}</h4><small>{message.from} · {date(message.received_at)}</small><p>{message.snippet}</p></article>)}
      </details>}
    </div>}
  </div>;
}

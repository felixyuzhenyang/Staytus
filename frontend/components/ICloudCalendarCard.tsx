"use client";
import { useEffect, useRef, useState } from "react";
import { CalendarDays } from "lucide-react";
import { api, ApiError } from "@/lib/api-client";
import { Badge, ErrorNotice } from "./ui";

type Status = { connected: boolean; configured: boolean; account_label?: string | null; calendars: { id: string; name: string }[]; selected_calendar_id?: string | null; calendar_write?: boolean };

export default function ICloudCalendarCard({ onUpdated, onSessionExpired }: { onUpdated: () => void; onSessionExpired?: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [appleId, setAppleId] = useState("");
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const life = useRef<AbortController | null>(null);
  const expired = useRef(onSessionExpired); expired.current = onSessionExpired;
  function fail(value: unknown, signal?: AbortSignal) {
    if (signal?.aborted) return;
    if (value instanceof ApiError && value.status === 401) expired.current?.();
    else setError(value instanceof Error ? value.message : "iCloud calendar connection could not be confirmed.");
  }
  function show(value: Status) { setStatus(value); setSelected(value.selected_calendar_id || ""); }
  useEffect(() => {
    const controller = new AbortController(); life.current = controller;
    void api<Status>("connections/icloud", { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) show(value);
    }).catch(value => fail(value, controller.signal));
    return () => controller.abort();
  }, []);
  async function action(kind: "link" | "select" | "disconnect") {
    const signal = life.current?.signal;
    if (!signal || busy || (kind === "link" && (!status?.configured || status.connected))) return;
    setBusy(true); setError("");
    try {
      const path = kind === "link" ? "connections/icloud/link" : kind === "select" ? "connections/icloud/calendar" : "connections/icloud";
      const body = kind === "link" ? { apple_id: appleId, app_specific_password: password } : { calendar_id: selected };
      const value = await api<Status>(path, { method: kind === "link" ? "POST" : kind === "select" ? "PATCH" : "DELETE", ...(kind !== "disconnect" ? { body: JSON.stringify(body) } : {}), signal });
      if (!signal.aborted) {
        if (kind === "disconnect") show(await api<Status>("connections/icloud", { signal }));
        else show(value);
        setShowForm(false); setPassword(""); onUpdated();
      }
    } catch (value) { fail(value, signal); }
    finally { if (!signal.aborted) { setPassword(""); setBusy(false); } }
  }
  return <div>
    <div className="provider-row">
      <span className="tile-icon small"><CalendarDays size={19} /></span>
      <div><h3>iCloud Calendar</h3>{status?.connected && status.account_label && <p>{status.account_label}</p>}</div>
      <Badge tone={status?.calendar_write ? "green" : "neutral"}>{status?.calendar_write ? "Connected" : status?.connected ? "Choose a calendar" : !status ? "Checking…" : status.configured ? "Not connected" : "Unavailable"}</Badge>
      <div className="provider-actions">
        {status?.connected
          ? <button type="button" className="text-button" disabled={busy} onClick={() => void action("disconnect")}>Disconnect iCloud</button>
          : !showForm && <button type="button" className="button secondary compact" disabled={busy || !status?.configured} aria-label="Connect iCloud Calendar" onClick={() => setShowForm(true)}>Connect</button>}
      </div>
    </div>
    <ErrorNotice message={error} />
    {showForm && status?.configured && !status.connected && <form className="connection-details icloud-form" onSubmit={event => { event.preventDefault(); void action("link"); }}>
      <p className="muted">App-specific passwords may allow broader iCloud access. Staytus encrypts this password and uses it only for Apple’s calendar service.</p>
      <div className="form-grid"><label>Apple Account email<input type="email" autoComplete="off" value={appleId} required disabled={busy} onChange={event => setAppleId(event.target.value)} /></label><label>Apple app-specific password<input type="password" autoComplete="off" value={password} required disabled={busy} placeholder="xxxx-xxxx-xxxx-xxxx" onChange={event => setPassword(event.target.value)} /></label></div>
      <p className="muted">Use a new, revocable app-specific password. Keep your main Apple Account password private. <a href="https://support.apple.com/en-us/102654" target="_blank" rel="noreferrer">Apple setup instructions</a></p>
      <div className="provider-actions connection-actions">
        <button className="button secondary compact" type="submit" disabled={busy || !appleId || !password}>Connect iCloud Calendar</button>
        <button type="button" className="text-button" disabled={busy} onClick={() => { setShowForm(false); setAppleId(""); setPassword(""); setError(""); }}>Cancel</button>
      </div>
    </form>}
    {status?.connected && <details className="connection-disclosure" open={!status.calendar_write}>
      <summary>Manage iCloud Calendar</summary>
      <div className="connection-details">
        <label>Calendar for approved reminders<select value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}><option value="">Choose an owned writable calendar</option>{status.calendars.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <div className="provider-actions connection-actions"><button className="button secondary compact" disabled={busy || !selected} onClick={() => void action("select")}>Save calendar</button></div>
        <p className="muted">Changing calendars requires a new reminder preview. You can revoke the app-specific password in your Apple Account.</p>
      </div>
    </details>}
  </div>;
}

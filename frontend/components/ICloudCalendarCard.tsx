"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { Badge, ErrorNotice } from "./ui";

type Status = { connected: boolean; configured: boolean; account_label?: string | null; calendars: { id: string; name: string }[]; selected_calendar_id?: string | null; calendar_write?: boolean };

export default function ICloudCalendarCard({ onUpdated, onSessionExpired }: { onUpdated: () => void; onSessionExpired?: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
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
    if (!signal || busy) return;
    setBusy(true); setError("");
    try {
      const path = kind === "link" ? "connections/icloud/link" : kind === "select" ? "connections/icloud/calendar" : "connections/icloud";
      const body = kind === "link" ? { apple_id: appleId, app_specific_password: password } : { calendar_id: selected };
      const value = await api<Status>(path, { method: kind === "link" ? "POST" : kind === "select" ? "PATCH" : "DELETE", ...(kind !== "disconnect" ? { body: JSON.stringify(body) } : {}), signal });
      if (!signal.aborted) {
        if (kind === "disconnect") show(await api<Status>("connections/icloud", { signal }));
        else show(value);
        setPassword(""); onUpdated();
      }
    } catch (value) { fail(value, signal); }
    finally { if (!signal.aborted) { setPassword(""); setBusy(false); } }
  }
  return <div className="email-provider">
    <div className="provider-row"><div><h3>iCloud Calendar</h3><p>{status?.connected ? status.account_label || "Apple calendar account connected" : "Connect an owned iCloud calendar using an Apple app-specific password."}</p></div><Badge tone={status?.calendar_write ? "green" : "neutral"}>{status?.calendar_write ? "Calendar ready" : status?.connected ? "Choose a calendar" : "Not connected"}</Badge></div>
    <ErrorNotice message={error} />
    <p className="muted">Apple's app-specific password is different from a granular Google/Microsoft OAuth grant and may allow broader iCloud access. Staytus restricts its use to Apple's calendar service, encrypts it on the server, and does not give it to the chat model. Use an independently revocable password for Staytus.</p>
    {!status?.connected && <form onSubmit={event => { event.preventDefault(); void action("link"); }}>
      <div className="form-grid"><label>Apple Account email<input type="email" autoComplete="off" value={appleId} required disabled={busy} onChange={event => setAppleId(event.target.value)} /></label><label>Apple app-specific password<input type="password" autoComplete="off" value={password} required disabled={busy} placeholder="xxxx-xxxx-xxxx-xxxx" onChange={event => setPassword(event.target.value)} /></label></div>
      <p className="scope-note">Create the app-specific password yourself at Apple Account → Sign-In and Security → App-Specific Passwords. Two-factor authentication is required. Never enter your main Apple Account password here.</p>
      <a href="https://support.apple.com/en-us/102654" target="_blank" rel="noreferrer">Apple's official instructions</a>
      <div className="provider-actions"><button className="button secondary compact" type="submit" disabled={busy || !status?.configured || !appleId || !password}>Connect iCloud Calendar</button></div>
      {status && !status.configured && <p className="scope-note">Server token encryption must be configured before linking.</p>}
    </form>}
    {status?.connected && <><label>Calendar for approved reminders<select value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}><option value="">Choose an owned writable calendar</option>{status.calendars.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="provider-actions"><button className="button secondary compact" disabled={busy || !selected} onClick={() => void action("select")}>Save calendar</button><button className="text-button" disabled={busy} onClick={() => void action("disconnect")}>Disconnect iCloud</button></div><p className="muted">Changing the calendar requires a fresh action preview. Disconnecting removes the local credential; revoke its app-specific password in your Apple Account to remove provider access.</p></>}
    <small>Staytus creates a calendar event only after you review and approve it. Two-way calendar synchronization is not included.</small>
  </div>;
}

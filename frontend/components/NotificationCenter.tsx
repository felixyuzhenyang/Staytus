"use client";
import { Bell, CheckCheck, Settings2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";

type InboxNotice = { id: string; title: string; message: string; kind: string; created_at: string; read_at: string | null; popup_seen_at: string | null };
type InboxResponse = { notifications: InboxNotice[]; unread_count: number; popup_enabled: boolean };
type Preferences = { in_app_enabled: boolean; popup_enabled: boolean; email_enabled: boolean; email_consent_current: boolean; frequency: string; timezone: string; digest_hour: number; digest_weekday: number; digest_monthday: number; lead_days: number; email_provider: string | null; email_recipient: string | null; next_email_at: string | null };
type PreferenceResponse = { preferences: Preferences; email_readiness: { configured: boolean }; verified_mailboxes: { email: string; provider: string }[] };

/** Account-scoped polling while the page is open. It does not request OS permissions. */
export default function NotificationCenter({ accountId, onSessionExpired, onOpenConnections }: {
  accountId: string; onSessionExpired?: () => void; onOpenConnections?: () => void;
}) {
  const [inbox, setInbox] = useState<InboxResponse>({ notifications: [], unread_count: 0, popup_enabled: false });
  const [settings, setSettings] = useState<PreferenceResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [emailTest, setEmailTest] = useState("");
  const [popup, setPopup] = useState<InboxNotice | null>(null);
  const seen = useRef(new Set<string>());
  const activePopup = useRef<string | null>(null);
  const lifecycle = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLElement | null>(null);
  const callbacks = useRef({ onSessionExpired, onOpenConnections });
  callbacks.current = { onSessionExpired, onOpenConnections };

  const handleError = useCallback((failure: unknown, signal?: AbortSignal) => {
    if (signal?.aborted) return;
    if (failure instanceof ApiError && failure.status === 401) callbacks.current.onSessionExpired?.();
    else setError(failure instanceof Error ? failure.message : "Unable to load reminders.");
  }, []);
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api<InboxResponse>("notifications", { signal });
    if (signal.aborted) return;
    setInbox(result);
    if (result.popup_enabled && !activePopup.current) {
      const fresh = result.notifications.find(item => !item.read_at && !item.popup_seen_at && !seen.current.has(item.id));
      if (fresh) {
        seen.current.add(fresh.id); activePopup.current = fresh.id; setPopup(fresh);
        void api(`notifications/${fresh.id}/popup-seen`, { method: "POST", signal }).catch(failure => handleError(failure, signal));
      }
    }
  }, [handleError]);
  useEffect(() => {
    const controller = new AbortController(); lifecycle.current = controller;
    seen.current = new Set(); activePopup.current = null; setPopup(null); setInbox({ notifications: [], unread_count: 0, popup_enabled: false });
    setSettings(null); setOpen(false); setEditing(false); setError(""); setEmailTest("");
    const refresh = () => { if (document.visibilityState !== "hidden") void load(controller.signal).catch(failure => handleError(failure, controller.signal)); };
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [accountId, load, handleError]);
  useEffect(() => {
    if (!editing) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const target = dialog.current;
    const focusable = () => [...(target?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex='0']") || [])];
    focusable()[0]?.focus();
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); setEditing(false); return; }
      if (event.key !== "Tab") return;
      const items = focusable(), first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    target?.addEventListener("keydown", key);
    return () => { target?.removeEventListener("keydown", key); previous?.focus(); };
  }, [editing]);

  async function markRead(id?: string) {
    const signal = lifecycle.current?.signal;
    if (!signal || busy) return;
    setBusy(true); setError("");
    try {
      await api(id ? `notifications/${id}/read` : "notifications/read-all", { method: "POST", signal });
      if (id === activePopup.current || !id) { activePopup.current = null; setPopup(null); }
      await load(signal);
    } catch (failure) { handleError(failure, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  async function openSettings() {
    const signal = lifecycle.current?.signal;
    if (!signal) return;
    setOpen(false); setError(""); setEmailTest(""); setBusy(true);
    try { const result = await api<PreferenceResponse>("notifications/preferences", { signal }); if (!signal.aborted) { setSettings(result); setEditing(true); } }
    catch (failure) { handleError(failure, signal); if (!signal.aborted) setOpen(true); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  async function save(form: HTMLFormElement) {
    const signal = lifecycle.current?.signal;
    if (!signal || busy) return;
    const data = new FormData(form);
    const provider = String(data.get("email_provider") || "");
    const body = { in_app_enabled: data.has("in_app_enabled"), popup_enabled: data.has("popup_enabled"),
      email_enabled: data.has("email_enabled"), frequency: data.get("frequency"), timezone: data.get("timezone"),
      digest_hour: Number(data.get("digest_hour")), digest_weekday: Number(data.get("digest_weekday")), digest_monthday: Number(data.get("digest_monthday")), lead_days: Number(data.get("lead_days")),
      ...(provider ? { email_provider: provider } : {}) };
    setBusy(true); setError("");
    try { const result = await api<PreferenceResponse>("notifications/preferences", { method: "PATCH", body: JSON.stringify(body), signal }); if (!signal.aborted) { setSettings(result); setEditing(false); await load(signal); } }
    catch (failure) { handleError(failure, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  async function sendTestEmail() {
    const signal = lifecycle.current?.signal;
    if (!signal || busy) return;
    setBusy(true); setError(""); setEmailTest("");
    try {
      const result = await api<{ status: string }>("notifications/test-email", { method: "POST", body: "{}", signal });
      if (!signal.aborted) setEmailTest(result.status === "SENT"
        ? "The mail service accepted your test email. Check your inbox and spam folder; inbox delivery is not yet confirmed."
        : result.status === "QUEUED" ? "Your test is queued for a later delivery attempt."
        : result.status === "UNKNOWN" || result.status === "SENDING"
          ? "The delivery result is uncertain. Check your inbox before requesting another test."
          : "The test was not sent. Check the delivery configuration and your current mailbox connection.");
    } catch (failure) { handleError(failure, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  function closePopup() { activePopup.current = null; setPopup(null); }
  const pref = settings?.preferences;
  const emailReady = !!settings?.email_readiness.configured && !!settings.verified_mailboxes.length;
  return <div className="reminder-center">
    <button type="button" className="icon-button reminder-bell" aria-label={`Reminders, ${inbox.unread_count} unread`} aria-expanded={open} onClick={() => { setOpen(!open); setError(""); }}><Bell size={18} />{inbox.unread_count > 0 && <span className="reminder-count">{inbox.unread_count > 99 ? "99+" : inbox.unread_count}</span>}</button>
    {open && <section className="reminder-popover panel" aria-label="Your reminders"><div className="reminder-heading"><strong>Your reminders</strong><div><button type="button" className="icon-button" title="Reminder settings" aria-label="Reminder settings" disabled={busy} onClick={() => void openSettings()}><Settings2 size={17} /></button><button type="button" className="icon-button" aria-label="Close reminders" onClick={() => setOpen(false)}><X size={17} /></button></div></div>
      {!!inbox.unread_count && <button type="button" className="reminder-text-button" disabled={busy} onClick={() => void markRead()}><CheckCheck size={15} />Mark all as read</button>}
      {!inbox.notifications.length && <p>No reminders yet. Upcoming preparation targets and source changes will appear here.</p>}
      <div className="reminder-items">{inbox.notifications.map(item => <article key={item.id} className={item.read_at ? "reminder-item read" : "reminder-item"}><small>{item.kind === "planning" ? "Planning reminder" : "Source update"}</small><strong>{item.title}</strong><p>{item.message}</p>{!item.read_at && <button type="button" className="reminder-text-button" disabled={busy} onClick={() => void markRead(item.id)}>Mark as read</button>}</article>)}</div>
      {error && <p role="alert" className="reminder-error">{error}</p>}</section>}
    {popup && <aside className="reminder-toast panel" role="status" aria-live="polite"><button type="button" className="icon-button reminder-close" aria-label="Dismiss reminder popup" onClick={closePopup}><X size={16} /></button><small>{popup.kind === "planning" ? "A preparation target is approaching" : "A source update for you"}</small><strong>{popup.title}</strong><p>{popup.message}</p><button type="button" className="reminder-text-button" onClick={() => { closePopup(); setOpen(true); }}>Review reminders</button></aside>}
    {editing && pref && <div className="reminder-overlay"><section ref={dialog} className="panel reminder-settings" role="dialog" aria-modal="true" aria-labelledby="reminder-settings-title"><div className="reminder-heading"><h2 id="reminder-settings-title">Reminder settings</h2><button type="button" className="icon-button" aria-label="Close reminder settings" onClick={() => setEditing(false)}><X size={18} /></button></div>
      <form onSubmit={event => { event.preventDefault(); void save(event.currentTarget); }}>
        <label className="reminder-checkbox"><input type="checkbox" name="in_app_enabled" defaultChecked={pref.in_app_enabled} />Show reminders in Staytus</label>
        <label className="reminder-checkbox"><input type="checkbox" name="popup_enabled" defaultChecked={pref.popup_enabled} />Show an in-app popup for new reminders</label>
        <div className="reminder-fields"><label>Update frequency<select name="frequency" defaultValue={pref.frequency}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="off">Off</option></select></label><label>Timezone<input name="timezone" defaultValue={pref.timezone} required maxLength={100} placeholder="America/New_York" /><button type="button" className="reminder-text-button" onClick={event => { const input = event.currentTarget.parentElement?.querySelector("input"); if (input) input.value = Intl.DateTimeFormat().resolvedOptions().timeZone; }}>Use device timezone</button></label><label>Digest hour<input type="number" name="digest_hour" min={0} max={23} defaultValue={pref.digest_hour} required /></label><label>Weekly digest day<select name="digest_weekday" defaultValue={pref.digest_weekday}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label><label>Monthly digest day<input type="number" name="digest_monthday" min={1} max={31} defaultValue={pref.digest_monthday} required /><small>Clamped to the last day of shorter months</small></label><label>Preparation reminder lead time<input type="number" name="lead_days" min={0} max={30} defaultValue={pref.lead_days} required /><small>Days before a Staytus planning target</small></label></div>
        <p className="reminder-help">Daily, weekly or monthly selects the email digest schedule. Off pauses new reminders. Popups appear as new items become available.</p>
        <label className="reminder-checkbox"><input type="checkbox" name="email_enabled" defaultChecked={pref.email_enabled && pref.email_consent_current} disabled={!emailReady} />Email me scheduled digests</label>
        {!!settings.verified_mailboxes.length && <label>Authorized mailbox<select name="email_provider" defaultValue={pref.email_provider || settings.verified_mailboxes[0].provider}>{settings.verified_mailboxes.map(item => <option key={item.provider} value={item.provider}>{item.email} ({item.provider})</option>)}</select></label>}
        {!emailReady && <p className="reminder-help">Email digests need a configured delivery service and an authorized mailbox.{onOpenConnections && <button type="button" className="reminder-text-button" onClick={() => { setEditing(false); callbacks.current.onOpenConnections?.(); }}>Open Connections</button>}</p>}
        {pref.email_enabled && !pref.email_consent_current && <p className="reminder-help">Your mailbox connection changed. Select the email option and save to authorize delivery to the current mailbox.</p>}
        <p className="reminder-help">Cloud checks continue when this page is closed. The current deployment processes reminders in a daily batch; your selected hour is the earliest eligible time, not an exact delivery appointment. Digests are sent only when eligible reminders exist. Popups appear while Staytus is open.</p>
        <button type="button" className="button secondary" disabled={busy || !emailReady || !pref.email_enabled || !pref.email_consent_current || pref.frequency === "off"} onClick={() => void sendTestEmail()}>Send me a test email</button>
        <p className="reminder-help">Save your email subscription first, then reopen these settings to request one test. Tests contain no immigration records or mailbox content and are limited to one per five minutes.</p>
        {emailTest && <p role="status" className="reminder-help">{emailTest}</p>}
        {error && <p role="alert" className="reminder-error">{error}</p>}<button type="submit" className="button primary" disabled={busy}>{busy ? "Saving…" : "Save reminder settings"}</button>
      </form></section></div>}
    {!open && !editing && error && <span className="reminder-sr-status" role="status">{error}</span>}
    <style jsx>{`
      .reminder-center { position: relative; }
      .reminder-bell { position: relative; }
      .reminder-count { position: absolute; top: -5px; right: -6px; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 20px; background: #9d6b70; color: white; font-size: 10px; line-height: 17px; }
      .reminder-popover { position: absolute; top: 44px; right: 0; z-index: 45; width: min(390px, calc(100vw - 28px)); padding: 20px; box-shadow: 0 15px 48px #26384b20; }
      .reminder-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 12px; }
      .reminder-heading > div { display: flex; gap: 4px; }
      .reminder-heading h2 { margin: 0; }
      .reminder-items { max-height: 55vh; overflow: auto; }
      .reminder-item { display: grid; gap: 7px; padding: 16px 0; border-top: 1px solid #dce2e6; }
      .reminder-item.read { opacity: .65; }
      .reminder-item small, .reminder-toast small { color: #687d8b; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
      .reminder-item p, .reminder-toast p, .reminder-popover > p { font-size: 13px; line-height: 1.55; margin: 0; }
      .reminder-text-button { display: inline-flex; align-items: center; justify-self: start; gap: 5px; padding: 3px 0; background: none; border: 0; color: #4c687f; font-size: 12px; cursor: pointer; text-align: left; }
      .reminder-toast { position: fixed; right: 28px; bottom: 28px; z-index: 60; width: min(390px, calc(100vw - 32px)); padding: 25px; display: grid; gap: 10px; box-shadow: 0 15px 48px #26384b20; }
      .reminder-close { position: absolute; top: 8px; right: 8px; }
      .reminder-toast strong { padding-right: 12px; }
      .reminder-overlay { position: fixed; inset: 0; background: #26384b45; z-index: 80; display: grid; place-items: center; padding: 20px; }
      .reminder-settings { width: min(580px, 100%); padding: 28px; max-height: 90vh; overflow: auto; }
      .reminder-settings form { display: grid; gap: 17px; }
      .reminder-settings label { display: grid; gap: 6px; font-size: 13px; }
      .reminder-settings .reminder-checkbox { display: flex; align-items: center; gap: 9px; }
      .reminder-checkbox input { width: 16px; height: 16px; }
      .reminder-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 17px; }
      .reminder-settings input:not([type=checkbox]), .reminder-settings select { width: 100%; padding: 9px 10px; border: 1px solid #d6dfe4; border-radius: 8px; background: #fff; color: inherit; }
      .reminder-help, .reminder-settings small { color: #73818b; font-size: 12px; line-height: 1.6; }
      .reminder-error { color: #9d535c; font-size: 13px; }
      .reminder-sr-status { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
      @media (max-width: 500px) { .reminder-fields { grid-template-columns: 1fr; } .reminder-toast { right: 16px; bottom: 16px; } }
    `}</style>
  </div>;
}

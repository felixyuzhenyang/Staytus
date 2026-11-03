"use client";
import { useEffect, useRef, useState } from "react";
import { CalendarDays, LoaderCircle, X } from "lucide-react";
import type { CalendarProvider, Connection, Deadline } from "@/lib/types";
import { date } from "@/lib/types";
import { canWriteCalendar } from "@/lib/calendar";
import { ErrorNotice, IconButton } from "./ui";

export default function CalendarReminderDialog({ deadline, connections, busy, error, onClose, onPreview, onConnections }: {
  deadline: Deadline; connections: Connection[]; busy: boolean; error: string;
  onClose: () => void; onPreview: (provider: CalendarProvider, reminderMinutes: number) => Promise<void>; onConnections: () => void;
}) {
  const firstConnected = connections.find(canWriteCalendar)?.provider;
  const [provider, setProvider] = useState<CalendarProvider>(firstConnected === "google" || firstConnected === "microsoft" || firstConnected === "icloud" ? firstConnected : "export");
  const [minutes, setMinutes] = useState(1440);
  const dialog = useRef<HTMLElement>(null);
  const ready = provider === "export" || canWriteCalendar(connections.find(item => item.provider === provider));
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
      if (event.key !== "Tab") return;
      const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), select, a[href]') || []);
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keyboard);
    return () => { document.removeEventListener("keydown", keyboard); previous?.focus(); };
  }, [busy, onClose]);
  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}>
    <section ref={dialog} className="modal panel" role="dialog" aria-modal="true" aria-labelledby="calendar-reminder-title" tabIndex={-1} onClick={event => event.stopPropagation()}>
      <div className="modal-heading"><div><span className="eyebrow">CALENDAR REMINDER</span><h2 id="calendar-reminder-title">Choose where it goes.</h2></div><IconButton title="Close calendar options" disabled={busy} onClick={onClose}><X size={20} /></IconButton></div>
      <ErrorNotice message={error} /><p><strong>{deadline.title}</strong><br />{date(deadline.date)}</p>
      <p className="muted">This date is a Staytus preparation reminder. Review current school requirements separately.</p>
      <div className="form-grid"><label>Calendar<select value={provider} onChange={event => setProvider(event.target.value as CalendarProvider)} disabled={busy}>
        <option value="export">Calendar file (.ics)</option><option value="google">Google Calendar</option><option value="microsoft">Outlook / Microsoft Calendar</option><option value="icloud">iCloud Calendar</option>
      </select></label><label>Alert before the date<select value={minutes} onChange={event => setMinutes(Number(event.target.value))} disabled={busy}>
        <option value={0}>On the date</option><option value={60}>1 hour before</option><option value={1440}>1 day before</option><option value={10080}>1 week before</option>
      </select></label></div>
      {!ready && <div className="note"><p>Calendar permission is needed for this account. <button className="text-button" type="button" disabled={busy} onClick={onConnections}>Open Connections</button></p></div>}
      <p className="muted">Google or Outlook events also appear in Apple Calendar when that account is enabled on your iPhone or Mac. You will review the exact action before it is created.</p>
      <div className="modal-actions"><button className="button secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="button primary" disabled={busy || !ready} onClick={() => void onPreview(provider, minutes)}>{busy ? <LoaderCircle className="spin" size={16} /> : <CalendarDays size={16} />}Preview reminder</button></div>
    </section>
  </div>;
}

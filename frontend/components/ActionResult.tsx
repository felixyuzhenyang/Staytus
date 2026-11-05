import { AlertCircle, CheckCircle2, Clock3, FileDown, XCircle } from "lucide-react";
import type { Approval } from "@/lib/types";
import { date } from "@/lib/types";
import { actionOutcome, calendarName, reminderText } from "@/lib/action-outcome";

export default function ActionResult({ approval }: { approval: Approval }) {
  const outcome = actionOutcome(approval);
  if (!outcome) return null;
  const Icon = { success: CheckCircle2, download: FileDown, warning: AlertCircle, error: XCircle, pending: Clock3 }[outcome.icon];
  const receipt = approval.receipt;
  const provider = receipt?.provider || approval.payload.provider;
  const eventDate = typeof receipt?.date === "string" ? receipt.date : approval.payload.date;
  const alert = reminderText(receipt?.reminder_minutes ?? approval.payload.reminder_minutes);
  const detail = (title: string, value: unknown) => typeof value === "string" && value.trim()
    ? <div key={title}><dt>{title}</dt><dd>{value}</dd></div> : null;
  return <section className={`action-result ${outcome.tone}`} aria-label="Action result" role="status">
    <div className="action-result-heading"><Icon size={22} aria-hidden="true" /><h3>{outcome.title}</h3></div>
    <p>{outcome.message}</p>
    <dl className="action-result-details">
      {detail(approval.kind === "email" ? "Subject" : "Reminder", approval.payload.title || approval.payload.subject)}
      {approval.kind === "calendar" && <>
        {detail("Date", typeof eventDate === "string" ? date(eventDate) : null)}
        {detail("Alert", alert)}
        {detail("Destination", receipt?.mode === "file_export" ? "Calendar file (.ics)" : calendarName(provider))}
        {detail("Calendar", receipt?.calendar_name)}
      </>}
      {detail("Connected account", approval.target_account)}
    </dl>
  </section>;
}

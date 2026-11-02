import { Check, ChevronRight, Clock3 } from "lucide-react";
import type { AuditEvent } from "@/lib/types";
import { date, label } from "@/lib/types";
import { Badge, Empty } from "./ui";

export default function ActivityLog({ events }: { events: AuditEvent[] }) {
  return <section className="panel audit-panel"><div className="section-heading inside"><h2>Your activity trail</h2><Badge>{events.length} events</Badge></div>{events.map(event => <details className="audit-event" key={event.id}><summary><span className="audit-icon"><Check size={15} /></span><div><strong>{label(event.action || "Activity")}</strong><small>{date(event.created_at)}{event.created_at ? ` · ${new Date(event.created_at).toLocaleTimeString()}` : ""}</small></div><ChevronRight size={16} /></summary><div className="audit-data">{event.correlation_id && <small>Correlation ID: {event.correlation_id}</small>}<pre>{JSON.stringify(event.detail || {}, null, 2)}</pre></div></details>)}{!events.length && <Empty icon={Clock3} title="Your activity starts here" text="Profile updates, source retrieval, and approved actions create an inspectable trail." />}</section>;
}

import { ArrowRight, CalendarDays, FileCheck2, ShieldCheck } from "lucide-react";
import type { Approval } from "@/lib/types";
import { date, label } from "@/lib/types";
import { Badge, Empty } from "./ui";

export default function ApprovalsPanel({ approvals, busy, onInspect }: { approvals: Approval[]; busy: boolean; onInspect: (approval: Approval) => Promise<void> }) {
  return <><div className="info-strip"><ShieldCheck size={18} /><p>Inspect the recipient, content, and destination of each action before approving. An approval applies only to the exact preview and expires at the time shown.</p></div>
    <div className="approval-list">{approvals.map(approval => <div className="panel approval-row" key={approval.id}><span className="tile-icon">{approval.kind === "calendar" ? <CalendarDays size={23} /> : <FileCheck2 size={23} />}</span><div className="approval-details"><h3>{String(approval.payload.title || approval.payload.subject || label(approval.kind))}</h3><p>{label(approval.kind)} · Expires {date(approval.expires_at)}</p><small>Payload {approval.payload_hash.slice(0, 12)}…</small></div><Badge tone={approval.status === "SUCCEEDED" ? "green" : ["REJECTED", "EXPIRED"].includes(approval.status) ? "neutral" : "amber"}>{label(approval.status)}</Badge><button className="button secondary compact" disabled={busy} onClick={() => void onInspect(approval)}>Inspect <ArrowRight size={14} /></button></div>)}</div>
    {!approvals.length && <Empty icon={FileCheck2} title="Nothing waiting for you" text="Prepare a calendar reminder from your dashboard, or ask your assistant to prepare an available action." />}
  </>;
}

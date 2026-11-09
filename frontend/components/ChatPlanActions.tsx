import { CalendarDays, AlertCircle } from "lucide-react";
import type { Deadline, GuidedPlan } from "@/lib/types";
import { date } from "@/lib/types";

export default function ChatPlanActions({ plan, profileVersion, busy, onRemind }: {
  plan: GuidedPlan; profileVersion?: number; busy: boolean; onRemind: (target: Deadline) => void;
}) {
  const stale = plan.profile_version !== profileVersion;
  return <div className="chat-plan-actions">
    <div className="plan-provenance"><span>Personal plan · {date(plan.generated_at)}</span><span>{plan.retrieved_source_count} retrieved source{plan.retrieved_source_count === 1 ? "" : "s"}</span></div>
    <p className="muted">Based on your saved profile and the details entered for this plan. Official-source snapshots may still need review.</p>
    {plan.record_checks.filter(check => check.state === "review_required").map(check => <p className="plan-attention" key={check.id}><AlertCircle size={15} />{check.message}</p>)}
    {stale && <p className="plan-attention">Your profile has changed. Generate a new plan before preparing its reminders.</p>}
    {!plan.timeline && plan.calendar_targets.length > 0 && <><h4>Suggested preparation reminders</h4><p className="muted">These are internal planning dates, not legal filing deadlines. Review the destination and exact event before approving.</p><div className="plan-reminders">{plan.calendar_targets.map(target => <div className="plan-reminder" key={target.workflow}><div><strong>{target.title}</strong><span>{date(target.date)}</span><details><summary>How this date was chosen</summary><p>{target.trace?.join(" ")}</p></details></div><button className="button secondary compact" disabled={busy || stale} onClick={() => onRemind(target)}><CalendarDays size={14} />Add to calendar</button></div>)}</div></>}
    {!plan.calendar_targets.length && <p className="muted">No dated reminder can be prepared from these facts yet. Confirm the missing dates with your adviser, then generate a new plan.</p>}
    {!!plan.missing_information.length && <details className="plan-questions"><summary>Questions to confirm ({plan.missing_information.length})</summary><ul>{plan.missing_information.map(item => <li key={item.field}>{item.question}</li>)}</ul></details>}
  </div>;
}

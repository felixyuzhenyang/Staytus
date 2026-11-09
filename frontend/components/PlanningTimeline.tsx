import { CalendarDays, ChevronDown, ExternalLink } from "lucide-react";
import type { Deadline, GuidedPlan } from "@/lib/types";
import { date, label } from "@/lib/types";

const dateLabels = { preparation_target: "Preparation target", saved_date: "Saved date", user_goal: "Your goal", to_confirm: "To confirm", sequence: "Process step" };

export default function PlanningTimeline({ plan, profileVersion, busy, onRemind }: {
  plan: GuidedPlan; profileVersion?: number; busy: boolean; onRemind: (target: Deadline) => void;
}) {
  const timeline = plan.timeline;
  if (!timeline) return null;
  const stale = plan.profile_version !== profileVersion;
  return <section className="planning-timeline" aria-label="Personal planning timeline">
    <div className="timeline-heading"><h4>Your planning timeline</h4><span>{timeline.nodes.length} steps</span></div>
    <p className="timeline-notice">{timeline.notice}</p>
    <ol className="timeline-list">{timeline.nodes.map((node, index) => <li className={`timeline-node ${node.date_kind}`} key={node.id}>
      <span className="timeline-marker" aria-hidden="true">{index + 1}</span>
      <div className="timeline-node-content"><div className="timeline-date"><strong>{node.date ? date(node.date) : node.time_label}</strong>{node.date_kind !== "to_confirm" && <span>{dateLabels[node.date_kind]}</span>}{node.node_role === "contextual" && <span className="timeline-personalized">Added for your situation</span>}</div>
        <h5>{node.title}</h5><p>{node.explanation}</p>
        <details className="timeline-evidence"><summary>Date basis and official sources <ChevronDown size={13} /></summary>
          <div>{node.selection_reason && <><h6>Why this step was included</h6><p>{node.selection_reason}</p></>}<h6>{node.date ? "How this date was chosen" : "What determines the timing"}</h6><ul>{node.basis.map((item, key) => <li key={key}>{item}</li>)}</ul>
            {!!node.depends_on.length && <p><strong>Depends on:</strong> {node.depends_on.map(id => timeline.nodes.find(item => item.id === id)?.title).filter(Boolean).join("; ")}</p>}
            <h6>Official references</h6>{node.sources.length ? node.sources.map(source => <div className="timeline-source" key={source.source_id || source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}<ExternalLink size={12} /></a><small>{label(source.capture_state || "not_captured")}{source.captured_at ? ` · Captured ${date(source.captured_at)}` : ""}</small></div>) : <p>School-specific sources are not available for this profile. Confirm the process with your school's adviser.</p>}
            {node.date_kind === "preparation_target" && <p className="timeline-calculation-note">The preparation buffer is a Staytus planning preference. The official references do not establish this reminder as a filing deadline.</p>}
          </div>
        </details>
        {node.calendar_target && <button className="button secondary compact timeline-calendar" disabled={busy || stale} onClick={() => onRemind(node.calendar_target!)}><CalendarDays size={14} />Add preparation reminder</button>}
      </div>
    </li>)}</ol>
  </section>;
}

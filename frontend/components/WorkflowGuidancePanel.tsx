import type { WorkflowGuidance } from "@/lib/types";
import { label } from "@/lib/types";
import { Badge } from "./ui";

type Workflow = WorkflowGuidance["workflows"][number];

const ACTIVE_STAGES = new Set(["considering", "preparing", "submitted", "approved", "active", "authorized", "denied"]);
const LOW_RELEVANCE = new Set(["not_planned", "not_currently_needed", "recorded_complete"]);

function attentionScore(workflow: Workflow) {
  let score = workflow.priority === "review_soon" ? 100 : 0;
  score += (workflow.record_checks || []).filter(check => check.state === "review_required").length * 70;
  if (workflow.saved_stage && ACTIVE_STAGES.has(workflow.saved_stage)) score += 45;
  if (workflow.applicability === "planned_travel") score += 35;
  if (workflow.applicability === "profile_review") score += 10;
  score += Math.min(workflow.missing_information.length, 5) * 4;
  if (LOW_RELEVANCE.has(workflow.applicability)) score -= 100;
  return score;
}

function WorkflowItem({ workflow }: { workflow: Workflow }) {
  return <details className="workflow-item"><summary>{workflow.title} · {label(workflow.priority)}</summary><p>{workflow.reason}</p><Badge tone="amber">{label(workflow.evidence_state)}</Badge>{workflow.saved_stage && <p className="field-hint">Saved stage: {label(workflow.saved_stage)}</p>}<ul>{workflow.checklist.map(item => <li key={item}>{item}</li>)}</ul>
    {!!workflow.record_checks?.length && <><h4>What your saved information suggests checking</h4><ul>{workflow.record_checks.map(check => <li key={check.id}>{check.message}</li>)}</ul></>}
    {!!workflow.missing_information.length && <><h4>Information to confirm</h4><ul>{workflow.missing_information.map(item => <li key={item.field}>{item.question}</li>)}</ul></>}
    <h4>Official sources and capture status</h4>{workflow.sources.map(source => <p key={source.source_id || source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><small> · {label(source.capture_state || "not captured")}</small></p>)}
  </details>;
}

export default function WorkflowGuidancePanel({ guidance }: { guidance?: WorkflowGuidance }) {
  if (!guidance?.workflows.length) return null;
  const ranked = guidance.workflows.map((workflow, index) => ({ workflow, index, score: attentionScore(workflow) }))
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .map(item => item.workflow);
  const priority = ranked.slice(0, 2), remaining = ranked.slice(2);
  return <section className="panel workflow-guidance"><div className="section-heading inside"><h2>Priority checklists</h2><Badge>Profile-specific</Badge></div>
    <p className="muted">The two most relevant checklists are shown first based on your saved dates, application stage and record checks. They help you prepare but do not determine eligibility, admission validity or an official filing deadline.</p>
    {priority.map(workflow => <WorkflowItem workflow={workflow} key={workflow.id} />)}
    {!!remaining.length && <details className="workflow-more"><summary>View {remaining.length} more {remaining.length === 1 ? "checklist" : "checklists"}</summary><div>{remaining.map(workflow => <WorkflowItem workflow={workflow} key={workflow.id} />)}</div></details>}
  </section>;
}

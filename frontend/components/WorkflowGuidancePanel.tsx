import type { WorkflowGuidance } from "@/lib/types";
import { label } from "@/lib/types";
import { Badge } from "./ui";

export default function WorkflowGuidancePanel({ guidance }: { guidance?: WorkflowGuidance }) {
  if (!guidance?.workflows.length) return null;
  return <section className="panel workflow-guidance"><div className="section-heading inside"><h2>Your situation and next questions</h2><Badge>Profile-specific</Badge></div>
    <p className="muted">These checklists help you prepare and identify missing information. They do not determine eligibility, admission validity or an official filing deadline.</p>
    {guidance.workflows.map(workflow => <details className="workflow-item" key={workflow.id}><summary>{workflow.title} · {label(workflow.priority)}</summary><p>{workflow.reason}</p><Badge tone="amber">{label(workflow.evidence_state)}</Badge>{workflow.saved_stage && <p className="field-hint">Saved stage: {label(workflow.saved_stage)}</p>}<ul>{workflow.checklist.map(item => <li key={item}>{item}</li>)}</ul>
      {!!workflow.record_checks?.length && <><h4>What your saved information suggests checking</h4><ul>{workflow.record_checks.map(check => <li key={check.id}>{check.message}</li>)}</ul></>}
      {!!workflow.missing_information.length && <><h4>Information to confirm</h4><ul>{workflow.missing_information.map(item => <li key={item.field}>{item.question}</li>)}</ul></>}
      <h4>Official sources and capture status</h4>{workflow.sources.map(source => <p key={source.source_id || source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><small> · {label(source.capture_state || "not captured")}</small></p>)}
    </details>)}
  </section>;
}

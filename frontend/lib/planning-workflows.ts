import type { PlanningWorkflow, Profile } from "./types";

export const planningWorkflows: { id: PlanningWorkflow; title: string; description: string }[] = [
  { id: "travel", title: "Plan a trip abroad", description: "Documents, travel signature and return checks" },
  { id: "opt", title: "Plan OPT / EAD", description: "Prepare, track an application or review your EAD" },
  { id: "extension", title: "Extend my program", description: "Documents, adviser questions and preparation dates" },
  { id: "academic_training", title: "Plan Academic Training", description: "J-1 student training and sponsor review" },
  { id: "scholar", title: "Review my appointment", description: "J-1 scholar dates, sponsor and next steps" },
];
export function availableWorkflows(profile: Profile) {
  return planningWorkflows.filter(item => item.id !== "opt" || profile.status_type === "F-1")
    .filter(item => item.id !== "academic_training" || profile.status_type === "J-1 student")
    .filter(item => item.id !== "scholar" || profile.status_type === "J-1 scholar");
}

type PlanningField = { key: string; label: string; type?: "date"; required?: boolean; options?: string[] };
export function workflowFields(workflow: PlanningWorkflow, profile: Profile): PlanningField[] {
  if (workflow === "travel") return [
    { key: "travel_destination", label: "Destination country / countries", required: true },
    { key: "travel_date", label: "Departure from the US", type: "date", required: true },
    { key: "return_date", label: "Return to the US", type: "date", required: true },
    { key: "travel_signature_date", label: `Latest ${profile.status_type === "F-1" ? "I-20" : "DS-2019"} travel signature`, type: "date" },
    { key: "passport_expiry", label: "Passport expiration", type: "date" },
    { key: "visa_expiry", label: "US entry visa expiration (if applicable)", type: "date" },
    ...(profile.status_type === "F-1" ? [
      { key: "f1_activity", label: "Current activity", options: ["unknown", "studying", "post_completion_opt", "stem_opt", "other"] },
      { key: "opt_stage", label: "OPT application stage", options: ["unknown", "not_planning", "considering", "preparing", "submitted", "approved", "active", "completed", "denied", "withdrawn"] },
      { key: "ead_end", label: "Current EAD end (if applicable)", type: "date" as const },
    ] : []),
  ];
  if (workflow === "opt") return [
    { key: "opt_stage", label: "Where are you in the process?", options: ["unknown", "not_planning", "considering", "preparing", "submitted", "approved", "active", "completed", "denied", "withdrawn"] },
    { key: "opt_type", label: "Application type", options: ["unknown", "pre_completion", "post_completion", "stem_extension"] },
    { key: "f1_activity", label: "Current activity", options: ["unknown", "studying", "post_completion_opt", "stem_opt", "other"] },
    { key: "academic_completion_date", label: "Academic completion (confirm with school)", type: "date" },
    { key: "opt_requested_start", label: "Requested OPT start", type: "date" },
    { key: "dso_recommendation_date", label: "DSO recommendation date", type: "date" },
    { key: "opt_submitted_date", label: "Application submitted", type: "date" },
    { key: "ead_start", label: "Current EAD start", type: "date" },
    { key: "ead_end", label: "Current EAD end", type: "date" },
  ];
  if (workflow === "extension") return [
    { key: "extension_stage", label: "Extension stage", options: ["unknown", "not_needed", "considering", "preparing", "submitted", "completed"] },
    { key: "extension_requested_end", label: "Proposed new program end", type: "date" },
  ];
  if (workflow === "academic_training") return [
    { key: "academic_training_stage", label: "Academic Training stage", options: ["unknown", "not_planning", "considering", "preparing", "submitted", "authorized", "active", "completed"] },
    { key: "sponsor_name", label: "DS-2019 sponsor" },
    { key: "academic_completion_date", label: "Academic completion", type: "date" },
    { key: "academic_training_start", label: "Proposed / authorized training start", type: "date" },
    { key: "academic_training_end", label: "Proposed / authorized training end", type: "date" },
    { key: "sponsor_authorized_on", label: "Written sponsor authorization date", type: "date" },
  ];
  return [
    { key: "j1_category", label: "DS-2019 category", options: ["unknown", "research_scholar", "professor", "short_term_scholar", "other"] },
    { key: "sponsor_name", label: "DS-2019 sponsor" }, { key: "host_department", label: "Host department" },
    { key: "extension_stage", label: "Extension stage", options: ["unknown", "not_needed", "considering", "preparing", "submitted", "completed"] },
    { key: "extension_requested_end", label: "Proposed appointment end", type: "date" },
  ];
}

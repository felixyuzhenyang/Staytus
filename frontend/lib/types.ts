export type Account = { id: string; email: string; name: string };
export type PlanningDetails = {
  f1_activity?: string; opt_stage?: string; opt_type?: string; academic_completion_date?: string | null;
  dso_recommendation_date?: string | null; opt_submitted_date?: string | null; opt_requested_start?: string | null;
  ead_start?: string | null; ead_end?: string | null; training_history_reviewed?: boolean | null; stem_eligibility_reviewed?: boolean | null;
  post_completion_plan?: string; i94_admission_type?: string; i94_admit_until_date?: string | null;
  passport_expiry?: string | null; visa_expiry?: string | null; return_date?: string | null;
  travel_destination?: string | null; visa_renewal_planned?: boolean | null;
  extension_stage?: string; extension_requested_end?: string | null; j1_category?: string;
  sponsor_name?: string | null; host_department?: string | null; academic_training_stage?: string;
  academic_training_start?: string | null; academic_training_end?: string | null; sponsor_authorized_on?: string | null;
};
export type Profile = {
  id: string; name: string; school: string; status_type: string; nationality?: string;
  program_start: string; program_end: string; graduation_date?: string | null;
  travel_date?: string | null; travel_signature_date?: string | null;
  notification_frequency?: string; email?: string; version?: number;
  planning_details?: PlanningDetails;
};
export type AuthState = { account: Account; profile: Profile | null; needs_onboarding: boolean; role: string };
export type Deadline = {
  id?: string; title: string; workflow: string; date?: string; recommended_start?: string;
  rule_version?: string; trace?: string[]; is_planning_buffer?: boolean;
  source?: { title: string; url: string; verified_at?: string | null };
  description?: string;
};
export type Task = { id?: string; title: string; status: string; due_date?: string };
export type Notice = {
  id: string; title?: string; message?: string; created_at?: string;
  old_date?: string; new_date?: string; data?: { old_date?: string; new_date?: string };
};
export type WorkflowSource = { source_id?: string; title: string; url: string; capture_state?: string; policy_status?: string; reviewed?: boolean; stale?: boolean; captured_at?: string | null };
export type WorkflowGuidance = { profile_version?: number; scope?: string; workflows: { id: string; title: string; category?: string; applicability: string; reason: string; priority: string; saved_stage?: string; planning_rule_version?: string; record_checks?: { id: string; message: string; state: string; fields: string[] }[]; checklist: string[]; missing_information: { field: string; question: string; required_for?: string }[]; evidence_state: string; sources: WorkflowSource[]; legal_deadline: null; eligibility_determined: boolean }[] };
export type DashboardData = { profile: Profile; deadlines: Deadline[]; tasks: Task[]; notifications: Notice[]; workflow_guidance?: WorkflowGuidance };
export type Citation = { title?: string; url?: string; source_url?: string; status?: string; verified_at?: string | null };
export type Policy = Citation & {
  id: string; title: string; text: string; status: string; reviewed: boolean;
  source_url: string; version?: string | number; fixture?: boolean; fictional?: boolean;
  source_authority?: "university" | "government" | string;
  freshness?: string; created_at?: string; captured_at?: string;
};
export type SourceStatus = { id: string; title: string; source_url: string; authority?: string; freshness: string; last_attempt_at?: string | null; last_success_at?: string | null; last_error?: string | null; review_status: string; reviewed: boolean; captured_at?: string | null };
export type Approval = {
  id: string; kind: string; status: string; payload: Record<string, unknown>; payload_hash: string;
  expires_at: string; created_at?: string; receipt?: Record<string, unknown> | null; target_account?: string | null;
};
export type AuditEvent = { id: string; action?: string; created_at?: string; detail?: unknown; correlation_id?: string };
export type Review = { id: string; title?: string; status: string; old_text?: string; new_text?: string; diff_summary?: string };
export type ChatMessage = {
  role: "user" | "assistant"; message: string; citations?: Citation[]; tools?: unknown[]; approval?: Approval | null;
  planning?: GuidedPlan;
};
export type PlanningWorkflow = "travel" | "opt" | "extension" | "academic_training" | "scholar";
export type PlanningRequest = { workflow: PlanningWorkflow; profile_version: number; goal_date?: string | null; travel_date?: string | null;
  travel_signature_date?: string | null; planning_details: PlanningDetails; notes: string };
export type GuidedPlan = { workflow: PlanningWorkflow; title: string; profile_version: number; generated_at: string;
  inputs: PlanningRequest; uses_temporary_details: boolean; calendar_targets: Deadline[]; retrieved_source_count: number;
  record_checks: { id: string; message: string; state: string }[];
  missing_information: { field: string; question: string }[]; sources: WorkflowSource[];
  timeline?: { version: string; layout: string; notice: string; nodes: {
    id: string; title: string; date: string | null; date_kind: "preparation_target" | "saved_date" | "user_goal" | "to_confirm" | "sequence";
    time_label: string; explanation: string; basis: string[]; depends_on: string[]; sources: WorkflowSource[];
    calendar_target: Deadline | null; rule_version: string;
  }[] } };
export type ChatResponse = Omit<ChatMessage, "role"> & { mode: string; conversation_id?: string; thread_id?: string };
export type ChatHistory = { conversation_id?: string | null; messages: ChatMessage[]; hide_assistant_updates: boolean };
export type AssistantUpdate = { id: string; created_at: string; read_at: string | null; outdated: boolean;
  profile_version: number; trigger_kinds: string[]; citations: Citation[];
  content: { title: string; summary: string; why_it_matters: string; next_steps: string[]; questions: string[]; omitted_unverified_details?: boolean } };
export type AssistantPreferences = { enabled: boolean; language: "en" | "zh"; active?: boolean; schedule?: string };
export type AssistantUpdatePage = { updates: AssistantUpdate[]; next_before: string | null; unread_count: number };
export type Connection = {
  provider: string; configured: boolean; connected: boolean; email?: string; scopes?: string[]; last_sync_at?: string;
  agent_access?: boolean; content_analysis_enabled?: boolean;
  connection_id?: string | null;
  calendar_write?: boolean;
  email_identity_verified?: boolean;
  setup?: { missing: string[]; errors: string[]; callback_uri?: string | null; frontend_url?: string; application_type?: string; testing_note?: string };
};
export type CalendarProvider = "export" | "google" | "microsoft" | "icloud";
export type OAuthCapability = "mail_read" | "mail_draft" | "calendar_write";
export type MailMessage = { id: string; subject?: string; from?: string; received_at?: string; snippet?: string };
export type MailAnalysis = {
  id: string; provider: string; subject?: string; from?: string; received_at?: string;
  generated_at: string; expires_at: string; model?: string;
  analysis: { summary: string; why_relevant: string;
    action_items: { text: string; due_date?: string | null; needs_confirmation: boolean }[];
    dates: { date_text: string; meaning: string; exact_quote: string }[];
    questions_to_confirm: string[]; needs_human_review: boolean };
};
export type Tab = "overview" | "assistant" | "policies" | "approvals" | "updates" | "profile" | "review" | "audit" | "connections";

export function date(value?: string | null) {
  if (!value) return "Not provided";
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(parsed);
}
export function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase()); }

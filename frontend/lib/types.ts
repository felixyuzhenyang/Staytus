export type Account = { id: string; email: string; name: string };
export type Profile = {
  id: string; name: string; school: string; status_type: string; nationality?: string;
  program_start: string; program_end: string; graduation_date?: string | null;
  travel_date?: string | null; travel_signature_date?: string | null;
  notification_frequency?: string; email?: string; version?: number;
};
export type AuthState = { account: Account; profile: Profile | null; needs_onboarding: boolean; role: string };
export type Deadline = {
  id?: string; title: string; workflow: string; date?: string; recommended_start?: string;
  rule_version?: string; trace?: string[]; is_planning_buffer?: boolean;
  source?: { title: string; url: string; verified_at?: string | null };
};
export type Task = { id?: string; title: string; status: string; due_date?: string };
export type Notice = {
  id: string; title?: string; message?: string; created_at?: string;
  old_date?: string; new_date?: string; data?: { old_date?: string; new_date?: string };
};
export type WorkflowSource = { source_id?: string; title: string; url: string; capture_state?: string; policy_status?: string; reviewed?: boolean; stale?: boolean; captured_at?: string | null };
export type WorkflowGuidance = { profile_version?: number; scope?: string; workflows: { id: string; title: string; category?: string; applicability: string; reason: string; priority: string; checklist: string[]; missing_information: { field: string; question: string; required_for?: string }[]; evidence_state: string; sources: WorkflowSource[]; legal_deadline: null; eligibility_determined: boolean }[] };
export type DashboardData = { profile: Profile; deadlines: Deadline[]; tasks: Task[]; notifications: Notice[]; workflow_guidance?: WorkflowGuidance };
export type Citation = { title?: string; url?: string; source_url?: string; status?: string; verified_at?: string | null };
export type Policy = Citation & {
  id: string; title: string; text: string; status: string; reviewed: boolean;
  source_url: string; version?: string | number; fixture?: boolean; fictional?: boolean;
  freshness?: string; created_at?: string; captured_at?: string;
};
export type SourceStatus = { id: string; title: string; source_url: string; freshness: string; last_attempt_at?: string | null; last_success_at?: string | null; last_error?: string | null; review_status: string; reviewed: boolean; captured_at?: string | null };
export type Approval = {
  id: string; kind: string; status: string; payload: Record<string, unknown>; payload_hash: string;
  expires_at: string; created_at?: string; receipt?: Record<string, unknown> | null; target_account?: string | null;
};
export type AuditEvent = { id: string; action?: string; created_at?: string; detail?: unknown; correlation_id?: string };
export type Review = { id: string; title?: string; status: string; old_text?: string; new_text?: string; diff_summary?: string };
export type ChatMessage = {
  role: "user" | "assistant"; message: string; citations?: Citation[]; tools?: unknown[]; approval?: Approval | null;
};
export type ChatResponse = Omit<ChatMessage, "role"> & { mode: string; conversation_id?: string; thread_id?: string };
export type Connection = {
  provider: string; configured: boolean; connected: boolean; email?: string; scopes?: string[]; last_sync_at?: string;
  agent_access?: boolean;
  connection_id?: string | null;
  calendar_write?: boolean;
  email_identity_verified?: boolean;
  setup?: { missing: string[]; errors: string[]; callback_uri?: string | null; frontend_url?: string; application_type?: string; testing_note?: string };
};
export type CalendarProvider = "export" | "google" | "microsoft" | "icloud";
export type OAuthCapability = "mail_read" | "mail_draft" | "calendar_write";
export type MailMessage = { id: string; subject?: string; from?: string; received_at?: string; snippet?: string };
export type Tab = "overview" | "assistant" | "policies" | "approvals" | "updates" | "profile" | "review" | "audit" | "connections";

export function date(value?: string | null) {
  if (!value) return "Not provided";
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(parsed);
}
export function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase()); }

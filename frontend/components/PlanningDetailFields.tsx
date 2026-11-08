"use client";
import { useId, useState, type ReactNode } from "react";
import type { PlanningDetails, Profile } from "@/lib/types";
import CountrySelect from "./CountrySelect";

type FieldName = keyof PlanningDetails;
const unknown = ["unknown", "Not sure / not recorded"] as const;
const optStages = [unknown, ["not_planning", "Not planning to apply"], ["considering", "Considering OPT"],
  ["preparing", "Preparing an application"], ["submitted", "Submitted / awaiting a decision"],
  ["approved", "Approved / not yet started"], ["active", "Authorization is active"],
  ["completed", "Authorization completed"], ["denied", "Application denied"], ["withdrawn", "Application withdrawn"]];
const optGuide = "https://global.upenn.edu/isss/f-1-opt-faqs/";
const eadGuide = "https://www.uscis.gov/green-card/green-card-processes-and-procedures/employment-authorization-document";
function OfficialLink({ href, children }: { href: string; children: ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}<span className="sr-only"> (opens in a new tab)</span></a>;
}
function Group({ title, children }: { title: string; children: ReactNode }) {
  return <details className="planning-field-group"><summary>{title}<span>Optional</span></summary>{children}</details>;
}

export default function PlanningDetailFields({ value = {}, category, disabled, profileDates, onProfileDate }: {
  value?: PlanningDetails; category: string; disabled: boolean;
  profileDates: Pick<Profile, "graduation_date" | "travel_date" | "travel_signature_date">;
  onProfileDate: (field: "graduation_date" | "travel_date" | "travel_signature_date", value: string) => void;
}) {
  const [draft, setDraft] = useState<PlanningDetails>(value);
  const id = useId();
  function select(field: FieldName, title: string, options: readonly (readonly string[])[], hint?: ReactNode) {
    const hintId = `${id}-${field}-hint`;
    return <div className="profile-field"><label htmlFor={`${id}-${field}`}>{title}</label>
      <select id={`${id}-${field}`} name={`planning_details.${field}`} value={draft[field] == null ? "unknown" : String(draft[field])} disabled={disabled}
        aria-describedby={hint ? hintId : undefined} onChange={event => setDraft(old => ({ ...old, [field]: event.target.value }))}>
        {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select>{hint && <small id={hintId} className="field-hint">{hint}</small>}</div>;
  }
  function input(field: FieldName, title: string, type = "date", hint?: ReactNode, visible = true) {
    // Retain unsaved edits across stage changes. Hiding is not an erase request.
    const current = String(draft[field] ?? ""), name = `planning_details.${field}`;
    if (!visible) return <input type="hidden" name={name} value={current} disabled={disabled} />;
    const hintId = `${id}-${field}-hint`;
    return <div className="profile-field"><label htmlFor={`${id}-${field}`}>{title}</label>
      <input id={`${id}-${field}`} name={name} type={type} value={current} maxLength={type === "text" ? 120 : undefined} disabled={disabled}
        aria-describedby={hint ? hintId : undefined} onChange={event => setDraft(old => ({ ...old, [field]: event.target.value }))} />
      {hint && <small id={hintId} className="field-hint">{hint}</small>}</div>;
  }
  function profileDate(field: "graduation_date" | "travel_date" | "travel_signature_date", title: string) {
    return <label>{title}<input name={field} type="date" value={profileDates[field] || ""} onChange={event => onProfileDate(field, event.target.value)} disabled={disabled} /></label>;
  }
  const stage = draft.opt_stage || "unknown", atStage = draft.academic_training_stage || "unknown";
  const trackingOpt = !["unknown", "not_planning"].includes(stage);
  const applicationDates = trackingOpt && stage !== "considering";
  const submitted = ["submitted", "approved", "active", "completed", "denied", "withdrawn"].includes(stage);
  const savedApplicationDates = [draft.dso_recommendation_date, draft.opt_requested_start, draft.opt_submitted_date].some(Boolean);
  const optDateFields = <>
    {input("dso_recommendation_date", "DSO recommendation date", "date", <>DSO means Designated School Official: your school's international student adviser. Use the OPT recommendation date for this application; leave blank until it is issued. <OfficialLink href={optGuide}>Penn OPT guide</OfficialLink></>, applicationDates)}
    {input("opt_requested_start", stage === "preparing" ? "Planned OPT start date to request" : "OPT start date requested in your application", "date", <>The OPT authorization start date you plan to request, or already requested, from USCIS. This can differ from an internship start date and the approved EAD dates. <OfficialLink href={optGuide}>About OPT dates</OfficialLink></>, applicationDates)}
    {input("opt_submitted_date", "OPT application submission date", "date", "The date you submitted this application to USCIS, if known.", submitted)}
  </>;
  return <div className="planning-details">
    <div className="planning-section-heading"><h3>Your next chapter <span className="field-status">Optional</span></h3><p>Share what you know. Every field below is optional; expand a section when it is relevant.</p></div>
    <div className="form-grid">
      {category === "F-1" && <>
        {select("f1_activity", "What are you currently doing?", [unknown, ["studying", "Studying"], ["post_completion_opt", "On post-completion OPT"], ["stem_opt", "On STEM OPT"], ["other", "Another activity"]])}
        {select("opt_stage", "Are you preparing or tracking an OPT application?", optStages, "Your current activity and the application you are tracking can differ, for example while preparing a STEM extension.")}
        {trackingOpt ? select("opt_type", "Which OPT process are you considering or tracking?", [unknown, ["pre_completion", "Pre-completion OPT"], ["post_completion", "Initial post-completion OPT"], ["stem_extension", "STEM OPT extension"]]) : <input type="hidden" name="planning_details.opt_type" value={draft.opt_type || "unknown"} disabled={disabled} />}
      </>}
      {category !== "F-1" && <>
        {select("j1_category", "Category on your DS-2019", category === "J-1 student" ? [unknown, ["student", "College / university student"]] : [unknown, ["research_scholar", "Research scholar"], ["professor", "Professor"], ["short_term_scholar", "Short-term scholar"], ["other", "Another scholar category"]])}
        {input("sponsor_name", "Program sponsor", "text")}
        {category === "J-1 scholar" && input("host_department", "Host department", "text")}
        {category === "J-1 student" && select("academic_training_stage", "Are you preparing or tracking Academic Training?", [unknown, ["not_planning", "Not planning Academic Training"], ["considering", "Considering"], ["preparing", "Preparing a request"], ["submitted", "Request submitted"], ["authorized", "Sponsor authorization received"], ["active", "Training is active"], ["completed", "Training completed"]])}
      </>}
    </div>
    {category === "F-1" && <>
      {stage === "considering" && <p className="planning-stage-note">Just considering OPT? You can save this stage without any application dates. Add those once you start preparing an application.</p>}
      {applicationDates ? <Group title="OPT application dates"><p className="field-hint">Add dates only when known. A school recommendation and an application do not mean USCIS has approved work authorization.</p><div className="form-grid">{optDateFields}</div></Group> : <>{optDateFields}{savedApplicationDates && <p className="field-hint planning-saved-note">Previously saved application dates are retained. Select the relevant application stage to review or clear them.</p>}</>}
      <Group title="Work authorization card (EAD)"><p className="field-hint">EAD means Employment Authorization Document: the work authorization card issued by USCIS. Fill this section only if you have an OPT EAD, including an existing card while preparing a STEM extension. A submitted application alone is not an EAD. <OfficialLink href={eadGuide}>USCIS explanation</OfficialLink></p><div className="form-grid">
        {input("ead_start", "EAD valid from", "date", 'The "Valid From" date printed on your OPT EAD, not your intended job start date.')}
        {input("ead_end", "EAD card expires", "date", 'The "Card Expires" date printed on that card. Leave blank if you do not have a card yet.')}
      </div></Group>
    </>}
    {category === "J-1 student" && <Group title="Academic Training dates"><p className="field-hint">Add proposed or authorized training dates when relevant.</p><div className="form-grid">
      {input("academic_training_start", "Academic Training start", "date", undefined, !["unknown", "not_planning"].includes(atStage))}
      {input("academic_training_end", "Academic Training end", "date", undefined, !["unknown", "not_planning"].includes(atStage))}
      {input("sponsor_authorized_on", "Written sponsor authorization date", "date", undefined, ["authorized", "active", "completed"].includes(atStage))}
    </div></Group>}
    {category !== "J-1 scholar" && <Group title="Academic dates"><div className="form-grid">
      {profileDate("graduation_date", "Expected graduation date")}
      {input("academic_completion_date", "School-confirmed academic completion", "date", "When all degree requirements will be completed, as confirmed by your school; this can differ from the ceremony date.")}
    </div></Group>}
    <Group title="Program extension and next plans"><div className="form-grid">
      {select("extension_stage", "Do you need more program / appointment time?", [unknown, ["not_needed", "No extension currently needed"], ["considering", "Considering an extension"], ["preparing", "Preparing a request"], ["submitted", "Request submitted"], ["completed", "Completed — current document dates saved"]])}
      {input("extension_requested_end", "Requested new program end", "date", undefined, ["considering", "preparing", "submitted"].includes(draft.extension_stage || ""))}
      {category !== "J-1 scholar" && select("post_completion_plan", "What is your plan after completion?", [unknown, ["undecided", "Still deciding"], ...(category === "F-1" ? [["opt", "OPT"], ["stem_opt", "STEM OPT"]] : []), ["transfer", "Transfer"], ["new_program", "Another program"], ["departure", "Leave the United States"], ["other", "Another plan"]])}
    </div></Group>
    <Group title="Travel and document dates"><p className="field-hint">Add these when planning a trip. No document numbers or copies are needed.</p><div className="form-grid">
      {profileDate("travel_date", "Planned departure from the US")}
      {profileDate("travel_signature_date", "Last travel endorsement date")}
      {input("return_date", "Planned return to the US")}
      <CountrySelect name="planning_details.travel_destination" label="Destination country / countries" defaultValue={value.travel_destination || ""} required={false} multiple maxLength={80} disabled={disabled} />
      {input("passport_expiry", "Passport expiration")}{input("visa_expiry", "US entry visa expiration, if applicable")}
      {select("visa_renewal_planned", "Are you planning to apply for a new entry visa?", [["unknown", "Not sure / not applicable"], ["true", "Yes"], ["false", "No"]], "Visa expiration and permission to stay in the US are different. Exceptions require an individual review.")}
    </div></Group>
    <Group title="Admission record and adviser checks"><p className="field-hint">Copy only the type and date from your latest I-94, not its identifying number.{category === "F-1" && <> Your DSO is your school's designated international student adviser. <OfficialLink href={optGuide}>Penn adviser and OPT guidance</OfficialLink></>}</p><div className="form-grid">
      {select("i94_admission_type", "Latest I-94 admission notation", [unknown, ["duration_of_status", "D/S (duration of status)"], ["dated", "A specific Admit Until Date"]])}
      {draft.i94_admission_type === "dated" ? input("i94_admit_until_date", "I-94 Admit Until Date") : <input type="hidden" name="planning_details.i94_admit_until_date" value="" disabled={disabled} />}
      {category === "F-1" && <>
        {select("training_history_reviewed", "Has your DSO reviewed prior training / enrollment?", [["unknown", "Not recorded"], ["true", "Yes"], ["false", "Not yet"]])}
        {select("stem_eligibility_reviewed", "Has your DSO reviewed STEM qualifications?", [["unknown", "Not recorded / not applicable"], ["true", "Yes"], ["false", "Not yet"]])}
      </>}
    </div></Group>
  </div>;
}

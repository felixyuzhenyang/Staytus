"use client";
import { useState } from "react";
import type { PlanningDetails } from "@/lib/types";
import CountrySelect from "./CountrySelect";

type FieldName = keyof PlanningDetails;
const unknown = ["unknown", "Not sure / not recorded"] as const;
const optStages = [unknown, ["not_planning", "Not planning to apply"], ["considering", "Considering OPT"],
  ["preparing", "Preparing an application"], ["submitted", "Submitted / awaiting a decision"],
  ["approved", "Approved / not yet started"], ["active", "Authorization is active"],
  ["completed", "Authorization completed"], ["denied", "Application denied"], ["withdrawn", "Application withdrawn"]];

export default function PlanningDetailFields({ value = {}, category, disabled }: { value?: PlanningDetails; category: string; disabled: boolean }) {
  const [draft, setDraft] = useState<PlanningDetails>(value);
  function select(field: FieldName, title: string, options: readonly (readonly string[])[], hint?: string) {
    const current = draft[field];
    return <label>{title}<select name={`planning_details.${field}`} value={current == null ? "unknown" : String(current)} disabled={disabled}
      onChange={event => setDraft(old => ({ ...old, [field]: event.target.value }))}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>{hint && <small className="field-hint">{hint}</small>}</label>;
  }
  function input(field: FieldName, title: string, type = "date") {
    return <label>{title}<input name={`planning_details.${field}`} type={type} defaultValue={String(value[field] ?? "")} maxLength={type === "text" ? (field === "travel_destination" ? 80 : 120) : undefined} disabled={disabled} /></label>;
  }
  const stage = draft.opt_stage || "unknown", atStage = draft.academic_training_stage || "unknown";
  const optDates = !["unknown", "not_planning"].includes(stage);
  return <div className="planning-details">
    <div className="planning-section-heading"><h3>Your next chapter</h3><p>Optional details help tailor your checklist. Choose “Not sure” when you do not know; you can return to these later.</p></div>
    <div className="form-grid">
      {category !== "J-1 scholar" && input("academic_completion_date", "School-confirmed academic completion (not the ceremony)")}
      {category === "F-1" && <>
        {select("f1_activity", "What are you currently doing?", [unknown, ["studying", "Studying"], ["post_completion_opt", "On post-completion OPT"], ["stem_opt", "On STEM OPT"], ["other", "Another activity"]])}
        {select("opt_stage", "Are you preparing or tracking an OPT application?", optStages, "Your current activity and the application you are tracking can differ, for example while preparing a STEM extension.")}
        {optDates && <>
          {select("opt_type", "Which OPT process are you tracking?", [unknown, ["pre_completion", "Pre-completion OPT"], ["post_completion", "Initial post-completion OPT"], ["stem_extension", "STEM OPT extension"]])}
          {input("dso_recommendation_date", "DSO recommendation date for this application")}
          {["submitted", "approved", "active", "completed", "denied", "withdrawn"].includes(stage) && input("opt_submitted_date", "Application submission date")}
          {["considering", "preparing", "submitted"].includes(stage) && input("opt_requested_start", "Requested employment start")}
        </>}
        {(optDates || ["post_completion_opt", "stem_opt"].includes(draft.f1_activity || "")) && <>
          {input("ead_start", "Current EAD start date")}{input("ead_end", "Current EAD end date")}
        </>}
      </>}
      {category !== "F-1" && <>
        {select("j1_category", "Category on your DS-2019", category === "J-1 student" ? [unknown, ["student", "College / university student"]] : [unknown, ["research_scholar", "Research scholar"], ["professor", "Professor"], ["short_term_scholar", "Short-term scholar"], ["other", "Another scholar category"]])}
        {input("sponsor_name", "Program sponsor", "text")}
        {category === "J-1 scholar" && input("host_department", "Host department", "text")}
        {category === "J-1 student" && <>
          {select("academic_training_stage", "Are you preparing or tracking Academic Training?", [unknown, ["not_planning", "Not planning Academic Training"], ["considering", "Considering"], ["preparing", "Preparing a request"], ["submitted", "Request submitted"], ["authorized", "Sponsor authorization received"], ["active", "Training is active"], ["completed", "Training completed"]])}
          {!["unknown", "not_planning"].includes(atStage) && <>
            {input("academic_training_start", "Academic Training start")}{input("academic_training_end", "Academic Training end")}
            {["authorized", "active", "completed"].includes(atStage) && input("sponsor_authorized_on", "Written sponsor authorization date")}
          </>}
        </>}
      </>}
      {select("extension_stage", "Do you need more program / appointment time?", [unknown, ["not_needed", "No extension currently needed"], ["considering", "Considering an extension"], ["preparing", "Preparing a request"], ["submitted", "Request submitted"], ["completed", "Completed — current document dates saved"]])}
      {["considering", "preparing", "submitted"].includes(draft.extension_stage || "") && input("extension_requested_end", "Requested new program end")}
      {category !== "J-1 scholar" && select("post_completion_plan", "What is your plan after completion?", [unknown, ["undecided", "Still deciding"], ...(category === "F-1" ? [["opt", "OPT"], ["stem_opt", "STEM OPT"]] : []), ["transfer", "Transfer"], ["new_program", "Another program"], ["departure", "Leave the United States"], ["other", "Another plan"]])}
    </div>
    <details className="planning-field-group"><summary>Travel and document dates <span>Optional</span></summary><p className="field-hint">Departure and last travel endorsement are above. Return and document dates help identify what to review. No document numbers or copies are needed.</p><div className="form-grid">
      {input("return_date", "Planned return to the US")}
      <CountrySelect name="planning_details.travel_destination" label="Destination country / countries"
        defaultValue={value.travel_destination || ""} required={false} multiple maxLength={80} disabled={disabled} />
      {input("passport_expiry", "Passport expiration")}{input("visa_expiry", "US entry visa expiration, if applicable")}
      {select("visa_renewal_planned", "Are you planning to apply for a new entry visa?", [["unknown", "Not sure / not applicable"], ["true", "Yes"], ["false", "No"]], "Visa expiration and permission to stay in the US are different. Exceptions require an individual review.")}
    </div></details>
    <details className="planning-field-group"><summary>Admission record and adviser checks <span>Optional</span></summary><p className="field-hint">Copy only the type and date from your latest I-94, not its identifying number.</p><div className="form-grid">
      {select("i94_admission_type", "Latest I-94 admission notation", [unknown, ["duration_of_status", "D/S (duration of status)"], ["dated", "A specific Admit Until Date"]])}
      {draft.i94_admission_type === "dated" ? input("i94_admit_until_date", "I-94 Admit Until Date") : <input type="hidden" name="planning_details.i94_admit_until_date" value="" />}
      {category === "F-1" && <>
        {select("training_history_reviewed", "Has your DSO reviewed prior training / enrollment?", [["unknown", "Not recorded"], ["true", "Yes"], ["false", "Not yet"]])}
        {select("stem_eligibility_reviewed", "Has your DSO reviewed STEM qualifications?", [["unknown", "Not recorded / not applicable"], ["true", "Yes"], ["false", "Not yet"]])}
      </>}
    </div></details>
  </div>;
}

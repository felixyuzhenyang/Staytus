"use client";
import { useState } from "react";
import type { Profile } from "@/lib/types";
import PlanningDetailFields from "./PlanningDetailFields";
import CountrySelect from "./CountrySelect";

export default function ProfileFields({ profile, disabled = false }: { profile?: Partial<Profile>; disabled?: boolean }) {
  const [category, setCategory] = useState(profile?.status_type || "F-1");
  return <><div className="form-grid">
    <label>School<input name="school" defaultValue={profile?.school || "University of Pennsylvania"} required maxLength={100} disabled={disabled} /><small className="field-hint">Penn procedures are supported first. Other schools can save a profile, but school-specific actions may be unavailable.</small></label>
    <label>Current category<select name="status_type" value={category} onChange={event => setCategory(event.target.value)} disabled={disabled}><option>F-1</option><option>J-1 student</option><option>J-1 scholar</option></select><small className="field-hint">Changing category resets details that apply only to your previous category.</small></label>
    <CountrySelect defaultValue={profile?.nationality || ""} disabled={disabled} />
    <label>Update frequency<select name="notification_frequency" defaultValue={profile?.notification_frequency || "weekly"} disabled={disabled}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="off">Off</option></select></label>
    <label>Program start date<input name="program_start" type="date" defaultValue={profile?.program_start || ""} required disabled={disabled} /></label>
    <label>Program end date<input name="program_end" type="date" defaultValue={profile?.program_end || ""} required disabled={disabled} /></label>
    <label>Expected graduation date <span className="field-hint">Optional</span><input name="graduation_date" type="date" defaultValue={profile?.graduation_date || ""} disabled={disabled} /></label>
    <label>Planned travel date <span className="field-hint">Optional</span><input name="travel_date" type="date" defaultValue={profile?.travel_date || ""} disabled={disabled} /></label>
    <label>Last travel endorsement <span className="field-hint">Optional</span><input name="travel_signature_date" type="date" defaultValue={profile?.travel_signature_date || ""} disabled={disabled} /></label>
  </div><PlanningDetailFields key={category} category={category} disabled={disabled} value={!profile || profile.status_type === category ? profile?.planning_details : {}} /></>;
}

export function profileFormData(form: HTMLFormElement) {
  const result: Record<string, unknown> = {}, details: Record<string, unknown> = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (key.startsWith("planning_details.")) {
      const field = key.slice("planning_details.".length);
      details[field] = value === "" || (value === "unknown" && ["visa_renewal_planned", "training_history_reviewed", "stem_eligibility_reviewed"].includes(field)) ? null : value === "true" ? true : value === "false" ? false : value;
    } else result[key] = value || null;
  }
  result.planning_details = details;
  return result;
}

"use client";
import { useId, useState } from "react";
import type { Profile } from "@/lib/types";
import PlanningDetailFields from "./PlanningDetailFields";
import CountrySelect from "./CountrySelect";

export default function ProfileFields({ profile, disabled = false }: { profile?: Partial<Profile>; disabled?: boolean }) {
  const frequencyHint = `${useId()}-frequency-hint`;
  const [category, setCategory] = useState(profile?.status_type || "F-1");
  const [profileDates, setProfileDates] = useState({ graduation_date: profile?.graduation_date, travel_date: profile?.travel_date, travel_signature_date: profile?.travel_signature_date });
  return <><p className="profile-required-note">Fields marked * are required. Planning details below are optional.</p><div className="form-grid">
    {profile && <label>Display name *<input name="name" defaultValue={profile.name || ""} autoComplete="nickname" required maxLength={100} pattern=".*\S.*" title="Enter a name containing at least one non-space character" disabled={disabled} /><small className="field-hint">The name shown in your Staytus workspace.</small></label>}
    <label>School *<input name="school" defaultValue={profile?.school || "University of Pennsylvania"} required maxLength={100} disabled={disabled} /><small className="field-hint">Staytus currently supports the University of Pennsylvania. Support for more schools is planned for future versions.</small></label>
    <label>Current category *<select name="status_type" value={category} required onChange={event => setCategory(event.target.value)} disabled={disabled}><option>F-1</option><option>J-1 student</option><option>J-1 scholar</option></select><small className="field-hint">Changing category resets details that apply only to your previous category.</small></label>
    <CountrySelect label="Nationality / country or region *" defaultValue={profile?.nationality || ""} disabled={disabled} />
    <label>Update frequency<select name="notification_frequency" aria-label="Update frequency" aria-describedby={frequencyHint} defaultValue={profile?.notification_frequency || "weekly"} disabled={disabled}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="off">Off</option></select><small id={frequencyHint} className="field-hint">How often to receive reminder summaries after enabling email notifications. Policy checks run separately.</small></label>
    <label>Program start date *<input name="program_start" type="date" defaultValue={profile?.program_start || ""} required disabled={disabled} /></label>
    <label>Program end date *<input name="program_end" type="date" defaultValue={profile?.program_end || ""} required disabled={disabled} /></label>
  </div><PlanningDetailFields key={category} category={category} disabled={disabled} profileDates={profileDates} onProfileDate={(field, value) => setProfileDates(old => ({ ...old, [field]: value }))} value={!profile || profile.status_type === category ? profile?.planning_details : {}} /></>;
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

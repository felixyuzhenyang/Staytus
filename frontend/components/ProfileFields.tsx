import type { Profile } from "@/lib/types";

export default function ProfileFields({ profile, disabled = false }: { profile?: Partial<Profile>; disabled?: boolean }) {
  return <div className="form-grid">
    <label>School<input name="school" defaultValue={profile?.school || "University of Pennsylvania"} required maxLength={100} disabled={disabled} /><small className="field-hint">Penn procedures are supported first. Other schools can save a profile, but school-specific actions may be unavailable.</small></label>
    <label>Current category<select name="status_type" defaultValue={profile?.status_type || "F-1"} disabled={disabled}><option>F-1</option><option>J-1 student</option><option>J-1 scholar</option></select></label>
    <label>Nationality<input name="nationality" defaultValue={profile?.nationality || ""} required maxLength={64} disabled={disabled} /></label>
    <label>Update frequency<select name="notification_frequency" defaultValue={profile?.notification_frequency || "weekly"} disabled={disabled}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="off">Off</option></select></label>
    <label>Program start date<input name="program_start" type="date" defaultValue={profile?.program_start || ""} required disabled={disabled} /></label>
    <label>Program end date<input name="program_end" type="date" defaultValue={profile?.program_end || ""} required disabled={disabled} /></label>
    <label>Expected graduation date <span className="field-hint">Optional</span><input name="graduation_date" type="date" defaultValue={profile?.graduation_date || ""} disabled={disabled} /></label>
    <label>Planned travel date <span className="field-hint">Optional</span><input name="travel_date" type="date" defaultValue={profile?.travel_date || ""} disabled={disabled} /></label>
    <label>Last travel endorsement <span className="field-hint">Optional</span><input name="travel_signature_date" type="date" defaultValue={profile?.travel_signature_date || ""} disabled={disabled} /></label>
  </div>;
}

export function profileFormData(form: HTMLFormElement) {
  return Object.fromEntries([...new FormData(form).entries()].map(([key, value]) => [key, value || null]));
}

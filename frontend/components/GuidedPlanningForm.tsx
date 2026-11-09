"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircle, Sparkles, X } from "lucide-react";
import type { PlanningDetails, PlanningRequest, PlanningWorkflow, Profile } from "@/lib/types";
import { date, label } from "@/lib/types";
import { planningWorkflows, workflowFields } from "@/lib/planning-workflows";
import CountrySelect from "./CountrySelect";

export default function GuidedPlanningForm({ workflow, profile, busy, error, onClose, onGenerate }: {
  workflow: PlanningWorkflow; profile: Profile; busy: boolean; error: string; onClose: () => void;
  onGenerate: (message: string, request: PlanningRequest) => Promise<boolean>;
}) {
  const fields = workflowFields(workflow, profile);
  const option = planningWorkflows.find(item => item.id === workflow)!;
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(fields.map(field => [field.key,
    String((field.key === "goal_date" ? "" : field.key === "travel_date" || field.key === "travel_signature_date" ? profile[field.key] : profile.planning_details?.[field.key as keyof PlanningDetails]) || (field.options ? "unknown" : ""))])));
  const [notes, setNotes] = useState("");
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => { form.current?.querySelector<HTMLElement>(".country-trigger, input, select:not(.country-form-value)")?.focus(); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const request: PlanningRequest = { workflow, profile_version: profile.version || 1, planning_details: {}, notes };
    for (const field of fields) {
      const value = values[field.key]?.trim() || null;
      if (field.key === "goal_date" || field.key === "travel_date" || field.key === "travel_signature_date") request[field.key] = value;
      else Object.assign(request.planning_details, { [field.key]: value });
    }
    if (await onGenerate(`${option.title}.${notes.trim() ? ` ${notes.trim()}` : ""}`, request)) onClose();
  }
  return <form ref={form} className="guided-form" onSubmit={submit} aria-label={`${option.title} form`}>
    <div className="guided-heading"><div><span className="eyebrow">PERSONAL PLAN</span><h3>{option.title}</h3></div><button className="icon-button" type="button" onClick={onClose} disabled={busy} aria-label="Close planning form"><X size={18} /></button></div>
    <p className="guided-intro">Prefilled from your profile: {profile.status_type} · {profile.school} · Program ends {date(profile.program_end)}. These details are used for this plan only. Edit Profile to save changes for ongoing reminders.</p>
    <fieldset disabled={busy}><div className="form-grid">{fields.map(field => field.key === "travel_destination"
      ? <div key={field.key} className="form-field-wide"><CountrySelect name={field.key} label={field.label} value={values[field.key]}
        required={field.required} multiple maxLength={80} disabled={busy} onChange={value => setValues(previous => ({ ...previous, [field.key]: value }))} /></div>
      : <label key={field.key}>{field.label}{field.required ? " *" : ""}{field.options ? <select value={values[field.key]} onChange={event => setValues(previous => ({ ...previous, [field.key]: event.target.value }))}>{field.options.map(value => <option key={value} value={value}>{value === "unknown" ? "Not sure / not provided" : label(value)}</option>)}</select> : <input type={field.type || "text"} value={values[field.key]} required={field.required} maxLength={120} onChange={event => setValues(previous => ({ ...previous, [field.key]: event.target.value }))} />}</label>)}</div>
      <label className="guided-notes">Anything else to consider?<textarea value={notes} maxLength={1500} rows={2} onChange={event => setNotes(event.target.value)} placeholder="Your goals, questions, or preferred language" /></label>
    </fieldset>
    {error && <p className="chat-inline-error" role="alert">{error}</p>}
    <div className="guided-footer"><span>Fill in what you know. Missing details appear as To confirm in your timeline.</span><button className="button primary compact" disabled={busy}>{busy ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}{busy ? "Building your plan…" : "Generate my plan"}</button></div>
  </form>;
}

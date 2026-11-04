"use client";
import { Check, LoaderCircle, UserRound } from "lucide-react";
import type { FormEvent } from "react";
import type { Profile } from "@/lib/types";
import ProfileFields, { profileFormData } from "./ProfileFields";
import { Badge } from "./ui";

export default function ProfilePanel({ profile, busy, onSave }: { profile: Profile; busy: boolean; onSave: (data: Record<string, unknown>) => Promise<void> }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void onSave(profileFormData(event.currentTarget)); }
  return <form key={profile.version || profile.id} className="panel profile-form" onSubmit={submit}>
    <div className="form-heading"><span className="avatar"><UserRound size={21} /></span><div><h2>{profile.name}</h2><p>{profile.school}</p></div><Badge tone="blue">{profile.status_type}</Badge></div>
    <ProfileFields profile={profile} disabled={busy} />
    <p className="field-hint profile-help">Use dates from your current documents. Changing your saved dates updates your planning timeline; it does not change your university or government records.</p>
    <div className="form-actions"><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}Save profile</button></div>
  </form>;
}

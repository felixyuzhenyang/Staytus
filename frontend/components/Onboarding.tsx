"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, LoaderCircle, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Account, Profile } from "@/lib/types";
import ProfileFields, { profileFormData } from "./ProfileFields";
import { ErrorNotice, Logo } from "./ui";

export default function Onboarding({ account, onComplete, onLogout }: { account: Account; onComplete: (profile: Profile) => void; onLogout: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const body = profileFormData(event.currentTarget);
    setBusy(true); setError(""); const controller = new AbortController(); request.current = controller;
    try {
      const profile = await api<Profile>("profile", { method: "POST", body: JSON.stringify(body), signal: controller.signal });
      if (!controller.signal.aborted) onComplete(profile);
    } catch (problem) { if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : "Unable to save your profile."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <main className="onboarding"><header className="onboarding-header"><Logo /><button className="text-button" disabled={busy} onClick={() => void onLogout()}>Sign out</button></header>
    <section className="onboarding-copy"><span className="eyebrow">LET'S START WITH YOU</span><h1>A little context.<br />A clearer next step.</h1><p>Welcome, {account.name.split(" ")[0]}. Add your program details so your workspace can organize your dates and relevant sources.</p></section>
    <form className="panel onboarding-form" onSubmit={submit}><ErrorNotice message={error} /><ProfileFields disabled={busy} /><div className="note"><ShieldCheck size={18} /><p>You can update these details anytime. Connecting a mailbox is optional and requires its own authorization.</p></div><div className="form-actions"><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}Create my workspace</button></div></form>
  </main>;
}

"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, LoaderCircle, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api-client";
import type { AuthState } from "@/lib/types";
import { ErrorNotice, Logo } from "./ui";

export default function AuthScreen({ onAuthenticated, initialError, onRetry }: {
  onAuthenticated: (session: AuthState) => void; initialError?: string; onRetry: () => void;
}) {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const body = { email: String(form.get("email") || "").trim(), password: String(form.get("password") || ""), ...(register ? { name: String(form.get("name") || "").trim() } : {}) };
    const controller = new AbortController(); request.current = controller;
    try {
      const result = await api<AuthState>(register ? "auth/register" : "auth/login", { method: "POST", body: JSON.stringify(body), signal: controller.signal });
      if (!controller.signal.aborted) onAuthenticated(result);
    } catch (problem) {
      if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : "Unable to sign in.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  return <main className="welcome">
    <div className="welcome-left"><Logo /><div className="welcome-copy"><span className="eyebrow"><span className="tiny-dot" /> INTERNATIONAL, TOGETHER</span><h1>Your next chapter.<br /><em>A little clearer.</em></h1><p>One place for your status, important dates, and next steps. Built for international students and scholars finding their way.</p><div className="welcome-points"><span><ShieldCheck size={18} /> Your actions, your approval</span><span><BookOpen size={18} /> Sources you can inspect</span></div></div><p className="welcome-bottom">STAY CURIOUS. STAY CONNECTED. STAYTUS.</p><div className="orb orb-one" /><div className="orb orb-two" /></div>
    <section className="welcome-right auth-panel">
      <span className="eyebrow">YOUR OWN WORKSPACE</span><h2>{register ? "Make room for your next chapter." : "Welcome back."}</h2>
      <p className="muted">{register ? "Create your Staytus account, then add the dates and details that shape your plans." : "Sign in to your personal profile and pick up where you left off."}</p>
      <ErrorNotice message={error || initialError || ""} />
      {initialError && <button className="text-button auth-retry" onClick={onRetry}>Retry connection</button>}
      <form className="auth-form" onSubmit={submit}>
        {register && <label>Your name<input name="name" autoComplete="name" required minLength={1} maxLength={100} disabled={busy} /></label>}
        <label>Email address<input name="email" type="email" autoComplete="username" required maxLength={320} disabled={busy} /></label>
        <label>Password<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 12 : 1} maxLength={256} disabled={busy} /></label>
        {register && <p className="field-hint">Use at least 12 characters. This is your Staytus account, separate from your university login.</p>}
        <button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}{register ? "Create account" : "Sign in"}</button>
      </form>
      <p className="auth-toggle">{register ? "Already have an account?" : "New to Staytus?"} <button type="button" className="text-button" disabled={busy} onClick={() => { setRegister(value => !value); setError(""); }}>{register ? "Sign in" : "Create an account"}</button></p>
    </section>
  </main>;
}

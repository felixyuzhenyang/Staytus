"use client";
import { BookOpen, ExternalLink, RefreshCw, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Policy, SourceStatus } from "@/lib/types";
import { date, label } from "@/lib/types";
import { Badge, Empty } from "./ui";
import PolicyCard from "./PolicyCard";

export default function PoliciesPanel({ policies, sources, query, busy, onSearch, onCapture }: { policies: Policy[]; sources: SourceStatus[]; query: string; busy: boolean; onSearch: (query: string) => void; onCapture: () => Promise<void> }) {
  const [input, setInput] = useState(query);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); onSearch(input); }
  return <><form className="searchbar" onSubmit={submit}><Search size={19} /><input value={input} onChange={event => setInput(event.target.value)} placeholder="Search extension, travel, F-1, J-1…" aria-label="Search policies" maxLength={200} /><button className="button primary compact" disabled={busy}>Search</button></form>
    <div className="info-strip"><BookOpen size={18} /><p>These are captured source versions, not an assurance that a rule is currently effective. Check the original page, capture date, and review state.</p><button className="button secondary compact" disabled={busy} onClick={() => void onCapture()}><RefreshCw size={14} />Check official sources</button></div>
    <div className="policy-grid">{policies.map(policy => <PolicyCard key={policy.id} policy={policy} />)}</div>
    {!policies.length && <Empty icon={Search} title="No source captures to show" text="Check the official sources to capture published information, or try a broader search." />}
    <section className="panel source-status"><div className="section-heading inside"><h2>Official source checks</h2><Badge>{sources.length} sources</Badge></div>{sources.map(source => <article className="source-status-row" key={source.id}><div><a href={source.source_url} target="_blank" rel="noreferrer"><strong>{source.title}</strong> <ExternalLink size={12} /></a><p>Last checked {date(source.last_attempt_at)} · Last captured {date(source.last_success_at)}</p>{source.last_error && <p className="source-error">Latest check failed: {label(source.last_error)}</p>}</div><div className="source-badges"><Badge tone={source.freshness === "fresh_capture" ? "blue" : "neutral"}>{label(source.freshness)}</Badge><Badge tone={source.reviewed ? "green" : "amber"}>{label(source.review_status)}</Badge></div></article>)}{!sources.length && <p className="muted">No registered official sources were returned.</p>}</section>
  </>;
}

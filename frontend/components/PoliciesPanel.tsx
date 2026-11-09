"use client";
import { BookOpen, ChevronDown, ExternalLink, GraduationCap, Landmark, RefreshCw, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Policy, SourceStatus } from "@/lib/types";
import { date, label } from "@/lib/types";
import { Badge, Empty } from "./ui";
import PolicyCard from "./PolicyCard";

const policyGroups = [
  { id: "university", title: "Penn and school guidance", description: "University-specific processes, adviser instructions, and planning information.", icon: GraduationCap },
  { id: "government", title: "U.S. government guidance", description: "Federal immigration requirements and program information from registered government sources.", icon: Landmark },
  { id: "other", title: "Other official sources", description: "Additional registered sources that do not fit the school or government groups above.", icon: BookOpen },
] as const;

export default function PoliciesPanel({ policies, sources, query, busy, onSearch, onCapture }: { policies: Policy[]; sources: SourceStatus[]; query: string; busy: boolean; onSearch: (query: string) => void; onCapture: () => Promise<void> }) {
  const [input, setInput] = useState(query);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); onSearch(input); }
  const groups = policyGroups.map(group => ({ ...group, policies: policies.filter(policy =>
    group.id === "other" ? !["university", "government"].includes(policy.source_authority || "") : policy.source_authority === group.id) })).filter(group => group.policies.length);
  const captured = sources.filter(source => source.last_success_at).length;
  const failed = sources.filter(source => source.last_error).length;
  return <><form className="searchbar" onSubmit={submit}><Search size={19} /><input value={input} onChange={event => setInput(event.target.value)} placeholder="Search extension, travel, F-1, J-1…" aria-label="Search policies" maxLength={200} /><button className="button primary compact" disabled={busy}>Search</button></form>
    <div className="info-strip"><BookOpen size={18} /><p>These are captured source versions, not an assurance that a rule is currently effective. Check the original page, capture date, and review state.</p><button className="button secondary compact" disabled={busy} onClick={() => void onCapture()}><RefreshCw size={14} />Check official sources</button></div>
    <div className="policy-sections">{groups.map(group => { const Icon = group.icon; return <section className="policy-section" aria-labelledby={`policy-group-${group.id}`} key={group.id}>
      <div className="policy-section-heading"><span className="policy-section-icon"><Icon size={17} /></span><div><h2 id={`policy-group-${group.id}`}>{group.title}</h2><p>{group.description}</p></div><Badge>{group.policies.length} {group.policies.length === 1 ? "source" : "sources"}</Badge></div>
      <div className="policy-grid">{group.policies.map(policy => <PolicyCard key={policy.id} policy={policy} />)}</div>
    </section>; })}</div>
    {!policies.length && <Empty icon={Search} title="No source captures to show" text="Check the official sources to capture published information, or try a broader search." />}
    <details className="panel source-status"><summary className="source-status-summary"><div><h2>Official source checks</h2><p>Expand to review capture freshness, latest checks, and source review states.</p></div><div className="source-status-overview"><Badge>{sources.length} registered</Badge><span>{captured} captured{failed ? ` · ${failed} with a latest error` : ""}</span><ChevronDown size={16} /></div></summary><div className="source-status-body">{sources.map(source => <article className="source-status-row" key={source.id}><div><a href={source.source_url} target="_blank" rel="noreferrer"><strong>{source.title}</strong> <ExternalLink size={12} /></a><p>Last checked {date(source.last_attempt_at)} · Last captured {date(source.last_success_at)}</p>{source.last_error && <p className="source-error">Latest check failed: {label(source.last_error)}</p>}</div><div className="source-badges"><Badge tone={source.freshness === "fresh_capture" ? "blue" : "neutral"}>{label(source.freshness)}</Badge><Badge tone={source.reviewed ? "green" : "amber"}>{label(source.review_status)}</Badge></div></article>)}{!sources.length && <p className="muted">No registered official sources were returned.</p>}</div></details>
  </>;
}

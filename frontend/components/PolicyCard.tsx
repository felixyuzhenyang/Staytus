import { ExternalLink, ShieldCheck } from "lucide-react";
import type { Policy } from "@/lib/types";
import { date, label } from "@/lib/types";
import { Badge } from "./ui";

export default function PolicyCard({ policy }: { policy: Policy }) {
  const long = policy.text.length > 440;
  return <article className="panel policy-card">
    <div className="card-meta"><Badge tone={policy.reviewed && policy.status === "current_effective" ? "green" : "amber"}>{label(policy.status)}</Badge><span>{policy.version ? `v${policy.version}` : "Source capture"}</span></div>
    <h2>{policy.title}</h2>
    <p>{long ? `${policy.text.slice(0, 440)}…` : policy.text}</p>
    {long && <details className="policy-fulltext"><summary>Read captured excerpt</summary><p>{policy.text}</p></details>}
    <div className="policy-bottom"><span><ShieldCheck size={14} />{policy.reviewed ? "Human reviewed" : "Not yet reviewed"}</span><small>Captured: {date(policy.captured_at || policy.created_at)}</small>{policy.verified_at && <small>Reviewed: {date(policy.verified_at)}</small>}{policy.freshness && <small>{label(policy.freshness)}</small>}</div>
    <a className="text-button" href={policy.source_url} target="_blank" rel="noreferrer">Open original source <ExternalLink size={14} /></a>
    {(policy.fixture || policy.fictional) && <small className="fictional-label">Sample record — not a live policy source.</small>}
  </article>;
}

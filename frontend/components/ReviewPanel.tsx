import { ShieldCheck } from "lucide-react";
import type { Review } from "@/lib/types";
import { label } from "@/lib/types";
import { Badge, Empty } from "./ui";

export default function ReviewPanel({ reviews }: { reviews: Review[] }) {
  return <><div className="info-strip"><ShieldCheck size={18} /><p>Review captured source changes alongside the official publication. No active planning rule changes automatically because a page was updated.</p></div><div className="review-list">{reviews.map(review => <article className="panel review-card" key={review.id}><div className="card-meta"><Badge tone={review.status.toLowerCase().includes("approved") ? "green" : "amber"}>{label(review.status)}</Badge><small>{review.id}</small></div><h2>{review.title || "Captured policy change"}</h2>{review.diff_summary && <p>{review.diff_summary}</p>}<div className="diff-grid"><div><span className="eyebrow">PREVIOUS VERSION</span><p>{review.old_text || "No previous text available"}</p></div><div><span className="eyebrow">CAPTURED VERSION</span><p>{review.new_text || "No captured text available"}</p></div></div></article>)}</div>{!reviews.length && <Empty icon={ShieldCheck} title="Review queue is clear" text="Newly captured source versions that require review will appear here." />}</>;
}

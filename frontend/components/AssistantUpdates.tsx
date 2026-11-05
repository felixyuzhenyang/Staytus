import { ArrowRight, BookOpen, Check, Sparkles } from "lucide-react";
import type { AssistantUpdate } from "@/lib/types";
import { date, label } from "@/lib/types";

export default function AssistantUpdates({ updates, busy, onRead, onAsk }: {
  updates: AssistantUpdate[]; busy: boolean; onRead: (id: string) => Promise<void>; onAsk: (message: string) => void;
}) {
  if (!updates.length) return null;
  return <section className="assistant-updates" aria-label="Proactive assistant messages">
    <div className="assistant-update-heading"><Sparkles size={16} /><strong>Updates from your assistant</strong><span>Prepared while you were away</span></div>
    {updates.map(item => <details className={`assistant-update ${item.read_at ? "read" : "unread"}`} key={item.id} open={!item.read_at}>
      <summary><span>{!item.read_at && <span className="tiny-dot" />}<strong>{item.content.title}</strong></span><small>{date(item.created_at)} · AI-generated</small></summary>
      <div className="assistant-update-body"><p>{item.content.summary}</p><h4>Why this may matter to you</h4><p>{item.content.why_it_matters}</p>
        {item.outdated && <p className="plan-attention">Your profile, preferences or source event has changed since this message. Review the latest information before acting.</p>}
        <h4>Suggested next steps</h4><ol>{item.content.next_steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
        {!!item.content.questions.length && <><h4>What still needs confirmation</h4><ul>{item.content.questions.map((question, index) => <li key={index}>{question}</li>)}</ul></>}
        {item.citations.map((source, index) => <a className="source-card" key={index} href={source.source_url || source.url} target="_blank" rel="noreferrer"><BookOpen size={14} /><span><strong>{source.title}</strong><small>{label(source.status || "Source snapshot")}</small></span></a>)}
        <p className="muted">Prepared from your saved profile and detected events. Source changes require review; no action has been executed.</p>
        {item.content.omitted_unverified_details && <p className="muted">Some AI-drafted details could not be verified and were omitted. Confirm the applicable requirements with your adviser.</p>}
        <div className="assistant-update-actions"><button className="button secondary compact" disabled={busy} onClick={() => onAsk(`Please explain this assistant update and help me plan next steps.\nUpdate: ${item.content.title}\nSummary: ${item.content.summary}\nWhy it may matter: ${item.content.why_it_matters}`)}>Discuss this update<ArrowRight size={14} /></button>{!item.read_at && <button className="text-button" disabled={busy} onClick={() => void onRead(item.id)}><Check size={14} />Mark as read</button>}</div>
      </div>
    </details>)}
  </section>;
}

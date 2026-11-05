import { ArrowLeft, History, LoaderCircle } from "lucide-react";
import type { AssistantUpdatePage } from "@/lib/types";
import AssistantUpdates from "./AssistantUpdates";

export default function AssistantUpdateHistory({ page, loading, locked, onLoadOlder, onBack, onRead, onAsk }: {
  page: AssistantUpdatePage; loading: boolean; locked: boolean; onLoadOlder: () => void;
  onBack: () => void; onRead: (id: string) => Promise<void>; onAsk: (message: string) => void;
}) {
  return <section className="assistant-history" aria-label="Assistant update history">
    <div className="assistant-history-heading"><div><h2><History size={18} />Assistant update history</h2><p>Messages prepared for you, kept separately from your chats. New chat never deletes these updates.</p></div><button className="text-button" onClick={onBack}><ArrowLeft size={14} />Back to chat</button></div>
    {loading && <p className="chat-thinking" role="status"><LoaderCircle size={16} className="spin" />Loading assistant updates…</p>}
    {!loading && !page.updates.length && <p className="assistant-history-empty">No assistant updates yet. Relevant policy changes and approaching preparation dates can trigger a personalized AI message.</p>}
    <AssistantUpdates updates={[...page.updates].reverse()} busy={locked} onRead={onRead} onAsk={onAsk} />
    {page.next_before && <button className="button secondary compact" disabled={locked} onClick={onLoadOlder}>Load older updates</button>}
  </section>;
}

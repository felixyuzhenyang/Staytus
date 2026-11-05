"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, CheckCircle2, ExternalLink, History, LoaderCircle, MessageSquarePlus, Send, ShieldCheck, Sparkles } from "lucide-react";
import type { ChatMessage, Deadline, PlanningRequest, PlanningWorkflow, Profile } from "@/lib/types";
import { date, label } from "@/lib/types";
import { availableWorkflows } from "@/lib/planning-workflows";
import GuidedPlanningForm from "./GuidedPlanningForm";
import ChatPlanActions from "./ChatPlanActions";
import PlanNarrative from "./PlanNarrative";
import AssistantUpdates from "./AssistantUpdates";
import AssistantUpdateSettings from "./AssistantUpdateSettings";
import AssistantUpdateHistory from "./AssistantUpdateHistory";
import type { AssistantPreferences, AssistantUpdate, AssistantUpdatePage } from "@/lib/types";
import { Badge } from "./ui";

export default function ChatPanel({ messages, updates, unread, history, historyLoading, hideUpdates, onNewChat, onLoadHistory, preferences, onReadUpdate, onUpdatePreferences, onCheckUpdates, checking, busy, locked, error, profile, onSend, onRemind, onApprovals, onEditProfile }: { messages: ChatMessage[]; updates: AssistantUpdate[]; unread: number; history: AssistantUpdatePage; historyLoading: boolean; hideUpdates: boolean; onNewChat: () => Promise<boolean>; onLoadHistory: (older?: boolean) => Promise<void>; preferences: AssistantPreferences | null; onReadUpdate: (id: string) => Promise<void>; onUpdatePreferences: (data: AssistantPreferences) => Promise<void>; onCheckUpdates: () => Promise<void>; checking: boolean; busy: boolean; locked: boolean; error: string; profile: Profile; onSend: (message: string, request?: PlanningRequest) => Promise<boolean>; onRemind: (target: Deadline) => void; onApprovals: () => void; onEditProfile: () => void }) {
  const [input, setInput] = useState("");
  const [workflow, setWorkflow] = useState<PlanningWorkflow | null>(null);
  const [view, setView] = useState<"chat" | "updates">("chat");
  const messagesContainer = useRef<HTMLDivElement>(null);
  const composerInput = useRef<HTMLInputElement>(null);
  useEffect(() => { const container = messagesContainer.current; if (view === "chat" && container && (messages.length || busy)) container.scrollTop = container.scrollHeight; }, [messages.length, busy, view]);
  useEffect(() => {
    if (hideUpdates || view !== "chat") return;
    const container = messagesContainer.current;
    const unread = container?.querySelectorAll<HTMLElement>(".assistant-update.unread");
    const latest = unread?.[unread.length - 1];
    if (container && latest) container.scrollTop += latest.getBoundingClientRect().top - container.getBoundingClientRect().top - 10;
  }, [updates.length, hideUpdates, view]);
  async function startNewChat() {
    if (await onNewChat()) { setInput(""); setWorkflow(null); setView("chat"); requestAnimationFrame(() => composerInput.current?.focus()); }
  }
  function openUpdates() { setView("updates"); setWorkflow(null); void onLoadHistory(); }
  function openWorkflow(value: PlanningWorkflow) { setView("chat"); setWorkflow(value); }
  function ask(message: string) { setView("chat"); setWorkflow(null); void onSend(message); }
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!input.trim() || locked) return; const message = input; setInput(""); await onSend(message); }
  return <section className="chat-layout"><div className="chat-main panel"><div className="chat-top"><span className="assistant-avatar"><Sparkles size={21} /></span><div><strong>Staytus Assistant</strong><small>Your plans, with your profile in context</small></div><Badge tone="blue">AI assistant</Badge></div>
    <div className="chat-toolbar" aria-label="Chat controls"><button className="button secondary compact" onClick={() => void startNewChat()} disabled={locked}><MessageSquarePlus size={15} />New chat</button><button className={`button secondary compact ${view === "updates" ? "active" : ""}`} onClick={openUpdates} disabled={locked} aria-pressed={view === "updates"}><History size={15} />Assistant updates{unread > 0 && <span className="assistant-unread" aria-label={`${unread} unread updates`}>{unread}</span>}</button></div>
    <div className="planning-shortcuts" aria-label="Common requests">{availableWorkflows(profile).map(option => <button key={option.id} className={workflow === option.id ? "active" : ""} onClick={() => openWorkflow(option.id)} aria-pressed={workflow === option.id} disabled={locked}>{option.title}<ArrowRight size={13} /></button>)}<button onClick={() => ask("What do the latest official sources say for my situation?")} disabled={locked}><BookOpen size={13} />Latest policy sources<ArrowRight size={13} /></button></div>
    {view === "updates" ? <>
      {preferences && <AssistantUpdateSettings preferences={preferences} busy={locked} checking={checking} onSave={onUpdatePreferences} onCheck={onCheckUpdates} />}
      <AssistantUpdateHistory page={history} loading={historyLoading} locked={locked} onLoadOlder={() => void onLoadHistory(true)} onBack={() => setView("chat")} onRead={onReadUpdate} onAsk={ask} />
    </> : <>
    {workflow && <GuidedPlanningForm key={`${workflow}-${profile.version}`} workflow={workflow} profile={profile} busy={locked} error={error} onClose={() => setWorkflow(null)} onGenerate={onSend} />}
    <div ref={messagesContainer} className="chat-messages" aria-live="polite">{!messages.length && !workflow && <div className="chat-welcome"><span className="big-spark"><Sparkles size={32} /></span><h2>What would you like to plan?</h2><p>Choose a guided request above. Review your details, then get an AI plan grounded in official sources and your personal situation.</p><div className="prompt-grid">{availableWorkflows(profile).map(option => <button key={option.id} onClick={() => openWorkflow(option.id)} disabled={locked}><span><strong>{option.title}</strong><small>{option.description}</small></span><ArrowRight size={15} /></button>)}<button onClick={() => ask("What do the latest official sources say for my situation?")} disabled={locked}>Explore the latest policy sources<ArrowRight size={15} /></button></div></div>}
      {!hideUpdates && <AssistantUpdates updates={updates} busy={locked} onRead={onReadUpdate} onAsk={ask} />}
      {messages.map((message, index) => <div key={index} className={`chat-message ${message.role}`}>
        <span className={`avatar mini ${message.role === "assistant" ? "bot" : ""}`}>{message.role === "assistant" ? <Sparkles size={15} /> : profile.name[0]}</span>
        <div className="message-content">
          <span className="message-author">{message.role === "assistant" ? "Staytus" : "You"}</span>
          {message.planning && <h3 className="plan-message-title">{message.planning.title}</h3>}
          {message.planning ? <PlanNarrative text={message.message} /> : <p className="message-text">{message.message}</p>}
          {!!message.tools?.length && <div className="tool-tags">{message.tools.map((tool, key) => <span key={key}><CheckCircle2 size={12} />{typeof tool === "string" ? tool : typeof tool === "object" && tool ? String((tool as Record<string, unknown>).name || (tool as Record<string, unknown>).tool || "Assistant tool") : "Assistant tool"}</span>)}</div>}
          {message.citations?.map((citation, key) => <a key={key} className="source-card" href={citation.url || citation.source_url} target="_blank" rel="noreferrer"><BookOpen size={15} /><span><strong>{citation.title || "Source reference"}</strong><small>{citation.status ? label(citation.status) : "Source snapshot"}{citation.verified_at ? ` · ${date(citation.verified_at)}` : ""}</small></span><ExternalLink size={13} /></a>)}
          {message.planning && <ChatPlanActions plan={message.planning} profileVersion={profile.version} busy={locked} onRemind={onRemind} />}
          {message.approval && <button className="button secondary" onClick={onApprovals}>Review prepared action <ArrowRight size={15} /></button>}
        </div>
      </div>)}
      {busy && <div className="chat-thinking" role="status"><LoaderCircle size={16} className="spin" />{workflow ? "Retrieving policy sources and building your personal plan…" : "Your assistant is working…"}</div>}
    </div><form className="chat-composer" onSubmit={submit}><input ref={composerInput} aria-label="Message Staytus" placeholder="Ask about your next step…" value={input} onChange={event => setInput(event.target.value)} disabled={locked} maxLength={4000} /><button className="send-button" disabled={locked || !input.trim()} aria-label="Send message"><Send size={18} /></button></form><p className="chat-footnote">{locked && !busy ? "Finish the current action before sending a new message." : "Review linked sources and confirm prepared actions before execution."}</p></>}
    {error && <p className="chat-inline-error" aria-hidden="true">{error}</p>}</div>
    <aside className="chat-context"><div className="panel"><span className="eyebrow">IN YOUR CONTEXT</span><h3>{profile.name}</h3><p>{profile.status_type} · {profile.school}</p><div className="context-line"><span>Program ends</span><strong>{date(profile.program_end)}</strong></div><button className="text-button" onClick={onEditProfile}>Edit your profile <ArrowRight size={14} /></button></div><div className="note"><ShieldCheck size={19} /><p>Your saved dates support planning. Sensitive decisions and final submissions stay under your control.</p></div></aside>
  </section>;
}

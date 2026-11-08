import { ArrowRight, Bell, CalendarDays, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import type { DashboardData, Deadline, Profile } from "@/lib/types";
import { date } from "@/lib/types";
import { Badge, Empty, IconButton } from "./ui";
import WorkflowGuidancePanel from "./WorkflowGuidancePanel";

function DeadlineCard({ deadline, index, onAsk, onRemind }: { deadline: Deadline; index: number; onAsk: () => void; onRemind: () => void }) {
  const due = deadline.date, parsed = due ? new Date(`${due.slice(0, 10)}T12:00:00`) : null;
  return <article className={`panel deadline-card deadline-${index}`}><div className="card-meta"><span className="tile-icon small"><CalendarDays size={18} /></span><Badge tone={deadline.is_planning_buffer ? "amber" : "blue"}>{deadline.is_planning_buffer ? "Planning target" : "Profile date"}</Badge></div><h3>{deadline.title}</h3>
    <div className="big-date">{parsed && !Number.isNaN(parsed.getTime()) ? <>{new Intl.DateTimeFormat("en-US", { month: "short" }).format(parsed)} <strong>{parsed.getDate()}</strong><small>{parsed.getFullYear()}</small></> : <strong>{date(due)}</strong>}</div>
    <p>{deadline.recommended_start ? `Start preparing ${date(deadline.recommended_start)}` : "Check your documents and the official process."}</p><details className="trace-details"><summary>How this date was calculated <ChevronRight size={12} /></summary><div>{deadline.trace?.map((trace, key) => <p key={key}>{trace}</p>)}<small>Rule: {deadline.rule_version || "internal planning preference"}</small>{deadline.source && <a href={deadline.source.url} target="_blank" rel="noreferrer">{deadline.source.title} <ExternalLink size={11} /></a>}</div></details><div className="deadline-actions"><button className="text-button" onClick={onAsk}>See next steps <ArrowRight size={14} /></button><IconButton title={`Prepare reminder for ${deadline.title}`} onClick={onRemind}><Bell size={16} /></IconButton></div>
  </article>;
}

export default function Dashboard({ data, profile, onAsk, onEditProfile, onUpdates, onRemind }: { data: DashboardData | null; profile: Profile; onAsk: (message?: string) => void; onEditProfile: () => void; onUpdates: () => void; onRemind: (deadline: Deadline) => void }) {
  if (!data) return <Empty icon={CalendarDays} title="Your timeline will appear here" text="Your saved profile is ready. Refresh this view to load your planning dates." />;
  return <>
    <section className="journey-banner"><div className="journey-copy"><h2>Your current planning context</h2><p>This overview uses the dates and status information saved in your {profile.status_type} profile. Dates on your horizon shows preparation targets, Recent policy updates lists detected changes in monitored official sources, and Priority checklists highlights the workflows most relevant to your saved information.</p><button className="button light" onClick={() => onAsk()}>Ask your assistant <ArrowRight size={16} /></button></div><div className="journey-art" aria-hidden="true"><div className="orbit" /><div className="orbit smaller" /><span className="art-plane">↗</span><span className="art-sparkle">✳</span></div></section>
    <div className="section-heading"><h2>Dates on your horizon <span>{data.deadlines.length}</span></h2><button className="text-button" onClick={onEditProfile}>Update my dates <ArrowRight size={15} /></button></div>
    <div className="deadline-grid">{data.deadlines.map((deadline, index) => <DeadlineCard key={deadline.id || deadline.workflow} deadline={deadline} index={index} onAsk={() => onAsk(`Help me plan my ${deadline.title.toLowerCase()}.`)} onRemind={() => onRemind(deadline)} />)}</div>
    {!data.deadlines.length && <Empty icon={CalendarDays} title="No school-specific timeline yet" text="Your profile is saved. School-specific planning support will appear when an adapter is available." />}
    <div className="overview-lower">
      <section className="panel updates-preview"><div className="section-heading inside"><h2>Recent policy updates</h2><Bell size={17} /></div>{data.notifications.length ? data.notifications.slice(0, 2).map(notice => <div className="notice-preview" key={notice.id}><Badge tone="amber">Source update</Badge><h3>{notice.title || "A change to review"}</h3><p>{notice.message}</p></div>) : <div className="notice-preview"><Badge tone="blue">Sources in context</Badge><h3>Changes deserve context.</h3><p>Your updates will show what was captured and whether it has been reviewed.</p></div>}<button className="text-button" onClick={onUpdates}>View policy updates <ArrowRight size={15} /></button></section>
    </div><WorkflowGuidancePanel guidance={data.workflow_guidance} /><div className="bottom-note"><ShieldCheck size={16} />Planning reminders are not official filing deadlines. Your adviser can help confirm individual requirements.</div>
  </>;
}

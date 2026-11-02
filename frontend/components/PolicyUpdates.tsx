import { ArrowRight, Bell, RefreshCw } from "lucide-react";
import type { Notice } from "@/lib/types";
import { date } from "@/lib/types";
import { Empty } from "./ui";

export default function PolicyUpdates({ notices }: { notices: Notice[] }) {
  return <><section className="panel update-explainer"><span className="tile-icon"><RefreshCw size={24} /></span><div><h2>Captured → Reviewed → Applied</h2><p>A change to a published page is a signal to investigate. Captured information and active planning rules stay separate until the change has been reviewed.</p></div></section><div className="notification-list">{notices.map(notice => <article key={notice.id} className="panel notification"><span className="timeline-dot" /><div><span className="eyebrow">{date(notice.created_at)}</span><h2>{notice.title || "An update for your plans"}</h2><p>{notice.message}</p>{(notice.old_date || notice.new_date) && <div className="date-change"><span>{date(notice.old_date)}</span><ArrowRight size={16} /><strong>{date(notice.new_date)}</strong></div>}</div></article>)}</div>{!notices.length && <Empty icon={Bell} title="No updates to show" text="Notifications relevant to your profile will appear here when official sources are checked and reviewed changes are recorded." />}</>;
}

import { Bell, BookOpen, CheckCircle2, ChevronRight, Clock3, FileCheck2, Globe2, LayoutDashboard, Link2, LogOut, RefreshCw, ShieldCheck, Sparkles, UserRound, X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { Account, Profile, Tab } from "@/lib/types";
import { IconButton, Logo } from "./ui";
import NotificationCenter from "./NotificationCenter";

const nav: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "assistant", label: "Your assistant", icon: Sparkles },
  { id: "policies", label: "Policy library", icon: BookOpen },
  { id: "approvals", label: "Action inbox", icon: FileCheck2 },
  { id: "updates", label: "Policy updates", icon: Bell },
];
const secondary: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: "profile", label: "Your profile", icon: UserRound },
  { id: "connections", label: "Connections", icon: Link2 },
  { id: "audit", label: "Activity log", icon: Clock3 },
];
const titles: Record<Tab, [string, string]> = {
  overview: ["Your next chapter, clearly.", "A little less uncertainty. A clearer next step."],
  assistant: ["Let's figure it out.", "Ask about your next step, with your profile in context."],
  policies: ["Information you can trace.", "Explore official source snapshots, review states, and their original pages."],
  approvals: ["You're in control.", "Review the exact action before anything happens."],
  updates: ["Stay ahead of changes.", "See newly captured information and changes relevant to your plans."],
  profile: ["Your journey, in context.", "Keep your program dates and profile information up to date."],
  review: ["Policy review workspace.", "Inspect captured changes before changing an active rule."],
  audit: ["Every step, accounted for.", "An inspectable record of your actions and approvals."],
  connections: ["Connect on your terms.", "Choose the services you want Staytus to access."],
};

export default function AppShell({ account, profile, role, tab, onTab, onLogout, onRefresh, loading, toast, onDismissToast, onSessionExpired, children, assistantUnread = 0 }: {
  account: Account; profile: Profile; role: string; tab: Tab; onTab: (tab: Tab) => void;
  onLogout: () => Promise<void>; onRefresh: () => void; loading: boolean;
  toast: string; onDismissToast: () => void; children: ReactNode;
  onSessionExpired?: () => void;
  assistantUnread?: number;
}) {
  const firstName = account.name.split(" ")[0];
  const items = role === "reviewer" ? [...secondary, { id: "review" as Tab, label: "Review workspace", icon: ShieldCheck }] : secondary;
  const navigationButton = ({ id, label, icon: Icon }: { id: Tab; label: string; icon: LucideIcon }) => <button key={id} type="button" className={`nav-item ${tab === id ? "active" : ""}`} aria-label={label} aria-current={tab === id ? "page" : undefined} onClick={() => onTab(id)}><Icon size={18} /><span>{label}</span>{id === "assistant" && assistantUnread > 0 && <small className="assistant-unread" aria-label={`${assistantUnread} unread assistant updates`}>{assistantUnread}</small>}</button>;
  return <div className="app-shell">
    <aside className="sidebar"><Logo /><div className="workspace-label">YOUR WORKSPACE</div><nav aria-label="Main navigation">{nav.map(navigationButton)}</nav>
      <div className="sidebar-bottom"><div className="quiet-card"><Globe2 size={22} /><strong>A world of possibilities.</strong><p>Make room for what comes next. We'll help with the details.</p></div><nav aria-label="Account navigation">{items.map(navigationButton)}</nav><div className="sidebar-profile"><span className="avatar small">{firstName[0]}</span><div><strong>{account.name}</strong><small>{profile.status_type} · {profile.school === "University of Pennsylvania" ? "Penn" : profile.school}</small></div><IconButton title="Sign out" onClick={() => void onLogout()}><LogOut size={16} /></IconButton></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">Your workspace <ChevronRight size={14} /><span>{titles[tab][0].replace(/\.$/, "")}</span></div><div className="topbar-right"><NotificationCenter key={account.id} accountId={account.id} onSessionExpired={onSessionExpired} onOpenConnections={() => onTab("connections")} /><span className="avatar mini">{firstName[0]}</span></div></header>
      <main className="workspace"><div className="page-heading"><div><span className="eyebrow">{tab === "overview" ? `WELCOME BACK, ${firstName.toUpperCase()}` : "STAYTUS / YOUR WORKSPACE"}</span><h1>{titles[tab][0]}</h1><p>{titles[tab][1]}</p></div><button className="button secondary compact" aria-label="Refresh current view" onClick={onRefresh} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} /><span>Refresh</span></button></div>{children}</main>
      <footer className="footer"><span>Made for the journey beyond borders.</span><span>Staytus · Your personal planning workspace</span></footer>
    </div>
    {toast && <div className="toast" role="status"><CheckCircle2 size={18} />{toast}<button onClick={onDismissToast} aria-label="Dismiss notification"><X size={14} /></button></div>}
  </div>;
}

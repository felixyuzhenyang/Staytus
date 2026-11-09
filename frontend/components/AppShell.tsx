import { Bell, BookOpen, CheckCircle2, ChevronRight, Clock3, FileCheck2, Globe2, LayoutDashboard, Link2, LogOut, RefreshCw, ShieldCheck, Sparkles, UserRound, X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { Account, Profile, Tab } from "@/lib/types";
import { IconButton, Logo } from "./ui";
import NotificationCenter from "./NotificationCenter";

type NavigationItem = { id: Tab; label: string; description: string; icon: LucideIcon };

const nav: NavigationItem[] = [
  { id: "overview", label: "Overview", description: "Review and track your next steps.", icon: LayoutDashboard },
  { id: "assistant", label: "My Assistant", description: "Ask questions and build plans with your profile in context.", icon: Sparkles },
  { id: "policies", label: "Policy library", description: "Browse official sources and school guidance by topic.", icon: BookOpen },
  { id: "approvals", label: "Action inbox", description: "Review and download or approve actions prepared for you.", icon: FileCheck2 },
  { id: "updates", label: "Policy updates", description: "See captured changes relevant to your profile and their review state.", icon: Bell },
];
const secondary: NavigationItem[] = [
  { id: "profile", label: "My Profile", description: "Review and update your status, dates, and planning information.", icon: UserRound },
  { id: "connections", label: "Connections", description: "Manage the email and calendar services you choose to connect.", icon: Link2 },
  { id: "audit", label: "Activity log", description: "Review your saved actions, approvals, and results.", icon: Clock3 },
];
const titles: Record<Tab, [string, string]> = {
  overview: ["Planning overview", ""],
  assistant: ["My Assistant", "Ask about your next step, with your profile in context."],
  policies: ["Information you can trace.", "Explore official source snapshots, review states, and their original pages."],
  approvals: ["You're in control.", "Review the exact action before anything happens."],
  updates: ["Stay ahead of changes.", "See newly captured information and changes relevant to your plans."],
  profile: ["My Profile", "Keep your program dates and profile information up to date."],
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
  const initial = Array.from(firstName)[0] || "U";
  const items: NavigationItem[] = role === "reviewer" ? [...secondary, { id: "review", label: "Review workspace", description: "Review captured changes before active guidance is updated.", icon: ShieldCheck }] : secondary;
  const navigationButton = ({ id, label, description, icon: Icon }: NavigationItem) => <button key={id} type="button" className={`nav-item ${tab === id ? "active" : ""}`} aria-label={`${label}. ${description}`} title={`${label}: ${description}`} aria-current={tab === id ? "page" : undefined} onClick={() => onTab(id)}><Icon size={18} /><span className="nav-copy"><strong>{label}</strong><small className="nav-description">{description}</small></span>{id === "assistant" && assistantUnread > 0 && <small className="assistant-unread" aria-label={`${assistantUnread} unread assistant updates`}>{assistantUnread}</small>}</button>;
  return <div className="app-shell">
    <aside className="sidebar"><Logo /><div className="workspace-label">MY WORKSPACE</div><nav aria-label="Main navigation">{nav.map(navigationButton)}</nav>
      <div className="sidebar-bottom"><div className="quiet-card"><Globe2 size={22} /><strong>A world of possibilities.</strong><p>Make room for what comes next. We'll help with the details.</p></div><nav aria-label="Account navigation">{items.map(navigationButton)}</nav><div className="sidebar-profile"><button type="button" className="avatar avatar-link small" aria-label="Open My Profile from sidebar" title="My Profile" aria-current={tab === "profile" ? "page" : undefined} onClick={() => onTab("profile")}>{initial}</button><div><strong>{account.name}</strong><small>{profile.status_type} · {profile.school === "University of Pennsylvania" ? "Penn" : profile.school}</small></div><IconButton title="Sign out" onClick={() => void onLogout()}><LogOut size={16} /></IconButton></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">My workspace <ChevronRight size={14} /><span>{titles[tab][0].replace(/\.$/, "")}</span></div><div className="topbar-right"><NotificationCenter key={account.id} accountId={account.id} onSessionExpired={onSessionExpired} onOpenConnections={() => onTab("connections")} /><button type="button" className="avatar avatar-link mini" aria-label="Open My Profile from top bar" title="My Profile" aria-current={tab === "profile" ? "page" : undefined} onClick={() => onTab("profile")}>{initial}</button></div></header>
      <main className="workspace"><div className="page-heading"><div><span className="eyebrow">{tab === "overview" ? `WELCOME BACK, ${firstName.toUpperCase()}` : "STAYTUS / MY WORKSPACE"}</span><h1>{titles[tab][0]}</h1>{titles[tab][1] && <p>{titles[tab][1]}</p>}</div><button className="button secondary compact refresh-data" aria-label="Refresh data" title="Reload saved data; keep your current conversation" onClick={onRefresh} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} /><span>Refresh data</span></button></div>{children}</main>
      <footer className="footer"><span>Made for the journey beyond borders.</span><span>Staytus · Your personal planning workspace</span></footer>
    </div>
    {toast && <div className="toast" role="status"><CheckCircle2 size={18} />{toast}<button onClick={onDismissToast} aria-label="Dismiss notification"><X size={14} /></button></div>}
  </div>;
}

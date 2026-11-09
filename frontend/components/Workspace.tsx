"use client";
import type { Account, Profile } from "@/lib/types";
import { useWorkspace } from "@/hooks/useWorkspace";
import AppShell from "./AppShell";
import Dashboard from "./Dashboard";
import ChatPanel from "./ChatPanel";
import PoliciesPanel from "./PoliciesPanel";
import ApprovalsPanel from "./ApprovalsPanel";
import ApprovalDialog from "./ApprovalDialog";
import PolicyUpdates from "./PolicyUpdates";
import ProfilePanel from "./ProfilePanel";
import ReviewPanel from "./ReviewPanel";
import ActivityLog from "./ActivityLog";
import ConnectionsPanel from "./ConnectionsPanel";
import CalendarReminderDialog from "./CalendarReminderDialog";
import { ErrorNotice, Loading } from "./ui";

export default function Workspace({ account, profile, role, onLogout, onSessionExpired, onProfileUpdated }: { account: Account; profile: Profile; role: string; onLogout: () => Promise<void>; onSessionExpired: () => void; onProfileUpdated: (profile: Profile) => void }) {
  const workspace = useWorkspace({ onSessionExpired, onProfileUpdated });
  const { tab, setTab, busy } = workspace;
  return <AppShell account={account} profile={profile} role={role} tab={tab} onTab={setTab} onLogout={onLogout} onRefresh={workspace.refresh} loading={workspace.loading} toast={workspace.toast} onDismissToast={workspace.clearToast} onSessionExpired={onSessionExpired} assistantUnread={workspace.assistantUnread}>
    {workspace.error && !workspace.selected && <ErrorNotice message={workspace.error} onDismiss={workspace.clearError} />}
    {workspace.loading && !["assistant", "profile"].includes(tab) ? <Loading /> : <>
      {tab === "overview" && <Dashboard data={workspace.dashboard} profile={profile} onAsk={message => { setTab("assistant"); if (message) void workspace.sendChat(message); }} onEditProfile={() => setTab("profile")} onUpdates={() => setTab("updates")} onRemind={deadline => void workspace.remind(deadline)} />}
      {tab === "assistant" && <ChatPanel profile={profile} messages={workspace.messages} updates={workspace.assistantUpdates} unread={workspace.assistantUnread} history={workspace.assistantHistory} historyLoading={busy === "assistant-history"} hideUpdates={workspace.hideAssistantUpdates} onNewChat={workspace.newChat} onLoadHistory={workspace.loadAssistantHistory} preferences={workspace.assistantPreferences} onReadUpdate={workspace.readAssistantUpdate} onUpdatePreferences={workspace.saveAssistantPreferences} onCheckUpdates={workspace.checkAssistantUpdates} checking={busy === "assistant-check"} busy={busy === "chat"} locked={!!busy || workspace.loading} error={workspace.error} onSend={workspace.sendChat} onRemind={deadline => void workspace.remind(deadline)} onApprovals={() => { setTab("approvals"); workspace.refresh(); }} onEditProfile={() => setTab("profile")} />}
      {tab === "policies" && <PoliciesPanel policies={workspace.policies} sources={workspace.sources} query={workspace.query} busy={!!busy} onSearch={workspace.setQuery} onCapture={workspace.captureSources} />}
      {tab === "approvals" && <ApprovalsPanel approvals={workspace.approvals} busy={!!busy} onInspect={workspace.inspect} />}
      {tab === "updates" && <PolicyUpdates notices={workspace.dashboard?.notifications || []} />}
      {tab === "profile" && <ProfilePanel profile={profile} busy={!!busy} onSave={workspace.saveProfile} />}
      {tab === "review" && role === "reviewer" && <ReviewPanel reviews={workspace.reviews} />}
      {tab === "audit" && <ActivityLog events={workspace.events} />}
      {tab === "connections" && <ConnectionsPanel connections={workspace.connections} integrations={workspace.integrations} messages={workspace.mailMessages} analyses={workspace.mailAnalyses} mailboxLoaded={workspace.mailboxLoaded} busy={!!busy} onConnect={workspace.connect} onDisconnect={workspace.disconnect} onReadMail={workspace.readMail} onAgentAccess={workspace.setMailAgentAccess} onContentAnalysis={workspace.setMailContentAnalysis} onAnalyzeMail={workspace.analyzeMail} onUpdated={workspace.refresh} onSessionExpired={onSessionExpired} />}
    </>}
    {workspace.selected && <ApprovalDialog approval={workspace.selected} busy={!!busy} error={workspace.error} onClose={workspace.closeApproval} onDecision={workspace.decide} />}
    {workspace.calendarDeadline && <CalendarReminderDialog deadline={workspace.calendarDeadline} connections={workspace.connections} busy={!!busy} error={workspace.error} onClose={workspace.closeCalendar} onPreview={workspace.createCalendar} onConnections={() => { workspace.closeCalendar(); setTab("connections"); }} />}
  </AppShell>;
}

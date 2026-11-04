"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { Approval, AuditEvent, CalendarProvider, ChatMessage, ChatResponse, Connection, DashboardData, Deadline, MailMessage, OAuthCapability, Policy, Profile, Review, SourceStatus, Tab } from "@/lib/types";

type Options = { onSessionExpired: () => void; onProfileUpdated: (profile: Profile) => void };

export function useWorkspace({ onSessionExpired, onProfileUpdated }: Options) {
  const [tab, setTab] = useState<Tab>("overview");
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [integrations, setIntegrations] = useState<Record<string, unknown>>({});
  const [connections, setConnections] = useState<Connection[]>([]);
  const [mailMessages, setMailMessages] = useState<MailMessage[]>([]);
  const [mailboxLoaded, setMailboxLoaded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [calendarDeadline, setCalendarDeadline] = useState<Deadline | null>(null);
  const [query, setQuery] = useState("");
  const [errors, setErrors] = useState<Partial<Record<Tab, string>>>({});
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [revision, setRevision] = useState(0);
  const conversation = useRef<string | undefined>(undefined);
  const requestLock = useRef(false);
  const lifecycle = useRef<AbortController | null>(null);
  const callbacks = useRef({ onSessionExpired, onProfileUpdated });
  callbacks.current = { onSessionExpired, onProfileUpdated };
  const signal = useCallback(() => {
    if (!lifecycle.current) lifecycle.current = new AbortController();
    return lifecycle.current.signal;
  }, []);
  useEffect(() => {
    // Remounting by account id gives each account its own request lifetime,
    // conversation, cached views and approval selection.
    lifecycle.current = new AbortController();
    return () => { lifecycle.current?.abort(); lifecycle.current = null; };
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    const connected = url.searchParams.get("connection");
    if (!["google", "microsoft", "cancelled"].includes(connected || "")) return;
    setTab("connections");
    setToast(connected === "cancelled" ? "Email authorization was cancelled. Your other settings are unchanged." : "Email authorization completed. Check your connection permissions below.");
    url.searchParams.delete("connection");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  }, []);
  useEffect(() => { window.scrollTo({ top: 0, left: 0, behavior: "instant" }); }, [tab]);
  const handleError = useCallback((failure: unknown, requestSignal: AbortSignal, errorTab: Tab) => {
    if (requestSignal.aborted) return;
    if (failure instanceof ApiError && failure.status === 401) callbacks.current.onSessionExpired();
    else setErrors(previous => ({ ...previous, [errorTab]: failure instanceof Error ? failure.message : "Unable to complete this request." }));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    setLoading(true); setErrors(previous => ({ ...previous, [tab]: "" }));
    async function load() {
      if (tab === "overview" || tab === "updates") {
        const result = await api<DashboardData>("dashboard", options);
        if (!controller.signal.aborted) setDashboard({ ...result, notifications: result.notifications.map(notice => ({ ...notice, old_date: notice.old_date || notice.data?.old_date, new_date: notice.new_date || notice.data?.new_date })) });
      } else if (tab === "policies") {
        const [result, sourceResult] = await Promise.all([api<{ policies: Policy[] }>(`policies?q=${encodeURIComponent(query)}`, options), api<{ sources: SourceStatus[] }>("sources", options)]);
        if (!controller.signal.aborted) { setPolicies(result.policies); setSources(sourceResult.sources); }
      } else if (tab === "approvals") {
        const result = await api<{ approvals: Approval[] }>("approvals", options);
        if (!controller.signal.aborted) setApprovals(result.approvals);
      } else if (tab === "audit") {
        const result = await api<{ events: AuditEvent[] }>("audit", options);
        if (!controller.signal.aborted) setEvents(result.events);
      } else if (tab === "review") {
        const result = await api<{ reviews: Review[] }>("admin/reviews", options);
        if (!controller.signal.aborted) setReviews(result.reviews);
      } else if (tab === "connections") {
        const [integrationResult, connectionResult] = await Promise.all([api<Record<string, unknown>>("integration-status", options), api<{ providers: Connection[] }>("connections", options)]);
        if (!controller.signal.aborted) { setIntegrations(integrationResult); setConnections(connectionResult.providers); }
      }
    }
    void load().catch(failure => handleError(failure, controller.signal, tab)).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [tab, query, revision, handleError]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(""), 6500); return () => clearTimeout(timer); }, [toast]);

  async function action(key: string, run: (requestSignal: AbortSignal) => Promise<void>, errorTab: Tab = tab) {
    if (requestLock.current) return;
    requestLock.current = true;
    const requestSignal = signal();
    setBusy(key); setErrors(previous => ({ ...previous, [errorTab]: "" }));
    try { await run(requestSignal); } catch (failure) { handleError(failure, requestSignal, errorTab); }
    finally { requestLock.current = false; if (!requestSignal.aborted) setBusy(""); }
  }
  async function sendChat(message: string) {
    const text = message.trim();
    if (!text || requestLock.current) return;
    setTab("assistant");
    setMessages(previous => [...previous, { role: "user", message: text }]);
    await action("chat", async requestSignal => {
      const answer = await api<ChatResponse>("chat", { method: "POST", body: JSON.stringify({ message: text, conversation_id: conversation.current }), signal: requestSignal });
      if (requestSignal.aborted) return;
      if (answer.mode !== "orchestrate" || !answer.message?.trim()) throw new Error("The assistant did not return a verified Orchestrate response. Please check the service connection.");
      conversation.current = answer.conversation_id || answer.thread_id;
      setMessages(previous => [...previous, { role: "assistant", ...answer }]);
    }, "assistant");
  }
  async function saveProfile(data: Record<string, unknown>) {
    await action("profile", async requestSignal => {
      const result = await api<Profile>("profile", { method: "PATCH", body: JSON.stringify(data), signal: requestSignal });
      if (requestSignal.aborted) return;
      callbacks.current.onProfileUpdated(result); setRevision(value => value + 1); setToast("Profile saved. Your timeline will use the updated dates.");
    });
  }
  async function inspect(approval: Approval) {
    await action("inspect", async requestSignal => {
      const result = ["PROPOSED", "PREVIEWED"].includes(approval.status) ? await api<Approval>(`approvals/${approval.id}/preview`, { method: "POST", signal: requestSignal }) : approval;
      if (!requestSignal.aborted) setSelected(result);
    });
  }
  async function decide(decision: "approve" | "reject") {
    if (!selected) return;
    await action(decision, async requestSignal => {
      const result = await api<Approval>(`approvals/${selected.id}/${decision}`, { method: "POST", body: JSON.stringify({ payload_hash: selected.payload_hash }), signal: requestSignal });
      if (requestSignal.aborted) return;
      setSelected(result); setRevision(value => value + 1); setToast(decision === "approve" ? "Action processed. Check the execution receipt for the result." : "Action rejected.");
    });
  }
  async function remind(deadline: Deadline) {
    await action("calendar-options", async requestSignal => {
      const result = await api<{ providers: Connection[] }>("connections", { signal: requestSignal });
      if (!requestSignal.aborted) { setConnections(result.providers); setCalendarDeadline(deadline); }
    });
  }
  async function createCalendar(provider: CalendarProvider, reminderMinutes: number) {
    if (!calendarDeadline) return;
    const deadline = calendarDeadline;
    await action("reminder", async requestSignal => {
      const approval = await api<Approval>("approvals", { method: "POST", body: JSON.stringify({ kind: "calendar", payload: { title: deadline.title, date: deadline.date, description: `Staytus preparation reminder. Review your documents and the official school process for ${deadline.workflow}.`, provider, reminder_minutes: reminderMinutes } }), signal: requestSignal });
      const preview = await api<Approval>(`approvals/${approval.id}/preview`, { method: "POST", signal: requestSignal });
      if (requestSignal.aborted) return;
      setCalendarDeadline(null); setSelected(preview); setTab("approvals"); setRevision(value => value + 1);
    });
  }
  async function captureSources() {
    await action("capture", async requestSignal => {
      const result = await api<{ status: string; attempted?: number; changed_count?: number; error_count?: number; notice?: string }>("policies/refresh", { method: "POST", signal: requestSignal });
      if (!requestSignal.aborted) { setRevision(value => value + 1); setToast(result.status === "busy" ? result.notice || "Another source check is already running." : `Checked ${result.attempted || 0} source(s); ${result.changed_count || 0} changed; ${result.error_count || 0} failed. Review the source states below.`); }
    });
  }
  async function connect(provider: "google" | "microsoft", capability: OAuthCapability = "mail_read") {
    await action(`connect-${provider}`, async requestSignal => {
      const callback = connections.find(item => item.provider === provider)?.setup?.callback_uri;
      if (callback && new URL(callback).origin !== window.location.origin) {
        throw new Error(`Open ${new URL(callback).origin} and sign in there before connecting email. The callback must return to the same login session.`);
      }
      const result = await api<{ authorization_url: string }>(`connections/${provider}/start`, { method: "POST", body: JSON.stringify({ capability }), signal: requestSignal });
      if (requestSignal.aborted) return;
      const url = new URL(result.authorization_url);
      const allowed = provider === "google" ? url.hostname === "accounts.google.com" : url.hostname === "login.microsoftonline.com";
      if (url.protocol !== "https:" || !allowed) throw new Error("The email provider returned an unexpected authorization destination.");
      window.location.assign(url.href);
    });
  }
  async function disconnect(provider: "google" | "microsoft") {
    await action(`disconnect-${provider}`, async requestSignal => {
      await api(`connections/${provider}`, { method: "DELETE", signal: requestSignal });
      if (!requestSignal.aborted) { setMailMessages([]); setMailboxLoaded(false); setRevision(value => value + 1); setToast("Email connection removed."); }
    });
  }
  async function readMail(provider: "google" | "microsoft") {
    await action(`mail-${provider}`, async requestSignal => {
      const result = await api<{ messages: MailMessage[]; synced_at?: string }>(`connections/${provider}/messages`, { signal: requestSignal });
      if (!requestSignal.aborted) { setMailMessages(result.messages); setMailboxLoaded(true); }
    });
  }
  async function setMailAgentAccess(provider: "google" | "microsoft", enabled: boolean) {
    await action(`agent-mail-${provider}`, async requestSignal => {
      await api(`connections/${provider}/agent-access`, { method: "PATCH", body: JSON.stringify({ enabled }), signal: requestSignal });
      if (!requestSignal.aborted) {
        setConnections(previous => previous.map(item => item.provider === provider ? { ...item, agent_access: enabled } : item));
        setToast(enabled ? "The assistant may now read matching short email previews when you ask." : "Assistant email access disabled. You can still check messages yourself.");
      }
    });
  }
  const closeApproval = useCallback(() => setSelected(null), []);
  const closeCalendar = useCallback(() => setCalendarDeadline(null), []);
  return { tab, setTab, dashboard, policies, sources, approvals, events, reviews, integrations, connections, mailMessages, mailboxLoaded, messages, selected, calendarDeadline, createCalendar, closeCalendar, query, setQuery, error: errors[tab] || "", clearError: () => setErrors(previous => ({ ...previous, [tab]: "" })), toast, clearToast: () => setToast(""), loading, busy, refresh: () => setRevision(value => value + 1), sendChat, saveProfile, inspect, decide, remind, captureSources, connect, disconnect, readMail, setMailAgentAccess, closeApproval };
}

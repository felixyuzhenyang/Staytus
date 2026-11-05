"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { actionOutcome } from "@/lib/action-outcome";
import type { AssistantPreferences, AssistantUpdate, AssistantUpdatePage, ChatHistory } from "@/lib/types";
import type { Approval, AuditEvent, CalendarProvider, ChatMessage, ChatResponse, Connection, DashboardData, Deadline, MailMessage, OAuthCapability, PlanningRequest, Policy, Profile, Review, SourceStatus, Tab } from "@/lib/types";

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
  const [assistantUpdates, setAssistantUpdates] = useState<AssistantUpdate[]>([]);
  const [assistantUnread, setAssistantUnread] = useState(0);
  const [assistantHistory, setAssistantHistory] = useState<AssistantUpdatePage>({ updates: [], next_before: null, unread_count: 0 });
  const [hideAssistantUpdates, setHideAssistantUpdates] = useState(false);
  const [assistantPreferences, setAssistantPreferences] = useState<AssistantPreferences | null>(null);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [calendarDeadline, setCalendarDeadline] = useState<Deadline | null>(null);
  const [query, setQuery] = useState("");
  const [errors, setErrors] = useState<Partial<Record<Tab, string>>>({});
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [revision, setRevision] = useState(0);
  const conversation = useRef<string | undefined>(undefined);
  const historyLoaded = useRef(false);
  const assistantHistoryLoaded = useRef(false);
  const chatRevision = useRef(0);
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
    let pending = false;
    let firstLoad = true;
    async function loadUpdates() {
      if (pending || document.visibilityState === "hidden") return;
      pending = true;
      try {
        const [result, prefs] = await Promise.all([
          api<AssistantUpdatePage>("assistant-updates", { signal: controller.signal }),
          api<AssistantPreferences>("assistant-updates/preferences", { signal: controller.signal }),
        ]);
        if (!controller.signal.aborted) {
          setAssistantUpdates(result.updates); setAssistantUnread(result.unread_count); setAssistantPreferences(prefs);
          if (firstLoad && assistantHistoryLoaded.current) setAssistantHistory(result);
          firstLoad = false;
        }
      } catch (failure) { handleError(failure, controller.signal, "assistant"); }
      finally { pending = false; }
    }
    void loadUpdates();
    const timer = setInterval(() => void loadUpdates(), 30000);
    const focus = () => void loadUpdates();
    document.addEventListener("visibilitychange", focus);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", focus); };
  }, [handleError, revision]);
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
      } else if (tab === "assistant" && !requestLock.current) {
        const version = chatRevision.current;
        const result = await api<ChatHistory>("chat/history", options);
        if (!controller.signal.aborted && !requestLock.current && version === chatRevision.current) {
          conversation.current = result.conversation_id || undefined;
          setMessages(result.messages);
          setHideAssistantUpdates(result.hide_assistant_updates);
          historyLoaded.current = true;
        }
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
  async function sendChat(message: string, planningRequest?: PlanningRequest): Promise<boolean> {
    const text = message.trim();
    if (!text || requestLock.current) return false;
    let completed = false;
    setTab("assistant");
    chatRevision.current += 1;
    await action("chat", async requestSignal => {
      if (!historyLoaded.current) {
        const saved = await api<ChatHistory>("chat/history", { signal: requestSignal });
        if (requestSignal.aborted) return;
        conversation.current = saved.conversation_id || undefined;
        setMessages(saved.messages);
        setHideAssistantUpdates(saved.hide_assistant_updates);
        historyLoaded.current = true;
      }
      setMessages(previous => [...previous, { role: "user", message: text }]);
      const answer = await api<ChatResponse>("chat", { method: "POST", body: JSON.stringify({ message: text, conversation_id: conversation.current, planning_request: planningRequest }), signal: requestSignal });
      if (requestSignal.aborted) return;
      if (answer.mode !== "orchestrate" || !answer.message?.trim()) throw new Error("The assistant did not return a verified Orchestrate response. Please check the service connection.");
      conversation.current = answer.conversation_id || answer.thread_id;
      setMessages(previous => [...previous, { role: "assistant", ...answer }]);
      historyLoaded.current = true;
      completed = true;
    }, "assistant");
    return completed;
  }
  async function newChat(): Promise<boolean> {
    if (requestLock.current) return false;
    let completed = false;
    chatRevision.current += 1;
    await action("chat-new", async requestSignal => {
      const saved = await api<ChatHistory>("chat/new", { method: "POST", signal: requestSignal });
      if (requestSignal.aborted) return;
      conversation.current = saved.conversation_id || undefined;
      historyLoaded.current = true;
      setMessages(saved.messages);
      setHideAssistantUpdates(saved.hide_assistant_updates);
      setToast("New chat started. Your previous conversation is saved; assistant updates remain in their history.");
      completed = true;
    }, "assistant");
    return completed;
  }
  async function loadAssistantHistory(older = false) {
    await action("assistant-history", async requestSignal => {
      const before = older ? assistantHistory.next_before : null;
      if (older && !before) return;
      const page = await api<AssistantUpdatePage>(`assistant-updates${before ? `?before=${encodeURIComponent(before)}` : ""}`, { signal: requestSignal });
      if (requestSignal.aborted) return;
      setAssistantHistory(previous => ({ ...page, updates: older ? [...page.updates, ...previous.updates] : page.updates }));
      assistantHistoryLoaded.current = true;
      setAssistantUnread(page.unread_count);
    }, "assistant");
  }
  async function saveProfile(data: Record<string, unknown>) {
    await action("profile", async requestSignal => {
      const result = await api<Profile>("profile", { method: "PATCH", body: JSON.stringify(data), signal: requestSignal });
      if (requestSignal.aborted) return;
      callbacks.current.onProfileUpdated(result); setRevision(value => value + 1); setToast("Profile saved. Your workspace is up to date.");
    });
  }
  async function readAssistantUpdate(id: string) {
    await action("assistant-read", async requestSignal => {
      const result = await api<{ read_at: string }>(`assistant-updates/${id}/read`, { method: "POST", signal: requestSignal });
      if (!requestSignal.aborted) {
        const mark = (items: AssistantUpdate[]) => items.map(item => item.id === id ? { ...item, read_at: result.read_at } : item);
        setAssistantUpdates(mark);
        setAssistantHistory(previous => ({ ...previous, updates: mark(previous.updates) }));
        const current = await api<AssistantUpdatePage>("assistant-updates", { signal: requestSignal });
        if (!requestSignal.aborted) { setAssistantUpdates(current.updates); setAssistantUnread(current.unread_count); }
      }
    }, "assistant");
  }
  async function saveAssistantPreferences(data: AssistantPreferences) {
    await action("assistant-preferences", async requestSignal => {
      const result = await api<AssistantPreferences>("assistant-updates/preferences", { method: "PATCH", body: JSON.stringify({ enabled: data.enabled, language: data.language }), signal: requestSignal });
      if (!requestSignal.aborted) { setAssistantPreferences(result); setToast("Assistant update preferences saved."); }
    }, "assistant");
  }
  async function checkAssistantUpdates() {
    await action("assistant-check", async requestSignal => {
      const result = await api<{ generated: number; queued: number; failed: number; model_configured?: boolean }>("assistant-updates/check", { method: "POST", signal: requestSignal });
      const refreshed = await api<AssistantUpdatePage>("assistant-updates", { signal: requestSignal });
      if (!requestSignal.aborted) {
        setAssistantUpdates(refreshed.updates);
        setAssistantUnread(refreshed.unread_count);
        setAssistantHistory(refreshed);
        setToast(result.generated ? "Your new AI message is ready in Assistant updates." : result.failed || result.model_configured === false ? "AI generation is currently unavailable. Saved events will be checked again by the background service." : "No new eligible events to summarize. Daily monitoring will continue.");
      }
    }, "assistant");
  }
  async function inspect(approval: Approval) {
    await action("inspect", async requestSignal => {
      const result = ["PROPOSED", "PREVIEWED"].includes(approval.status) ? await api<Approval>(`approvals/${approval.id}/preview`, { method: "POST", signal: requestSignal }) : approval;
      if (!requestSignal.aborted) setSelected(result);
    });
  }
  async function decide(decision: "approve" | "reject") {
    if (!selected) return;
    const approval = selected;
    await action(decision, async requestSignal => {
      let result: Approval;
      try {
        result = await api<Approval>(`approvals/${approval.id}/${decision}`, { method: "POST", body: JSON.stringify({ payload_hash: approval.payload_hash }), signal: requestSignal });
      } catch (failure) {
        if (!requestSignal.aborted && decision === "approve" && (!(failure instanceof ApiError) || failure.status >= 500)) {
          // A lost write response is not proof of failure. Reconcile from the
          // owned inbox without automatically sending the action again.
          setSelected({ ...approval, status: "UNCONFIRMED", receipt: null });
          try {
            const saved = await api<{ approvals: Approval[] }>("approvals", { signal: requestSignal });
            if (!requestSignal.aborted) {
              setApprovals(saved.approvals);
              const latest = saved.approvals.find(item => item.id === approval.id);
              if (latest && !["PROPOSED", "PREVIEWED"].includes(latest.status)) {
                setSelected(latest);
                if (latest.status === "SUCCEEDED") {
                  setRevision(value => value + 1);
                  setToast(actionOutcome(latest)?.title || "Action completed.");
                  return;
                }
              }
            }
          } catch { /* Keep the cautious result if status retrieval also fails. */ }
        }
        throw failure;
      }
      if (requestSignal.aborted) return;
      setSelected(result); setRevision(value => value + 1); setToast(decision === "approve" ? actionOutcome(result)?.title || "Action updated." : "Action rejected.");
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
      const approval = await api<Approval>("approvals", { method: "POST", body: JSON.stringify({ kind: "calendar", payload: { title: deadline.title, date: deadline.date, description: deadline.description || `Staytus preparation reminder. Review your documents and the official school process for ${deadline.workflow}.`, provider, reminder_minutes: reminderMinutes } }), signal: requestSignal });
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
  return { tab, setTab, dashboard, policies, sources, approvals, events, reviews, integrations, connections, mailMessages, mailboxLoaded, messages, assistantUpdates, assistantUnread, assistantHistory, hideAssistantUpdates, newChat, loadAssistantHistory, assistantPreferences, readAssistantUpdate, saveAssistantPreferences, checkAssistantUpdates, selected, calendarDeadline, createCalendar, closeCalendar, query, setQuery, error: errors[tab] || "", clearError: () => setErrors(previous => ({ ...previous, [tab]: "" })), toast, clearToast: () => setToast(""), loading, busy, refresh: () => setRevision(value => value + 1), sendChat, saveProfile, inspect, decide, remind, captureSources, connect, disconnect, readMail, setMailAgentAccess, closeApproval };
}

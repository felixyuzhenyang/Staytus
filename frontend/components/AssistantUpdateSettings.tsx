import { LoaderCircle, RefreshCw } from "lucide-react";
import type { AssistantPreferences } from "@/lib/types";

export default function AssistantUpdateSettings({ preferences, busy, checking, onSave, onCheck }: {
  preferences: AssistantPreferences; busy: boolean; checking: boolean;
  onSave: (data: AssistantPreferences) => Promise<void>; onCheck: () => Promise<void>;
}) {
  return <details className="assistant-preferences"><summary>Proactive assistant updates · {preferences.enabled ? "On" : "Off"}</summary>
    <p>When policy sources change or a saved preparation date approaches, AI prepares a message for your next visit. Daily batches run even while this page is closed.</p>
    <div><label><input type="checkbox" checked={preferences.enabled} disabled={busy} onChange={event => void onSave({ ...preferences, enabled: event.target.checked })} />Receive proactive assistant messages</label><label>Message language<select value={preferences.language} disabled={busy} onChange={event => void onSave({ ...preferences, language: event.target.value as "en" | "zh" })}><option value="en">English</option><option value="zh">中文</option></select></label>
      <button className="button secondary compact" disabled={busy || preferences.active === false} onClick={() => void onCheck()}>{checking ? <LoaderCircle size={13} className="spin" /> : <RefreshCw size={13} />}{checking ? "Preparing update…" : "Check for assistant updates"}</button></div>
    {preferences.active === false && <p>Inactive while in-app reminders or the reminder frequency are turned off. You can change those in the reminder settings.</p>}
  </details>;
}

"use client";
import { useEffect, useRef } from "react";
import { ArrowDownToLine, Check, LoaderCircle, X } from "lucide-react";
import type { Approval } from "@/lib/types";
import { label } from "@/lib/types";
import { Badge, ErrorNotice, IconButton } from "./ui";
import { actionOutcome } from "@/lib/action-outcome";
import ActionResult from "./ActionResult";

export default function ApprovalDialog({ approval, busy, error, onClose, onDecision }: { approval: Approval; busy: boolean; error: string; onClose: () => void; onDecision: (decision: "approve" | "reject") => Promise<void> }) {
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]') || []);
    focusable()[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
      if (event.key !== "Tab") return;
      const targets = focusable(); const first = targets[0], last = targets.at(-1);
      if (!first) { event.preventDefault(); dialog.current?.focus(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previous?.focus(); };
  }, [approval.id, busy, onClose]);
  const expired = new Date(approval.expires_at).getTime() <= Date.now();
  const outcome = actionOutcome(approval);
  const preview = <>
    <dl className="payload-preview">{Object.entries(approval.payload).filter(([key]) => !key.startsWith("_")).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}</dd></div>)}</dl>
    {(approval.kind === "email" || (approval.kind === "calendar" && (approval.payload.provider || "export") !== "export")) && <p className="note">Connected account: {approval.target_account || "No eligible account was connected when this preview was created. Connect an account and create a fresh preview."}</p>}
  </>;
  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}><section ref={dialog} className="modal panel" role="dialog" aria-modal="true" aria-labelledby="approval-title" tabIndex={-1} onClick={event => event.stopPropagation()}>
    <div className="modal-heading"><div><span className="eyebrow">{outcome ? "ACTION RESULT" : "ACTION PREVIEW"}</span><h2 id="approval-title">{label(approval.kind)}</h2></div><IconButton title={outcome ? "Close result" : "Close preview"} disabled={busy} onClick={onClose}><X size={21} /></IconButton></div>
    <ErrorNotice message={error} /><Badge tone={outcome?.tone || "amber"}>{outcome?.badge || label(approval.status)}</Badge>
    {outcome ? <><ActionResult approval={approval} /><details className="approved-action-details"><summary>Action details</summary>{preview}</details></> : <>{preview}<p className="hash-label">Bound to payload {approval.payload_hash.slice(0, 18)}…<br />Expires {new Date(approval.expires_at).toLocaleString()}</p></>}
    <div className="modal-actions">
      {!outcome && ["PROPOSED", "PREVIEWED"].includes(approval.status) && <><button className="button secondary" disabled={busy} onClick={() => void onDecision("reject")}>Reject</button><button className="button primary" disabled={busy || expired} onClick={() => void onDecision("approve")}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{expired ? "Approval expired" : "Approve exact action"}</button></>}
      {approval.status === "SUCCEEDED" && approval.kind === "calendar" && approval.receipt?.mode === "file_export" && <a className="button primary" href={`/api/backend/approvals/${approval.id}/calendar.ics`}><ArrowDownToLine size={16} />Download calendar file</a>}
    </div>
  </section></div>;
}

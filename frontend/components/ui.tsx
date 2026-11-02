import { Globe2, LoaderCircle, X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function Logo() {
  return <a className="logo" href="/" aria-label="Staytus home"><span className="logo-mark"><Globe2 size={22} /></span>staytus<span className="logo-period">.</span></a>;
}
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Loading({ text = "Loading your workspace…" }: { text?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{text}</div>;
}
export function Empty({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return <div className="empty"><span className="empty-icon"><Icon size={26} /></span><h3>{title}</h3><p>{text}</p></div>;
}
export function ErrorNotice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  if (!message) return null;
  return <div role="alert" className="error-box"><span>{message}</span>{onDismiss && <button type="button" aria-label="Dismiss error" onClick={onDismiss}><X size={17} /></button>}</div>;
}
export function IconButton({ children, title, onClick, disabled }: { children: ReactNode; title: string; onClick: () => void; disabled?: boolean }) {
  return <button type="button" className="icon-button" title={title} aria-label={title} disabled={disabled} onClick={onClick}>{children}</button>;
}

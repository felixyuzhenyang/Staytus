import { Fragment } from "react";

function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith("**") && part.endsWith("**")
    ? <strong key={index}>{part.slice(2, -2)}</strong> : <Fragment key={index}>{part}</Fragment>);
}

export default function PlanNarrative({ text }: { text: string }) {
  return <div className="plan-narrative">{text.split("\n").filter(line => line.trim() && !/^[-*_]{3,}$/.test(line.trim())).map((line, index) => {
    const clean = line.trim();
    if (/^#{1,6}\s/.test(clean)) return <h4 key={index}>{inline(clean.replace(/^#{1,6}\s+/, ""))}</h4>;
    if (/^\*\*[^*]+\*\*\s*$/.test(clean)) return <h4 key={index}>{inline(clean)}</h4>;
    return <p key={index} className={/^[-*]\s|^\d+[.)、]\s?/.test(clean) ? "plan-list-line" : ""}>{inline(clean.replace(/^[-*]\s/, "• "))}</p>;
  })}</div>;
}

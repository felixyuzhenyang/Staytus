import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownNode = { type: string; value?: string; children?: MarkdownNode[] };

// Models sometimes use <br> inside table cells. Convert only a bare line-break
// node; all other raw HTML stays disabled, including scripts and event handlers.
function remarkLineBreaks() {
  return function transform(node: MarkdownNode) {
    node.children?.forEach((child, index, children) => {
      if (child.type === "html" && /^<br\s*\/?\s*>$/i.test(child.value || "")) children[index] = { type: "break" };
      else transform(child);
    });
  };
}

function safeUrl(url: string) {
  const safe = defaultUrlTransform(url);
  return /^(https?:|mailto:)/i.test(safe) ? safe : "";
}

export default function MessageMarkdown({ text }: { text: string }) {
  return <div className="message-markdown"><Markdown remarkPlugins={[remarkGfm, remarkLineBreaks]} skipHtml urlTransform={safeUrl}
    components={{
      a: ({ href, children }) => href
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        : <span>{children}</span>,
      // Rendering a message must not automatically fetch model-supplied images.
      img: ({ alt }) => <span>{alt ? `[Image: ${alt}]` : "[Image]"}</span>,
      table: ({ children }) => <div className="markdown-table" role="region" aria-label="Scrollable message table" tabIndex={0}><table>{children}</table></div>,
    }}>{text}</Markdown></div>;
}

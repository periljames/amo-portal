import { useId, useRef, useState } from "react";
import Markdown from "react-markdown";

// Raw HTML and remote images are intentionally unavailable in governed notes.
export function AnalysisMarkdown({ text }: { text: string }) {
  return <Markdown skipHtml disallowedElements={["img"]}>{text}</Markdown>;
}
export default function AnalysisEditor({ label, value, onChange, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void; disabled?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLTextAreaElement>(null);
  const [preview, setPreview] = useState(false);
  const insert = (before: string, after = "") => {
    const el = input.current;
    if (!el) return;
    const start = el.selectionStart, end = el.selectionEnd;
    const selection = value.slice(start, end) || "text";
    onChange(value.slice(0, start) + before + selection + after + value.slice(end));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + before.length, start + before.length + selection.length); });
  };
  return <div className="qa-analysis-editor">
    <label htmlFor={id}>{label}</label>
    <div className="qa-analysis-actions" aria-label={`${label} formatting`}>
      {[["Bold", "**", "**"], ["Italic", "*", "*"], ["Heading", "\n## ", ""], ["Bullet list", "\n- ", ""], ["Numbered list", "\n1. ", ""], ["Quote", "\n> ", ""]].map(([name, before, after]) => <button key={name} type="button" disabled={disabled || preview} onClick={() => insert(before, after)}>{name}</button>)}
      <button type="button" aria-pressed={preview} onClick={() => setPreview(!preview)}>{preview ? "Edit" : "Preview"}</button>
    </div>
    {preview ? <div className="qa-analysis-prose"><AnalysisMarkdown text={value || "No text entered."} /></div> : <textarea id={id} ref={input} value={value} maxLength={12000} rows={8} disabled={disabled} onChange={event => onChange(event.target.value)} />}
    <small>Markdown formatting · {value.length.toLocaleString()} / 12,000 characters</small>
  </div>;
}

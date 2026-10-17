import { useEffect, useRef } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { portalScrollBehavior } from "../../../utils/portalMotion";
import "./auditFieldworkPresentation.css";

export type ChecklistFilter = "ALL" | "UNANSWERED" | "VERIFIED" | "FINDINGS" | "EVIDENCE_REQUIRED";
type Props = {
  search: string; onSearch: (value: string) => void; filter: ChecklistFilter; onFilter: (value: ChecklistFilter) => void;
  sections: Array<{ id: string; title: string }>; visible: number; total: number; sourceLabel: string;
};
export default function AuditChecklistToolbar(props: Props) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable=true]")) return;
      event.preventDefault(); input.current?.focus();
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  return <>
    <div className="audit-checklist-heading"><div><span className="audit-checklist-heading__eyebrow">ASSESSMENT REGISTER</span><h2>Checklist</h2></div><span className="audit-checklist-heading__source" title={props.sourceLabel}>{props.sourceLabel}</span></div>
    <div className="qms-live-audit-focus__matrix-toolbar audit-checklist-toolbar">
      <div className="audit-checklist-toolbar__search"><Search size={17} aria-hidden /><input ref={input} aria-label="Search checklist" value={props.search} onChange={(event) => props.onSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") props.onSearch(""); }} placeholder="Search questions, sections or references…" />{props.search ? <button type="button" aria-label="Clear checklist search" onClick={() => { props.onSearch(""); input.current?.focus(); }}><X size={14} /></button> : <kbd>/</kbd>}</div>
      <label><SlidersHorizontal size={15} aria-hidden /><span className="sr-only">Filter checklist</span><select aria-label="Filter checklist" value={props.filter} onChange={(event) => props.onFilter(event.target.value as ChecklistFilter)}><option value="ALL">All questions</option><option value="UNANSWERED">Unanswered</option><option value="VERIFIED">Server-confirmed</option><option value="FINDINGS">Findings</option><option value="EVIDENCE_REQUIRED">Evidence required</option></select></label>
      <label className="audit-checklist-toolbar__sections"><span className="sr-only">Jump to section</span><select aria-label="Jump to section" value="" onChange={(event) => document.getElementById(`audit-section-${event.target.value}`)?.scrollIntoView({ behavior: portalScrollBehavior(), block: "nearest" })}><option value="">Jump to section</option>{props.sections.map((section) => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label>
      <span className="audit-checklist-toolbar__count" role="status">{props.visible === props.total ? `${props.total} questions` : `${props.visible} of ${props.total} questions`}</span>
    </div>
  </>;
}

import { Fragment, useMemo } from "react";
import { ArrowUpRight, ChevronUp } from "lucide-react";
import type { ChecklistExecutionGovernanceRow } from "../../../services/qmsChecklistExecutionGovernance";
import type { ChecklistResponseOption } from "../../../services/qmsChecklistTemplates";
import "./auditChecklistTable.css";

type Item = ChecklistExecutionGovernanceRow;
const responseMeaning: Record<string, string> = {
  COMPLIANT: "Satisfactory", NONCOMPLIANT: "Unsatisfactory", OBSERVATION: "Observation",
  NOT_VERIFIED: "Not checked; record the reason in remarks", NOT_APPLICABLE: "Not applicable",
};
type Props = {
  items: Item[];
  numberById: Map<string, number>;
  optionsForItem: (item: Item) => ChecklistResponseOption[];
  valueForItem: (item: Item) => string;
  notesForItem: (item: Item) => string;
  pendingForItem: (item: Item) => { status: string } | undefined;
  expandedId?: string;
  detailsId?: string;
  canEdit: boolean;
  busy: boolean;
  onResponse: (item: Item, option: ChecklistResponseOption) => void;
  onNotes: (item: Item, value: string) => void;
  onSaveNotes: (item: Item) => void;
  onOpenDetails: (item: Item) => void;
};

/** The uploaded form's question order and answer vocabulary remain the table. */
export default function AuditChecklistTable(props: Props) {
  const columns = useMemo(() => {
    const result = new Map<string, ChecklistResponseOption>();
    props.items.forEach((item) => props.optionsForItem(item).forEach((option) => {
      if (!result.has(option.value)) result.set(option.value, option);
    }));
    return [...result.values()];
  }, [props.items, props.optionsForItem]);
  const span = columns.length + 4;
  return <><div className="audit-checklist-table__scroll-hint">Scroll across for assessment and remarks <span aria-hidden>↔</span></div><div className="audit-checklist-table-scroll" tabIndex={0} role="region" aria-label="Scrollable checklist">
    <table className="qms-live-audit-focus__matrix-table audit-checklist-table" aria-label="Checklist assessment table">
      <thead><tr><th scope="col">No.</th><th scope="col">Checklist question</th>
        {columns.map((option) => <th className="audit-checklist-table__answer" scope="col" key={option.value} title={responseMeaning[option.canonical_status] || option.label}>{option.label}</th>)}
        <th scope="col">Remarks / objective evidence</th><th scope="col">Evidence</th>
      </tr></thead>
      <tbody>{props.items.map((item, index) => {
        const choices = props.optionsForItem(item);
        const value = props.valueForItem(item);
        const selected = choices.find((option) => option.value === value)
          || (value !== "NOT_VERIFIED" ? choices.find((option) => option.canonical_status === value) : undefined);
        const number = item.checklist_ref && /^\d+(?:[.\-]\d+)*$/.test(item.checklist_ref) ? item.checklist_ref : props.numberById.get(item.checklist_item_id) || index + 1;
        const pending = props.pendingForItem(item);
        const expanded = props.expandedId === item.checklist_item_id;
        return <Fragment key={item.checklist_item_id}>
          {(index === 0 || props.items[index - 1].section !== item.section) ? <tr id={`audit-section-${item.checklist_item_id}`} className="audit-checklist-table__section"><th colSpan={span} scope="rowgroup"><span>{item.section || "Checklist"}</span></th></tr> : null}
          <tr className={expanded ? "is-selected" : ""} data-response={selected?.canonical_status} data-pending={Boolean(pending) || undefined}>
            <th scope="row" className="audit-checklist-table__number">{number}</th>
            <td className="audit-checklist-table__question">{item.prompt}</td>
            {columns.map((column) => {
              const option = choices.find((choice) => choice.value === column.value);
              return <td key={column.value} className="audit-checklist-table__answer">{option ? <label className="audit-checklist-table__response-target" data-status={option.canonical_status}><input type="radio"
                name={`checklist-answer-${item.checklist_item_id}`} aria-label={`${option.label} — question ${number}`}
                checked={selected?.value === option.value} disabled={!props.canEdit || props.busy}
                onChange={() => props.onResponse(item, option)} /><span className="audit-checklist-table__mobile-choice">{option.label}</span></label> : <span aria-label="Not offered by this question">—</span>}</td>;
            })}
            <td className="audit-checklist-table__remarks">
              <textarea aria-label={`Remarks for question ${number}`} rows={2} value={props.notesForItem(item)}
                readOnly={!props.canEdit} onChange={(event) => props.onNotes(item, event.target.value)}
                placeholder={props.canEdit ? "Add remarks…" : "No remarks"} />
              {props.notesForItem(item) !== (item.auditor_notes || "") ? <>
                <button type="button" disabled={!props.canEdit || props.busy || !selected} onClick={() => props.onSaveNotes(item)}>Save remarks</button>
                {!selected ? <small>Choose a response to save these remarks.</small> : null}
              </> : null}
              {pending ? <small role="status">{["conflict", "failed"].includes(pending.status) ? "Sync needs review" : "Saved on device · awaiting sync"}</small> : null}
            </td>
            <td className="audit-checklist-table__details"><button type="button" aria-expanded={expanded}
              data-detail-item={item.checklist_item_id} aria-controls={props.detailsId}
              aria-label={`Evidence and details for question ${number}`} onClick={() => props.onOpenDetails(item)}><span>{expanded ? "Close" : "Details"}</span>{item.evidence_references?.length ? <span>{item.evidence_references.length}</span> : null}{expanded ? <ChevronUp size={13} aria-hidden /> : <ArrowUpRight size={13} aria-hidden />}</button></td>
          </tr>
        </Fragment>;
      })}{!props.items.length ? <tr><td colSpan={span}>No questions match this filter.</td></tr> : null}</tbody>
    </table>
  </div><div className="audit-checklist-table__footer"><span>Source questions and response columns are preserved.</span><span>Responses save when selected. Remarks save with your assessment.</span></div></>;
}

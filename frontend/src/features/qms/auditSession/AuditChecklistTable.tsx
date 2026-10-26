import { Fragment, isValidElement, memo, useLayoutEffect, useMemo, useRef, type CSSProperties, type ReactNode, type RefObject } from "react";
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
  renderDetails?: (item: Item) => ReactNode;
  renderAttachments?: (item: Item) => ReactNode;
};

type RowProps = {
  item: Item; choices: ChecklistResponseOption[]; columns: ChecklistResponseOption[];
  value: string; notes: string; number: string | number; pendingStatus?: string;
  expanded: boolean; canEdit: boolean; busy: boolean; detailsId?: string;
  actions: RefObject<Props>; details?: ReactNode; attachments?: ReactNode;
};
function sameAttachment(left: ReactNode, right: ReactNode): boolean {
  if (left === right) return true;
  if (!isValidElement<Record<string, unknown>>(left) || !isValidElement<Record<string, unknown>>(right) || left.type !== right.type || left.key !== right.key) return false;
  const keys = Object.keys(left.props);
  return keys.length === Object.keys(right.props).length && keys.every(key => left.props[key] === right.props[key]);
}
// Editing one answer or remark must not rerender every input and attachment menu.
const ChecklistRow = memo(function ChecklistRow({ item, choices, columns, value, notes, number, pendingStatus, expanded, canEdit, busy, detailsId, actions, details, attachments }: RowProps) {
  const selected = choices.find(option => option.value === value)
    || (value !== "NOT_VERIFIED" ? choices.find(option => option.canonical_status === value) : undefined);
  const pending = pendingStatus ? { status: pendingStatus } : undefined;
  const span = columns.length + 4;
  return <><tr className={expanded ? "is-selected" : ""} data-response={selected?.canonical_status} data-pending={Boolean(pending) || undefined}>
            <th scope="row" className="audit-checklist-table__number">{number}</th>
            <td className="audit-checklist-table__question">{item.prompt}</td>
            {columns.map((column) => {
              const option = choices.find((choice) => choice.value === column.value);
              return <td key={column.value} className="audit-checklist-table__answer">{option ? <label className="audit-checklist-table__response-target" data-status={option.canonical_status}><input type="radio"
                name={`checklist-answer-${item.checklist_item_id}`} aria-label={`${option.label} — question ${number}`}
                checked={selected?.value === option.value} disabled={!canEdit || busy}
                onChange={() => actions.current.onResponse(item, option)} /><span className="audit-checklist-table__mobile-choice">{option.label}</span></label> : <span aria-label="Not offered by this question">—</span>}</td>;
            })}
            <td className="audit-checklist-table__remarks">
              <textarea aria-label={`Remarks for question ${number}`} rows={2} value={notes}
                readOnly={!canEdit} onChange={(event) => actions.current.onNotes(item, event.target.value)}
                placeholder={canEdit ? "Add remarks…" : "No remarks"} />
              {attachments}
              {notes !== (item.auditor_notes || "") ? <>
                <button type="button" disabled={!canEdit || busy || !selected} onClick={() => actions.current.onSaveNotes(item)}>Save remarks</button>
                {!selected ? <small>Choose a response to save these remarks.</small> : null}
              </> : null}
              {pending ? <small role="status">{pending.status === "finding-draft" ? "Finding draft · not submitted" : pending.status === "draft" ? "Response draft" : ["conflict", "failed"].includes(pending.status) ? "Sync needs review" : "Saved on device · awaiting sync"}</small> : null}
            </td>
            <td className="audit-checklist-table__details"><button type="button" aria-expanded={expanded}
              data-detail-item={item.checklist_item_id} aria-controls={detailsId}
              aria-label={`Details for question ${number}`} title="Evidence and response details" onClick={() => actions.current.onOpenDetails(item)}><span>{expanded ? "Close" : "Details"}</span>{item.evidence_references?.length ? <span>{item.evidence_references.length}</span> : null}{expanded ? <ChevronUp size={13} aria-hidden /> : <ArrowUpRight size={13} aria-hidden />}</button></td>
          </tr>
          {expanded && details ? <tr className="audit-checklist-table__context-row"><td colSpan={span}>{details}</td></tr> : null}</>;
}, (previous, next) => (Object.keys(previous) as Array<keyof RowProps>).every(key => key === "attachments" ? sameAttachment(previous.attachments, next.attachments) : previous[key] === next[key]) && Object.keys(previous).length === Object.keys(next).length);

/** The uploaded form's question order and answer vocabulary remain the table. */
export default function AuditChecklistTable(props: Props) {
  const actions = useRef(props);
  useLayoutEffect(() => { actions.current = props; });
  const options = new Map<string, ChecklistResponseOption>();
  props.items.forEach(item => props.optionsForItem(item).forEach(option => { if (!options.has(option.value)) options.set(option.value, option); }));
  const columnsKey = JSON.stringify([...options.values()]);
  const columns = useMemo(() => JSON.parse(columnsKey) as ChecklistResponseOption[], [columnsKey]);
  const span = columns.length + 4;
  return <><div className="audit-checklist-table__scroll-hint">Scroll across for assessment and remarks <span aria-hidden>↔</span></div><div className="audit-checklist-table-scroll" tabIndex={0} role="region" aria-label="Scrollable checklist">
    <table className="qms-live-audit-focus__matrix-table audit-checklist-table" aria-label="Checklist assessment table"
      style={{ "--checklist-response-columns": Math.max(columns.length, 1) } as CSSProperties}>
      <thead><tr><th scope="col">No.</th><th scope="col">Checklist question</th>
        {columns.map(option => <th className="audit-checklist-table__answer" scope="col" key={option.value} title={responseMeaning[option.canonical_status] || option.label}>{option.label}</th>)}
        <th scope="col">Remarks / evidence</th><th scope="col">Context</th>
      </tr></thead>
      <tbody>{props.items.map((item, index) => {
        const expanded = props.expandedId === item.checklist_item_id;
        const number = item.checklist_ref && /^\d+(?:[.\-]\d+)*$/.test(item.checklist_ref) ? item.checklist_ref : props.numberById.get(item.checklist_item_id) || index + 1;
        return <Fragment key={item.checklist_item_id}>
          {(index === 0 || props.items[index - 1].section !== item.section) ? <tr id={`audit-section-${item.checklist_item_id}`} className="audit-checklist-table__section"><th colSpan={span} scope="rowgroup"><span>{item.section || "Checklist"}</span></th></tr> : null}
          <ChecklistRow item={item} choices={props.optionsForItem(item)} columns={columns} value={props.valueForItem(item)} notes={props.notesForItem(item)} number={number}
            pendingStatus={props.pendingForItem(item)?.status} expanded={expanded} canEdit={props.canEdit} busy={props.busy} detailsId={props.detailsId} actions={actions}
            attachments={props.renderAttachments?.(item)} details={expanded ? props.renderDetails?.(item) : undefined} />
        </Fragment>;
      })}{!props.items.length ? <tr><td colSpan={span}>No questions match this filter.</td></tr> : null}</tbody>
    </table>
  </div></>;
}

import QuestionEvidenceCapture from "../../../src/features/qms/auditSession/QuestionEvidenceCapture";
import "../../../src/styles/index.css";
import AuditWorkspaceDetails from "../../../src/features/qms/auditSession/AuditWorkspaceDetails";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import AuditFieldworkHeader from "../../../src/features/qms/auditSession/AuditFieldworkHeader";
import AuditChecklistToolbar, { type ChecklistFilter } from "../../../src/features/qms/auditSession/AuditChecklistToolbar";
import AuditChecklistTable from "../../../src/features/qms/auditSession/AuditChecklistTable";
import "../../../src/styles/qms-live-audit-workspace.css";
import type { ChecklistExecutionGovernanceRow as Item } from "../../../src/services/qmsChecklistExecutionGovernance";

const options = [
  { value: "S", label: "S", canonical_status: "COMPLIANT" },
  { value: "U", label: "U", canonical_status: "NONCOMPLIANT" },
  { value: "N/C", label: "N/C", canonical_status: "NOT_VERIFIED" },
  { value: "N/A", label: "N/A", canonical_status: "NOT_APPLICABLE" },
] as const;
const rows = [
  { checklist_item_id: "first", section: "ORGANIZATION/ MANAGEMENT", prompt: "Is there a description and organogram?", canonical_response_status: "COMPLIANT" },
  { checklist_item_id: "second", section: "ORGANIZATION/ MANAGEMENT", prompt: "Are approved key post holders in place?\nVerify responsibilities and authorization.", canonical_response_status: "NOT_VERIFIED" },
  { checklist_item_id: "third", section: "FLIGHT SAFETY MANAGEMENT", prompt: "Are risk assessments conducted for all identified hazards?", canonical_response_status: "NOT_VERIFIED" },
].map((row) => ({ audit_id: "audit", legacy_response_status: "PENDING", auditor_notes: "", evidence_references: [], entity_version: 1, ...row })) as Item[];

type Mode = { readOnly?: boolean; connectivity?: string; pendingStatus?: string };
function Harness({ initialRows = rows, mode = {} }: { initialRows?: Item[]; mode?: Mode }) {
  const [items, setItems] = useState(initialRows);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ChecklistFilter>("ALL");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, { status: string }>>(mode.pendingStatus ? { second: { status: mode.pendingStatus } } : {});
  const [expanded, setExpanded] = useState<string>();
  const visible = items.filter((item) => (!search || `${item.prompt} ${item.section}`.toLowerCase().includes(search.toLowerCase())) && (filter !== "UNANSWERED" || item.canonical_response_status === "NOT_VERIFIED"));
  return <div className="audit-fieldwork-preview qms-surface-root">
    <AuditFieldworkHeader title="Contractors audit" auditRef="SL / QAR / 2026 / 0042" backLink={<a href="#prepare">Preparation</a>} completed={items.filter((item) => item.canonical_response_status !== "NOT_VERIFIED").length} total={items.length} pending={Object.keys(pending).length} connectivity={mode.connectivity || "ONLINE"} teamCount={2} readOnly={Boolean(mode.readOnly)}
      syncMessage={Object.keys(pending).length ? "Changes awaiting sync" : "Offline package ready on this device"} syncActions={null}
      actions={<button type="button" className="is-primary" disabled>Complete fieldwork →</button>} />
    <AuditWorkspaceDetails><p>SL-QMS-20 · Contractors Audit Checklist · Rev 01</p></AuditWorkspaceDetails>
    <div className="audit-fieldwork-preview__body"><section className="qms-live-audit-focus__matrix" aria-label="Assessment register">
    <AuditChecklistToolbar search={search} onSearch={setSearch} filter={filter} onFilter={setFilter} visible={visible.length} total={items.length} sourceLabel="SL-QMS-20 · Rev 01" sections={visible.filter((item,index) => !index || visible[index-1].section !== item.section).map((item) => ({id:item.checklist_item_id, title:item.section || "Checklist"}))} />
    <AuditChecklistTable items={visible} numberById={new Map(items.map((row, index) => [row.checklist_item_id, index + 1]))}
      optionsForItem={() => [...options]} valueForItem={(row) => row.response_value || row.canonical_response_status}
      notesForItem={(row) => notes[row.checklist_item_id] ?? row.auditor_notes ?? ""}
      pendingForItem={(row) => pending[row.checklist_item_id]} canEdit={!mode.readOnly} busy={false} expandedId={expanded}
      onResponse={(row, option) => { setItems((current) => current.map((item) => item === row ? { ...item, response_value: option.value } : item)); setPending((current) => ({ ...current, [row.checklist_item_id]: { status: "pending" } })); }}
      onNotes={(row, value) => setNotes((current) => ({ ...current, [row.checklist_item_id]: value }))}
      onSaveNotes={(row) => setItems((current) => current.map((item) => item === row ? { ...item, auditor_notes: notes[row.checklist_item_id] } : item))}
      renderAttachments={(row) => <QuestionEvidenceCapture amoCode="test-amo" auditId="audit" item={row} disabled={Boolean(mode.readOnly)} />}
      renderDetails={(row) => <section aria-label="Question context"><h2>Criteria for {row.checklist_item_id}</h2><p>Review the applicable regulation and previous evidence.</p></section>}
      onOpenDetails={(row) => setExpanded(row.checklist_item_id === expanded ? undefined : row.checklist_item_id)} />
    </section></div>
  </div>;
}
let root: ReturnType<typeof createRoot>;
export function mount(source?: Array<{prompt: string; section: string; checklist_ref?: string}>, mode: Mode = {}) {
  root ||= createRoot(document.getElementById("root")!);
  const initialRows = source?.map((row, index) => ({ ...rows[2], ...row, checklist_item_id: `source-${index}` }));
  root.render(<Harness key={`${source?.length || 3}-${JSON.stringify(mode)}`} initialRows={initialRows} mode={mode} />);
}

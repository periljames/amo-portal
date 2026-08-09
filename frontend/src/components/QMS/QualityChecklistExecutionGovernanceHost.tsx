import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, History, PanelRightClose, PanelRightOpen, Save, ShieldAlert } from "lucide-react";

import { qmsResolveAudit } from "../../services/qms";
import {
  listChecklistExecutionGovernance,
  updateChecklistExecutionGovernance,
  type CanonicalChecklistResponse,
  type ChecklistExecutionGovernanceRow,
} from "../../services/qmsChecklistExecutionGovernance";
import "../../styles/qms-checklist-execution-governance.css";

type Props = { amoCode: string; auditKey: string; activeTab?: string | null };

type Draft = {
  status: CanonicalChecklistResponse;
  notes: string;
  evidence: string;
  reason: string;
};

const RESPONSE_OPTIONS: Array<{ value: CanonicalChecklistResponse; label: string }> = [
  { value: "COMPLIANT", label: "Compliant" },
  { value: "NONCOMPLIANT", label: "Noncompliant" },
  { value: "OBSERVATION", label: "Observation" },
  { value: "NOT_APPLICABLE", label: "Not applicable" },
  { value: "NOT_VERIFIED", label: "Not verified" },
];

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Checklist execution update could not be saved.";
}

function evidenceText(row: ChecklistExecutionGovernanceRow): string {
  return (row.evidence_references || []).map((value) => typeof value === "string" ? value : JSON.stringify(value)).join("\n");
}

function parseEvidence(value: string): Array<Record<string, unknown> | string> {
  return value.split("\n").map((entry) => entry.trim()).filter(Boolean).map((entry) => {
    if (!entry.startsWith("{")) return entry;
    try {
      const parsed = JSON.parse(entry);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : entry;
    } catch {
      return entry;
    }
  });
}

const QualityChecklistExecutionGovernanceHost: React.FC<Props> = ({ amoCode, auditKey, activeTab }) => {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const queryClient = useQueryClient();
  const shouldRender = activeTab === "checklist";

  const auditQuery = useQuery({
    queryKey: ["qms-checklist-execution-audit", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    enabled: Boolean(open && shouldRender && auditKey),
  });
  const auditId = auditQuery.data?.id || "";
  const executionQuery = useQuery({
    queryKey: ["qms-checklist-execution-governance", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistExecutionGovernance(amoCode, auditId, signal),
    enabled: Boolean(open && auditId),
  });
  const rows = useMemo(() => executionQuery.data?.items || [], [executionQuery.data?.items]);

  useEffect(() => {
    if (!rows.length) return;
    setDrafts((current) => {
      const next = { ...current };
      rows.forEach((row) => {
        if (next[row.checklist_item_id]) return;
        next[row.checklist_item_id] = {
          status: row.canonical_response_status,
          notes: row.auditor_notes || "",
          evidence: evidenceText(row),
          reason: "Record attributable checklist execution evidence and auditor judgment.",
        };
      });
      return next;
    });
  }, [rows]);

  const updateMutation = useMutation({
    mutationFn: ({ row, draft }: { row: ChecklistExecutionGovernanceRow; draft: Draft }) => updateChecklistExecutionGovernance(
      amoCode,
      auditId,
      row.checklist_item_id,
      {
        canonical_response_status: draft.status,
        auditor_notes: draft.notes.trim() || null,
        evidence_references: parseEvidence(draft.evidence),
        reason: draft.reason.trim(),
      },
    ),
    onSuccess: async (saved) => {
      setError("");
      setSuccess(`${saved.checklist_ref || "Checklist item"} saved as ${saved.canonical_response_status.replaceAll("_", " ")}.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-checklist-execution-governance", amoCode, auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-items", auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-context", auditKey] }),
      ]);
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  if (!shouldRender || !amoCode || !auditKey) return null;
  const setDraft = (itemId: string, patch: Partial<Draft>) => setDrafts((current) => ({
    ...current,
    [itemId]: { ...(current[itemId] || { status: "NOT_VERIFIED", notes: "", evidence: "", reason: "" }), ...patch },
  }));

  return <>
    <button className="qms-checklist-execution-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-checklist-execution-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Checklist execution
    </button>
    {open ? <aside id="qms-checklist-execution-panel" className="qms-checklist-execution-panel" aria-label="Checklist execution governance">
      <header>
        <div><span>Execution governance</span><strong>Canonical response · notes · evidence</strong></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close checklist execution governance"><PanelRightClose size={18} /></button>
      </header>
      <div className="qms-checklist-execution-body">
        <p>The existing audit checklist row remains authoritative. This layer records the controlled MD response vocabulary, auditor notes and structured evidence references without rewriting historical values.</p>
        <div className="qms-checklist-execution-compat"><ShieldAlert size={16} /><span><strong>Compatibility:</strong> Noncompliant is stored as legacy <code>NON_CONFORMING</code>; Not verified remains legacy <code>PENDING</code> so existing closeout gates stay unresolved.</span></div>
        {error ? <div className="qms-checklist-execution-error" role="alert">{error}</div> : null}
        {success ? <div className="qms-checklist-execution-success"><CheckCircle2 size={16} /> {success}</div> : null}
        {auditQuery.isLoading || executionQuery.isLoading ? <p>Loading authoritative checklist execution rows…</p> : null}
        {!executionQuery.isLoading && !rows.length ? <div className="qms-checklist-execution-empty"><ClipboardCheck size={20} /><span>No checklist execution rows are available yet. Apply or create the audit checklist first.</span></div> : null}
        {rows.map((row, index) => {
          const draft = drafts[row.checklist_item_id] || {
            status: row.canonical_response_status,
            notes: row.auditor_notes || "",
            evidence: evidenceText(row),
            reason: "Record attributable checklist execution evidence and auditor judgment.",
          };
          return <article className="qms-checklist-execution-row" key={row.checklist_item_id}>
            <header><div><span>{row.section || "Checklist"} · {row.checklist_ref || `Item ${index + 1}`}</span><strong>{row.prompt}</strong></div><span className={`qms-checklist-execution-status is-${draft.status.toLowerCase()}`}>{draft.status.replaceAll("_", " ")}</span></header>
            <div className="qms-checklist-execution-grid">
              <label>Canonical response<select value={draft.status} onChange={(event) => setDraft(row.checklist_item_id, { status: event.target.value as CanonicalChecklistResponse })}>{RESPONSE_OPTIONS.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
              <label>Requirement / reference<input value={row.requirement_ref || ""} readOnly /></label>
            </div>
            <label>Objective evidence from authoritative row<textarea value={row.objective_evidence || ""} readOnly placeholder="No objective-evidence narrative has been recorded on the audit checklist row." /></label>
            <label>Auditor notes<textarea value={draft.notes} onChange={(event) => setDraft(row.checklist_item_id, { notes: event.target.value })} placeholder="Record the auditor's controlled judgment, limitations or verification note." /></label>
            <label>Evidence attachments / references<textarea value={draft.evidence} onChange={(event) => setDraft(row.checklist_item_id, { evidence: event.target.value })} placeholder={'One reference per line, e.g. DMS:DOC-123@REV-4\n{"source_type":"PHOTO","source_id":"evidence-88"}'} /></label>
            <label>Change reason<input value={draft.reason} onChange={(event) => setDraft(row.checklist_item_id, { reason: event.target.value })} /></label>
            <div className="qms-checklist-execution-actions"><span><History size={14} /> {row.events.length} governed change event{row.events.length === 1 ? "" : "s"}</span><button type="button" onClick={() => updateMutation.mutate({ row, draft })} disabled={updateMutation.isPending || draft.reason.trim().length < 8}><Save size={15} /> Save governed execution</button></div>
          </article>;
        })}
      </div>
    </aside> : null}
  </>;
};

export default QualityChecklistExecutionGovernanceHost;

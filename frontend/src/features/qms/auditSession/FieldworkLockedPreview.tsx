import React, { useMemo } from "react";
import { ClipboardCheck, LockKeyhole, X } from "lucide-react";
import { Link } from "react-router-dom";

import type { ChecklistBinding, ChecklistTemplateItem } from "../../../services/qmsChecklistTemplates";
import { auditSessionPath } from "./auditSessionRoutes";

type Props = {
  amoCode: string;
  auditKey: string;
  stageLabel: string;
  detail: string;
  bindings: ChecklistBinding[];
};

type PreviewItem = ChecklistTemplateItem & {
  previewId: string;
  templateCode: string;
  revisionNo: number;
  contentSha256: string;
};

const PREVIEW_RESPONSES = ["Compliant", "NCR", "Observation", "N/A", "Not verified"];

const FieldworkLockedPreview: React.FC<Props> = ({ amoCode, auditKey, stageLabel, detail, bindings }) => {
  const items = useMemo<PreviewItem[]>(() => bindings.flatMap((binding) =>
    (binding.item_snapshot || []).map((item, index) => ({
      ...item,
      previewId: `${binding.id}-${index}`,
      templateCode: binding.template_code,
      revisionNo: binding.revision_no,
      contentSha256: binding.content_sha256,
    })),
  ), [bindings]);
  const selected = items[0] || null;

  return (
    <div className="qms-live-audit-focus qms-live-audit-focus--locked" role="region" aria-label="Locked fieldwork preview">
      <div className="qms-live-audit-focus__preview-surface" aria-hidden="true">
        <header className="qms-live-audit-focus__header">
          <div>
            <h2>Fieldwork</h2>
            <p className="qms-live-audit-focus__helper">Record checklist responses, findings, and evidence.</p>
          </div>
          <div className="qms-live-audit-focus__header-meta">
            <span>Preview</span>
            <span>Stage: {stageLabel}</span>
            <span>{items.length ? `0/${items.length} complete · 0%` : "No checklist items · Not applicable"}</span>
            <span>0 active</span>
            <span>Sync clear</span>
            <button type="button" className="qms-live-audit-focus__closing-link is-primary" disabled><ClipboardCheck size={16} /> Complete Fieldwork</button>
            <span className="qms-live-audit-focus__closing-link"><X size={16} /> Back to Prepare</span>
          </div>
        </header>

        <div className="qms-live-audit-focus__body">
          <aside className="qms-live-audit-focus__sections" aria-label="Checklist questions preview">
            <div className="qms-live-audit-focus__progress"><span style={{ width: "0%" }} /></div>
            <h2 className="qms-live-audit-focus__sections-title">Checklist</h2>
            <div className="qms-live-audit-focus__question-list">
              {items.map((item, index) => (
                <button type="button" key={item.previewId} className={index === 0 ? "is-selected" : ""} disabled>
                  <span>{index + 1}</span>
                  <div><strong>{item.checklist_ref || item.requirement_ref || `Question ${index + 1}`}</strong><small>{item.section || "General"}</small></div>
                  <em data-status="NOT_VERIFIED">NOT VERIFIED</em>
                </button>
              ))}
            </div>
          </aside>

          <main className="qms-live-audit-focus__question">
            {selected ? (
              <>
                <div className="qms-live-audit-focus__question-head"><div><span>{selected.section || "Checklist"}</span><h2>{selected.prompt}</h2></div><span>1 / {items.length}</span></div>
                <dl className="qms-live-audit-focus__references">
                  <div><dt>Checklist ref</dt><dd>{selected.checklist_ref || "—"}</dd></div>
                  <div><dt>Requirement</dt><dd>{selected.requirement_ref || "—"}</dd></div>
                  <div><dt>Regulatory source</dt><dd>{selected.regulatory_source_ref || "—"}</dd></div>
                  <div><dt>Manual source</dt><dd>{selected.manual_source_ref || "—"}</dd></div>
                  <div><dt>Frozen checklist</dt><dd>{selected.templateCode} Rev {selected.revisionNo} · SHA {selected.contentSha256.slice(0, 12)}…</dd></div>
                  <div><dt>Current</dt><dd>NOT VERIFIED</dd></div>
                </dl>
                <section className="qms-live-audit-focus__expected-evidence" aria-label="Expected evidence preview">
                  <h3>Expected evidence</h3>
                  <p>{selected.expected_evidence || "No expected-evidence statement was defined in the applied checklist revision."}</p>
                  <small>{selected.mandatory === false ? "Optional verification item" : "Mandatory verification item"}</small>
                </section>
                <div className="qms-live-audit-focus__responses" aria-label="Checklist response preview">
                  {PREVIEW_RESPONSES.map((label) => <button type="button" key={label} disabled>{label}</button>)}
                </div>
                <label className="qms-live-audit-focus__notes"><span>Auditor note</span><textarea readOnly rows={5} placeholder="Record objective, attributable fieldwork notes." /></label>
                <div className="qms-live-audit-focus__note-actions"><button type="button" disabled>Save note</button></div>
                <section className="qms-live-audit-focus__evidence"><strong>Evidence</strong><p>Attach or link objective evidence during active fieldwork.</p></section>
                <footer className="qms-live-audit-focus__nav"><button type="button" disabled>Previous</button><button type="button" disabled>Next</button></footer>
              </>
            ) : <div className="qms-live-audit-focus__empty">No governed checklist is bound yet. The fieldwork layout remains visible while preparation is completed.</div>}
          </main>

          <aside className="qms-live-audit-focus__summary">
            <section><span>Progress</span><strong>{items.length ? "0%" : "N/A"}</strong><small>{items.length ? `0 of ${items.length} questions resolved` : "No required checklist items"}</small></section>
            <section className="qms-live-audit-focus__stats"><div><strong>0</strong><span>Compliant</span></div><div><strong>0</strong><span>NCR</span></div><div><strong>0</strong><span>Observations</span></div><div><strong>{items.length}</strong><span>Pending</span></div></section>
            <section><span>Device sync</span><strong>0</strong><small>No fieldwork changes can be recorded until the lifecycle gate is satisfied.</small></section>
            <section><span>Audit team live</span><strong>0</strong><small>Presence starts when Fieldwork is active.</small></section>
            <section><span>Findings</span><strong>0</strong><small>Findings are raised from governed checklist responses during fieldwork.</small></section>
            <section className="qms-live-audit-focus__sharing"><span>Auditee live view</span><strong>Released-data boundary</strong><small>Private checklist notes remain internal.</small></section>
          </aside>
        </div>
      </div>

      <section className="qms-live-audit-focus__lock-overlay" aria-label="Fieldwork requirements">
        <div className="qms-live-audit-focus__lock-card">
          <span className="qms-live-audit-focus__lock-eyebrow"><LockKeyhole size={15} /> FIELDWORK LOCKED</span>
          <h2>Prepare the audit before fieldwork</h2>
          <p>{detail}</p>
          <small>The actual fieldwork page is shown underneath in preview mode. It remains read-only until the required preparation and lifecycle gates are complete.</small>
          <div className="qms-live-audit-focus__lock-actions">
            <Link to={auditSessionPath(amoCode, auditKey, "prepare")}>Back to Prepare</Link>
            <Link className="is-primary" to={auditSessionPath(amoCode, auditKey, "setup")}>Open Setup</Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default FieldworkLockedPreview;

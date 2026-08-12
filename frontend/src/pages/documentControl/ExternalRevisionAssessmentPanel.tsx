import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, ExternalLink, FileCheck2, ShieldAlert, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  assessExternalRevision,
  getExternalAssessmentContext,
  type ExternalApplicabilityDecision,
  type ExternalAssessmentContext,
} from "../../services/documentControlCompliancePortfolio";
import { DocumentControlError, DocumentControlLoading, DocumentControlStatus } from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";

export default function ExternalRevisionAssessmentPanel({ sourceId, onClose, onChanged }: { sourceId: string; onClose: () => void; onChanged: () => void }) {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [context, setContext] = useState<ExternalAssessmentContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<ExternalApplicabilityDecision>("APPLICABLE");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void getExternalAssessmentContext(tenant, sourceId).then((payload) => {
      if (!active) return;
      setContext(payload);
      const existing = payload.received_revision?.applicability_status;
      if (existing === "APPLICABLE" || existing === "PARTIAL" || existing === "NOT_APPLICABLE") setStatus(existing);
      setNotes(payload.received_revision?.notes || "");
    }).catch((caught) => active && setError(caught instanceof Error ? caught.message : "Assessment context could not be loaded.")).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [sourceId, tenant]);

  const save = async () => {
    if (!context?.received_revision) return;
    setSaving(true);
    setError("");
    try {
      const next = await assessExternalRevision(tenant, sourceId, {
        receipt_id: context.received_revision.id,
        applicability_status: status,
        notes,
      });
      setContext(next);
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The external revision assessment could not be recorded.");
    } finally {
      setSaving(false);
    }
  };

  return <aside className="dms-external-assessment" role="dialog" aria-modal="true" aria-label="External revision assessment">
    <header><div><small>EXTERNAL TECHNICAL DATA</small><h2>Revision assessment</h2></div><button type="button" aria-label="Close external revision assessment" onClick={onClose}><X size={16} /></button></header>
    {loading ? <DocumentControlLoading label="Loading external revision evidence…" /> : null}
    {error ? <DocumentControlError message={error} /> : null}
    {!loading && context ? <div className="dms-external-assessment__body">
      <section className="dms-external-assessment__source">
        <div><small>Provider</small><strong>{context.source.provider}</strong><span>{context.source.authority || "No authority recorded"}</span></div>
        <div><small>Received revision</small><strong>{context.received_revision?.revision_label || "No revision received"}</strong><span>{context.received_revision?.received_at ? new Date(context.received_revision.received_at).toLocaleString() : "No receipt date"}</span></div>
        <div><small>Current source revision</small><strong>{context.current_revision?.revision_label || "No CURRENT receipt recorded"}</strong><span>{context.current_revision?.publication_date || "Publication date unavailable"}</span></div>
        <div><small>Work item</small><DocumentControlStatus status={context.work_item_status} kind={context.assessment_required ? "warning" : "success"} /></div>
      </section>

      {context.assessment_required ? <div className="dms-external-assessment__alert"><ShieldAlert size={18} /><div><strong>Applicability assessment required</strong><p>Determine whether the received source revision applies to the AMO and record the decision against the retained receipt.</p></div></div> : <div className="dms-external-assessment__complete"><CheckCircle2 size={18} /> Latest receipt has a recorded applicability assessment.</div>}

      <section>
        <header className="dms-external-assessment__section-head"><div><strong>Affected internal documents</strong><span>{context.affected_internal_documents.length} confirmed governed relationship{context.affected_internal_documents.length === 1 ? "" : "s"}</span></div></header>
        {context.affected_internal_documents.length ? <div className="dms-external-assessment__affected">{context.affected_internal_documents.map((document) => <button type="button" key={document.id} onClick={() => navigate(`${basePath}/library/${document.id}?tab=compliance`)}><FileCheck2 size={15} /><span><strong>{document.code}</strong><small>{document.title}</small></span><ArrowRight size={14} /></button>)}</div> : <p className="dms-external-assessment__muted">No confirmed governed internal-document relationship is currently recorded for this external source.</p>}
      </section>

      {context.received_revision ? <section className="dms-external-assessment__decision">
        <label><span>Applicability decision</span><select value={status} onChange={(event) => setStatus(event.target.value as ExternalApplicabilityDecision)}><option value="APPLICABLE">Applicable</option><option value="PARTIAL">Partially applicable</option><option value="NOT_APPLICABLE">Not applicable</option></select></label>
        <label><span>Assessment evidence / rationale</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} placeholder="Record the applicability reasoning, impacted manuals/processes and follow-up required." /></label>
        <div className="dms-external-assessment__actions"><button type="button" className="dc-button dc-button--primary" disabled={saving} onClick={() => void save()}>{saving ? "Recording…" : "Record assessment"}</button>{context.source.access_url ? <a className="dc-button" href={context.source.access_url} target="_blank" rel="noreferrer">Open provider source <ExternalLink size={14} /></a> : null}</div>
      </section> : null}
    </div> : null}
  </aside>;
}
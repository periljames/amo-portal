import { useState } from "react";
import { rebuildChecklistSource, reviewChecklistSource, type ChecklistSourceReview as Review } from "../../../services/qmsChecklistTemplates";
import { listOfflineMutations } from "../../../services/offlinePersistence";
import { listOfflineAuditEvidence } from "../../../services/qmsOfflineAuditEvidence";
import "./auditChecklistTable.css";

export default function ChecklistSourceReview({ amoCode, auditId, hasPendingChanges, onRebuilt }: {
  amoCode: string; auditId: string; hasPendingChanges: boolean; onRebuilt: () => Promise<void>;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("Rebuild the unanswered checklist from the original uploaded table, excluding form fields and preserving source order.");
  const load = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true); setBusy(true); setError("");
    try { setReview(await reviewChecklistSource(amoCode, auditId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "The uploaded source could not be reviewed."); }
    finally { setBusy(false); }
  };
  const rebuild = async () => {
    if (!review || hasPendingChanges) return;
    setBusy(true); setError("");
    try {
      const [mutations, evidence] = await Promise.all([listOfflineMutations(), listOfflineAuditEvidence(amoCode, auditId)]);
      if (mutations.some((entry) => entry.path.includes(`/audits/${encodeURIComponent(auditId)}/`)) || evidence.length) {
        throw new Error("Sync or resolve this device’s pending fieldwork and evidence before rebuilding.");
      }
      await rebuildChecklistSource(amoCode, auditId, review.preview_sha256, reason);
      await onRebuilt();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The checklist could not be rebuilt."); }
    finally { setBusy(false); }
  };
  return <section className="checklist-source-review">
    <button type="button" onClick={() => void load()} disabled={busy} aria-expanded={open}>Review uploaded checklist source</button>
    {open ? <div className="checklist-source-review__content">
      {busy ? <p role="status">Reading the controlled source…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {review && !review.documents.length ? <p>No checklist imported by the legacy text-line extractor needs rebuilding.</p> : null}
      {review?.documents.map((document) => <div key={document.binding_id}>
        <h3>{document.document_code} · {document.filename}</h3>
        <p>{document.previous_count} imported rows → <strong>{document.question_count} source assessment rows</strong>. Form fields and page furniture are excluded.</p>
        <details><summary>Preview every extracted question</summary><ol>{document.items.map((item, index) => <li key={index}><small>{item.section}</small><p>{item.prompt}</p></li>)}</ol></details>
      </div>)}
      {review?.blocker ? <p role="status">{review.blocker}</p> : null}
      {hasPendingChanges ? <p role="status">Sync or resolve this device’s pending fieldwork before rebuilding.</p> : null}
      {review?.can_rebuild && review.can_manage ? <div>
        <p>Rebuild replaces only unanswered imported rows. The previous preparation remains in history; review and issue a new preparation revision before resuming fieldwork.</p>
        <label>Reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} /></label>
        <button type="button" disabled={busy || hasPendingChanges || reason.trim().length < 8} onClick={() => void rebuild()}>Rebuild unanswered rows and review preparation</button>
      </div> : null}
    </div> : null}
  </section>;
}

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileCheck2, Files, Link2, X } from "lucide-react";

import {
  downloadAuditDocumentSubmission,
  listAuditDocumentSubmissions,
} from "../../../services/qmsAuditExternalAccess";
import {
  listControlledDocumentSubmissions,
  listGovernedAuditDocumentRequests,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { saveDownloadedFile } from "../../../utils/downloads";
import OccurrenceToolbarPortal, { AUDIT_PREPARE_TOOLBAR_ID } from "./OccurrenceToolbarPortal";
import "../../../styles/qms-audit-document-review.css";

type Props = { amoCode: string; auditKey: string; launcherPortalId?: string };

function bytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

const AuditDocumentSubmissionReviewPanel: React.FC<Props> = ({ amoCode, auditKey, launcherPortalId = AUDIT_PREPARE_TOOLBAR_ID }) => {
  const [open, setOpen] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-prepare-document-review-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const requestsQuery = useQuery({
    queryKey: ["qms-governed-audit-document-requests", amoCode, auditId],
    queryFn: ({ signal }) => listGovernedAuditDocumentRequests(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const controlledQuery = useQuery({
    queryKey: ["qms-controlled-document-submissions", amoCode, auditId],
    queryFn: ({ signal }) => listControlledDocumentSubmissions(amoCode, auditId, signal),
    enabled: Boolean(open && auditId),
    staleTime: 1_500,
  });
  const requests = useMemo(() => requestsQuery.data?.items ?? [], [requestsQuery.data?.items]);
  const controlledByRequest = useMemo(
    () => new Map((controlledQuery.data?.items || []).map((submission) => [submission.request_id, submission])),
    [controlledQuery.data?.items],
  );
  const selectedRequest = useMemo(
    () => requests.find((request) => request.id === selectedRequestId) || requests.find((request) => request.status === "UPLOADED") || requests[0] || null,
    [requests, selectedRequestId],
  );
  const controlledSubmission = selectedRequest ? controlledByRequest.get(selectedRequest.id) || null : null;
  const submissionsQuery = useQuery({
    queryKey: ["qms-audit-document-submissions", amoCode, auditId, selectedRequest?.id],
    queryFn: ({ signal }) => listAuditDocumentSubmissions(amoCode, auditId, selectedRequest!.id, signal),
    enabled: Boolean(open && auditId && selectedRequest?.id && selectedRequest.source_mode !== "CONTROLLED_DMS"),
    staleTime: 1_500,
  });

  const download = async (submissionId: string, filename: string) => {
    if (!selectedRequest) return;
    setBusy(submissionId); setError(null);
    try { saveDownloadedFile(await downloadAuditDocumentSubmission(amoCode, auditId, selectedRequest.id, submissionId), filename); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Document download failed."); }
    finally { setBusy(null); }
  };

  const submittedCount = requests.filter((request) => Boolean(request.uploaded_at) || request.status === "UPLOADED" || controlledByRequest.has(request.id)).length;

  const launcher = (
    <button
      className="qms-audit-document-review-launcher qms-occurrence-toolbar-btn"
      type="button"
      onClick={() => setOpen((value) => !value)}
      aria-expanded={open}
    >
      <Files size={16} /> Submissions <span>{submittedCount}</span>
    </button>
  );

  return <>
    {launcherPortalId ? (
      <OccurrenceToolbarPortal containerId={launcherPortalId}>{launcher}</OccurrenceToolbarPortal>
    ) : launcher}
    {open ? <aside className="qms-audit-document-review" aria-label="Submitted pre-audit evidence">
      <header><div><span>PRE-AUDIT EVIDENCE</span><strong>Governed submissions</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close document review"><X size={17} /></button></header>
      {error ? <div className="qms-audit-document-review__error" role="alert">{error}</div> : null}
      <div className="qms-audit-document-review__requests">
        {requests.map((request) => <button key={request.id} type="button" className={selectedRequest?.id === request.id ? "is-active" : ""} onClick={() => setSelectedRequestId(request.id)}><div><strong>{request.title}</strong><small>{request.request_type.replaceAll("_", " ")} · {request.status.replaceAll("_", " ")} · {request.is_required ? "required" : "optional"}</small></div>{request.uploaded_at || controlledByRequest.has(request.id) ? <FileCheck2 size={15} /> : null}</button>)}
        {!requests.length ? <p>No document requests exist for this audit.</p> : null}
      </div>
      {selectedRequest ? <section>
        <header><strong>{selectedRequest.title}</strong><small>{selectedRequest.description || "No additional request instructions."}</small></header>
        {selectedRequest.linked_criterion ? <blockquote><strong>Criterion:</strong> {selectedRequest.linked_criterion}</blockquote> : null}
        {selectedRequest.controlled_document_id ? <div className="qms-audit-document-review__controlled"><Link2 size={15} /><span><strong>Requested controlled DMS source</strong><small>Document {selectedRequest.controlled_document_id}{selectedRequest.controlled_revision_id ? ` · revision ${selectedRequest.controlled_revision_id}` : " · authorised revision may be selected"}</small></span></div> : null}
        {controlledSubmission ? <div className="qms-audit-document-review__controlled"><FileCheck2 size={15} /><span><strong>Auditee controlled-record response</strong><small>Document {controlledSubmission.document_id}{controlledSubmission.revision_id ? ` · revision ${controlledSubmission.revision_id}` : " · current authorised revision"}</small>{controlledSubmission.response_comment ? <small>{controlledSubmission.response_comment}</small> : null}<small>Linked {new Date(controlledSubmission.created_at).toLocaleString()}</small></span></div> : null}
        <div className="qms-audit-document-review__submissions">
          {(submissionsQuery.data?.items || []).map((submission) => <article key={submission.id}><div><strong>{submission.filename}</strong><small>{bytes(submission.size_bytes)} · {submission.content_type || "unknown content type"}</small><code>SHA-256 {submission.sha256}</code>{submission.response_comment ? <blockquote>{submission.response_comment}</blockquote> : null}<small>Submitted {new Date(submission.created_at).toLocaleString()}</small></div><button type="button" disabled={busy === submission.id} onClick={() => void download(submission.id, submission.filename)}><Download size={15} /> {busy === submission.id ? "Downloading…" : "Download"}</button></article>)}
          {submissionsQuery.isLoading ? <p>Loading uploaded evidence…</p> : null}
          {!submissionsQuery.isLoading && !(submissionsQuery.data?.items.length) && !controlledSubmission ? <p>No auditee evidence response is recorded for this request yet.</p> : null}
        </div>
      </section> : null}
    </aside> : null}
  </>;
};

export default AuditDocumentSubmissionReviewPanel;
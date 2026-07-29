import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Download,
  Eye,
  FileCheck2,
  RefreshCw,
  Search,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react";

import {
  getGeneratedDocumentationRecord,
  getGeneratedDocumentationRecords,
  reviewGeneratedDocumentationRecord,
  type GeneratedDocumentationRecord,
  type GeneratedDocumentationRecordsResponse,
} from "../../services/documentationRecords";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import "./documentControlRecords.css";

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function statusKind(status: string): "success" | "warning" | "danger" | "neutral" | "info" {
  if (["ACCEPTED", "VERIFIED"].includes(status)) return "success";
  if (["RETURNED", "MISMATCH", "MISSING"].includes(status)) return "danger";
  if (["PENDING_REVIEW", "SUBMITTED"].includes(status)) return "warning";
  return "neutral";
}

export default function DocumentControlRecordsPage() {
  const { tenant } = useDocumentControlRoute();
  const [response, setResponse] = useState<GeneratedDocumentationRecordsResponse | null>(null);
  const [selected, setSelected] = useState<GeneratedDocumentationRecord | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setResponse(await getGeneratedDocumentationRecords(tenant, { status: status || undefined, page, perPage: 75 }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Generated documentation records could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [page, status, tenant]);

  useEffect(() => { void load(); }, [load]);

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return response?.items || [];
    return (response?.items || []).filter((record) => [
      record.record_number,
      record.template?.code,
      record.template?.title,
      record.record_series?.code,
      record.record_series?.title,
      record.status,
      record.artifact_filename,
    ].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, response]);

  const inspect = async (record: GeneratedDocumentationRecord) => {
    setBusy(true);
    setError("");
    try {
      setSelected(await getGeneratedDocumentationRecord(tenant, record.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The retained record could not be verified.");
    } finally {
      setBusy(false);
    }
  };

  return <DocumentControlShell
    title="Generated records"
    subtitle="Immutable outputs created from controlled forms, checklists, and registers, retained against their exact template revision and originating document reference."
    canControl
    actions={<button type="button" className="dc-button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button>}
  >
    <div className="dc-records-summary">
      <div><strong>{response?.pagination.total || 0}</strong><span>retained records</span></div>
      <div><strong>{response?.items.filter((item) => ["PENDING_REVIEW", "SUBMITTED"].includes(item.status)).length || 0}</strong><span>awaiting review on this page</span></div>
      <div><strong>{response?.items.filter((item) => item.status === "ACCEPTED").length || 0}</strong><span>accepted on this page</span></div>
    </div>

    <div className="dc-records-toolbar">
      <label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find record number, template, record series, status, or filename" /></label>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter records by status">
        <option value="">All statuses</option>
        <option value="PENDING_REVIEW">Pending review</option>
        <option value="SUBMITTED">Submitted</option>
        <option value="ACCEPTED">Accepted</option>
        <option value="RETURNED">Returned</option>
      </select>
    </div>

    {loading ? <DocumentControlLoading label="Loading retained records…" /> : null}
    {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
    {!loading && !error && !items.length ? <DocumentControlEmpty icon={FileCheck2} title="No generated records match this view" message="Completed controlled forms and checklists will appear here after submission." /> : null}

    {!loading && items.length ? <div className="dc-table-wrap"><table className="dc-table dc-records-table"><thead><tr><th>Record</th><th>Controlled template</th><th>Record series</th><th>Submitted</th><th>Status</th><th>Retention</th><th>Action</th></tr></thead><tbody>{items.map((record) => <tr key={record.id}>
      <td><strong>{record.record_number}</strong><small>{record.artifact_filename}</small></td>
      <td><strong>{record.template?.code || "Unavailable"}</strong><small>{record.template?.title || "Template metadata unavailable"}</small><small>{record.template_revision ? `Issue ${record.template_revision.issue_number || "—"} · Rev ${record.template_revision.revision_number}` : "Revision unavailable"}</small></td>
      <td><strong>{record.record_series?.code || "Unassigned"}</strong><small>{record.record_series?.title || "No record series"}</small></td>
      <td><strong>{formatDate(record.submitted_at)}</strong><small>{record.submitted_by_user_id || "System"}</small></td>
      <td><DocumentControlStatus status={record.status} kind={statusKind(record.status)} /></td>
      <td><strong>{record.retention_years ? `${record.retention_years} years` : "Policy-driven"}</strong></td>
      <td><button type="button" className="dc-button" onClick={() => void inspect(record)} disabled={busy}><Eye size={14} /> Inspect</button></td>
    </tr>)}</tbody></table></div> : null}

    {response && response.pagination.total > response.pagination.per_page ? <div className="dc-records-pagination"><button type="button" className="dc-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><span>Page {page}</span><button type="button" className="dc-button" disabled={page * response.pagination.per_page >= response.pagination.total} onClick={() => setPage((value) => value + 1)}>Next</button></div> : null}

    {selected ? <RecordDetail record={selected} tenant={tenant} canReview={Boolean(response?.capabilities.review)} onClose={() => setSelected(null)} onReviewed={() => { setSelected(null); void load(); }} /> : null}
  </DocumentControlShell>;
}

function RecordDetail({ record, tenant, canReview, onClose, onReviewed }: { record: GeneratedDocumentationRecord; tenant: string; canReview: boolean; onClose: () => void; onReviewed: () => void }) {
  const [decision, setDecision] = useState<"ACCEPT" | "RETURN">("ACCEPT");
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reviewable = canReview && ["PENDING_REVIEW", "SUBMITTED", "RETURNED"].includes(record.status) && record.integrity?.status === "VERIFIED";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await reviewGeneratedDocumentationRecord(tenant, record.id, {
        decision,
        comments: comments.trim(),
        evidence_references: evidence.split(/[\n,;]+/).map((value) => value.trim()).filter(Boolean),
      });
      onReviewed();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The record review decision could not be retained.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><section className="publications-upload-dialog dc-record-detail" role="dialog" aria-modal="true" aria-label={`Generated record ${record.record_number}`}>
    <header><div><h2>{record.record_number}</h2><p>{record.template?.code} · {record.template?.title}</p></div><button type="button" onClick={onClose} disabled={busy}><X size={18} /></button></header>
    <div className="dc-record-detail__facts">
      <div><span>Status</span><DocumentControlStatus status={record.status} kind={statusKind(record.status)} /></div>
      <div><span>Integrity</span><DocumentControlStatus status={record.integrity?.status || "UNKNOWN"} kind={statusKind(record.integrity?.status || "UNKNOWN")} /></div>
      <div><span>Template</span><strong>{record.template?.code} · Rev {record.template_revision?.revision_number}</strong></div>
      <div><span>Submitted</span><strong>{formatDate(record.submitted_at)}</strong></div>
      <div><span>Retention</span><strong>{record.retention_years ? `${record.retention_years} years` : "Policy-driven"}</strong></div>
      <div><span>Checksum</span><code>{record.artifact_sha256}</code></div>
    </div>
    {record.integrity?.status !== "VERIFIED" ? <div className="dc-error"><AlertTriangle size={18} /><div><strong>Artifact integrity failed</strong><span>The retained file cannot be approved or relied upon until custody is repaired and investigated.</span></div></div> : <div className="dc-callout"><ShieldCheck size={18} /><div><strong>Checksum verified</strong><div>The retained PDF matches the checksum recorded at submission.</div></div></div>}
    <div className="dc-record-detail__actions"><a className="dc-button" href={record.download_url} target="_blank" rel="noreferrer"><Download size={14} /> Open retained PDF</a></div>
    {reviewable ? <form className="dc-form" onSubmit={submit}>
      <label><span>Decision</span><select value={decision} onChange={(event) => setDecision(event.target.value as "ACCEPT" | "RETURN")}><option value="ACCEPT">Accept retained record</option><option value="RETURN">Return for correction</option></select></label>
      <label className="wide"><span>Review comments</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} required /></label>
      <label className="wide"><span>Evidence references</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="Audit item, work order, inspection, or evidence IDs—one per line" /></label>
      {error ? <div className="dc-form__error">{error}</div> : null}
      <div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className={`dc-button ${decision === "ACCEPT" ? "dc-button--primary" : "dc-button--danger"}`} disabled={busy || comments.trim().length < 3}>{decision === "ACCEPT" ? <ClipboardCheck size={14} /> : <Undo2 size={14} />}{busy ? "Saving…" : decision === "ACCEPT" ? "Accept record" : "Return record"}</button></div>
    </form> : null}
    {!reviewable && record.status === "ACCEPTED" ? <div className="dc-record-detail__complete"><CheckCircle2 size={18} /><div><strong>Review complete</strong><span>Accepted {formatDate(record.reviewed_at)}</span></div></div> : null}
  </section></div>;
}

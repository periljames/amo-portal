import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  FileCheck2,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import {
  getDocumentationRecord,
  reviewDocumentationRecord,
  type DocumentationRecordDetail,
} from "../../services/documentation";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import "./documentControlStructure.css";

function displayDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function displayBytes(value?: number): string {
  if (!value) return "Size unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentControlGeneratedRecordPage() {
  const { tenant, basePath } = useDocumentControlRoute();
  const { recordId = "" } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<DocumentationRecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const load = async () => {
    if (!tenant || !recordId) return;
    setLoading(true);
    setError("");
    try { setRecord(await getDocumentationRecord(tenant, recordId)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The retained record could not be loaded."); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [recordId, tenant]); // eslint-disable-line react-hooks/exhaustive-deps

  const review = async (decision: "ACCEPT" | "RETURN") => {
    if (!record || comments.trim().length < 3) return;
    setReviewing(true);
    setError("");
    try {
      await reviewDocumentationRecord(tenant, record.id, {
        decision,
        comments: comments.trim(),
        evidence_references: evidence.split("\n").map((item) => item.trim()).filter(Boolean),
      });
      setComments("");
      setEvidence("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The record review decision could not be saved.");
    } finally {
      setReviewing(false);
    }
  };

  return <DocumentControlShell
    title={record?.record_number || "Retained record"}
    subtitle={record?.template ? `${record.template.code} · ${record.template.title}` : "Controlled completed-document evidence"}
    canControl={record?.capabilities.control ?? false}
    actions={<button type="button" className="dc-button" onClick={() => navigate(`${basePath}/structure`)}><ArrowLeft size={14} /> Back to structure</button>}
  >
    {loading && !record ? <DocumentControlLoading label="Verifying retained record…" /> : null}
    {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
    {!loading && !error && !record ? <DocumentControlEmpty icon={FileCheck2} title="Record not available" message="It may be outside your permitted record scope or no longer available." /> : null}
    {record ? <div className="dc-record-detail">
      <section className="dc-record-detail__identity">
        <div><span>Status</span><DocumentControlStatus status={record.status} kind={["ACCEPTED", "SUBMITTED"].includes(record.status) ? "success" : record.status === "RETURNED" ? "danger" : "warning"} /></div>
        <div><span>Submitted</span><strong>{displayDate(record.submitted_at)}</strong></div>
        <div><span>Retention</span><strong>{record.retention_years ? `${record.retention_years} years` : "Not set"}</strong></div>
        <div><span>Template revision</span><strong>{record.template_revision ? `Issue ${record.template_revision.issue_number || "—"} · Rev ${record.template_revision.revision_number}` : "Not available"}</strong></div>
        <div><span>Integrity</span><DocumentControlStatus status={record.integrity.status} kind={record.integrity.status === "VERIFIED" ? "success" : "danger"} /></div>
      </section>

      <DocumentControlSection title="Auditable artifact" description="The stored PDF is retained with the immutable record identity.">
        <div className="dc-record-detail__artifact">
          <FileCheck2 size={28} />
          <div>
            <strong>{record.artifact_filename}</strong>
            <span>{displayBytes(record.integrity.size_bytes)}</span>
            <small>{record.integrity.status === "VERIFIED" ? "Verified" : record.integrity.status}</small>
          </div>
          <a className="dc-button" href={record.download_url} target="_blank" rel="noreferrer"><Download size={14} /> Open / download PDF</a>
        </div>
      </DocumentControlSection>

      <DocumentControlSection title="Lineage and custody" description="The source template, output series and submission identity remain attached to the completed record.">
        <dl className="dc-record-detail__lineage">
          <div><dt>Template</dt><dd>{record.template ? `${record.template.code} · ${record.template.title} · ${record.template.manual_type}` : record.template_manual_id}</dd></div>
          <div><dt>Record series</dt><dd>{record.record_series ? `${record.record_series.code} · ${record.record_series.title}` : record.record_series_node_id || "Not assigned"}</dd></div>
          <div><dt>Submitted by</dt><dd>{record.submitted_by_user_id ? "Recorded" : "Not recorded"}</dd></div>
          <div><dt>Reviewed by</dt><dd>{record.reviewed_by_user_id ? `Reviewed · ${displayDate(record.reviewed_at)}` : "Not reviewed"}</dd></div>
        </dl>
      </DocumentControlSection>

      {record.capabilities.review && ["PENDING_REVIEW", "SUBMITTED", "RETURNED"].includes(record.status) ? <DocumentControlSection title="Record review" description="Accept or return the verified artifact with a permanent review note and optional governed evidence references.">
        <div className="dc-record-detail__review">
          <label><span>Decision comments</span><textarea rows={3} minLength={3} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="State the evidence reviewed and the basis for the decision." /></label>
          <label><span>Evidence references (one per line)</span><textarea rows={3} value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="Evidence asset or controlled reference" /></label>
          <div><button type="button" disabled={reviewing || comments.trim().length < 3 || record.integrity.status !== "VERIFIED"} onClick={() => void review("RETURN")}><RotateCcw size={14} /> Return</button><button type="button" className="is-primary" disabled={reviewing || comments.trim().length < 3 || record.integrity.status !== "VERIFIED"} onClick={() => void review("ACCEPT")}><CheckCircle2 size={14} /> Accept record</button></div>
        </div>
      </DocumentControlSection> : <div className="dc-record-detail__readonly"><ShieldCheck size={17} /><span><strong>{record.status === "ACCEPTED" ? "Review complete" : "Read-only record"}</strong>This session may inspect and download the retained artifact but cannot make the review decision.</span></div>}
    </div> : null}
  </DocumentControlShell>;
}

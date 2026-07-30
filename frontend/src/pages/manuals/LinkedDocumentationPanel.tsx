import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  LoaderCircle,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";

import {
  getLinkedResource,
  submitLinkedPdfResource,
  type DocumentationRecord,
  type LinkedResourceDetail,
} from "../../services/documentation";
import type { PdfReaderCapabilities } from "../../services/pdfReader";
import PdfReaderCore from "./PdfReaderCore";
import "./linkedDocumentationPanel.css";

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
}

function humanize(value: unknown, fallback = "Not recorded"): string {
  const text = String(value ?? "").trim();
  return text ? text.replaceAll("_", " ") : fallback;
}

function uploadOnlyCapabilities(detail: LinkedResourceDetail): PdfReaderCapabilities {
  return {
    execution: detail.target.execution,
    renderer: "PDF.js",
    processor: "PDFium",
    processor_version: "server",
    source_sha256: "",
    page_count: Number(detail.target.page_count || 0),
    has_acroform: false,
    has_javascript: false,
    is_dynamic_xfa: false,
    encrypted: false,
    unsupported_reason: "Complete this controlled template externally, then upload the completed PDF.",
    can_fill: false,
    can_save_draft: false,
    can_download_original: detail.capabilities.download,
    can_download_working: false,
    can_flatten: false,
    can_submit: false,
  };
}

export default function LinkedDocumentationPanel({
  tenant,
  referenceId,
  onClose,
}: {
  tenant: string;
  referenceId: string;
  onClose: () => void;
}) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [detail, setDetail] = useState<LinkedResourceDetail | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [readerDirty, setReaderDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setDetail(null);
    setRecord(null);
    setUploadFile(null);
    setReaderDirty(false);
    getLinkedResource(tenant, referenceId)
      .then((value) => { if (active) setDetail(value); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "The linked controlled resource could not be opened."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [referenceId, tenant]);

  const execution = detail?.target.execution;
  const canUpload = Boolean(
    detail?.capabilities.execute
    && execution?.submission_mode === "DOWNLOAD_AND_UPLOAD",
  );
  const canFill = Boolean(
    detail?.capabilities.execute
    && execution?.submission_mode === "FILL_AND_SUBMIT"
    && ["PDF_ACROFORM", "HYBRID"].includes(String(execution.execution_type || "")),
  );

  const close = () => {
    if ((readerDirty || uploadFile) && !window.confirm("Close and discard the current working copy or selected completed file?")) return;
    onClose();
  };

  const selectUpload = (file: File | null) => {
    if (!file) return;
    const looksLikePdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!looksLikePdf) {
      setUploadFile(null);
      setError("Select the completed PDF version of this controlled template.");
      if (uploadInputRef.current) uploadInputRef.current.value = "";
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setUploadFile(null);
      setError("The completed PDF exceeds the 100 MB processing limit.");
      if (uploadInputRef.current) uploadInputRef.current.value = "";
      return;
    }
    setError("");
    setUploadFile(file);
  };

  const submitUpload = async () => {
    if (!detail || !uploadFile || !canUpload) return;
    if (!window.confirm(`Submit the completed ${detail.target.code} as an immutable flattened record?`)) return;
    setBusy(true);
    setError("");
    try {
      const created = await submitLinkedPdfResource(tenant, referenceId, uploadFile, {
        source_manual_id: detail.reference.source_manual_id,
        source_revision_id: detail.reference.source_revision_id,
        source_page_number: detail.reference.source_page_number,
        relationship_type: detail.reference.relationship_type,
        output_mode: "FLATTENED_RECORD",
      });
      setRecord(created);
      setUploadFile(null);
      setReaderDirty(false);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The completed PDF could not be submitted.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="linked-documentation-panel" aria-label="Linked controlled resource">
      <header className="linked-documentation-panel__header">
        <div>
          <p>Linked controlled information</p>
          <h2>{detail?.target.title || "Opening linked resource"}</h2>
          {detail ? <span>{detail.target.code} · Issue {detail.target.issue_number || "—"} · Rev {detail.target.revision_number}</span> : null}
        </div>
        <button type="button" onClick={close} aria-label="Close linked resource"><X size={18} /></button>
      </header>

      {loading ? <div className="linked-documentation-panel__state"><LoaderCircle className="is-spinning" size={22} /><strong>Resolving effective controlled resource…</strong></div> : null}
      {error ? <div className="linked-documentation-panel__error" role="alert"><AlertTriangle size={19} /><span>{error}</span></div> : null}

      {detail ? <>
        <div className="linked-documentation-panel__context">
          <div><span>Referenced as</span><strong>{detail.reference.raw_token || "Reference"}</strong></div>
          <div><span>Relationship</span><strong>{humanize(detail.reference.relationship_type)}</strong></div>
          <div><span>Effective</span><strong>{formatDate(detail.target.effective_date)}</strong></div>
          <div><span>Hierarchy</span><strong>{humanize(detail.target.node?.node_type, detail.target.manual_type || "Document")}</strong></div>
        </div>

        <div className="linked-documentation-panel__actions">
          <a href={detail.target.reader_url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open full reader</a>
          {canUpload ? <>
            <input ref={uploadInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => selectUpload(event.target.files?.[0] || null)} />
            <button type="button" onClick={() => uploadInputRef.current?.click()} disabled={busy}><Upload size={15} /> {uploadFile ? "Replace completed PDF" : "Choose completed PDF"}</button>
            <button type="button" className="primary" disabled={busy || !uploadFile} onClick={() => void submitUpload()}><Upload size={15} /> {busy ? "Flattening and submitting…" : "Submit flattened record"}</button>
          </> : null}
        </div>

        {record ? <div className="linked-documentation-panel__success" role="status"><CheckCircle2 size={19} /><div><strong>Controlled record created</strong><span>{record.record_number} · {humanize(record.status)}</span><a href={record.download_url} target="_blank" rel="noreferrer">Open retained copy</a></div></div> : null}
        {!record && !detail.capabilities.execute ? <div className="linked-documentation-panel__notice"><ShieldCheck size={18} /><div><strong>Read-only controlled resource</strong><span>This linked item is controlled for reference or download only.</span></div></div> : null}
        {!record && canUpload ? <div className="linked-documentation-panel__notice linked-documentation-panel__notice--editable"><Upload size={18} /><div><strong>Completed PDF upload</strong><span>{uploadFile ? `${uploadFile.name} selected. PDFium will flatten and verify it before record creation.` : "Download and complete the controlled template, then choose the completed PDF."}</span></div></div> : null}

        <PdfReaderCore
          compact
          fileUrl={detail.target.pdf_url}
          originalDownloadUrl={detail.target.download_url}
          title={detail.target.title}
          filename={detail.target.source_filename || `${detail.target.code}.pdf`}
          identity={{ tenant, manualId: detail.target.manual_id, revisionId: detail.target.revision_id }}
          capabilities={canUpload ? uploadOnlyCapabilities(detail) : undefined}
          onDirtyChange={setReaderDirty}
          onSubmitWorkingCopy={canFill ? (file) => submitLinkedPdfResource(tenant, referenceId, file, {
            source_manual_id: detail.reference.source_manual_id,
            source_revision_id: detail.reference.source_revision_id,
            source_page_number: detail.reference.source_page_number,
            relationship_type: detail.reference.relationship_type,
            output_mode: "FLATTENED_RECORD",
          }) : undefined}
          onRecordCreated={(created) => { setRecord(created); setReaderDirty(false); }}
        />
      </> : null}
    </aside>
  );
}

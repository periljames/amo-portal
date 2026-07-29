import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileCheck2,
  LoaderCircle,
  Save,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import {
  getLinkedResource,
  submitLinkedPdfResource,
  type DocumentationRecord,
  type LinkedResourceDetail,
} from "../../services/documentation";
import {
  downloadBlob,
  fetchPublicationBlob,
  publicationPdfSource,
} from "../../services/publications";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./linkedDocumentationPanel.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfDocument = Document as unknown as React.FC<any>;
const PdfPage = Page as unknown as React.FC<any>;

type PdfHandle = {
  numPages: number;
  getFieldObjects?: () => Promise<Record<string, unknown[]> | null>;
  hasJSActions?: () => Promise<boolean>;
  saveDocument?: () => Promise<Uint8Array>;
};

function copyBytes(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function safeFilename(value: string, fallback: string): string {
  const cleaned = (value || fallback).split(/[\\/]+/).pop()?.replace(/[^A-Za-z0-9._-]+/g, "_") || fallback;
  return cleaned.toLowerCase().endsWith(".pdf") ? cleaned : `${cleaned}.pdf`;
}

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
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
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [detail, setDetail] = useState<LinkedResourceDetail | null>(null);
  const [pdf, setPdf] = useState<PdfHandle | null>(null);
  const [pageCount, setPageCount] = useState(1);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageWidth, setPageWidth] = useState(520);
  const [fieldCount, setFieldCount] = useState(0);
  const [hasJavaScript, setHasJavaScript] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [dirty, setDirty] = useState(false);
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
    setDirty(false);
    getLinkedResource(tenant, referenceId)
      .then((value) => { if (active) setDetail(value); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "The linked controlled resource could not be opened."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [referenceId, tenant]);

  useEffect(() => {
    const host = viewportRef.current;
    if (!host) return;
    const resize = () => setPageWidth(Math.max(300, Math.min(760, host.clientWidth - 28)));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    return () => observer.disconnect();
  }, [detail]);

  const source = useMemo(() => detail ? publicationPdfSource(detail.target.pdf_url) : null, [detail]);
  const execution = detail?.target.execution;
  const canExecute = Boolean(
    detail?.capabilities.execute
    && execution?.submission_mode === "FILL_AND_SUBMIT"
    && execution.execution_type === "PDF_ACROFORM"
    && fieldCount > 0
    && !hasJavaScript,
  );
  const canUpload = Boolean(
    detail?.capabilities.execute
    && execution?.submission_mode === "DOWNLOAD_AND_UPLOAD",
  );
  const canSubmit = canExecute || canUpload;
  const readOnlyReason = !detail?.capabilities.execute
    ? "This linked item is controlled for reference or download only."
    : canUpload
      ? null
      : execution?.execution_type !== "PDF_ACROFORM"
        ? "This template is not configured as an interactive PDF form."
        : hasJavaScript
          ? "This PDF contains scripted actions. The portal keeps it read-only for safety."
          : fieldCount === 0
            ? "No interactive AcroForm fields were detected."
            : null;

  const onPdfLoad = async (document: PdfHandle) => {
    setPdf(document);
    setPageCount(document.numPages || 1);
    setPageNumber(1);
    setError("");
    try {
      const [fields, scripted] = await Promise.all([
        typeof document.getFieldObjects === "function" ? document.getFieldObjects().catch(() => null) : Promise.resolve(null),
        typeof document.hasJSActions === "function" ? document.hasJSActions().catch(() => false) : Promise.resolve(false),
      ]);
      setFieldCount(Object.values(fields || {}).reduce((count, values) => count + values.length, 0));
      setHasJavaScript(Boolean(scripted));
    } catch {
      setFieldCount(0);
    }
  };

  const download = async () => {
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      if (canExecute && pdf?.saveDocument) {
        const bytes = await pdf.saveDocument();
        downloadBlob(new Blob([copyBytes(bytes)], { type: "application/pdf" }), safeFilename(detail.target.source_filename || "", `${detail.target.code}.pdf`));
      } else {
        const result = await fetchPublicationBlob(detail.target.download_url);
        downloadBlob(result.blob, result.filename || safeFilename(detail.target.source_filename || "", `${detail.target.code}.pdf`));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The linked resource could not be downloaded.");
    } finally {
      setBusy(false);
    }
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
    setError("");
    setUploadFile(file);
    setDirty(true);
  };

  const submit = async () => {
    if (!detail || !canSubmit) return;
    let file: File | null = null;
    if (canExecute && pdf?.saveDocument) {
      const bytes = await pdf.saveDocument();
      file = new File(
        [copyBytes(bytes)],
        safeFilename(detail.target.source_filename || "", `${detail.target.code}.pdf`),
        { type: "application/pdf" },
      );
    } else if (canUpload) {
      file = uploadFile;
    }
    if (!file) {
      setError("Select the completed PDF before submitting this controlled record.");
      return;
    }
    if (!window.confirm(`Submit the completed ${detail.target.code} as an immutable controlled record?`)) return;
    setBusy(true);
    setError("");
    try {
      const created = await submitLinkedPdfResource(tenant, referenceId, file, {
        source_manual_id: detail.reference.source_manual_id,
        source_revision_id: detail.reference.source_revision_id,
        source_page_number: detail.reference.source_page_number,
        relationship_type: detail.reference.relationship_type,
      });
      setRecord(created);
      setUploadFile(null);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The completed form could not be submitted.");
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
        <button type="button" onClick={() => {
          if (dirty && !window.confirm("Close and discard unsaved form entries or the selected completed file?")) return;
          onClose();
        }} aria-label="Close linked resource"><X size={18} /></button>
      </header>

      {loading ? <div className="linked-documentation-panel__state"><LoaderCircle className="is-spinning" size={22} /><strong>Resolving effective controlled resource…</strong></div> : null}
      {error ? <div className="linked-documentation-panel__error" role="alert"><AlertTriangle size={19} /><span>{error}</span></div> : null}

      {detail ? <>
        <div className="linked-documentation-panel__context">
          <div><span>Referenced as</span><strong>{detail.reference.raw_token}</strong></div>
          <div><span>Relationship</span><strong>{detail.reference.relationship_type.replaceAll("_", " ")}</strong></div>
          <div><span>Effective</span><strong>{formatDate(detail.target.effective_date)}</strong></div>
          <div><span>Hierarchy</span><strong>{detail.target.node?.node_type.replaceAll("_", " ") || detail.target.manual_type}</strong></div>
        </div>

        <div className="linked-documentation-panel__actions">
          <button type="button" onClick={() => void download()} disabled={busy || !detail.capabilities.download}><Download size={15} /> Download</button>
          <a href={detail.target.reader_url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open full reader</a>
          {canUpload ? <>
            <input
              ref={uploadInputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(event) => selectUpload(event.target.files?.[0] || null)}
            />
            <button type="button" onClick={() => uploadInputRef.current?.click()} disabled={busy}>
              <Upload size={15} /> {uploadFile ? "Replace completed PDF" : "Choose completed PDF"}
            </button>
          </> : null}
          {canSubmit ? <button type="button" className="primary" onClick={() => void submit()} disabled={busy || (canUpload && !uploadFile)}><Save size={15} /> {busy ? "Submitting…" : canUpload ? "Submit completed PDF" : "Submit completed form"}</button> : null}
        </div>

        {record ? <div className="linked-documentation-panel__success" role="status"><CheckCircle2 size={19} /><div><strong>Controlled record created</strong><span>{record.record_number} · {record.status.replaceAll("_", " ")}</span><a href={record.download_url} target="_blank" rel="noreferrer">Open retained copy</a></div></div> : null}
        {!record && readOnlyReason ? <div className="linked-documentation-panel__notice"><ShieldCheck size={18} /><div><strong>Read-only controlled resource</strong><span>{readOnlyReason}</span></div></div> : null}
        {!record && canExecute ? <div className="linked-documentation-panel__notice linked-documentation-panel__notice--editable"><FileCheck2 size={18} /><div><strong>Executable AcroForm</strong><span>{fieldCount} field{fieldCount === 1 ? "" : "s"} detected. Entries remain local until submitted as a retained record.</span></div></div> : null}
        {!record && canUpload ? <div className="linked-documentation-panel__notice linked-documentation-panel__notice--editable"><Upload size={18} /><div><strong>Completed PDF upload</strong><span>{uploadFile ? `${uploadFile.name} selected. Submit it to create the retained record.` : "Download and complete the controlled template, then choose the completed PDF for submission."}</span></div></div> : null}

        <div
          className="linked-documentation-panel__viewport"
          ref={viewportRef}
          onInput={() => canExecute && setDirty(true)}
          onChange={() => canExecute && setDirty(true)}
        >
          <PdfDocument
            file={source}
            onLoadSuccess={onPdfLoad}
            onLoadError={(caught: unknown) => setError(caught instanceof Error ? caught.message : "The linked PDF could not be rendered.")}
            options={{ isEvalSupported: false, enableXfa: true }}
            loading={<div className="linked-documentation-panel__state"><LoaderCircle className="is-spinning" size={20} /> Opening page…</div>}
          >
            <PdfPage
              pageNumber={pageNumber}
              width={pageWidth}
              renderTextLayer
              renderAnnotationLayer
              renderForms={canExecute}
              externalLinkTarget="_blank"
              devicePixelRatio={Math.min(window.devicePixelRatio || 1, 1.6)}
            />
          </PdfDocument>
        </div>

        <footer className="linked-documentation-panel__pager">
          <button type="button" onClick={() => setPageNumber((value) => Math.max(1, value - 1))} disabled={pageNumber <= 1}><ChevronLeft size={16} /> Previous</button>
          <strong>Page {pageNumber} of {pageCount}</strong>
          <button type="button" onClick={() => setPageNumber((value) => Math.min(pageCount, value + 1))} disabled={pageNumber >= pageCount}>Next <ChevronRight size={16} /></button>
        </footer>
      </> : null}
    </aside>
  );
}

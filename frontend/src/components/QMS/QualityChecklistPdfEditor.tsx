import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  LoaderCircle,
  Lock,
  RotateCcw,
  Save,
  ShieldCheck,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { getToken, handleAuthFailure } from "../../services/auth";
import {
  absoluteQualityUrl,
  qmsCommitChecklistVersion,
  qmsSaveChecklistDraft,
  type QualityAuditDocument,
} from "../../services/qmsAuditLifecycle";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const PdfPage = Page as unknown as React.FC<any>;

type PdfHandle = {
  numPages: number;
  isPureXfa?: boolean;
  getFieldObjects: () => Promise<Record<string, unknown[]> | null>;
  hasJSActions: () => Promise<boolean>;
  saveDocument: () => Promise<Uint8Array>;
};

export type QualityChecklistPdfEditorProps = {
  auditId: string;
  auditReference: string;
  auditTitle: string;
  documentRecord: QualityAuditDocument;
  open: boolean;
  readOnly: boolean;
  readOnlyReason?: string | null;
  onClose: () => void;
  onSaved: (documentRecord: QualityAuditDocument, committed: boolean) => void | Promise<void>;
};

function copyBytes(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function bytesToFile(bytes: Uint8Array, filename: string): File {
  return new File([copyBytes(bytes)], filename, { type: "application/pdf" });
}

async function fetchControlledPdf(record: QualityAuditDocument): Promise<Blob> {
  const token = getToken();
  const response = await fetch(absoluteQualityUrl(record.download_url), {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
    cache: "no-store",
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw new Error(`Checklist PDF could not be loaded (${response.status}).`);
  const blob = await response.blob();
  if (!blob.type.toLowerCase().includes("pdf") && !record.filename.toLowerCase().endsWith(".pdf")) {
    throw new Error("This controlled checklist version is not a PDF form.");
  }
  return blob;
}

function downloadBytes(bytes: Uint8Array, filename: string): void {
  const url = URL.createObjectURL(new Blob([copyBytes(bytes)], { type: "application/pdf" }));
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

const QualityChecklistPdfEditor: React.FC<QualityChecklistPdfEditorProps> = ({
  auditId,
  auditReference,
  auditTitle,
  documentRecord,
  open,
  readOnly,
  readOnlyReason,
  onClose,
  onSaved,
}) => {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [pdf, setPdf] = useState<PdfHandle | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [pageWidth, setPageWidth] = useState(820);
  const [zoom, setZoom] = useState(1);
  const [fieldCount, setFieldCount] = useState<number | null>(documentRecord.field_count);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [draftRecord, setDraftRecord] = useState<QualityAuditDocument | null>(null);
  const [hasJavaScript, setHasJavaScript] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const effectiveReadOnly = readOnly || documentRecord.lifecycle_status === "RETAINED" || documentRecord.lifecycle_status === "SUPERSEDED";
  const currentFilename = draftRecord?.filename || documentRecord.filename;

  const reset = useCallback(() => {
    setBlob(null);
    setPdf(null);
    setPageNumber(1);
    setPageCount(1);
    setZoom(1);
    setFieldCount(documentRecord.field_count);
    setDirty(false);
    setDraftRecord(null);
    setHasJavaScript(false);
    setError(null);
    setNotice(null);
  }, [documentRecord.field_count]);

  useEffect(() => {
    if (!open) {
      reset();
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchControlledPdf(documentRecord)
      .then((loaded) => {
        if (!cancelled) setBlob(loaded);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Checklist PDF could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [documentRecord, open, reset]);

  useEffect(() => {
    if (!open || !viewportRef.current) return;
    const host = viewportRef.current;
    const resize = () => setPageWidth(Math.max(360, Math.min(1_150, host.clientWidth - 40)));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    return () => observer.disconnect();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (dirty && !window.confirm("Discard unsaved PDF form changes?")) return;
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dirty, onClose, open]);

  const close = () => {
    if (dirty && !window.confirm("Discard unsaved PDF form changes?")) return;
    onClose();
  };

  const onPdfLoad = async (loaded: PdfHandle) => {
    setPdf(loaded);
    setPageCount(loaded.numPages);
    setPageNumber(1);
    setError(null);
    try {
      const [fields, scripted] = await Promise.all([
        loaded.getFieldObjects(),
        loaded.hasJSActions().catch(() => false),
      ]);
      const count = Object.values(fields || {}).reduce((total, entries) => total + entries.length, 0);
      setFieldCount(count);
      setHasJavaScript(scripted);
      if (count === 0) setNotice("This PDF has no interactive AcroForm fields. Use portal checklist rows or replace the source with a fillable form.");
    } catch (inspectionError: unknown) {
      setFieldCount(0);
      setNotice(inspectionError instanceof Error ? inspectionError.message : "PDF form fields could not be inspected.");
    }
  };

  const saveDraft = async (): Promise<QualityAuditDocument | null> => {
    if (!pdf || effectiveReadOnly || saving || fieldCount === 0) return null;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const file = bytesToFile(await pdf.saveDocument(), currentFilename);
      const saved = await qmsSaveChecklistDraft(auditId, file, {
        fillable: "YES",
        fieldCount,
      });
      setDraftRecord(saved);
      setBlob(file);
      setDirty(false);
      setNotice(`Working draft version ${saved.version_number} saved. The controlled source remains retained.`);
      await onSaved(saved, false);
      return saved;
    } catch (saveError: unknown) {
      setError(saveError instanceof Error ? saveError.message : "The PDF working draft could not be saved.");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const commitVersion = async () => {
    if (effectiveReadOnly || committing || fieldCount === 0) return;
    setCommitting(true);
    setError(null);
    try {
      let candidate = draftRecord;
      if (dirty || !candidate) candidate = await saveDraft();
      if (!candidate) return;
      const committed = await qmsCommitChecklistVersion(auditId, candidate.id, {
        fillable: "YES",
        fieldCount,
        note: "Filled checklist committed from the in-portal PDF form editor.",
      });
      setDraftRecord(committed);
      setDirty(false);
      setNotice(`Checklist version ${committed.version_number} committed. Earlier versions remain retained.`);
      await onSaved(committed, true);
    } catch (commitError: unknown) {
      setError(commitError instanceof Error ? commitError.message : "The checklist version could not be committed.");
    } finally {
      setCommitting(false);
    }
  };

  const downloadWorkingCopy = async () => {
    if (!pdf) return;
    setError(null);
    try {
      downloadBytes(await pdf.saveDocument(), currentFilename);
    } catch (downloadError: unknown) {
      setError(downloadError instanceof Error ? downloadError.message : "The working copy could not be downloaded.");
    }
  };

  const statusLabel = useMemo(() => {
    if (effectiveReadOnly) return "Read only";
    if (dirty) return "Unsaved changes";
    if (draftRecord?.lifecycle_status === "COMMITTED") return `Committed v${draftRecord.version_number}`;
    if (draftRecord) return `Draft v${draftRecord.version_number}`;
    return "Source loaded";
  }, [draftRecord, dirty, effectiveReadOnly]);

  if (!open) return null;

  return (
    <div className="qa2-pdf-modal" role="dialog" aria-modal="true" aria-label="Controlled fillable checklist editor">
      <section className="qa2-pdf-shell">
        <header className="qa2-pdf-header">
          <div>
            <span>Controlled checklist form</span>
            <h2>{currentFilename}</h2>
            <p>{auditReference} · {auditTitle} · Source v{documentRecord.version_number}</p>
          </div>
          <div className="qa2-pdf-header__actions">
            <button type="button" onClick={() => void downloadWorkingCopy()} disabled={!pdf || saving || committing}>
              <Download size={16} /> Download copy
            </button>
            <button type="button" onClick={() => void saveDraft()} disabled={effectiveReadOnly || !pdf || !dirty || saving || committing || fieldCount === 0}>
              {saving ? <LoaderCircle className="is-spinning" size={16} /> : <Save size={16} />} Save draft
            </button>
            <button type="button" className="is-primary" onClick={() => void commitVersion()} disabled={effectiveReadOnly || !pdf || saving || committing || fieldCount === 0}>
              {committing ? <LoaderCircle className="is-spinning" size={16} /> : effectiveReadOnly ? <Lock size={16} /> : <ShieldCheck size={16} />}
              {committing ? "Committing…" : "Commit version"}
            </button>
            <button type="button" className="is-icon" aria-label="Close checklist editor" onClick={close}><X size={19} /></button>
          </div>
        </header>

        <div className="qa2-pdf-toolbar">
          <div>
            <button type="button" aria-label="Previous page" disabled={pageNumber <= 1} onClick={() => setPageNumber((current) => Math.max(1, current - 1))}><ChevronLeft size={17} /></button>
            <strong>Page {pageNumber} of {pageCount}</strong>
            <button type="button" aria-label="Next page" disabled={pageNumber >= pageCount} onClick={() => setPageNumber((current) => Math.min(pageCount, current + 1))}><ChevronRight size={17} /></button>
          </div>
          <div>
            <button type="button" aria-label="Zoom out" onClick={() => setZoom((current) => Math.max(0.65, Number((current - 0.1).toFixed(2))))}><ZoomOut size={17} /></button>
            <strong>{Math.round(zoom * 100)}%</strong>
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((current) => Math.min(1.8, Number((current + 0.1).toFixed(2))))}><ZoomIn size={17} /></button>
            <button type="button" aria-label="Reset zoom" onClick={() => setZoom(1)}><RotateCcw size={16} /></button>
          </div>
          <div className="qa2-pdf-toolbar__status">
            <span>{fieldCount === null ? "Inspecting fields…" : `${fieldCount} interactive field${fieldCount === 1 ? "" : "s"}`}</span>
            <strong className={dirty ? "is-dirty" : effectiveReadOnly ? "is-locked" : "is-saved"}>{statusLabel}</strong>
          </div>
        </div>

        {readOnlyReason || effectiveReadOnly ? (
          <div className="qa2-pdf-alert is-warning"><Lock size={18} /><span>{readOnlyReason || "This retained version is read-only."}</span></div>
        ) : null}
        {hasJavaScript ? (
          <div className="qa2-pdf-alert is-warning"><AlertTriangle size={18} /><span>This PDF contains JavaScript. Browser-safe fields are supported, but scripted calculations must be verified in the saved copy.</span></div>
        ) : null}
        {pdf?.isPureXfa ? (
          <div className="qa2-pdf-alert is-warning"><AlertTriangle size={18} /><span>This is an XFA-only form. Verify the saved result before committing the checklist version.</span></div>
        ) : null}
        {error ? <div className="qa2-pdf-alert is-error" role="alert"><AlertTriangle size={18} /><span>{error}</span></div> : null}
        {notice ? <div className="qa2-pdf-alert is-notice"><CheckCircle2 size={18} /><span>{notice}</span></div> : null}

        <div
          className={`qa2-pdf-viewport${effectiveReadOnly ? " is-read-only" : ""}`}
          ref={viewportRef}
          onInputCapture={() => { if (!effectiveReadOnly) setDirty(true); }}
          onChangeCapture={() => { if (!effectiveReadOnly) setDirty(true); }}
        >
          {loading ? <div className="qa2-pdf-loading"><LoaderCircle className="is-spinning" size={26} /> Loading controlled checklist…</div> : null}
          {!loading && blob ? (
            <Document
              file={blob}
              onLoadSuccess={(loaded) => void onPdfLoad(loaded as unknown as PdfHandle)}
              onLoadError={(loadError) => setError(loadError.message || "The PDF could not be rendered.")}
              loading={<div className="qa2-pdf-loading"><LoaderCircle className="is-spinning" size={24} /> Rendering checklist…</div>}
            >
              <PdfPage
                pageNumber={pageNumber}
                width={pageWidth * zoom}
                renderAnnotationLayer
                renderForms
                renderTextLayer={false}
                loading={<div className="qa2-pdf-loading"><LoaderCircle className="is-spinning" size={22} /> Rendering page…</div>}
              />
            </Document>
          ) : null}
        </div>
      </section>
    </div>
  );
};

export default QualityChecklistPdfEditor;

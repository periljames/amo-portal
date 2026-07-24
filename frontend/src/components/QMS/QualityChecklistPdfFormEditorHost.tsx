import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Document, Page, pdfjs } from "react-pdf";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FilePenLine,
  LoaderCircle,
  Lock,
  RotateCcw,
  Save,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { getCachedUser } from "../../services/auth";
import {
  qmsDownloadAuditChecklist,
  qmsResolveAudit,
  qmsUploadAuditChecklist,
  type QMSAuditOut,
} from "../../services/qms";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "../../styles/quality-checklist-pdf-form-editor.css";
import "../../styles/car-invite-responsive.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const PdfPage = Page as unknown as React.FC<any>;

type PdfDocumentHandle = {
  numPages: number;
  isPureXfa?: boolean;
  getFieldObjects: () => Promise<Record<string, unknown[]> | null>;
  hasJSActions: () => Promise<boolean>;
  saveDocument: () => Promise<Uint8Array>;
};

type EditorState = {
  audit: QMSAuditOut;
  blob: Blob;
  filename: string;
  canSave: boolean;
  readOnlyReason: string | null;
};

function checklistFilename(fileRef?: string | null): string {
  const raw = (fileRef || "audit-checklist.pdf").trim();
  const basename = raw.split(/[\\/]+/).filter(Boolean).pop() || "audit-checklist.pdf";
  const cleaned = basename
    .replace(/^[a-f0-9]{32,64}[_-]+/i, "")
    .replace(/[^A-Za-z0-9._-]+/g, "_");
  return cleaned.toLowerCase().endsWith(".pdf") ? cleaned : `${cleaned || "audit-checklist"}.pdf`;
}

function checklistEditAccess(audit: QMSAuditOut): { allowed: boolean; reason: string | null } {
  const user = getCachedUser();
  if (!user) return { allowed: false, reason: "Sign in before editing this controlled checklist." };
  if (audit.status === "CLOSED") return { allowed: false, reason: "This audit is closed. The checklist is retained as a read-only record." };
  if (audit.report_file_ref) return { allowed: false, reason: "The audit report has been issued. The committed checklist is now read-only." };
  if (user.is_superuser || user.is_amo_admin) return { allowed: true, reason: null };
  if ([audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(user.id)) {
    return { allowed: true, reason: null };
  }
  return { allowed: false, reason: "Only the assigned audit team or an AMO administrator may edit the controlled checklist." };
}

function copyPdfBytes(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function downloadBytes(bytes: Uint8Array, filename: string): void {
  const url = URL.createObjectURL(new Blob([copyPdfBytes(bytes)], { type: "application/pdf" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

const QualityChecklistPdfFormEditorHost: React.FC = () => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [pdf, setPdf] = useState<PdfDocumentHandle | null>(null);
  const [pageCount, setPageCount] = useState(1);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageWidth, setPageWidth] = useState(820);
  const [zoom, setZoom] = useState(1);
  const [fieldCount, setFieldCount] = useState<number | null>(null);
  const [hasJavaScript, setHasJavaScript] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const route = useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/quality\/audits\/([^/]+)/i);
    const tab = new URLSearchParams(location.search).get("tab");
    if (!match || tab !== "checklist") return null;
    return {
      amoCode: decodeURIComponent(match[1]),
      auditKey: decodeURIComponent(match[2]),
    };
  }, [location.pathname, location.search]);

  const closeEditor = useCallback((force = false) => {
    if (!force && dirty && !window.confirm("Discard the unsaved PDF form changes?")) return;
    setEditor(null);
    setPdf(null);
    setPageCount(1);
    setPageNumber(1);
    setZoom(1);
    setFieldCount(null);
    setHasJavaScript(false);
    setDirty(false);
    setError(null);
    setNotice(null);
  }, [dirty]);

  useEffect(() => {
    if (route) return;
    closeEditor(true);
  }, [route, closeEditor]);

  useEffect(() => {
    if (!editor || !viewportRef.current) return;
    const host = viewportRef.current;
    const resize = () => setPageWidth(Math.max(320, Math.min(1_100, host.clientWidth - 32)));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    return () => observer.disconnect();
  }, [editor]);

  useEffect(() => {
    if (!editor) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeEditor();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editor, closeEditor]);

  const openEditor = async () => {
    if (!route || loading) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const audit = await qmsResolveAudit(route.auditKey, { silent: true });
      if (!audit) throw new Error("The audit could not be resolved from this route.");
      if (!audit.checklist_file_ref) throw new Error("Upload a checklist PDF before opening the form editor.");
      const blob = await qmsDownloadAuditChecklist(audit.id);
      const filename = checklistFilename(audit.checklist_file_ref);
      const appearsPdf = blob.type.toLowerCase().includes("pdf") || filename.toLowerCase().endsWith(".pdf");
      if (!appearsPdf) throw new Error("The committed checklist is not a PDF. Use the portal checklist rows or replace it with a PDF form.");
      const access = checklistEditAccess(audit);
      setEditor({ audit, blob, filename, canSave: access.allowed, readOnlyReason: access.reason });
      setDirty(false);
      if (access.reason) setNotice(access.reason);
    } catch (openError) {
      setError(openError instanceof Error ? openError.message : "The checklist PDF could not be opened.");
    } finally {
      setLoading(false);
    }
  };

  const onPdfLoad = async (document: PdfDocumentHandle) => {
    setPdf(document);
    setPageCount(document.numPages);
    setPageNumber(1);
    setError(null);
    try {
      const [fields, scripted] = await Promise.all([
        document.getFieldObjects(),
        document.hasJSActions().catch(() => false),
      ]);
      const count = Object.values(fields || {}).reduce((total, entries) => total + entries.length, 0);
      setFieldCount(count);
      setHasJavaScript(scripted);
      if (count === 0) {
        setNotice("This PDF has no interactive AcroForm fields. It remains available for review, but there is nothing to save from this editor.");
      }
    } catch (fieldError) {
      setFieldCount(0);
      setNotice(fieldError instanceof Error ? fieldError.message : "Form fields could not be inspected.");
    }
  };

  const saveToPortal = async () => {
    if (!editor || !editor.canSave || !pdf || saving || fieldCount === 0) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const bytes = await pdf.saveDocument();
      const file = new File([copyPdfBytes(bytes)], editor.filename, { type: "application/pdf" });
      const updated = await qmsUploadAuditChecklist(editor.audit.id, file);
      const access = checklistEditAccess(updated);
      setEditor({
        audit: updated,
        blob: file,
        filename: checklistFilename(updated.checklist_file_ref || editor.filename),
        canSave: access.allowed,
        readOnlyReason: access.reason,
      });
      setDirty(false);
      setNotice("Filled checklist saved to the audit workspace.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-audit-context"] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-items"] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-workflow"] }),
      ]);
      window.dispatchEvent(new CustomEvent("quality:checklist-pdf-saved", {
        detail: { auditId: editor.audit.id },
      }));
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "The filled PDF could not be saved to the portal.");
    } finally {
      setSaving(false);
    }
  };

  const downloadWorkingCopy = async () => {
    if (!editor || !pdf) return;
    setError(null);
    try {
      downloadBytes(await pdf.saveDocument(), editor.filename);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "The working copy could not be downloaded.");
    }
  };

  if (!route) return null;

  return (
    <>
      <div className="quality-pdf-form-launcher" role="region" aria-label="Checklist PDF form tools">
        <button type="button" onClick={() => void openEditor()} disabled={loading}>
          {loading ? <LoaderCircle className="is-spinning" size={17} /> : <FilePenLine size={17} />}
          <span>{loading ? "Opening PDF…" : "Fill PDF form"}</span>
        </button>
        {error && !editor ? <p role="alert">{error}</p> : null}
      </div>

      {editor ? (
        <div className="quality-pdf-form-modal" role="dialog" aria-modal="true" aria-label="Fillable audit checklist PDF editor">
          <section className="quality-pdf-form-shell">
            <header className="quality-pdf-form-header">
              <div>
                <p>Controlled checklist form</p>
                <h2>{editor.filename}</h2>
                <span>{editor.audit.audit_ref} · {editor.audit.title}</span>
              </div>
              <div className="quality-pdf-form-header__actions">
                <button type="button" onClick={() => void downloadWorkingCopy()} disabled={!pdf || saving}>
                  <Download size={16} /> Download copy
                </button>
                <button type="button" className="is-primary" onClick={() => void saveToPortal()} disabled={!editor.canSave || !pdf || saving || fieldCount === 0 || !dirty}>
                  {saving ? <LoaderCircle className="is-spinning" size={16} /> : editor.canSave ? <Save size={16} /> : <Lock size={16} />}
                  {saving ? "Saving…" : editor.canSave ? "Save to portal" : "Read only"}
                </button>
                <button type="button" className="is-icon" onClick={() => closeEditor()} aria-label="Close PDF form editor">
                  <X size={19} />
                </button>
              </div>
            </header>

            <div className="quality-pdf-form-toolbar">
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
              <div className="quality-pdf-form-status">
                {fieldCount === null ? <span>Inspecting form…</span> : <span>{fieldCount} interactive field{fieldCount === 1 ? "" : "s"}</span>}
                {editor.canSave ? (dirty ? <strong>Unsaved changes</strong> : <strong className="is-saved">Saved</strong>) : <strong className="is-read-only">Read only</strong>}
              </div>
            </div>

            {editor.readOnlyReason ? (
              <div className="quality-pdf-form-alert is-warning">
                <Lock size={18} />
                <span>{editor.readOnlyReason}</span>
              </div>
            ) : null}
            {hasJavaScript ? (
              <div className="quality-pdf-form-alert is-warning">
                <AlertTriangle size={18} />
                <span>This form contains PDF JavaScript. Browser-safe fields are supported, but scripted calculations may not behave exactly like a desktop PDF application.</span>
              </div>
            ) : null}
            {pdf?.isPureXfa ? (
              <div className="quality-pdf-form-alert is-warning">
                <AlertTriangle size={18} />
                <span>This is an XFA-only form. Rendering support varies; verify the saved copy before committing the audit stage.</span>
              </div>
            ) : null}
            {error ? <div className="quality-pdf-form-alert is-error" role="alert"><AlertTriangle size={18} /><span>{error}</span></div> : null}
            {notice && notice !== editor.readOnlyReason ? <div className="quality-pdf-form-alert is-notice"><CheckCircle2 size={18} /><span>{notice}</span></div> : null}

            <div
              className={`quality-pdf-form-viewport${editor.canSave ? "" : " is-read-only"}`}
              ref={viewportRef}
              onInputCapture={() => { if (editor.canSave) setDirty(true); }}
              onChangeCapture={() => { if (editor.canSave) setDirty(true); }}
            >
              <Document
                file={editor.blob}
                onLoadSuccess={(document) => void onPdfLoad(document as unknown as PdfDocumentHandle)}
                onLoadError={(loadError) => setError(loadError.message || "The PDF could not be rendered.")}
                loading={<div className="quality-pdf-form-loading"><LoaderCircle className="is-spinning" size={24} /> Rendering checklist…</div>}
              >
                <PdfPage
                  pageNumber={pageNumber}
                  width={pageWidth * zoom}
                  renderAnnotationLayer
                  renderForms
                  renderTextLayer={false}
                  loading={<div className="quality-pdf-form-loading"><LoaderCircle className="is-spinning" size={22} /> Rendering page…</div>}
                />
              </Document>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
};

export default QualityChecklistPdfFormEditorHost;

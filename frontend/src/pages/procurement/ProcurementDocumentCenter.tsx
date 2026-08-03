import React, { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArchiveX,
  CheckCircle2,
  Download,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Image,
  LoaderCircle,
  Paperclip,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";

import { useToast } from "../../components/feedback/ToastProvider";
import {
  downloadProcurementDocument,
  listProcurementDocuments,
  uploadProcurementDocument,
  voidProcurementDocument,
} from "../../services/procurement";
import type {
  ProcurementDocument,
  ProcurementDocumentEntityType,
  ProcurementDocumentSource,
  ProcurementPurchaseOrder,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../../types/procurement";

const MAX_BYTES = 25 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "csv", "jpg", "jpeg", "png", "tif", "tiff"];
const ACCEPT = ACCEPTED_EXTENSIONS.map((extension) => `.${extension}`).join(",");

const DOCUMENT_TYPES = [
  "PART_REQUISITION_FORM",
  "PURCHASE_REQUEST_FORM",
  "SUPPLIER_QUOTATION",
  "PURCHASE_ORDER",
  "DELIVERY_NOTE",
  "AIRWAY_BILL",
  "RELEASE_CERTIFICATE",
  "CERTIFICATE_OF_CONFORMITY",
  "INVOICE",
  "RECEIVING_INSPECTION",
  "QUALITY_EVIDENCE",
  "SUPPLIER_APPROVAL",
  "CORRESPONDENCE",
  "OTHER",
];

const SOURCES: ProcurementDocumentSource[] = [
  "PHYSICAL_FORM",
  "EXTERNAL_SOFTWARE",
  "EMAIL",
  "SUPPLIER_PORTAL",
  "PORTAL_EXPORT",
  "OTHER",
];

type EntityOption = {
  type: ProcurementDocumentEntityType;
  id: string;
  label: string;
  hint: string;
};

type ProcurementRecords = {
  requisitions: ProcurementRequisition[];
  rfqs: ProcurementRFQ[];
  quotes: ProcurementQuote[];
  orders: ProcurementPurchaseOrder[];
  receipts: ProcurementReceipt[];
  suppliers: ProcurementSupplier[];
  holds: ProcurementQualityHold[];
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function iconForDocument(document: ProcurementDocument): React.ReactNode {
  const name = document.original_filename.toLowerCase();
  if (/\.(jpg|jpeg|png|tif|tiff)$/.test(name)) return <Image size={18} />;
  if (/\.(xls|xlsx|csv)$/.test(name)) return <FileSpreadsheet size={18} />;
  return <FileText size={18} />;
}

function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    return "Upload PDF, Word, Excel, CSV, JPEG, PNG, or TIFF files only.";
  }
  if (file.size <= 0) return "The selected file is empty.";
  if (file.size > MAX_BYTES) return "The selected file exceeds the 25 MB limit.";
  return null;
}

function entityOptions(records: ProcurementRecords): EntityOption[] {
  return [
    ...records.requisitions.map((record) => ({
      type: "REQUISITION" as const,
      id: String(record.id),
      label: `${record.requisition_number} · ${record.title}`,
      hint: record.requesting_department,
    })),
    ...records.rfqs.map((record) => ({
      type: "RFQ" as const,
      id: String(record.id),
      label: `${record.rfq_number} · ${record.title}`,
      hint: record.status,
    })),
    ...records.quotes.map((record) => ({
      type: "QUOTE" as const,
      id: String(record.id),
      label: `${record.quote_reference} · Supplier #${record.supplier_id}`,
      hint: record.status,
    })),
    ...records.orders.map((record) => ({
      type: "PURCHASE_ORDER" as const,
      id: String(record.id),
      label: `${record.po_number} · Supplier #${record.supplier_id}`,
      hint: record.status,
    })),
    ...records.receipts.map((record) => ({
      type: "RECEIPT" as const,
      id: String(record.id),
      label: `${record.receipt_number} · PO #${record.purchase_order_id}`,
      hint: record.status,
    })),
    ...records.suppliers.map((record) => ({
      type: "SUPPLIER" as const,
      id: String(record.id),
      label: `${record.supplier_code} · ${record.legal_name}`,
      hint: record.status,
    })),
    ...records.holds.map((record) => ({
      type: "QUALITY_HOLD" as const,
      id: String(record.id),
      label: `${record.hold_number} · ${record.target_type} #${record.target_id}`,
      hint: record.status,
    })),
  ];
}

export default function ProcurementDocumentCenter({
  amoCode,
  records,
  initialEntity,
}: {
  amoCode: string;
  records: ProcurementRecords;
  initialEntity?: { type: ProcurementDocumentEntityType; id: string } | null;
}) {
  const { pushToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [documents, setDocuments] = useState<ProcurementDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [entityFilter, setEntityFilter] = useState<ProcurementDocumentEntityType | "ALL">("ALL");
  const [includeVoid, setIncludeVoid] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    entityType: initialEntity?.type || ("REQUISITION" as ProcurementDocumentEntityType),
    entityId: initialEntity?.id || "",
    documentType: "PART_REQUISITION_FORM",
    title: "",
    source: "PHYSICAL_FORM" as ProcurementDocumentSource,
    documentNumber: "",
    revision: "",
    documentDate: "",
    notes: "",
    isQualityEvidence: false,
    qmsReference: "",
  });

  const options = useMemo(() => entityOptions(records), [records]);
  const optionsForType = useMemo(
    () => options.filter((option) => option.type === form.entityType),
    [form.entityType, options],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await listProcurementDocuments(amoCode, { activeOnly: !includeVoid });
      setDocuments(next);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The retained Procurement documents could not be loaded.";
      setError(message);
      pushToast({ title: "Document register unavailable", message, variant: "error", sound: true });
    } finally {
      setLoading(false);
    }
  }, [amoCode, includeVoid, pushToast]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!initialEntity) return;
    setForm((current) => ({ ...current, entityType: initialEntity.type, entityId: initialEntity.id }));
    setShowUpload(true);
  }, [initialEntity]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return documents.filter((document) => {
      if (entityFilter !== "ALL" && document.entity_type !== entityFilter) return false;
      if (!query) return true;
      return `${document.title} ${document.document_type} ${document.document_number || ""} ${document.original_filename} ${document.entity_type} ${document.entity_id}`
        .toLowerCase()
        .includes(query);
    });
  }, [documents, entityFilter, search]);

  const selectFile = (file: File | null) => {
    if (!file) return;
    const validation = validateFile(file);
    if (validation) {
      setSelectedFile(null);
      setError(validation);
      pushToast({ title: "File not accepted", message: validation, variant: "error", sound: true });
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    setError("");
    setSelectedFile(file);
    setForm((current) => ({
      ...current,
      title: current.title || file.name.replace(/\.[^.]+$/, "").replaceAll("_", " "),
    }));
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    selectFile(event.dataTransfer.files?.[0] || null);
  };

  const resetUpload = () => {
    setSelectedFile(null);
    setError("");
    setForm((current) => ({
      ...current,
      entityId: initialEntity?.id || "",
      title: "",
      documentNumber: "",
      revision: "",
      documentDate: "",
      notes: "",
      isQualityEvidence: false,
      qmsReference: "",
    }));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const upload = async () => {
    if (!selectedFile || !form.entityId || !form.title.trim() || !form.documentType.trim()) {
      const message = "Select a linked record and file, then provide the document title and type.";
      setError(message);
      pushToast({ title: "Document details incomplete", message, variant: "warning", sound: true });
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await uploadProcurementDocument(amoCode, {
        entityType: form.entityType,
        entityId: form.entityId,
        documentType: form.documentType,
        title: form.title.trim(),
        source: form.source,
        documentNumber: form.documentNumber.trim() || undefined,
        revision: form.revision.trim() || undefined,
        documentDate: form.documentDate || undefined,
        notes: form.notes.trim() || undefined,
        isQualityEvidence: form.isQualityEvidence,
        qmsReference: form.qmsReference.trim() || undefined,
        file: selectedFile,
      });
      setDocuments((current) => [created, ...current]);
      pushToast({
        title: "Document linked and retained",
        message: `${created.original_filename} is now attached to ${humanize(created.entity_type)} #${created.entity_id}.`,
        variant: "success",
        sound: true,
      });
      resetUpload();
      setShowUpload(false);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The document could not be uploaded.";
      setError(message);
      pushToast({ title: "Upload failed", message, variant: "error", sound: true, duration: 8000 });
    } finally {
      setBusy(false);
    }
  };

  const download = async (document: ProcurementDocument) => {
    try {
      await downloadProcurementDocument(amoCode, document);
      pushToast({ title: "Download started", message: document.original_filename, variant: "success", sound: false });
    } catch (caught) {
      pushToast({
        title: "Download failed",
        message: caught instanceof Error ? caught.message : "The retained file could not be opened.",
        variant: "error",
        sound: true,
      });
    }
  };

  const voidDocument = async (document: ProcurementDocument) => {
    const reason = window.prompt("Why is this retained document being voided? The file and audit trail will remain available.");
    if (!reason?.trim()) return;
    try {
      const updated = await voidProcurementDocument(amoCode, document.id, reason.trim());
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      pushToast({ title: "Document voided", message: `${document.title} remains retained for audit.`, variant: "warning", sound: true });
    } catch (caught) {
      pushToast({
        title: "Document could not be voided",
        message: caught instanceof Error ? caught.message : "The control action failed.",
        variant: "error",
        sound: true,
      });
    }
  };

  return (
    <section className="proc-docs" aria-labelledby="proc-docs-title">
      <header className="proc-section-heading proc-section-heading--split">
        <div>
          <span className="proc-eyebrow">External and physical records</span>
          <h2 id="proc-docs-title">Linked document register</h2>
          <p>Retain scanned forms, external system exports, supplier documents, certificates, and receiving evidence against the exact Procurement record.</p>
        </div>
        <button type="button" className="proc-button proc-button--primary" onClick={() => setShowUpload((value) => !value)}>
          {showUpload ? <X size={16} /> : <UploadCloud size={16} />}
          {showUpload ? "Close upload" : "Link document"}
        </button>
      </header>

      <div className="proc-docs__assurance" role="note">
        <ShieldCheck size={20} />
        <div>
          <strong>Controlled retention</strong>
          <span>Files are tenant-scoped, signature-checked, hashed, immutable, and auditable. Voiding never destroys the retained copy.</span>
        </div>
      </div>

      {showUpload ? (
        <div className="proc-upload-card">
          <div
            className={`proc-dropzone${dragActive ? " is-dragging" : ""}${selectedFile ? " has-file" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(event) => selectFile(event.target.files?.[0] || null)}
            />
            {selectedFile ? <FileCheck2 size={30} /> : <UploadCloud size={32} />}
            <strong>{selectedFile ? selectedFile.name : "Drop a completed form or supporting document"}</strong>
            <span>{selectedFile ? `${fileSize(selectedFile.size)} · ready for controlled upload` : "PDF, Word, Excel, CSV, JPEG, PNG, or TIFF · maximum 25 MB"}</span>
            <button type="button" className="proc-button proc-button--secondary" onClick={() => fileInputRef.current?.click()} disabled={busy}>
              <FolderOpen size={16} /> {selectedFile ? "Replace file" : "Browse files"}
            </button>
          </div>

          <div className="proc-upload-form">
            <label>
              <span>Linked record type</span>
              <select
                value={form.entityType}
                onChange={(event) => setForm((current) => ({ ...current, entityType: event.target.value as ProcurementDocumentEntityType, entityId: "" }))}
              >
                {(["REQUISITION", "RFQ", "QUOTE", "PURCHASE_ORDER", "RECEIPT", "SUPPLIER", "QUALITY_HOLD"] as ProcurementDocumentEntityType[])
                  .map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
              </select>
            </label>
            <label className="proc-upload-form__wide">
              <span>Linked record</span>
              <select value={form.entityId} onChange={(event) => setForm((current) => ({ ...current, entityId: event.target.value }))}>
                <option value="">Select the exact record</option>
                {optionsForType.map((option) => <option key={`${option.type}-${option.id}`} value={option.id}>{option.label} · {humanize(option.hint)}</option>)}
              </select>
            </label>
            <label>
              <span>Document type</span>
              <select value={form.documentType} onChange={(event) => setForm((current) => ({ ...current, documentType: event.target.value }))}>
                {DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
              </select>
            </label>
            <label>
              <span>Source</span>
              <select value={form.source} onChange={(event) => setForm((current) => ({ ...current, source: event.target.value as ProcurementDocumentSource }))}>
                {SOURCES.map((source) => <option key={source} value={source}>{humanize(source)}</option>)}
              </select>
            </label>
            <label className="proc-upload-form__wide">
              <span>Document title</span>
              <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="Completed parts requisition form" />
            </label>
            <label>
              <span>Document number</span>
              <input value={form.documentNumber} onChange={(event) => setForm((current) => ({ ...current, documentNumber: event.target.value }))} placeholder="PRF-2026-014" />
            </label>
            <label>
              <span>Revision</span>
              <input value={form.revision} onChange={(event) => setForm((current) => ({ ...current, revision: event.target.value }))} placeholder="Rev 2" />
            </label>
            <label>
              <span>Document date</span>
              <input type="date" value={form.documentDate} onChange={(event) => setForm((current) => ({ ...current, documentDate: event.target.value }))} />
            </label>
            <label>
              <span>QMS reference</span>
              <input value={form.qmsReference} onChange={(event) => setForm((current) => ({ ...current, qmsReference: event.target.value }))} placeholder="Finding, CAR, audit, or evaluation" />
            </label>
            <label className="proc-upload-form__wide">
              <span>Notes</span>
              <textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} rows={3} placeholder="Explain the physical form, source system, signatures, or reconciliation performed." />
            </label>
            <label className="proc-check proc-upload-form__wide">
              <input type="checkbox" checked={form.isQualityEvidence} onChange={(event) => setForm((current) => ({ ...current, isQualityEvidence: event.target.checked }))} />
              <span><strong>Quality evidence</strong><small>Flag this record for Quality review, inspection, supplier approval, hold, or release evidence.</small></span>
            </label>
          </div>

          {error ? <div className="proc-message proc-message--error" role="alert"><AlertTriangle size={18} /><span>{error}</span></div> : null}
          {busy ? <div className="proc-upload-progress" role="status" aria-live="polite"><LoaderCircle className="is-spinning" size={18} /><div><strong>Validating and retaining document…</strong><span>Checking type, signature, size, duplicate hash, tenant link, and audit metadata.</span><div className="proc-progress-track"><span /></div></div></div> : null}

          <footer className="proc-upload-actions">
            <button type="button" className="proc-button proc-button--ghost" onClick={resetUpload} disabled={busy}>Clear</button>
            <button type="button" className="proc-button proc-button--primary" onClick={() => void upload()} disabled={busy || !selectedFile}>
              {busy ? <LoaderCircle className="is-spinning" size={16} /> : <UploadCloud size={16} />}
              {busy ? "Retaining document" : "Upload and link"}
            </button>
          </footer>
        </div>
      ) : null}

      <div className="proc-doc-toolbar">
        <label className="proc-search-box">
          <Search size={16} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title, filename, document number, or linked record" />
        </label>
        <select value={entityFilter} onChange={(event) => setEntityFilter(event.target.value as ProcurementDocumentEntityType | "ALL")} aria-label="Filter document entity type">
          <option value="ALL">All linked records</option>
          {(["REQUISITION", "RFQ", "QUOTE", "PURCHASE_ORDER", "RECEIPT", "SUPPLIER", "QUALITY_HOLD"] as ProcurementDocumentEntityType[])
            .map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
        </select>
        <label className="proc-check proc-check--compact">
          <input type="checkbox" checked={includeVoid} onChange={(event) => setIncludeVoid(event.target.checked)} />
          <span>Include void records</span>
        </label>
      </div>

      {loading ? (
        <div className="proc-document-skeleton" role="status" aria-label="Loading linked documents">
          {Array.from({ length: 4 }).map((_, index) => <span key={index} />)}
        </div>
      ) : null}

      {!loading && error && !documents.length ? <div className="proc-message proc-message--error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}

      {!loading && filtered.length ? (
        <div className="proc-document-list">
          {filtered.map((document) => (
            <article key={document.id} className={`proc-document${document.status === "VOID" ? " is-void" : ""}`}>
              <div className="proc-document__icon" aria-hidden="true">{iconForDocument(document)}</div>
              <div className="proc-document__identity">
                <div>
                  <strong>{document.title}</strong>
                  {document.is_quality_evidence ? <span className="proc-badge proc-badge--quality"><ShieldCheck size={12} /> Quality evidence</span> : null}
                  {document.status === "VOID" ? <span className="proc-badge proc-badge--danger">Void</span> : null}
                </div>
                <span>{document.original_filename} · {fileSize(document.size_bytes)}</span>
                <small>{humanize(document.entity_type)} #{document.entity_id} · {humanize(document.document_type)} · {humanize(document.source)}</small>
              </div>
              <div className="proc-document__meta">
                <span>{document.document_number || "No document number"}{document.revision ? ` · ${document.revision}` : ""}</span>
                <small>{formatDate(document.uploaded_at)}</small>
                <code title={document.sha256}>SHA-256 {document.sha256.slice(0, 12)}…</code>
              </div>
              <div className="proc-document__actions">
                <button type="button" className="proc-icon-button" onClick={() => void download(document)} aria-label={`Download ${document.title}`} title="Download retained copy"><Download size={16} /></button>
                {document.status === "ACTIVE" ? <button type="button" className="proc-icon-button proc-icon-button--danger" onClick={() => void voidDocument(document)} aria-label={`Void ${document.title}`} title="Void document without deleting it"><ArchiveX size={16} /></button> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {!loading && !filtered.length && !error ? (
        <div className="proc-empty-state">
          <Paperclip size={28} />
          <strong>No linked documents in this view</strong>
          <span>Upload the signed physical requisition form, supplier quotation, delivery note, release certificate, inspection evidence, or external-system export.</span>
          <button type="button" className="proc-button proc-button--secondary" onClick={() => setShowUpload(true)}><UploadCloud size={16} /> Link the first document</button>
        </div>
      ) : null}
    </section>
  );
}

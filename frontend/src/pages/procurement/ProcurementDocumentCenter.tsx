import React, { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArchiveX,
  CheckCircle2,
  ClipboardCheck,
  Download,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Image,
  Link2,
  LoaderCircle,
  MapPin,
  Paperclip,
  Search,
  ShieldAlert,
  ShieldCheck,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";

import { useToast } from "../../components/feedback/ToastProvider";
import {
  downloadProcurementDocument,
  listProcurementDocuments,
  uploadProcurementDocument,
  verifyProcurementDocument,
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
  "DMS_CONTROLLED",
  "EXTERNAL_SOFTWARE",
  "EMAIL",
  "SUPPLIER_PORTAL",
  "PORTAL_EXPORT",
  "OTHER",
];

const ENTITY_TYPES: ProcurementDocumentEntityType[] = [
  "REQUISITION",
  "RFQ",
  "QUOTE",
  "PURCHASE_ORDER",
  "RECEIPT",
  "SUPPLIER",
  "QUALITY_HOLD",
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

type EvidenceForm = {
  entityType: ProcurementDocumentEntityType;
  entityId: string;
  documentType: string;
  title: string;
  source: ProcurementDocumentSource;
  documentNumber: string;
  revision: string;
  documentDate: string;
  physicalReference: string;
  physicalLocation: string;
  externalSystem: string;
  externalReference: string;
  externalUrl: string;
  dmsDocumentId: string;
  dmsRevisionId: string;
  notes: string;
  isQualityEvidence: boolean;
  qmsReference: string;
};

type ReviewAction = {
  document: ProcurementDocument;
  mode: "VERIFY" | "REJECT" | "VOID";
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function fileSize(bytes?: number | null): string {
  if (!bytes) return "No retained file";
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
  const name = (document.original_filename || "").toLowerCase();
  if (/\.(jpg|jpeg|png|tif|tiff)$/.test(name)) return <Image size={18} />;
  if (/\.(xls|xlsx|csv)$/.test(name)) return <FileSpreadsheet size={18} />;
  if (document.download_url) return <FileText size={18} />;
  return <Link2 size={18} />;
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

function emptyForm(initialEntity?: { type: ProcurementDocumentEntityType; id: string } | null): EvidenceForm {
  return {
    entityType: initialEntity?.type || "REQUISITION",
    entityId: initialEntity?.id || "",
    documentType: "PART_REQUISITION_FORM",
    title: "",
    source: "PHYSICAL_FORM",
    documentNumber: "",
    revision: "",
    documentDate: "",
    physicalReference: "",
    physicalLocation: "",
    externalSystem: "",
    externalReference: "",
    externalUrl: "",
    dmsDocumentId: "",
    dmsRevisionId: "",
    notes: "",
    isQualityEvidence: false,
    qmsReference: "",
  };
}

function evidenceSummary(document: ProcurementDocument): string {
  if (document.original_filename) return `${document.original_filename} · ${fileSize(document.size_bytes)}`;
  if (document.dms_document_id) {
    return `DMS ${document.dms_document_id}${document.dms_revision_id ? ` · Rev ${document.dms_revision_id}` : ""}`;
  }
  if (document.external_system || document.external_reference) {
    return `${document.external_system || "External system"}${document.external_reference ? ` · ${document.external_reference}` : ""}`;
  }
  if (document.physical_reference) {
    return `${document.physical_reference}${document.physical_location ? ` · ${document.physical_location}` : ""}`;
  }
  return "Reference-only evidence";
}

function verificationClass(status: ProcurementDocument["verification_status"]): string {
  if (status === "VERIFIED") return "proc-badge--success";
  if (status === "REJECTED") return "proc-badge--danger";
  if (status === "PENDING") return "proc-badge--warning";
  return "proc-badge--info";
}

export default function ProcurementDocumentCenter({
  amoCode,
  records,
  initialEntity,
  canQuality,
  canControl,
}: {
  amoCode: string;
  records: ProcurementRecords;
  initialEntity?: { type: ProcurementDocumentEntityType; id: string } | null;
  canQuality: boolean;
  canControl: boolean;
}) {
  const { pushToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [documents, setDocuments] = useState<ProcurementDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [entityFilter, setEntityFilter] = useState<ProcurementDocumentEntityType | "ALL">("ALL");
  const [includeVoid, setIncludeVoid] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [form, setForm] = useState<EvidenceForm>(() => emptyForm(initialEntity));
  const [reviewAction, setReviewAction] = useState<ReviewAction | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);

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
      const message = caught instanceof Error ? caught.message : "The retained Procurement evidence could not be loaded.";
      setError(message);
      pushToast({ title: "Evidence register unavailable", message, variant: "error", sound: true });
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
      return [
        document.title,
        document.document_type,
        document.document_number,
        document.original_filename,
        document.entity_type,
        document.entity_id,
        document.physical_reference,
        document.physical_location,
        document.external_system,
        document.external_reference,
        document.dms_document_id,
        document.dms_revision_id,
        document.qms_reference,
      ].filter(Boolean).join(" ").toLowerCase().includes(query);
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
    setProgress(0);
    setForm(emptyForm(initialEntity));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const validateForm = (): string | null => {
    if (!form.entityId || !form.title.trim() || !form.documentType.trim()) {
      return "Select the exact Procurement record, document type, and title.";
    }
    if (form.isQualityEvidence && !form.qmsReference.trim()) {
      return "Quality evidence requires a QMS, audit, CAR, inspection, or release reference.";
    }
    if (form.source === "PHYSICAL_FORM" && !selectedFile && !form.physicalReference.trim()) {
      return "Provide a scanned file or the physical register/form reference.";
    }
    if (form.source === "DMS_CONTROLLED" && !form.dmsDocumentId.trim()) {
      return "Enter the controlled DMS document identifier.";
    }
    if (form.source === "EXTERNAL_SOFTWARE") {
      if (!form.externalSystem.trim()) return "Enter the external software or system name.";
      if (!form.externalReference.trim() && !form.externalUrl.trim()) {
        return "Enter the external record reference or its URL.";
      }
    }
    const hasReference = Boolean(
      selectedFile
      || form.physicalReference.trim()
      || form.externalReference.trim()
      || form.externalUrl.trim()
      || form.dmsDocumentId.trim(),
    );
    if (!hasReference) return "Attach a file or provide a physical, external-system, or DMS reference.";
    if (form.externalUrl.trim()) {
      try {
        const parsed = new URL(form.externalUrl.trim());
        if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("protocol");
      } catch {
        return "External URL must be a valid HTTP or HTTPS address.";
      }
    }
    return null;
  };

  const upload = async () => {
    const validation = validateForm();
    if (validation) {
      setError(validation);
      pushToast({ title: "Evidence details incomplete", message: validation, variant: "warning", sound: true });
      return;
    }
    setBusy(true);
    setProgress(1);
    setError("");
    try {
      const created = await uploadProcurementDocument(
        amoCode,
        {
          entityType: form.entityType,
          entityId: form.entityId,
          documentType: form.documentType,
          title: form.title.trim(),
          source: form.source,
          documentNumber: form.documentNumber.trim() || undefined,
          revision: form.revision.trim() || undefined,
          documentDate: form.documentDate || undefined,
          physicalReference: form.physicalReference.trim() || undefined,
          physicalLocation: form.physicalLocation.trim() || undefined,
          externalSystem: form.externalSystem.trim() || undefined,
          externalReference: form.externalReference.trim() || undefined,
          externalUrl: form.externalUrl.trim() || undefined,
          dmsDocumentId: form.dmsDocumentId.trim() || undefined,
          dmsRevisionId: form.dmsRevisionId.trim() || undefined,
          notes: form.notes.trim() || undefined,
          isQualityEvidence: form.isQualityEvidence,
          qmsReference: form.qmsReference.trim() || undefined,
          file: selectedFile,
        },
        setProgress,
      );
      setDocuments((current) => [created, ...current]);
      pushToast({
        title: "Evidence linked and retained",
        message: `${created.title} is now attached to ${humanize(created.entity_type)} #${created.entity_id}.`,
        variant: "success",
        sound: true,
      });
      resetUpload();
      setShowUpload(false);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The evidence could not be retained.";
      setError(message);
      pushToast({ title: "Evidence capture failed", message, variant: "error", sound: true, duration: 8000 });
    } finally {
      setBusy(false);
      setProgress(0);
    }
  };

  const download = async (document: ProcurementDocument) => {
    try {
      await downloadProcurementDocument(amoCode, document);
      pushToast({ title: "Download started", message: document.original_filename || document.title, variant: "success", sound: false });
    } catch (caught) {
      pushToast({
        title: "Download failed",
        message: caught instanceof Error ? caught.message : "The retained file could not be opened.",
        variant: "error",
        sound: true,
      });
    }
  };

  const openReview = (document: ProcurementDocument, mode: ReviewAction["mode"]) => {
    setReviewNotes("");
    setReviewAction({ document, mode });
  };

  const submitReview = async () => {
    if (!reviewAction || reviewNotes.trim().length < 3) {
      pushToast({ title: "Reason required", message: "Enter at least three characters to preserve the control decision.", variant: "warning", sound: true });
      return;
    }
    setReviewBusy(true);
    try {
      const { document, mode } = reviewAction;
      const updated = mode === "VOID"
        ? await voidProcurementDocument(amoCode, document.id, reviewNotes.trim())
        : await verifyProcurementDocument(amoCode, document.id, mode === "VERIFY" ? "VERIFIED" : "REJECTED", reviewNotes.trim());
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      pushToast({
        title: mode === "VOID" ? "Evidence voided" : mode === "VERIFY" ? "Evidence verified" : "Evidence rejected",
        message: `${document.title} remains retained with the control decision and audit trail.`,
        variant: mode === "VERIFY" ? "success" : "warning",
        sound: true,
      });
      setReviewAction(null);
      setReviewNotes("");
    } catch (caught) {
      pushToast({
        title: "Control action failed",
        message: caught instanceof Error ? caught.message : "The evidence control action could not be completed.",
        variant: "error",
        sound: true,
      });
    } finally {
      setReviewBusy(false);
    }
  };

  return (
    <section className="proc-docs" aria-labelledby="proc-docs-title">
      <header className="proc-section-heading proc-section-heading--split">
        <div>
          <span className="proc-eyebrow">Physical, external, and controlled records</span>
          <h2 id="proc-docs-title">Linked evidence register</h2>
          <p>Attach signed forms and certificates, register physical originals, link external software records, or reference controlled DMS revisions against the exact Procurement object.</p>
        </div>
        <button type="button" className="proc-button proc-button--primary" onClick={() => setShowUpload((value) => !value)}>
          {showUpload ? <X size={16} /> : <UploadCloud size={16} />}
          {showUpload ? "Close capture" : "Capture evidence"}
        </button>
      </header>

      <div className="proc-docs__assurance" role="note">
        <ShieldCheck size={20} />
        <div>
          <strong>Controlled retention and Quality oversight</strong>
          <span>Files are tenant-scoped, signature-checked, hashed, and immutable. Physical and digital references remain auditable; Quality evidence stays pending until verified or rejected.</span>
        </div>
      </div>

      {showUpload ? (
        <div className="proc-upload-card">
          <div className="proc-source-selector" aria-label="Evidence source">
            {SOURCES.map((source) => (
              <button
                key={source}
                type="button"
                className={form.source === source ? "is-active" : ""}
                onClick={() => setForm((current) => ({ ...current, source }))}
              >
                <span>{humanize(source)}</span>
                <small>{source === "PHYSICAL_FORM" ? "Signed paper or scanned form" : source === "DMS_CONTROLLED" ? "Controlled document and revision" : source === "EXTERNAL_SOFTWARE" ? "ERP, supplier, or other system" : "Retained supporting evidence"}</small>
              </button>
            ))}
          </div>

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
            <strong>{selectedFile ? selectedFile.name : "Drop a completed form or supporting file"}</strong>
            <span>{selectedFile ? `${fileSize(selectedFile.size)} · ready for controlled retention` : "Optional for reference-only links · PDF, Word, Excel, CSV, JPEG, PNG, or TIFF · maximum 25 MB"}</span>
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
                {ENTITY_TYPES.map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
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

            {form.source === "PHYSICAL_FORM" ? (
              <>
                <label>
                  <span>Physical form/register reference</span>
                  <input value={form.physicalReference} onChange={(event) => setForm((current) => ({ ...current, physicalReference: event.target.value }))} placeholder="PRF Register 2026 / Entry 014" />
                </label>
                <label>
                  <span>Physical storage location</span>
                  <input value={form.physicalLocation} onChange={(event) => setForm((current) => ({ ...current, physicalLocation: event.target.value }))} placeholder="Technical Records Room · Cabinet B4" />
                </label>
              </>
            ) : null}

            {form.source === "DMS_CONTROLLED" ? (
              <>
                <label>
                  <span>DMS document ID</span>
                  <input value={form.dmsDocumentId} onChange={(event) => setForm((current) => ({ ...current, dmsDocumentId: event.target.value }))} placeholder="DOC-PR-0014" />
                </label>
                <label>
                  <span>DMS revision ID</span>
                  <input value={form.dmsRevisionId} onChange={(event) => setForm((current) => ({ ...current, dmsRevisionId: event.target.value }))} placeholder="REV-03" />
                </label>
              </>
            ) : null}

            {form.source === "EXTERNAL_SOFTWARE" || form.source === "SUPPLIER_PORTAL" || form.source === "EMAIL" || form.source === "OTHER" ? (
              <>
                <label>
                  <span>External system or source</span>
                  <input value={form.externalSystem} onChange={(event) => setForm((current) => ({ ...current, externalSystem: event.target.value }))} placeholder="AMOS, TRAX, SAP, supplier portal, email" />
                </label>
                <label>
                  <span>External record reference</span>
                  <input value={form.externalReference} onChange={(event) => setForm((current) => ({ ...current, externalReference: event.target.value }))} placeholder="REQ-87421 or message ID" />
                </label>
                <label className="proc-upload-form__wide">
                  <span>External URL</span>
                  <input type="url" value={form.externalUrl} onChange={(event) => setForm((current) => ({ ...current, externalUrl: event.target.value }))} placeholder="https://external-system.example/record/87421" />
                </label>
              </>
            ) : null}

            <label>
              <span>QMS / inspection reference</span>
              <input value={form.qmsReference} onChange={(event) => setForm((current) => ({ ...current, qmsReference: event.target.value }))} placeholder="Audit, CAR, finding, inspection, or release" />
            </label>
            <label className="proc-upload-form__wide">
              <span>Notes</span>
              <textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} rows={3} placeholder="Explain signatures, source, reconciliation, chain of custody, or why the original remains physical." />
            </label>
            <label className="proc-check proc-upload-form__wide">
              <input type="checkbox" checked={form.isQualityEvidence} onChange={(event) => setForm((current) => ({ ...current, isQualityEvidence: event.target.checked }))} />
              <span><strong>Quality evidence</strong><small>Requires an independent Quality verification or rejection decision.</small></span>
            </label>
          </div>

          {error ? <div className="proc-message proc-message--error" role="alert"><AlertTriangle size={18} /><span>{error}</span></div> : null}
          {busy ? (
            <div className="proc-upload-progress" role="status" aria-live="polite">
              <LoaderCircle className="is-spinning" size={18} />
              <div>
                <strong>{progress < 100 ? `Uploading and validating · ${progress}%` : "Finalizing retained evidence"}</strong>
                <span>Type, signature, size, duplicate hash, tenant link, and audit metadata are checked before completion.</span>
                <div className="proc-progress-track"><span style={{ width: `${Math.max(progress, 4)}%` }} /></div>
              </div>
            </div>
          ) : null}

          <footer className="proc-upload-actions">
            <button type="button" className="proc-button proc-button--ghost" onClick={resetUpload} disabled={busy}>Clear</button>
            <button type="button" className="proc-button proc-button--primary" onClick={() => void upload()} disabled={busy}>
              {busy ? <LoaderCircle className="is-spinning" size={16} /> : <UploadCloud size={16} />}
              {busy ? "Retaining evidence" : "Link and retain"}
            </button>
          </footer>
        </div>
      ) : null}

      <div className="proc-doc-toolbar">
        <label className="proc-search-box">
          <Search size={16} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title, file, physical reference, system, DMS ID, or linked record" />
        </label>
        <select value={entityFilter} onChange={(event) => setEntityFilter(event.target.value as ProcurementDocumentEntityType | "ALL")} aria-label="Filter evidence entity type">
          <option value="ALL">All linked records</option>
          {ENTITY_TYPES.map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
        </select>
        <label className="proc-check proc-check--compact">
          <input type="checkbox" checked={includeVoid} onChange={(event) => setIncludeVoid(event.target.checked)} />
          <span>Include void records</span>
        </label>
      </div>

      {loading ? (
        <div className="proc-document-skeleton" role="status" aria-label="Loading linked evidence">
          {Array.from({ length: 4 }).map((_, index) => <span key={index} />)}
        </div>
      ) : null}

      {!loading && error && !documents.length ? (
        <div className="proc-message proc-message--error" role="alert">
          <AlertTriangle size={18} /><span>{error}</span><button type="button" onClick={() => void load()}>Retry</button>
        </div>
      ) : null}

      {!loading && filtered.length ? (
        <div className="proc-document-list">
          {filtered.map((document) => (
            <article key={document.id} className={`proc-document${document.status === "VOID" ? " is-void" : ""}`}>
              <div className="proc-document__icon" aria-hidden="true">{iconForDocument(document)}</div>
              <div className="proc-document__identity">
                <div>
                  <strong>{document.title}</strong>
                  {document.is_quality_evidence ? <span className="proc-badge proc-badge--quality"><ShieldCheck size={12} /> Quality evidence</span> : null}
                  <span className={`proc-badge ${verificationClass(document.verification_status)}`}>{humanize(document.verification_status)}</span>
                  {document.status === "VOID" ? <span className="proc-badge proc-badge--danger">Void</span> : null}
                </div>
                <span>{evidenceSummary(document)}</span>
                <small>{humanize(document.entity_type)} #{document.entity_id} · {humanize(document.document_type)} · {humanize(document.source)}</small>
                {document.verification_notes ? <small className="proc-document__decision">Decision: {document.verification_notes}</small> : null}
              </div>
              <div className="proc-document__meta">
                <span>{document.document_number || "No document number"}{document.revision ? ` · ${document.revision}` : ""}</span>
                <small>{formatDate(document.uploaded_at)}</small>
                {document.sha256 ? <code title={document.sha256}>SHA-256 {document.sha256.slice(0, 12)}…</code> : null}
                {document.physical_location ? <small><MapPin size={12} /> {document.physical_location}</small> : null}
              </div>
              <div className="proc-document__actions">
                {document.download_url ? <button type="button" className="proc-icon-button" onClick={() => void download(document)} aria-label={`Download ${document.title}`} title="Download retained copy"><Download size={16} /></button> : null}
                {document.external_url ? <a className="proc-icon-button" href={document.external_url} target="_blank" rel="noreferrer" aria-label={`Open external record for ${document.title}`} title="Open external record"><ExternalLink size={16} /></a> : null}
                {canQuality && document.status === "ACTIVE" && document.verification_status !== "VERIFIED" ? <button type="button" className="proc-icon-button proc-icon-button--quality" onClick={() => openReview(document, "VERIFY")} aria-label={`Verify ${document.title}`} title="Verify evidence"><CheckCircle2 size={16} /></button> : null}
                {canQuality && document.status === "ACTIVE" && document.verification_status !== "REJECTED" ? <button type="button" className="proc-icon-button proc-icon-button--warning" onClick={() => openReview(document, "REJECT")} aria-label={`Reject ${document.title}`} title="Reject evidence"><XCircle size={16} /></button> : null}
                {canControl && document.status === "ACTIVE" ? <button type="button" className="proc-icon-button proc-icon-button--danger" onClick={() => openReview(document, "VOID")} aria-label={`Void ${document.title}`} title="Void evidence without deleting it"><ArchiveX size={16} /></button> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {!loading && !filtered.length && !error ? (
        <div className="proc-empty-state">
          <Paperclip size={28} />
          <strong>No linked evidence in this view</strong>
          <span>Capture the signed requisition, supplier quotation, delivery note, release certificate, inspection evidence, physical register entry, DMS revision, or external-system record.</span>
          <button type="button" className="proc-button proc-button--secondary" onClick={() => setShowUpload(true)}><UploadCloud size={16} /> Capture the first record</button>
        </div>
      ) : null}

      {reviewAction ? (
        <div className="proc-modal" role="dialog" aria-modal="true" aria-labelledby="proc-evidence-action-title">
          <button type="button" className="proc-modal__backdrop" aria-label="Close evidence action" onClick={() => !reviewBusy && setReviewAction(null)} />
          <div className="proc-modal__panel proc-modal__panel--compact">
            <header>
              <div>
                <h2 id="proc-evidence-action-title">{reviewAction.mode === "VERIFY" ? "Verify evidence" : reviewAction.mode === "REJECT" ? "Reject evidence" : "Void retained evidence"}</h2>
                <p>{reviewAction.document.title}</p>
              </div>
              <button type="button" className="proc-icon-button" onClick={() => setReviewAction(null)} disabled={reviewBusy} aria-label="Close"><X size={17} /></button>
            </header>
            <div className={`proc-message ${reviewAction.mode === "VERIFY" ? "proc-message--success" : "proc-message--warning"}`} role="note">
              {reviewAction.mode === "VERIFY" ? <ClipboardCheck size={18} /> : <ShieldAlert size={18} />}
              <span>{reviewAction.mode === "VOID" ? "The retained file or reference will not be deleted. Its status and reason remain in the audit trail." : "Record the independent Quality decision and the evidence reviewed."}</span>
            </div>
            <label className="proc-field">
              <span>{reviewAction.mode === "VERIFY" ? "Verification notes" : reviewAction.mode === "REJECT" ? "Rejection reason" : "Void reason"}</span>
              <textarea rows={4} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} autoFocus />
            </label>
            <footer className="proc-form__footer">
              <button type="button" className="proc-button proc-button--ghost" onClick={() => setReviewAction(null)} disabled={reviewBusy}>Cancel</button>
              <button type="button" className={`proc-button ${reviewAction.mode === "VERIFY" ? "proc-button--primary" : "proc-button--danger"}`} onClick={() => void submitReview()} disabled={reviewBusy || reviewNotes.trim().length < 3}>
                {reviewBusy ? <LoaderCircle className="is-spinning" size={16} /> : reviewAction.mode === "VERIFY" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                {reviewBusy ? "Recording decision" : reviewAction.mode === "VERIFY" ? "Verify evidence" : reviewAction.mode === "REJECT" ? "Reject evidence" : "Void evidence"}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </section>
  );
}

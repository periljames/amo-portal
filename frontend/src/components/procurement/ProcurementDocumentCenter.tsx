import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BadgeCheck, FileCheck2, FileText, Link2, LoaderCircle, MapPin, Paperclip, ShieldCheck, UploadCloud } from "lucide-react";
import {
  linkProcurementDocument,
  listProcurementDocuments,
  uploadProcurementDocument,
  verifyProcurementDocument,
} from "../../services/procurementDocuments";
import type { ProcurementEvidence } from "../../types/procurementDocuments";

type Mode = "UPLOAD" | "PHYSICAL_RECORD" | "DMS_LINK";
type Feedback = (tone: "success" | "error" | "warning" | "info", message: string, detail?: string) => void;

function formatBytes(value?: number | null): string {
  if (!value) return "—";
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function ProcurementDocumentCenter({ amoCode, onFeedback }: { amoCode: string; onFeedback: Feedback }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<ProcurementEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [mode, setMode] = useState<Mode>("UPLOAD");
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    entityType: "REQUISITION",
    entityId: "",
    kind: "REQUISITION_FORM",
    title: "",
    notes: "",
    physicalReference: "",
    physicalLocation: "",
    dmsDocumentId: "",
    dmsRevisionId: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocuments(await listProcurementDocuments(amoCode));
    } catch (error) {
      onFeedback("error", "Document register unavailable", error instanceof Error ? error.message : "The evidence list could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [amoCode, onFeedback]);

  useEffect(() => { void load(); }, [load]);

  const pending = useMemo(() => documents.filter((item) => !item.is_verified).length, [documents]);

  const chooseFile = (next: File | null) => {
    setFile(next);
    if (next && !form.title) setForm((current) => ({ ...current, title: next.name.replace(/\.[^.]+$/, "") }));
  };

  const submit = async () => {
    if (!form.entityId.trim()) {
      onFeedback("warning", "Record reference required", "Enter the requisition, receipt, supplier, PO, or hold ID.");
      return;
    }
    setSaving(true);
    try {
      if (mode === "UPLOAD") {
        if (!file) throw new Error("Choose a document to upload.");
        await uploadProcurementDocument(amoCode, {
          entityType: form.entityType,
          entityId: form.entityId,
          documentKind: form.kind,
          title: form.title || file.name,
          notes: form.notes,
          file,
        });
      } else {
        await linkProcurementDocument(amoCode, {
          entity_type: form.entityType,
          entity_id: form.entityId,
          document_kind: form.kind,
          title: form.title,
          source_type: mode,
          physical_reference: mode === "PHYSICAL_RECORD" ? form.physicalReference : null,
          physical_location: mode === "PHYSICAL_RECORD" ? form.physicalLocation : null,
          dms_document_id: mode === "DMS_LINK" ? form.dmsDocumentId : null,
          dms_revision_id: mode === "DMS_LINK" ? form.dmsRevisionId : null,
          notes: form.notes || null,
        });
      }
      chooseFile(null);
      setForm((current) => ({ ...current, title: "", notes: "", physicalReference: "", physicalLocation: "", dmsDocumentId: "", dmsRevisionId: "" }));
      onFeedback("success", "Evidence linked", "The procurement record now includes a controlled evidence reference.");
      await load();
    } catch (error) {
      onFeedback("error", "Evidence action failed", error instanceof Error ? error.message : "The document could not be linked.");
    } finally {
      setSaving(false);
    }
  };

  const verify = async (documentId: number) => {
    try {
      await verifyProcurementDocument(amoCode, documentId, true, "Verified from Procurement document register.");
      onFeedback("success", "Evidence verified", "Quality verification was recorded against the evidence item.");
      await load();
    } catch (error) {
      onFeedback("error", "Verification failed", error instanceof Error ? error.message : undefined);
    }
  };

  return (
    <section className="proc-document-center">
      <header>
        <div>
          <span>Document evidence</span>
          <h2>Digital, DMS, and physical records</h2>
          <p>Attach externally completed requisition forms, delivery notes, certificates, quotations, approvals, and scanned records.</p>
        </div>
        <div className="proc-document-summary"><strong>{documents.length}</strong><span>records</span><em>{pending} awaiting Quality verification</em></div>
      </header>

      <div className="proc-document-layout">
        <div className="proc-document-compose">
          <div className="proc-segmented" role="tablist" aria-label="Evidence source">
            <button type="button" className={mode === "UPLOAD" ? "is-active" : ""} onClick={() => setMode("UPLOAD")}><UploadCloud size={15} /> Upload</button>
            <button type="button" className={mode === "PHYSICAL_RECORD" ? "is-active" : ""} onClick={() => setMode("PHYSICAL_RECORD")}><MapPin size={15} /> Physical record</button>
            <button type="button" className={mode === "DMS_LINK" ? "is-active" : ""} onClick={() => setMode("DMS_LINK")}><Link2 size={15} /> DMS link</button>
          </div>

          <div className="proc-document-fields">
            <label><span>Record type</span><select value={form.entityType} onChange={(event) => setForm({ ...form, entityType: event.target.value })}>{["REQUISITION", "RFQ", "QUOTE", "PURCHASE_ORDER", "RECEIPT", "SUPPLIER", "QUALITY_HOLD", "INVOICE_MATCH"].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label><span>Record ID</span><input value={form.entityId} onChange={(event) => setForm({ ...form, entityId: event.target.value })} placeholder="Portal record ID or reference" /></label>
            <label><span>Document kind</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value })}>{["REQUISITION_FORM", "QUOTATION", "PURCHASE_ORDER", "DELIVERY_NOTE", "AIRWAY_BILL", "CERTIFICATE", "INSPECTION_RECORD", "APPROVAL_EVIDENCE", "INVOICE", "OTHER"].map((value) => <option key={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
            <label><span>Title</span><input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Clear controlled record title" /></label>
          </div>

          {mode === "UPLOAD" && (
            <button
              type="button"
              className={`proc-dropzone ${dragging ? "is-dragging" : ""}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0] || null); }}
            >
              <input ref={inputRef} hidden type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.jpg,.jpeg,.png" onChange={(event) => chooseFile(event.target.files?.[0] || null)} />
              <UploadCloud size={26} />
              <strong>{file ? file.name : "Drop a controlled document here"}</strong>
              <span>{file ? formatBytes(file.size) : "PDF, Word, Excel, CSV, JPEG, or PNG · maximum 25MB"}</span>
            </button>
          )}

          {mode === "PHYSICAL_RECORD" && <div className="proc-document-fields proc-document-fields--secondary"><label><span>Physical reference</span><input value={form.physicalReference} onChange={(event) => setForm({ ...form, physicalReference: event.target.value })} placeholder="Box/file/form number" /></label><label><span>Storage location</span><input value={form.physicalLocation} onChange={(event) => setForm({ ...form, physicalLocation: event.target.value })} placeholder="Archive, cabinet, shelf" /></label></div>}
          {mode === "DMS_LINK" && <div className="proc-document-fields proc-document-fields--secondary"><label><span>DMS document ID</span><input value={form.dmsDocumentId} onChange={(event) => setForm({ ...form, dmsDocumentId: event.target.value })} /></label><label><span>Revision ID</span><input value={form.dmsRevisionId} onChange={(event) => setForm({ ...form, dmsRevisionId: event.target.value })} /></label></div>}

          <label className="proc-document-notes"><span>Notes</span><textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Traceability, reason for external creation, certification details, or handling instructions" /></label>
          <button type="button" className="proc-btn proc-btn--primary proc-document-submit" onClick={() => void submit()} disabled={saving}>{saving ? <><LoaderCircle size={16} className="is-spinning" /> Securing evidence…</> : <><Paperclip size={16} /> Link evidence</>}</button>
        </div>

        <div className="proc-document-register">
          {loading ? <div className="proc-document-loading"><LoaderCircle className="is-spinning" /> Loading evidence register…</div> : documents.length ? documents.map((item) => (
            <article key={item.id} className={item.is_verified ? "is-verified" : ""}>
              <div className="proc-document-icon">{item.source_type === "UPLOADED" ? <FileText /> : item.source_type === "DMS_LINK" ? <Link2 /> : <MapPin />}</div>
              <div className="proc-document-meta"><strong>{item.title}</strong><span>{item.entity_type} #{item.entity_id} · {item.document_kind.replaceAll("_", " ")}</span><small>{item.file_name || item.physical_reference || item.dms_document_id} · {new Date(item.created_at).toLocaleDateString()}</small></div>
              <div className="proc-document-actions">
                {item.is_verified ? <span className="proc-verified"><BadgeCheck size={14} /> Quality verified</span> : <button type="button" onClick={() => void verify(item.id)}><ShieldCheck size={14} /> Verify</button>}
                {item.download_url && <a href={item.download_url} target="_blank" rel="noreferrer"><FileCheck2 size={14} /> Open</a>}
              </div>
            </article>
          )) : <div className="proc-empty">No evidence has been linked to this view.</div>}
        </div>
      </div>
    </section>
  );
}

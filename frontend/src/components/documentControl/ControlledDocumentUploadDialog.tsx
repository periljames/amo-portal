import { useEffect, useMemo, useState } from "react";
import { FileCheck2, FolderTree, ShieldCheck, UploadCloud, X } from "lucide-react";

import { listIntegratedLibrary, type IntegratedLibraryItem } from "../../services/documentLibrary";
import {
  approvePublicationIntake,
  previewPublicationUpload,
  uploadPublicationRevision,
  type ApprovedPublicationIntakePayload,
  type ControlledDocumentIntakeMetadata,
  type ControlledDocumentType,
  type PublicationUploadPayload,
  type PublicationUploadPreview,
  type PublicationUploadResult,
} from "../../services/publications";
import "./controlledDocumentUploadDialog.css";

export type ControlledDocumentIntakeResult = PublicationUploadResult & Record<string, unknown>;

type Props = {
  tenant: string;
  open: boolean;
  defaultDocumentType?: ControlledDocumentType;
  allowedTypes?: ControlledDocumentType[];
  heading?: string;
  submitLabel?: string;
  allowApprovedIntake?: boolean;
  onClose: () => void;
  onUploaded: (result: ControlledDocumentIntakeResult) => void | Promise<void>;
  submitIntake?: (payload: PublicationUploadPayload) => Promise<ControlledDocumentIntakeResult>;
};

type IntakeState = "DRAFT" | "APPROVED";

type FormState = {
  documentType: ControlledDocumentType;
  code: string;
  title: string;
  description: string;
  revisionNumber: string;
  issueNumber: string;
  effectiveDate: string;
  ownerDepartment: string;
  sourceIssuer: string;
  parentDocumentId: string;
  nextReviewDue: string;
  reviewIntervalMonths: string;
  retentionYears: string;
  confidentiality: ControlledDocumentIntakeMetadata["confidentiality"];
  acknowledgementRequired: boolean;
  tags: string;
  changeLog: string;
};

const CONTROLLED_DOCUMENT_TYPES: Array<{ value: ControlledDocumentType; label: string; guidance: string }> = [
  { value: "MANUAL", label: "Manual", guidance: "Top-level controlled operating or management manual" },
  { value: "REGULATION", label: "Regulation / standard", guidance: "External statutory, regulatory, or industry requirement" },
  { value: "POLICY", label: "Policy", guidance: "Management intent and governing direction" },
  { value: "PROCEDURE", label: "Procedure", guidance: "Controlled process describing what must be done" },
  { value: "WORK_INSTRUCTION", label: "Work instruction", guidance: "Detailed task instruction derived from a procedure" },
  { value: "FORM", label: "Form", guidance: "Controlled blank template used to capture evidence" },
  { value: "CHECKLIST", label: "Checklist", guidance: "Controlled verification questions or inspection steps" },
  { value: "REGISTER", label: "Register", guidance: "Controlled log or index template" },
  { value: "RECORD", label: "Record", guidance: "Completed evidence retained under a defined period" },
  { value: "EXTERNAL_DOCUMENT", label: "External document", guidance: "Manufacturer, supplier, customer, or other external information" },
];

const PARENT_TYPES: Partial<Record<ControlledDocumentType, ControlledDocumentType[]>> = {
  POLICY: ["MANUAL", "REGULATION"],
  PROCEDURE: ["MANUAL", "REGULATION", "POLICY"],
  WORK_INSTRUCTION: ["MANUAL", "POLICY", "PROCEDURE"],
  FORM: ["MANUAL", "POLICY", "PROCEDURE", "WORK_INSTRUCTION"],
  CHECKLIST: ["MANUAL", "POLICY", "PROCEDURE", "WORK_INSTRUCTION"],
  REGISTER: ["MANUAL", "POLICY", "PROCEDURE", "WORK_INSTRUCTION"],
  RECORD: ["FORM", "CHECKLIST", "REGISTER"],
};

function isoAfterMonths(months: number): string {
  const value = new Date();
  value.setMonth(value.getMonth() + months);
  return value.toISOString().slice(0, 10);
}

function fileStem(filename: string): string {
  return filename.replace(/\.(docx|pdf)$/i, "").replace(/[_-]+/g, " ").trim();
}

function fallbackCode(filename: string): string {
  return filename.replace(/\.(docx|pdf)$/i, "").toUpperCase().replace(/[^A-Z0-9]+/g, "/").replace(/^\/+|\/+$/g, "").slice(0, 32);
}

function initialForm(documentType: ControlledDocumentType): FormState {
  const annual = documentType === "CHECKLIST";
  return {
    documentType,
    code: "",
    title: "",
    description: "",
    revisionNumber: "00",
    issueNumber: "00",
    effectiveDate: "",
    ownerDepartment: documentType === "CHECKLIST" ? "QUALITY" : "DOCUMENT_CONTROL",
    sourceIssuer: "Safarilink Aviation Limited",
    parentDocumentId: "",
    nextReviewDue: isoAfterMonths(annual ? 12 : 24),
    reviewIntervalMonths: annual ? "12" : "24",
    retentionYears: documentType === "RECORD" ? "5" : "",
    confidentiality: "INTERNAL",
    acknowledgementRequired: documentType !== "RECORD",
    tags: "",
    changeLog: "Initial controlled-document intake.",
  };
}

function detectedForm(file: File, preview: PublicationUploadPreview, current: FormState): FormState {
  const metadata = preview.metadata || {};
  return {
    ...current,
    code: String(metadata.part_number || fallbackCode(file.name)),
    title: String(metadata.title || preview.heading || fileStem(file.name)),
    revisionNumber: String(metadata.revision_number || current.revisionNumber),
    issueNumber: String(metadata.issue_number || current.issueNumber),
    effectiveDate: String(metadata.effective_date || current.effectiveDate),
  };
}

export default function ControlledDocumentUploadDialog({
  tenant,
  open,
  defaultDocumentType = "MANUAL",
  allowedTypes,
  heading = "Register controlled document",
  submitLabel = "Register controlled draft",
  allowApprovedIntake = false,
  onClose,
  onUploaded,
  submitIntake,
}: Props) {
  const permittedTypes = useMemo(
    () => CONTROLLED_DOCUMENT_TYPES.filter((item) => !allowedTypes || allowedTypes.includes(item.value)),
    [allowedTypes],
  );
  const safeDefault = permittedTypes.some((item) => item.value === defaultDocumentType) ? defaultDocumentType : permittedTypes[0]?.value || "MANUAL";
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PublicationUploadPreview | null>(null);
  const [form, setForm] = useState<FormState>(() => initialForm(safeDefault));
  const [parents, setParents] = useState<IntegratedLibraryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState<"FILE" | "METADATA">("FILE");
  const [intakeState, setIntakeState] = useState<IntakeState>("DRAFT");
  const [approvingAuthority, setApprovingAuthority] = useState("Quality Manager");
  const [approvalReference, setApprovalReference] = useState("");
  const [approvalDate, setApprovalDate] = useState("");
  const [approvalBasis, setApprovalBasis] = useState("");
  const [registeredUpload, setRegisteredUpload] = useState<ControlledDocumentIntakeResult | null>(null);
  const [approvedUpload, setApprovedUpload] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setPreview(null);
    setForm(initialForm(safeDefault));
    setBusy(false);
    setError("");
    setStep("FILE");
    setIntakeState("DRAFT");
    setApprovingAuthority("Quality Manager");
    setApprovalReference("");
    setApprovalDate("");
    setApprovalBasis("");
    setRegisteredUpload(null);
    setApprovedUpload(false);
    void listIntegratedLibrary(tenant, { status: "ACTIVE", perPage: 100, sort: "type" })
      .then((result) => setParents(result.items))
      .catch(() => setParents([]));
  }, [open, safeDefault, tenant]);

  const allowedParentTypes = PARENT_TYPES[form.documentType] || [];
  const parentOptions = parents.filter((item) => allowedParentTypes.includes(item.library.node_type as ControlledDocumentType));
  const changeType = (documentType: ControlledDocumentType) => {
    setForm((current) => ({
      ...current,
      documentType,
      parentDocumentId: "",
      reviewIntervalMonths: documentType === "CHECKLIST" ? "12" : current.reviewIntervalMonths || "24",
      nextReviewDue: documentType === "CHECKLIST" ? isoAfterMonths(12) : current.nextReviewDue,
      retentionYears: documentType === "RECORD" ? current.retentionYears || "5" : current.retentionYears,
      acknowledgementRequired: documentType !== "RECORD" && current.acknowledgementRequired,
    }));
  };

  const chooseFile = async (selected: File | null) => {
    if (!selected) return;
    if (!/\.(docx|pdf)$/i.test(selected.name)) {
      setError("Choose a PDF or DOCX file.");
      return;
    }
    setBusy(true);
    setError("");
    setFile(selected);
    try {
      const inspected = await previewPublicationUpload(tenant, selected);
      setPreview(inspected);
      setForm((current) => detectedForm(selected, inspected, current));
      if (inspected.source_type !== "PDF") setIntakeState("DRAFT");
      setStep("METADATA");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document could not be inspected.");
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!file || busy) return;
    if (!form.code.trim() || !form.title.trim() || !form.revisionNumber.trim() || !form.ownerDepartment.trim()) {
      setError("Document code, title, revision, and responsible department are required.");
      return;
    }
    if (intakeState === "APPROVED") {
      if (preview?.source_type !== "PDF") {
        setError("An already-approved checklist must be uploaded as its final PDF.");
        return;
      }
      if (!approvingAuthority.trim() || !approvalReference.trim() || !approvalDate || !approvalBasis.trim()) {
        setError("Approving function, approval reference, approval date, and approval basis are required.");
        return;
      }
    }
    const reviewInterval = Number(form.reviewIntervalMonths);
    const retention = form.retentionYears ? Number(form.retentionYears) : null;
    const maximumReviewMonths = form.documentType === "CHECKLIST" ? 12 : 24;
    if (!Number.isInteger(reviewInterval) || reviewInterval < 1 || reviewInterval > maximumReviewMonths) {
      setError(`Review interval must be between 1 and ${maximumReviewMonths} months for this document type.`);
      return;
    }
    if (form.nextReviewDue && form.nextReviewDue > isoAfterMonths(maximumReviewMonths)) {
      setError(`Next review must be due within ${maximumReviewMonths} months for this document type.`);
      return;
    }
    if (retention !== null && (!Number.isInteger(retention) || retention < 1 || retention > 100)) {
      setError("Retention period must be between 1 and 100 years.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload: PublicationUploadPayload = {
        code: form.code.trim(),
        title: form.title.trim(),
        rev_number: form.revisionNumber.trim(),
        issue_number: form.issueNumber.trim() || "00",
        effective_date: form.effectiveDate || undefined,
        manual_type: form.documentType,
        owner_role: form.ownerDepartment.trim(),
        change_log: form.changeLog.trim() || undefined,
        control_metadata: {
          document_type: form.documentType,
          document_class: form.documentType === "RECORD" ? "RECORD" : form.documentType === "REGULATION" || form.documentType === "EXTERNAL_DOCUMENT" ? "EXTERNAL" : "INTERNAL",
          description: form.description.trim() || null,
          owner_department: form.ownerDepartment.trim(),
          source_issuer: form.sourceIssuer.trim() || null,
          parent_document_id: form.parentDocumentId || null,
          next_review_due: form.nextReviewDue || null,
          review_interval_months: reviewInterval,
          retention_years: retention,
          confidentiality: form.confidentiality,
          acknowledgement_required: form.acknowledgementRequired,
          regulated_flag: form.documentType === "REGULATION",
          tags: form.tags.split(",").map((item) => item.trim()).filter(Boolean),
        },
        file,
      };
      const uploaded = registeredUpload || (submitIntake ? await submitIntake(payload) : await uploadPublicationRevision(tenant, payload));
      setRegisteredUpload(uploaded);
      let result: ControlledDocumentIntakeResult = { ...uploaded, intake_state: intakeState, approved_intake: false };
      if (intakeState === "APPROVED") {
        const approval: ApprovedPublicationIntakePayload = {
          approval_kind: "INTERNAL",
          authority_name: approvingAuthority.trim(),
          approval_reference: approvalReference.trim(),
          approval_date: approvalDate,
          effective_date: form.effectiveDate || approvalDate,
          comments: approvalBasis.trim(),
          acknowledgement_required: form.acknowledgementRequired,
          notify_eligible_users: false,
        };
        if (!approvedUpload) {
          await approvePublicationIntake(tenant, uploaded.manual_id, uploaded.revision_id, approval);
          setApprovedUpload(true);
        }
        result = { ...result, status: "PUBLISHED", approved_intake: true, approval_reference: approval.approval_reference };
      }
      await onUploaded(result);
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled document could not be registered.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;
  return (
    <div className="controlled-intake__backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="controlled-intake" role="dialog" aria-modal="true" aria-labelledby="controlled-intake-title">
        <header>
          <div><span className="controlled-intake__eyebrow">DOCUMENT CONTROL INTAKE</span><h2 id="controlled-intake-title">{heading}</h2><p>Choose the source, then confirm the information needed to control it.</p></div>
          <button type="button" onClick={onClose} disabled={busy} aria-label="Close controlled-document intake"><X size={18} /></button>
        </header>
        <div className="controlled-intake__rail" aria-label="Upload progress">
          <span className={step === "FILE" ? "is-active" : "is-complete"}><b>1</b> Source file</span>
          <span className={step === "METADATA" ? "is-active" : ""}><b>2</b> Confirm metadata</span>
        </div>
        {error ? <div className="controlled-intake__error" role="alert">{error}</div> : null}
        {error && registeredUpload ? <p role="status">The upload is saved. Retrying continues with this document and will not upload another copy. <a href={`/maintenance/${encodeURIComponent(tenant)}/document-control/library/${encodeURIComponent(registeredUpload.manual_id)}?tab=workflow`}>Open saved document</a></p> : null}
        {step === "FILE" ? (
          <div className="controlled-intake__file-step">
            <label>
              <UploadCloud size={26} />
              <strong>{busy ? "Inspecting source…" : "Choose a PDF or DOCX document"}</strong>
              <span>PDF up to 50 MB · DOCX up to 10 MB · original source retained</span>
              <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy} onChange={(event) => void chooseFile(event.target.files?.[0] || null)} />
            </label>
          </div>
        ) : (
          <div className="controlled-intake__body">
            <div className="controlled-intake__source-summary"><FileCheck2 size={18} /><span><strong>{file?.name}</strong><small>{preview?.source_type} · {preview?.page_count ? `${preview.page_count} pages · ` : ""}{preview?.paragraph_count || 0} indexed text blocks</small></span><button type="button" disabled={busy || Boolean(registeredUpload)} onClick={() => { setStep("FILE"); setFile(null); setPreview(null); }}>Change</button></div>
            <fieldset disabled={busy || Boolean(registeredUpload)}>
              <legend><ShieldCheck size={15} /> Required document details</legend>
              <label><span>Document type</span><select value={form.documentType} onChange={(event) => changeType(event.target.value as ControlledDocumentType)}>{permittedTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
              {allowApprovedIntake ? <label><span>Intake status</span><select value={intakeState} onChange={(event) => setIntakeState(event.target.value as IntakeState)}><option value="DRAFT">Draft for DMS review</option><option value="APPROVED" disabled={preview?.source_type !== "PDF"}>Already approved final PDF</option></select><small>{preview?.source_type !== "PDF" ? "Already approved intake requires the final PDF to preserve signatures and approval marks. Choose Change above to upload that PDF, or submit this DOCX for review." : "Select Already approved to record existing approval evidence and make the final PDF current."}</small></label> : null}
              <label><span>Document code</span><input required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></label>
              <label className="is-wide"><span>Title</span><input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
              <label><span>Revision</span><input required value={form.revisionNumber} onChange={(event) => setForm({ ...form, revisionNumber: event.target.value })} /></label>
              <label><span>Responsible department</span><input required value={form.ownerDepartment} onChange={(event) => setForm({ ...form, ownerDepartment: event.target.value })} /></label>
              {allowedParentTypes.length ? <label className="is-wide"><span>Parent controlled document</span><select value={form.parentDocumentId} onChange={(event) => setForm({ ...form, parentDocumentId: event.target.value })}><option value="">No direct parent</option>{parentOptions.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.title} · {item.library.node_type.replaceAll("_", " ")}</option>)}</select></label> : null}
            </fieldset>
            {allowApprovedIntake && intakeState === "APPROVED" ? <fieldset disabled={busy || approvedUpload}><legend>Existing approval evidence</legend>
                <label><span>Approving function</span><input required value={approvingAuthority} onChange={(event) => setApprovingAuthority(event.target.value)} /></label>
                <label><span>Approval reference</span><input required value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} /></label>
                <label><span>Approval date</span><input required type="date" max={new Date().toISOString().slice(0, 10)} value={approvalDate} onChange={(event) => setApprovalDate(event.target.value)} /></label>
                <label className="is-wide"><span>Approval basis</span><textarea required rows={2} value={approvalBasis} onChange={(event) => setApprovalBasis(event.target.value)} /></label>
            </fieldset> : null}
            <details className="controlled-intake__optional">
              <summary><FolderTree size={15} /> Additional controls</summary>
              <fieldset disabled={busy || Boolean(registeredUpload)}>
                <label><span>Issue</span><input value={form.issueNumber} onChange={(event) => setForm({ ...form, issueNumber: event.target.value })} /></label>
                <label><span>Proposed effective date</span><input type="date" value={form.effectiveDate} onChange={(event) => setForm({ ...form, effectiveDate: event.target.value })} /></label>
                <label className="is-wide"><span>Description</span><textarea rows={2} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
                <label><span>Source / issuer</span><input value={form.sourceIssuer} onChange={(event) => setForm({ ...form, sourceIssuer: event.target.value })} /></label>
                <label><span>Confidentiality</span><select value={form.confidentiality} onChange={(event) => setForm({ ...form, confidentiality: event.target.value as FormState["confidentiality"] })}><option value="PUBLIC">Public</option><option value="INTERNAL">Internal</option><option value="CONFIDENTIAL">Confidential</option><option value="RESTRICTED">Restricted</option></select></label>
                <label><span>Review every (months)</span><input type="number" min={1} max={form.documentType === "CHECKLIST" ? 12 : 24} value={form.reviewIntervalMonths} onChange={(event) => setForm({ ...form, reviewIntervalMonths: event.target.value })} /></label>
                <label><span>Next review due</span><input type="date" value={form.nextReviewDue} onChange={(event) => setForm({ ...form, nextReviewDue: event.target.value })} /></label>
                {form.documentType === "RECORD" ? <label><span>Retention (years)</span><input type="number" min={1} max={100} value={form.retentionYears} onChange={(event) => setForm({ ...form, retentionYears: event.target.value })} /></label> : null}
                <label><span>Tags</span><input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="quality, maintenance" /></label>
                <label className="is-check"><input type="checkbox" checked={form.acknowledgementRequired} onChange={(event) => setForm({ ...form, acknowledgementRequired: event.target.checked })} /><span>Require acknowledgement when issued</span></label>
                <label className="is-wide"><span>Change reason</span><textarea rows={2} value={form.changeLog} onChange={(event) => setForm({ ...form, changeLog: event.target.value })} /></label>
              </fieldset>
            </details>
          </div>
        )}
        <footer><span>{step === "METADATA" ? intakeState === "APPROVED" ? "The final PDF will become the current controlled revision." : "Registration creates a controlled draft and notifies Document Control. Open its workflow to submit for review." : "No record is created until the file is confirmed."}</span><div><button type="button" disabled={busy} onClick={onClose}>Cancel</button>{step === "METADATA" ? <button type="button" className="is-primary" disabled={busy} onClick={() => void submit()}><UploadCloud size={15} /> {busy ? "Registering…" : intakeState === "APPROVED" ? "Register approved document" : submitLabel}</button> : null}</div></footer>
      </section>
    </div>
  );
}

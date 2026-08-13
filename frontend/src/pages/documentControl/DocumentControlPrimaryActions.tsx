import { useState, type FormEvent, type ReactNode } from "react";
import { FileUp, Pencil, Rocket, ShieldCheck, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  transitionDocumentWorkflow,
  upsertDocumentProfile,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import { updateDocumentMetadata } from "../../services/documentControlReports";
import {
  approvePublicationIntake,
  previewPublicationUpload,
  uploadPublicationRevision,
  type PublicationUploadPreview,
} from "../../services/publications";
import DocumentEvidencePicker from "./DocumentEvidencePicker";


type EnhancedCapabilities = DocumentDetailResponse["capabilities"] & {
  approve?: boolean;
  edit_properties?: boolean;
  upload_revision?: boolean;
  publish?: boolean;
};

type Mode = "properties" | "upload" | "publish" | null;
type UploadState = "DRAFT" | "APPROVED";

function distributionPolicy(metadata: Record<string, unknown>): {
  auto_issue_on_publish: boolean;
  audience_mode: string;
  acknowledgement_due_days: number;
} {
  const raw = metadata.distribution_policy;
  const configured = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
  const due = Number(configured.acknowledgement_due_days || 10);
  return {
    auto_issue_on_publish: configured.auto_issue_on_publish !== false,
    audience_mode: String(configured.audience_mode || "ALL_ELIGIBLE_USERS"),
    acknowledgement_due_days: Number.isFinite(due) ? Math.max(1, Math.min(365, due)) : 10,
  };
}

export default function DocumentControlPrimaryActions({ detail, tenant, basePath, onChanged }: { detail: DocumentDetailResponse; tenant: string; basePath: string; onChanged: () => void }) {
  const navigate = useNavigate();
  const capabilities = detail.capabilities as EnhancedCapabilities;
  const workflow = detail.workflows[0];
  const canEdit = Boolean(capabilities.edit_properties ?? capabilities.control);
  const canUpload = Boolean(capabilities.upload_revision ?? capabilities.control);
  const canPublish = Boolean(capabilities.publish ?? capabilities.approve);
  const publishReady = canPublish && workflow?.state === "SCHEDULED_FOR_EFFECTIVITY";
  const [mode, setMode] = useState<Mode>(null);

  if (!canEdit && !canUpload && !canPublish) return null;

  return <>
    {canEdit ? <button type="button" className="dc-button" onClick={() => setMode("properties")}><Pencil size={14} /> Edit properties</button> : null}
    {canUpload ? <button type="button" className="dc-button" onClick={() => setMode("upload")}><FileUp size={14} /> Upload revision</button> : null}
    {canPublish ? publishReady
      ? <button type="button" className="dc-button dc-button--primary" onClick={() => setMode("publish")}><Rocket size={14} /> Publish revision</button>
      : <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${detail.document.id}?view=workflow`)}><Rocket size={14} /> Continue approval</button> : null}

    {mode === "properties" ? <PropertiesDialog detail={detail} tenant={tenant} onClose={() => setMode(null)} onChanged={onChanged} /> : null}
    {mode === "upload" ? <RevisionUploadDialog detail={detail} tenant={tenant} onClose={() => setMode(null)} onChanged={onChanged} /> : null}
    {mode === "publish" && workflow ? <PublishDialog detail={detail} tenant={tenant} onClose={() => setMode(null)} onChanged={onChanged} /> : null}
  </>;
}

function DialogShell({ title, description, busy, onClose, children }: { title: string; description: string; busy: boolean; onClose: () => void; children: ReactNode }) {
  return <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><section className="publications-upload-dialog" role="dialog" aria-modal="true" aria-label={title}>
    <header><div><h2>{title}</h2><p>{description}</p></div><button type="button" onClick={onClose} disabled={busy} aria-label="Close"><X size={18} /></button></header>{children}
  </section></div>;
}

function PropertiesDialog({ detail, tenant, onClose, onChanged }: { detail: DocumentDetailResponse; tenant: string; onClose: () => void; onChanged: () => void }) {
  const { document } = detail;
  const policy = distributionPolicy(document.profile.metadata);
  const [title, setTitle] = useState(document.title);
  const [code, setCode] = useState(document.code);
  const [manualType, setManualType] = useState(document.manual_type);
  const [ownerRole, setOwnerRole] = useState(document.owner_role);
  const [documentClass, setDocumentClass] = useState(document.profile.document_class);
  const [ownerDepartment, setOwnerDepartment] = useState(document.profile.owner_department);
  const [language, setLanguage] = useState(document.profile.language);
  const [criticality, setCriticality] = useState(document.profile.criticality);
  const [reviewInterval, setReviewInterval] = useState(String(document.profile.review_interval_months));
  const [nextReview, setNextReview] = useState(document.profile.next_review_due || "");
  const [regulated, setRegulated] = useState(document.profile.regulated_flag);
  const [restricted, setRestricted] = useState(document.profile.restricted_flag);
  const [authority, setAuthority] = useState(document.profile.requires_authority_approval);
  const [ackRequired, setAckRequired] = useState(document.profile.acknowledgement_required);
  const [autoIssue, setAutoIssue] = useState(policy.auto_issue_on_publish);
  const [ackDueDays, setAckDueDays] = useState(String(policy.acknowledgement_due_days));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await updateDocumentMetadata(tenant, document.id, { title, code, manual_type: manualType, owner_role: ownerRole });
      await upsertDocumentProfile(tenant, document.id, {
        document_class: documentClass, owner_department: ownerDepartment, owner_user_id: document.profile.owner_user_id,
        language, criticality, regulated_flag: regulated, restricted_flag: restricted,
        requires_authority_approval: authority, acknowledgement_required: ackRequired,
        review_interval_months: Number(reviewInterval), next_review_due: nextReview || null,
        access_scope: document.profile.access_scope, tags: document.profile.tags,
        metadata: { ...document.profile.metadata, distribution_policy: { auto_issue_on_publish: autoIssue, audience_mode: "ALL_ELIGIBLE_USERS", acknowledgement_due_days: Math.max(1, Math.min(365, Number(ackDueDays) || 10)) } },
        expected_version: document.profile.version || undefined,
      });
      onChanged(); onClose();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Document properties could not be saved."); }
    finally { setBusy(false); }
  };

  return <DialogShell title="Edit controlled document properties" description="Changes are tenant-scoped, audited, and do not alter immutable published revision content." busy={busy} onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <label><span>Document code</span><input value={code} onChange={(event) => setCode(event.target.value)} required /></label>
    <label><span>Document class</span><select value={documentClass} onChange={(event) => setDocumentClass(event.target.value as typeof documentClass)}><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External technical data</option><option value="RECORD">Record or evidence</option></select></label>
    <label className="wide"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
    <label><span>Publication type</span><input value={manualType} onChange={(event) => setManualType(event.target.value)} required /></label>
    <label><span>Owner role</span><input value={ownerRole} onChange={(event) => setOwnerRole(event.target.value)} required /></label>
    <label><span>Owner department</span><input value={ownerDepartment} onChange={(event) => setOwnerDepartment(event.target.value)} required /></label>
    <label><span>Language</span><input value={language} onChange={(event) => setLanguage(event.target.value)} required /></label>
    <label><span>Criticality</span><select value={criticality} onChange={(event) => setCriticality(event.target.value as typeof criticality)}><option value="STANDARD">Standard</option><option value="IMPORTANT">Important</option><option value="CRITICAL">Critical</option></select></label>
    <label><span>Review interval (months)</span><input type="number" min={1} max={120} value={reviewInterval} onChange={(event) => setReviewInterval(event.target.value)} required /></label>
    <label><span>Next review due</span><input type="date" value={nextReview} onChange={(event) => setNextReview(event.target.value)} /></label>
    <label><span><input type="checkbox" checked={regulated} onChange={(event) => setRegulated(event.target.checked)} /> Regulated document</span></label>
    <label><span><input type="checkbox" checked={restricted} onChange={(event) => setRestricted(event.target.checked)} /> Restricted access</span></label>
    <label><span><input type="checkbox" checked={authority} onChange={(event) => setAuthority(event.target.checked)} /> Authority approval required</span></label>
    <label><span><input type="checkbox" checked={ackRequired} onChange={(event) => setAckRequired(event.target.checked)} /> Read-and-understand acknowledgement required</span></label>
    <label><span><input type="checkbox" checked={autoIssue} onChange={(event) => setAutoIssue(event.target.checked)} /> Notify all eligible active users automatically on publish</span></label>
    <label><span>Acknowledgement due (days)</span><input type="number" min={1} max={365} value={ackDueDays} onChange={(event) => setAckDueDays(event.target.value)} required /></label>
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy}>{busy ? "Saving…" : "Save properties"}</button></div>
  </form></DialogShell>;
}

function RevisionUploadDialog({ detail, tenant, onClose, onChanged }: { detail: DocumentDetailResponse; tenant: string; onClose: () => void; onChanged: () => void }) {
  const latest = detail.document.latest_revision;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PublicationUploadPreview | null>(null);
  const [issue, setIssue] = useState(latest?.issue_number || "00");
  const [revision, setRevision] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>("DRAFT");
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [approvalReference, setApprovalReference] = useState("");
  const [approvalDate, setApprovalDate] = useState("");
  const [ackRequired, setAckRequired] = useState(detail.document.profile.acknowledgement_required);
  const [notifyUsers, setNotifyUsers] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const inspect = async (selected: File | null) => {
    setFile(selected); setPreview(null); if (!selected) return;
    setBusy(true); setError("");
    try {
      const result = await previewPublicationUpload(tenant, selected);
      setPreview(result); setIssue(result.metadata.issue_number || latest?.issue_number || "00");
      setRevision(result.metadata.revision_number || ""); setEffectiveDate(result.metadata.effective_date || "");
      if (result.source_type !== "PDF") setUploadState("DRAFT");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The revision source could not be inspected."); }
    finally { setBusy(false); }
  };

  const approvedValid = uploadState !== "APPROVED" || Boolean(preview?.source_type === "PDF" && authorityName.trim() && approvalReference.trim() && approvalDate && changeNote.trim());

  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!file || !approvedValid) return;
    setBusy(true); setError("");
    try {
      const result = await uploadPublicationRevision(tenant, {
        code: detail.document.code, title: detail.document.title, rev_number: revision.trim(), issue_number: issue.trim(),
        effective_date: effectiveDate || undefined, manual_type: detail.document.manual_type, owner_role: detail.document.owner_role,
        change_log: changeNote.trim() || undefined, file,
      });
      if (uploadState === "APPROVED") {
        await approvePublicationIntake(tenant, result.manual_id, result.revision_id, {
          authority_name: authorityName.trim(), approval_reference: approvalReference.trim(), approval_date: approvalDate,
          effective_date: effectiveDate || null, comments: changeNote.trim(), acknowledgement_required: ackRequired,
          notify_eligible_users: notifyUsers,
        });
      }
      onChanged(); onClose();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The controlled revision could not be uploaded."); }
    finally { setBusy(false); }
  };

  return <DialogShell title="Upload a controlled revision" description="Create a working draft, or register the exact final PDF when an authority approval already exists." busy={busy} onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <label className="wide"><span>PDF or DOCX source</span><input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void inspect(event.target.files?.[0] || null)} required /></label>
    <label><span>Intake state</span><select value={uploadState} onChange={(event) => setUploadState(event.target.value as UploadState)}><option value="DRAFT">Uncontrolled draft</option><option value="APPROVED" disabled={preview?.source_type !== "PDF"}>Already approved final PDF</option></select></label>
    <label><span>Issue</span><input value={issue} onChange={(event) => setIssue(event.target.value)} required /></label>
    <label><span>Revision</span><input value={revision} onChange={(event) => setRevision(event.target.value)} required /></label>
    <label><span>{uploadState === "APPROVED" ? "Effective date" : "Proposed effective date"}</span><input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></label>
    {uploadState === "APPROVED" ? <>
      <label><span>Approving authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label>
      <label><span>Approval reference</span><input value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} required /></label>
      <label><span>Approval date</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={approvalDate} onChange={(event) => setApprovalDate(event.target.value)} required /></label>
      <label><span><input type="checkbox" checked={ackRequired} onChange={(event) => setAckRequired(event.target.checked)} /> Require read-and-understand acknowledgement</span></label>
      <label><span><input type="checkbox" checked={notifyUsers} onChange={(event) => setNotifyUsers(event.target.checked)} /> Distribute and notify eligible users now</span></label>
    </> : null}
    <label className="wide"><span>{uploadState === "APPROVED" ? "Approval basis and verification note" : "Change summary"}</span><textarea value={changeNote} onChange={(event) => setChangeNote(event.target.value)} required /></label>
    {preview ? <div className="dc-callout"><FileUp size={17} /><div><strong>{preview.filename}</strong><div>{preview.source_type}{preview.page_count ? ` · ${preview.page_count} pages` : ""} · {preview.paragraph_count} extracted paragraphs</div></div></div> : null}
    {uploadState === "APPROVED" ? <div className="dc-callout"><ShieldCheck size={17} /><div><strong>Exact PDF preservation</strong><div>The source is checksum-locked and the authority decision is retained as controlled evidence.</div></div></div> : null}
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !file || !revision.trim() || !changeNote.trim() || !approvedValid}>{busy ? "Recording…" : uploadState === "APPROVED" ? "Register approved publication" : "Create draft revision"}</button></div>
  </form></DialogShell>;
}

function PublishDialog({ detail, tenant, onClose, onChanged }: { detail: DocumentDetailResponse; tenant: string; onClose: () => void; onChanged: () => void }) {
  const workflow = detail.workflows[0];
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!workflow) return;
    setBusy(true); setError("");
    try {
      await transitionDocumentWorkflow(tenant, workflow.id, { action: "PUBLISH", comments: comments.trim(), evidence, expected_version: workflow.version });
      onChanged(); onClose();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Publication could not be completed."); }
    finally { setBusy(false); }
  };

  return <DialogShell title="Publish controlled revision" description="Publication is immutable. Eligible users will be notified automatically and acknowledgement tasks will be created when required." busy={busy} onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <div className="dc-callout"><Rocket size={17} /><div><strong>{detail.document.code} · Rev {detail.document.latest_revision?.revision_number}</strong><div>Workflow state: {workflow?.state || "Unavailable"} · Effectivity: {workflow?.effective_at || "Immediate"}</div></div></div>
    <label className="wide"><span>Publication decision and release basis</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} required /></label>
    <DocumentEvidencePicker
      tenant={tenant}
      manualId={detail.document.id}
      revisionId={detail.document.latest_revision?.id || null}
      category="WORKFLOW"
      purpose="PUBLICATION_RELEASE"
      value={evidence}
      onChange={setEvidence}
      label="Publication evidence"
      help="Upload or select retained supporting evidence. Internal asset IDs are never entered manually."
    />
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !comments.trim() || !evidence.length}>{busy ? "Publishing…" : "Publish and notify users"}</button></div>
  </form></DialogShell>;
}

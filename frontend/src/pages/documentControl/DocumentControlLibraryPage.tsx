import { useCallback, useEffect, useState, type FormEvent } from "react";
import { BookOpen, FilePlus2, Search, ShieldAlert, ShieldCheck, UploadCloud, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  listDocumentControlDocuments,
  type DocumentLibraryItem,
  type DocumentLibraryResponse,
} from "../../services/documentControl";
import { updateDocumentMetadata } from "../../services/documentControlReports";
import {
  approvePublicationIntake,
  prefetchPublicationReader,
  previewPublicationUpload,
  uploadPublicationRevision,
  type ApprovedPublicationIntakePayload,
  type PublicationUploadPreview,
} from "../../services/publications";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";

function statusKind(document: DocumentLibraryItem): "success" | "warning" | "danger" | "neutral" {
  if (document.read_target.kind === "PUBLISHED") return "success";
  if (document.read_target.kind === "UNCONTROLLED") return "warning";
  if (!document.latest_revision) return "danger";
  return "neutral";
}

function fileStem(filename: string): string {
  return filename.replace(/\.(docx|pdf)$/i, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function fallbackCode(filename: string): string {
  return filename.replace(/\.(docx|pdf)$/i, "").toUpperCase().replace(/[^A-Z0-9]+/g, "/").replace(/^\/+|\/+$/g, "").slice(0, 48);
}

function genericOutlineTitle(value?: string | null): boolean {
  const text = String(value || "").trim();
  return !text || /^(chapter|section|part|appendix|annex)\b/i.test(text) || /front\s+matter/i.test(text) || /^table\s+of\s+contents$/i.test(text);
}

type IntakeMode = "DRAFT" | "APPROVED";

type IntakeState = {
  file: File | null;
  preview: PublicationUploadPreview | null;
  code: string;
  title: string;
  manualType: string;
  ownerRole: string;
  issue: string;
  revision: string;
  effectiveDate: string;
  changeNote: string;
  mode: IntakeMode;
  authorityName: string;
  approvalReference: string;
  approvalDate: string;
  acknowledgementRequired: boolean;
  notifyUsers: boolean;
};

const EMPTY_INTAKE: IntakeState = {
  file: null,
  preview: null,
  code: "",
  title: "",
  manualType: "GENERAL",
  ownerRole: "DOCUMENT_CONTROL",
  issue: "00",
  revision: "00",
  effectiveDate: "",
  changeNote: "",
  mode: "DRAFT",
  authorityName: "Kenya Civil Aviation Authority",
  approvalReference: "",
  approvalDate: "",
  acknowledgementRequired: true,
  notifyUsers: true,
};

function approvalPayload(values: {
  authorityName: string;
  approvalReference: string;
  approvalDate: string;
  effectiveDate?: string;
  comments: string;
  acknowledgementRequired: boolean;
  notifyUsers: boolean;
}): ApprovedPublicationIntakePayload {
  return {
    authority_name: values.authorityName.trim(),
    approval_reference: values.approvalReference.trim(),
    approval_date: values.approvalDate,
    effective_date: values.effectiveDate || null,
    comments: values.comments.trim(),
    acknowledgement_required: values.acknowledgementRequired,
    notify_eligible_users: values.notifyUsers,
  };
}

export default function DocumentControlLibraryPage() {
  const navigate = useNavigate();
  const { tenant, basePath, readerBasePath } = useDocumentControlRoute();
  const [response, setResponse] = useState<DocumentLibraryResponse | null>(null);
  const [query, setQuery] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [canControl, setCanControl] = useState(false);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intake, setIntake] = useState<IntakeState>(EMPTY_INTAKE);
  const [intakeBusy, setIntakeBusy] = useState(false);
  const [intakeError, setIntakeError] = useState("");
  const [approvalDocument, setApprovalDocument] = useState<DocumentLibraryItem | null>(null);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      const [library, dashboard] = await Promise.all([
        listDocumentControlDocuments(tenant, { q: query.trim() || undefined, documentClass: classFilter || undefined, perPage: 100 }),
        getDocumentControlDashboard(tenant),
      ]);
      setResponse(library);
      setCanControl(Boolean(dashboard.capabilities.control));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document library could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [classFilter, query, tenant]);

  useEffect(() => {
    const handle = window.setTimeout(() => void load(), query ? 260 : 0);
    return () => window.clearTimeout(handle);
  }, [load, query]);

  const documents = response?.items || [];

  const warmReader = (document: DocumentLibraryItem) => {
    const revisionId = document.read_target.revision_id || document.latest_revision?.id;
    if (revisionId) prefetchPublicationReader(tenant, document.id, revisionId);
  };

  const openPrimary = (document: DocumentLibraryItem) => {
    if (document.read_target.revision_id) {
      navigate(`${readerBasePath}/${document.id}/rev/${document.read_target.revision_id}/read`);
      return;
    }
    if (canControl) navigate(`${basePath}/library/${document.id}`);
  };

  const inspectFile = async (file: File | null) => {
    if (!file) return;
    setIntakeBusy(true);
    setIntakeError("");
    try {
      const preview = await previewPublicationUpload(tenant, file);
      const detectedTitle = preview.metadata.title || preview.heading;
      setIntake((current) => ({
        ...current,
        file,
        preview,
        code: preview.metadata.part_number || fallbackCode(file.name),
        title: genericOutlineTitle(detectedTitle) ? fileStem(file.name) : String(detectedTitle),
        manualType: preview.metadata.manual_type || "GENERAL",
        issue: preview.metadata.issue_number || "00",
        revision: preview.metadata.revision_number || "00",
        effectiveDate: preview.metadata.effective_date || "",
        mode: preview.source_type === "PDF" ? current.mode : "DRAFT",
      }));
    } catch (caught) {
      setIntakeError(caught instanceof Error ? caught.message : "The source could not be inspected.");
    } finally {
      setIntakeBusy(false);
    }
  };

  const approvedIntakeValid = intake.mode !== "APPROVED" || Boolean(
    intake.preview?.source_type === "PDF" && intake.authorityName.trim() && intake.approvalReference.trim()
    && intake.approvalDate && intake.changeNote.trim(),
  );

  const submitIntake = async () => {
    if (!intake.file || !intake.code.trim() || !intake.title.trim() || !intake.revision.trim() || !approvedIntakeValid) return;
    setIntakeBusy(true);
    setIntakeError("");
    try {
      const result = await uploadPublicationRevision(tenant, {
        code: intake.code.trim(),
        title: intake.title.trim(),
        rev_number: intake.revision.trim(),
        issue_number: intake.issue.trim(),
        effective_date: intake.effectiveDate || undefined,
        manual_type: intake.manualType.trim() || "GENERAL",
        owner_role: intake.ownerRole.trim() || "DOCUMENT_CONTROL",
        change_log: intake.changeNote.trim() || undefined,
        file: intake.file,
      });
      await updateDocumentMetadata(tenant, result.manual_id, {
        code: intake.code.trim(),
        title: intake.title.trim(),
        manual_type: intake.manualType.trim() || "GENERAL",
        owner_role: intake.ownerRole.trim() || "DOCUMENT_CONTROL",
      });
      if (intake.mode === "APPROVED") {
        await approvePublicationIntake(tenant, result.manual_id, result.revision_id, approvalPayload({
          authorityName: intake.authorityName,
          approvalReference: intake.approvalReference,
          approvalDate: intake.approvalDate,
          effectiveDate: intake.effectiveDate,
          comments: intake.changeNote,
          acknowledgementRequired: intake.acknowledgementRequired,
          notifyUsers: intake.notifyUsers,
        }));
      }
      setIntakeOpen(false);
      setIntake(EMPTY_INTAKE);
      await load();
      navigate(`${readerBasePath}/${result.manual_id}/rev/${result.revision_id}/read`);
    } catch (caught) {
      setIntakeError(caught instanceof Error ? caught.message : "The controlled source could not be uploaded.");
    } finally {
      setIntakeBusy(false);
    }
  };

  return (
    <DocumentControlShell
      title="Library"
      subtitle="One searchable register for internal manuals, external technical data, and controlled records. Select a row to open the permitted revision directly."
      canControl={canControl}
      actions={canControl ? <button type="button" className="dc-button dc-button--primary" onClick={() => setIntakeOpen(true)}><FilePlus2 size={15} /> Register or upload</button> : undefined}
    >
      <div className="dc-toolbar">
        <label className="dc-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, title, category, or status" /></label>
        <label className="dc-search" style={{ minWidth: "12rem" }}><select value={classFilter} onChange={(event) => setClassFilter(event.target.value)} aria-label="Document class"><option value="">All document classes</option><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External technical data</option><option value="RECORD">Records and evidence</option></select></label>
      </div>

      {loading ? <DocumentControlLoading label="Loading the controlled library…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && documents.length ? (
        <div className="dc-table-wrap"><table className="dc-table">
          <thead><tr><th>Code</th><th>Document</th><th>Revision available</th><th>Governance</th>{canControl ? <th>Work</th> : null}<th>Action</th></tr></thead>
          <tbody>{documents.map((document) => {
            const canMarkApproved = canControl && document.read_target.kind !== "PUBLISHED" && document.latest_revision?.source_type?.toUpperCase() === "PDF";
            return <tr key={document.id} className="dc-row--clickable" tabIndex={0} onMouseEnter={() => warmReader(document)} onFocus={() => warmReader(document)} onClick={() => openPrimary(document)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") openPrimary(document); }}>
              <td><strong>{document.code}</strong><small>{document.profile.document_class.replaceAll("_", " ")}</small></td>
              <td><strong>{document.title}</strong><small>{document.manual_type} · {document.profile.owner_department}</small></td>
              <td><strong>{document.latest_revision ? `Issue ${document.latest_revision.issue_number || "—"} · Rev ${document.latest_revision.revision_number}` : "No revision uploaded"}</strong><small>{document.latest_revision?.source_type || "No source"}{document.latest_revision?.source_page_count ? ` · ${document.latest_revision.source_page_count} pages` : ""}</small></td>
              <td><DocumentControlStatus status={document.read_target.kind === "PUBLISHED" ? "Effective publication" : document.read_target.kind === "UNCONTROLLED" ? "Uncontrolled draft" : document.latest_revision?.status || "No revision"} kind={statusKind(document)} /><small>{document.profile.regulated_flag ? "Regulated" : "Internal control"}{document.profile.restricted_flag ? " · Restricted" : ""}</small></td>
              {canControl ? <td><strong>{document.open_change_requests} changes</strong><small>{document.pending_acknowledgements} acknowledgements pending</small>{canMarkApproved ? <button type="button" className="dc-button" style={{ marginTop: "0.35rem" }} onClick={(event) => { event.stopPropagation(); setApprovalDocument(document); }}><ShieldCheck size={14} /> Record existing approval</button> : null}</td> : null}
              <td><button type="button" className="dc-button dc-button--primary" disabled={!document.read_target.revision_id && !canControl} onClick={(event) => { event.stopPropagation(); openPrimary(document); }}><BookOpen size={14} /> {document.read_target.label}</button>{canControl ? <button type="button" className="dc-button" style={{ marginTop: "0.35rem" }} onClick={(event) => { event.stopPropagation(); navigate(`${basePath}/library/${document.id}`); }}>View control record</button> : null}</td>
            </tr>;
          })}</tbody>
        </table></div>
      ) : null}

      {!loading && !error && !documents.length ? <DocumentControlEmpty icon={query || classFilter ? Search : ShieldAlert} title={query || classFilter ? "No document matches the current search" : "No document has been registered"} message={query || classFilter ? "Clear the search or select another document class." : canControl ? "Upload or register the first document before it can be governed or read." : "No effective publication is currently available within your access scope."} action={(query || classFilter) ? <button type="button" className="dc-button" onClick={() => { setQuery(""); setClassFilter(""); }}>Clear filters</button> : canControl ? <button type="button" className="dc-button dc-button--primary" onClick={() => setIntakeOpen(true)}>Register first document</button> : undefined} /> : null}

      {intakeOpen ? <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !intakeBusy) setIntakeOpen(false); }}>
        <section className="publications-upload-dialog" role="dialog" aria-modal="true" aria-label="Register controlled document">
          <header><div><h2>Register controlled document</h2><p>Upload a working draft or register a final PDF that already carries an external approval.</p></div><button type="button" onClick={() => setIntakeOpen(false)} disabled={intakeBusy} aria-label="Close"><X size={18} /></button></header>
          <div className="publications-file-picker"><UploadCloud size={22} /><div><strong>Choose a PDF or DOCX source</strong><span>Final approved intake requires the exact PDF so signatures, figures, annotations, and approval marks remain unchanged.</span></div><input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void inspectFile(event.target.files?.[0] || null)} /></div>
          {intakeBusy && !intake.preview ? <DocumentControlLoading label="Inspecting document structure and metadata…" /> : null}
          {intake.file ? <div className="dc-form">
            <label><span>Intake state</span><select value={intake.mode} onChange={(event) => setIntake({ ...intake, mode: event.target.value as IntakeMode })}><option value="DRAFT">Uncontrolled draft — enter workflow</option><option value="APPROVED" disabled={intake.preview?.source_type !== "PDF"}>Already approved final PDF</option></select></label>
            <label><span>Document code</span><input value={intake.code} onChange={(event) => setIntake({ ...intake, code: event.target.value })} required /></label>
            <label className="wide"><span>Document title</span><input value={intake.title} onChange={(event) => setIntake({ ...intake, title: event.target.value })} required /></label>
            <label><span>Document type</span><input value={intake.manualType} onChange={(event) => setIntake({ ...intake, manualType: event.target.value })} required /></label>
            <label><span>Issue</span><input value={intake.issue} onChange={(event) => setIntake({ ...intake, issue: event.target.value })} /></label>
            <label><span>Revision</span><input value={intake.revision} onChange={(event) => setIntake({ ...intake, revision: event.target.value })} required /></label>
            <label><span>Owner</span><input value={intake.ownerRole} onChange={(event) => setIntake({ ...intake, ownerRole: event.target.value })} /></label>
            <label><span>{intake.mode === "APPROVED" ? "Effective date" : "Proposed effective date"}</span><input type="date" value={intake.effectiveDate} onChange={(event) => setIntake({ ...intake, effectiveDate: event.target.value })} /></label>
            {intake.mode === "APPROVED" ? <>
              <label><span>Approving authority</span><input value={intake.authorityName} onChange={(event) => setIntake({ ...intake, authorityName: event.target.value })} required /></label>
              <label><span>Approval reference</span><input value={intake.approvalReference} onChange={(event) => setIntake({ ...intake, approvalReference: event.target.value })} required /></label>
              <label><span>Approval date</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={intake.approvalDate} onChange={(event) => setIntake({ ...intake, approvalDate: event.target.value })} required /></label>
              <label><span><input type="checkbox" checked={intake.acknowledgementRequired} onChange={(event) => setIntake({ ...intake, acknowledgementRequired: event.target.checked })} /> Read-and-understand acknowledgement required</span></label>
              <label><span><input type="checkbox" checked={intake.notifyUsers} onChange={(event) => setIntake({ ...intake, notifyUsers: event.target.checked })} /> Notify and distribute to eligible active users now</span></label>
            </> : null}
            <label className="wide"><span>{intake.mode === "APPROVED" ? "Approval basis and verification note" : "Intake or change note"}</span><textarea value={intake.changeNote} onChange={(event) => setIntake({ ...intake, changeNote: event.target.value })} required={intake.mode === "APPROVED"} /></label>
            {intake.preview ? <label className="wide"><span>Detected structure</span><div className="dc-callout">{intake.preview.source_type} · {intake.preview.page_count || "—"} pages · {intake.preview.outline.length} outline entries · {intake.preview.paragraph_count} extracted paragraphs</div></label> : null}
            {intake.mode === "APPROVED" ? <div className="dc-callout"><ShieldCheck size={17} /><div><strong>Governed shortcut, not a bypass.</strong><div>The final PDF is checksum-locked, the authority decision is retained as evidence, and distribution is audited.</div></div></div> : null}
            {intakeError ? <div className="dc-form__error">{intakeError}</div> : null}
          </div> : intakeError ? <div className="dc-error">{intakeError}</div> : null}
          <footer><span>{intake.file?.name || "No source selected"}</span><div><button type="button" onClick={() => setIntakeOpen(false)} disabled={intakeBusy}>Cancel</button><button type="button" className="primary" onClick={() => void submitIntake()} disabled={intakeBusy || !intake.file || !intake.code.trim() || !intake.title.trim() || !intake.revision.trim() || !approvedIntakeValid}><UploadCloud size={16} /> {intakeBusy ? "Recording…" : intake.mode === "APPROVED" ? "Register approved publication" : "Register draft revision"}</button></div></footer>
        </section>
      </div> : null}

      {approvalDocument?.latest_revision ? <ExistingApprovalDialog tenant={tenant} document={approvalDocument} busy={intakeBusy} setBusy={setIntakeBusy} onClose={() => setApprovalDocument(null)} onComplete={async () => { setApprovalDocument(null); await load(); }} /> : null}
    </DocumentControlShell>
  );
}

function ExistingApprovalDialog({ tenant, document, busy, setBusy, onClose, onComplete }: { tenant: string; document: DocumentLibraryItem; busy: boolean; setBusy: (value: boolean) => void; onClose: () => void; onComplete: () => Promise<void> }) {
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [reference, setReference] = useState("");
  const [approvalDate, setApprovalDate] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(document.latest_revision?.effective_date || "");
  const [comments, setComments] = useState("");
  const [acknowledgementRequired, setAcknowledgementRequired] = useState(document.profile.acknowledgement_required);
  const [notifyUsers, setNotifyUsers] = useState(true);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!document.latest_revision) return;
    setBusy(true);
    setError("");
    try {
      await approvePublicationIntake(tenant, document.id, document.latest_revision.id, approvalPayload({ authorityName, approvalReference: reference, approvalDate, effectiveDate, comments, acknowledgementRequired, notifyUsers }));
      await onComplete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The existing approval could not be recorded.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><section className="publications-upload-dialog" role="dialog" aria-modal="true" aria-label="Record existing approval">
    <header><div><h2>Record existing authority approval</h2><p>{document.code} · {document.title} · Rev {document.latest_revision?.revision_number}</p></div><button type="button" onClick={onClose} disabled={busy} aria-label="Close"><X size={18} /></button></header>
    <form className="dc-form" onSubmit={submit}>
      <label><span>Approving authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label>
      <label><span>Approval reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label>
      <label><span>Approval date</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={approvalDate} onChange={(event) => setApprovalDate(event.target.value)} required /></label>
      <label><span>Effective date</span><input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></label>
      <label className="wide"><span>Verification note</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} required /></label>
      <label><span><input type="checkbox" checked={acknowledgementRequired} onChange={(event) => setAcknowledgementRequired(event.target.checked)} /> Require acknowledgement</span></label>
      <label><span><input type="checkbox" checked={notifyUsers} onChange={(event) => setNotifyUsers(event.target.checked)} /> Notify eligible users now</span></label>
      {error ? <div className="dc-form__error">{error}</div> : null}
      <div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !reference.trim() || !approvalDate || !comments.trim()}><ShieldCheck size={15} /> {busy ? "Recording…" : "Mark approved and publish"}</button></div>
    </form>
  </section></div>;
}

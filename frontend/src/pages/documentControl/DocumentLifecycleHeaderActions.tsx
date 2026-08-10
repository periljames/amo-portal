import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Archive, FilePlus2, FileSearch2, Tags, Trash2, UploadCloud, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlDocument,
  transitionDocumentWorkflow,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import {
  deleteDocument,
  DOCUMENT_TYPES,
  getDocumentType,
  updateDocumentType,
  type DocumentType,
  type DocumentTypeResponse,
} from "../../services/documentLifecycle";
import {
  previewPublicationUpload,
  uploadPublicationRevision,
  type PublicationUploadPreview,
} from "../../services/publications";
import "./documentLifecycleActions.css";

const TYPE_LABELS: Record<DocumentType, string> = {
  MANUAL: "Manual",
  POLICY: "Policy",
  PROCEDURE: "Procedure / SOP",
  WORK_INSTRUCTION: "Work instruction",
  FORM: "Form / template",
  CHECKLIST: "Checklist",
  REGISTER: "Register / log",
  EXTERNAL_DOCUMENT: "External controlled document",
};

type Detection = {
  type: DocumentType;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reason: string;
};

function clean(value?: string | null): string {
  return String(value || "").replaceAll("_", " ").trim();
}

function detectionText(file: File, preview: PublicationUploadPreview): string {
  return [
    file.name,
    preview.heading,
    preview.excerpt,
    preview.metadata.title,
    preview.metadata.manual_type,
    preview.metadata.part_number,
    ...preview.sample.slice(0, 8),
  ].filter(Boolean).join(" \n ").toUpperCase().replaceAll("_", " ");
}

function detectDocumentType(file: File, preview: PublicationUploadPreview): Detection {
  const text = ` ${detectionText(file, preview)} `;
  const filename = file.name.toUpperCase().replaceAll("_", " ");
  const has = (...patterns: RegExp[]) => patterns.some((pattern) => pattern.test(text));

  if (has(/\bCHECK[ -]?LIST\b/, /\bINSPECTION CHECKLIST\b/, /\bCHK\b/)) {
    return { type: "CHECKLIST", confidence: "HIGH", reason: "Checklist wording was found in the source metadata or content." };
  }
  if (has(/\bWORK INSTRUCTION\b/, /\bQUALITY WORK INSTRUCTION\b/, /\bQWI[- .]/, /\bWI[- .]\d/)) {
    return { type: "WORK_INSTRUCTION", confidence: "HIGH", reason: "Work-instruction identifiers were found in the source." };
  }
  if (has(/\bSTANDARD OPERATING PROCEDURE\b/, /\bPROCEDURE\b/, /\bSOP[- .]/, /\bPROC(?:EDURE)?[- .]/)) {
    return { type: "PROCEDURE", confidence: "HIGH", reason: "Procedure or SOP wording was found in the source." };
  }
  if (has(/\bREGISTER\b/, /\bMASTER LOG\b/, /\bCONTROL LOG\b/) || /\bREGISTER\b/.test(filename)) {
    return { type: "REGISTER", confidence: "HIGH", reason: "Register or controlled-log wording was found in the source." };
  }
  if (has(/\bFORM\b/, /\bTEMPLATE\b/, /\bFRM[- .]/) || /(?:^|[-_. ])FORM(?:[-_. ]|$)/.test(filename)) {
    return { type: "FORM", confidence: "MEDIUM", reason: "Form or template wording was found; confirm before upload." };
  }
  if (has(/\bPOLICY\b/)) {
    return { type: "POLICY", confidence: "HIGH", reason: "Policy wording was found in the source." };
  }
  if (has(
    /\bAIRWORTHINESS DIRECTIVE\b/,
    /\bSERVICE BULLETIN\b/,
    /\bKENYA GAZETTE\b/,
    /\bCIVIL AVIATION REGULATION/,
    /\bREGULATORY NOTICE\b/,
  )) {
    return { type: "EXTERNAL_DOCUMENT", confidence: "MEDIUM", reason: "The source resembles externally issued regulatory or technical data." };
  }
  if (has(/\bMANUAL\b/, /\bHANDBOOK\b/)) {
    return { type: "MANUAL", confidence: "HIGH", reason: "Manual or handbook wording was found in the source." };
  }
  return { type: "MANUAL", confidence: "LOW", reason: "No reliable structural document-type marker was found. Confirm the type manually." };
}

function Modal({ title, description, busy, onClose, children }: {
  title: string;
  description: string;
  busy: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return <div className="dclife-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}>
    <section className="dclife-dialog" role="dialog" aria-modal="true" aria-label={title}>
      <header>
        <div><h2>{title}</h2><p>{description}</p></div>
        <button type="button" aria-label="Close" onClick={onClose} disabled={busy}><X size={18} /></button>
      </header>
      {children}
    </section>
  </div>;
}

function TypeSelect({ value, onChange, id }: { value: DocumentType; onChange: (value: DocumentType) => void; id?: string }) {
  return <select id={id} value={value} onChange={(event) => onChange(event.target.value as DocumentType)}>
    {DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{TYPE_LABELS[type]}</option>)}
  </select>;
}

export default function DocumentLifecycleHeaderActions({ tenant, basePath, manualId }: {
  tenant: string;
  basePath: string;
  manualId?: string;
}) {
  const [mode, setMode] = useState<"add" | "type" | "delete" | null>(null);

  return <>
    <button type="button" className="dc-button dc-button--primary" onClick={() => setMode("add")} data-testid="add-document-button">
      <FilePlus2 size={14} /> Add document
    </button>
    {manualId ? <>
      <button type="button" className="dc-button" onClick={() => setMode("type")} data-testid="change-document-type-button">
        <Tags size={14} /> Change type
      </button>
      <button type="button" className="dc-button dc-button--danger" onClick={() => setMode("delete")} data-testid="delete-document-button">
        <Trash2 size={14} /> Delete document
      </button>
    </> : null}

    {mode === "add" ? <AddDocumentDialog tenant={tenant} basePath={basePath} onClose={() => setMode(null)} /> : null}
    {mode === "type" && manualId ? <ChangeTypeDialog tenant={tenant} manualId={manualId} onClose={() => setMode(null)} /> : null}
    {mode === "delete" && manualId ? <DeleteDocumentDialog tenant={tenant} basePath={basePath} manualId={manualId} onClose={() => setMode(null)} /> : null}
  </>;
}

function AddDocumentDialog({ tenant, basePath, onClose }: { tenant: string; basePath: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PublicationUploadPreview | null>(null);
  const [detection, setDetection] = useState<Detection | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("MANUAL");
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [issue, setIssue] = useState("00");
  const [revision, setRevision] = useState("0");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [ownerRole, setOwnerRole] = useState("Document Control");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const inspect = async (selected: File | null) => {
    setFile(selected);
    setPreview(null);
    setDetection(null);
    setError("");
    if (!selected) return;
    setBusy(true);
    try {
      const next = await previewPublicationUpload(tenant, selected);
      const detected = detectDocumentType(selected, next);
      setPreview(next);
      setDetection(detected);
      setDocumentType(detected.type);
      if (!code.trim() && next.metadata.part_number) setCode(clean(next.metadata.part_number));
      if (!title.trim()) setTitle(clean(next.metadata.title) || clean(next.heading) || selected.name.replace(/\.(pdf|docx)$/i, ""));
      if (next.metadata.issue_number) setIssue(clean(next.metadata.issue_number));
      if (next.metadata.revision_number) setRevision(clean(next.metadata.revision_number));
      if (next.metadata.effective_date) setEffectiveDate(clean(next.metadata.effective_date).slice(0, 10));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document could not be inspected.");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !preview) return;
    setBusy(true);
    setError("");
    try {
      const uploaded = await uploadPublicationRevision(tenant, {
        code: code.trim(),
        title: title.trim(),
        rev_number: revision.trim(),
        issue_number: issue.trim(),
        effective_date: effectiveDate || undefined,
        manual_type: preview.metadata.manual_type || "GENERAL",
        owner_role: ownerRole.trim() || "Document Control",
        change_log: "Initial controlled document intake",
        file,
      });
      await updateDocumentType(tenant, uploaded.manual_id, documentType);
      onClose();
      navigate(`${basePath}/library/${uploaded.manual_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document could not be added.");
    } finally {
      setBusy(false);
    }
  };

  return <Modal title="Add controlled document" description="Upload the first PDF or DOCX revision. The portal inspects the source, proposes a document type, and always lets you override it before saving." busy={busy} onClose={onClose}>
    <form className="dclife-form" onSubmit={submit}>
      <label className="wide"><span>Source document</span><input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void inspect(event.target.files?.[0] || null)} required /></label>
      {preview ? <div className="dclife-detection wide" data-confidence={detection?.confidence || "LOW"}>
        <FileSearch2 size={18} />
        <div><strong>Detected as {TYPE_LABELS[detection?.type || "MANUAL"]} · {detection?.confidence.toLowerCase()} confidence</strong><span>{detection?.reason}</span><small>Detection is advisory. Your selection below is authoritative.</small></div>
      </div> : null}
      <label><span>Document type</span><TypeSelect value={documentType} onChange={setDocumentType} /></label>
      <label><span>Document code</span><input value={code} onChange={(event) => setCode(event.target.value)} placeholder="e.g. QWI-014" required /></label>
      <label className="wide"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label><span>Issue</span><input value={issue} onChange={(event) => setIssue(event.target.value)} required /></label>
      <label><span>Revision</span><input value={revision} onChange={(event) => setRevision(event.target.value)} required /></label>
      <label><span>Effective date</span><input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></label>
      <label><span>Owner / controller role</span><input value={ownerRole} onChange={(event) => setOwnerRole(event.target.value)} required /></label>
      {preview?.metadata.manual_type ? <div className="dclife-note wide"><strong>Detected publication family:</strong> {clean(preview.metadata.manual_type)}. This is retained separately from the DMS document type.</div> : null}
      {error ? <div className="dc-form__error wide" role="alert">{error}</div> : null}
      <div className="dclife-actions wide"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !file || !preview}>{busy ? "Saving…" : <><UploadCloud size={14} /> Add document</>}</button></div>
    </form>
  </Modal>;
}

function ChangeTypeDialog({ tenant, manualId, onClose }: { tenant: string; manualId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [state, setState] = useState<DocumentTypeResponse | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("MANUAL");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setBusy(true);
    void getDocumentType(tenant, manualId).then((result) => {
      if (!active) return;
      setState(result);
      setDocumentType(result.document_type);
      setError("");
    }).catch((caught) => {
      if (active) setError(caught instanceof Error ? caught.message : "The current document type could not be loaded.");
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [manualId, tenant]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await updateDocumentType(tenant, manualId, documentType);
      onClose();
      navigate(0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document type could not be changed.");
    } finally {
      setBusy(false);
    }
  };

  return <Modal title="Change document type" description="The selected type controls DMS category, hierarchy placement, filters and downstream document behavior." busy={busy} onClose={onClose}>
    <form className="dclife-form" onSubmit={submit}>
      {state ? <div className="dclife-note wide"><strong>Current type:</strong> {TYPE_LABELS[state.document_type]} · source: {state.source.toLowerCase()}{state.publication_family ? <> · publication family: {clean(state.publication_family)}</> : null}</div> : null}
      <label className="wide"><span>Document type</span><TypeSelect value={documentType} onChange={setDocumentType} /></label>
      <div className="dclife-note wide">This is a controlled metadata change. It does not rewrite immutable published revision content.</div>
      {error ? <div className="dc-form__error wide" role="alert">{error}</div> : null}
      <div className="dclife-actions wide"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy}>{busy ? "Saving…" : "Save document type"}</button></div>
    </form>
  </Modal>;
}

function DeleteDocumentDialog({ tenant, basePath, manualId, onClose }: { tenant: string; basePath: string; manualId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setBusy(true);
    void getDocumentControlDocument(tenant, manualId).then((result) => {
      if (active) { setDetail(result); setError(""); }
    }).catch((caught) => {
      if (active) setError(caught instanceof Error ? caught.message : "The document could not be loaded.");
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [manualId, tenant]);

  const controlledHistory = useMemo(() => Boolean(detail && (
    detail.document.current_published_revision_id ||
    detail.revisions.some((revision) => ["PUBLISHED", "SUPERSEDED", "ARCHIVED"].includes(revision.status) || revision.immutable || revision.published_at)
  )), [detail]);
  const publishedWorkflow = detail?.workflows.find((workflow) => workflow.state === "PUBLISHED");

  const remove = async () => {
    if (!detail || confirmation.trim() !== detail.document.code) return;
    setBusy(true);
    setError("");
    try {
      await deleteDocument(tenant, manualId);
      onClose();
      navigate(`${basePath}/library`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The draft document could not be deleted.");
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    if (!publishedWorkflow) return;
    setBusy(true);
    setError("");
    try {
      await transitionDocumentWorkflow(tenant, publishedWorkflow.id, {
        action: "ARCHIVE",
        comments: "Archived from the document lifecycle controls.",
        evidence: [],
        expected_version: publishedWorkflow.version,
      });
      onClose();
      navigate(0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled document could not be archived.");
    } finally {
      setBusy(false);
    }
  };

  return <Modal title={controlledHistory ? "Retire controlled document" : "Delete draft document"} description={controlledHistory ? "Published controlled information is retained for auditability and cannot be erased. Use the governed archive workflow instead." : "Never-published draft documents can be permanently removed, including their draft revisions."} busy={busy} onClose={onClose}>
    <div className="dclife-form">
      {detail ? <div className="dclife-document-card wide"><strong>{detail.document.code} · {detail.document.title}</strong><span>{detail.revisions.length} revision{detail.revisions.length === 1 ? "" : "s"} · {detail.document.status}</span></div> : null}
      {controlledHistory ? <>
        <div className="dclife-warning wide"><Archive size={18} /><div><strong>Permanent deletion is blocked.</strong><span>Published, superseded and archived revisions are controlled records. Removing them would destroy the required audit trail.</span></div></div>
        {publishedWorkflow ? <div className="dclife-actions wide"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="button" className="dc-button dc-button--danger" onClick={() => void archive()} disabled={busy}><Archive size={14} /> Archive document</button></div> : <div className="dclife-actions wide"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Close</button><button type="button" className="dc-button" onClick={() => { onClose(); navigate(`${basePath}/library/${manualId}?view=workflow`); }}><Archive size={14} /> Open lifecycle</button></div>}
      </> : <>
        <label className="wide"><span>Type <strong>{detail?.document.code || "the document code"}</strong> to confirm permanent deletion</span><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label>
        <div className="dclife-warning wide"><Trash2 size={18} /><div><strong>This cannot be undone.</strong><span>The draft document, draft revisions and tenant-scoped draft data are removed. Local uploaded source files are purged when they are inside the managed manual-upload store.</span></div></div>
        <div className="dclife-actions wide"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="button" className="dc-button dc-button--danger" onClick={() => void remove()} disabled={busy || !detail || confirmation.trim() !== detail.document.code}><Trash2 size={14} /> Delete permanently</button></div>
      </>}
      {error ? <div className="dc-form__error wide" role="alert">{error}</div> : null}
    </div>
  </Modal>;
}

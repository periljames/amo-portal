import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  ClipboardList,
  Copy,
  FileCheck2,
  FileClock,
  History,
  Link2,
  Plus,
  ShieldAlert,
  UserPlus,
  UserX,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { apiRequest } from "../../../services/apiClient";
import { qmsListDocuments, qmsResolveAudit, type QMSDocumentOut } from "../../../services/qms";
import {
  createExternalAuditParticipant,
  listExternalAuditParticipants,
  revokeExternalAuditParticipant,
  type ExternalParticipantType,
} from "../../../services/qmsAuditExternalAccess";
import {
  createGovernedAuditDocumentRequest,
  listGovernedAuditDocumentRequests,
  updateGovernedAuditDocumentRequest,
  type GovernedAuditDocumentRequest,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { getAuditPreparationContext } from "../../../services/qmsAuditPreparationContext";
import { getAuditSession } from "../../../services/qmsAuditSession";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-audit-prepare-workspace.css";

type Props = { amoCode: string; auditKey: string };

type ControlledRevision = {
  id: string;
  document_id: string;
  issue_no: number;
  rev_no: number;
  lifecycle_status: string;
  sha256?: string | null;
  issued_date?: string | null;
};

type NewRequest = {
  title: string;
  description: string;
  dueDate: string;
  requestType: GovernedAuditDocumentRequest["request_type"];
  linkedCriterion: string;
  isRequired: boolean;
  sourceMode: GovernedAuditDocumentRequest["source_mode"];
  controlledDocumentId: string;
  controlledRevisionId: string;
};

type ExternalParticipantDraft = {
  participantType: ExternalParticipantType;
  displayName: string;
  email: string;
  organisation: string;
  role: string;
  assuranceLevel: "EMAIL_LINK" | "PASSKEY";
  expiresAt: string;
  readProgress: boolean;
  readReleasedEvidence: boolean;
  executeChecklist: boolean;
  createEvidence: boolean;
  draftFinding: boolean;
};

const emptyRequest: NewRequest = {
  title: "",
  description: "",
  dueDate: "",
  requestType: "DOCUMENT",
  linkedCriterion: "",
  isRequired: true,
  sourceMode: "UPLOAD_OR_CONTROLLED",
  controlledDocumentId: "",
  controlledRevisionId: "",
};

const emptyExternalParticipant: ExternalParticipantDraft = {
  participantType: "AUDITEE_GUEST",
  displayName: "",
  email: "",
  organisation: "",
  role: "AUDITEE",
  assuranceLevel: "EMAIL_LINK",
  expiresAt: "",
  readProgress: false,
  readReleasedEvidence: false,
  executeChecklist: false,
  createEvidence: false,
  draftFinding: false,
};

function statusLabel(status: string) {
  return status.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function participantPermissions(draft: ExternalParticipantDraft): string[] {
  if (draft.participantType === "AUDITEE_GUEST") {
    return [
      "audit:read_summary",
      "audit:read_released_findings",
      "audit:document_submit",
      "audit:acknowledge",
      "car:respond",
      ...(draft.readProgress ? ["audit:read_progress"] : []),
      ...(draft.readReleasedEvidence ? ["audit:read_released_evidence"] : []),
    ];
  }
  return [
    "audit:read_assigned",
    "audit:read_summary",
    ...(draft.readProgress ? ["audit:read_progress"] : []),
    ...(draft.executeChecklist ? ["audit:checklist_execute"] : []),
    ...(draft.createEvidence ? ["audit:evidence_create"] : []),
    ...(draft.draftFinding ? ["audit:finding_draft"] : []),
  ];
}

function listControlledRevisions(documentId: string, signal?: AbortSignal) {
  return apiRequest<ControlledRevision[]>(`/quality/qms/documents/${encodeURIComponent(documentId)}/revisions`, {
    timeoutMs: 15_000,
    cacheTtlMs: 5_000,
    signal,
  });
}

const AuditPrepareWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [showParticipantForm, setShowParticipantForm] = useState(false);
  const [newRequest, setNewRequest] = useState<NewRequest>(emptyRequest);
  const [participantDraft, setParticipantDraft] = useState<ExternalParticipantDraft>(emptyExternalParticipant);
  const [oneTimeAccessUrl, setOneTimeAccessUrl] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-prepare-audit-resolve", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const contextQuery = useQuery({
    queryKey: ["qms-audit-preparation-context", amoCode, auditId],
    queryFn: ({ signal }) => getAuditPreparationContext(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 3_000,
  });
  const requestsQuery = useQuery({
    queryKey: ["qms-governed-audit-document-requests", amoCode, auditId],
    queryFn: ({ signal }) => listGovernedAuditDocumentRequests(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const participantsQuery = useQuery({
    queryKey: ["qms-audit-external-participants", amoCode, auditId],
    queryFn: ({ signal }) => listExternalAuditParticipants(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["qms-audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const controlledDocumentsQuery = useQuery({
    queryKey: ["qms-controlled-documents-for-audit", amoCode],
    queryFn: () => qmsListDocuments({}),
    enabled: Boolean(showRequestForm && newRequest.sourceMode !== "UPLOAD"),
    staleTime: 30_000,
  });
  const controlledRevisionsQuery = useQuery({
    queryKey: ["qms-controlled-document-revisions", newRequest.controlledDocumentId],
    queryFn: ({ signal }) => listControlledRevisions(newRequest.controlledDocumentId, signal),
    enabled: Boolean(showRequestForm && newRequest.sourceMode !== "UPLOAD" && newRequest.controlledDocumentId),
    staleTime: 10_000,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-governed-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-external-participants", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: () => createGovernedAuditDocumentRequest(amoCode, auditId, {
      title: newRequest.title.trim(),
      description: newRequest.description.trim() || null,
      due_date: newRequest.dueDate || null,
      request_type: newRequest.requestType,
      linked_criterion: newRequest.linkedCriterion.trim() || null,
      is_required: newRequest.isRequired,
      source_mode: newRequest.sourceMode,
      controlled_document_id: newRequest.sourceMode !== "UPLOAD" && newRequest.controlledDocumentId ? newRequest.controlledDocumentId : null,
      controlled_revision_id: newRequest.sourceMode !== "UPLOAD" && newRequest.controlledRevisionId ? newRequest.controlledRevisionId : null,
    }),
    onSuccess: async () => {
      setNewRequest(emptyRequest);
      setShowRequestForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document request could not be created."),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ request, status }: { request: GovernedAuditDocumentRequest; status: "ACCEPTED" | "REJECTED" | "WAIVED" }) =>
      updateGovernedAuditDocumentRequest(amoCode, auditId, request.id, {
        status,
        review_note: reviewNotes[request.id]?.trim() || null,
      }),
    onSuccess: async (updated) => {
      setReviewNotes((current) => ({ ...current, [updated.id]: "" }));
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document review decision failed."),
  });

  const participantMutation = useMutation({
    mutationFn: () => createExternalAuditParticipant(amoCode, auditId, {
      email: participantDraft.email.trim(),
      display_name: participantDraft.displayName.trim(),
      organisation: participantDraft.organisation.trim() || null,
      participant_type: participantDraft.participantType,
      role: participantDraft.role.trim(),
      permissions: participantPermissions(participantDraft),
      assurance_level: participantDraft.assuranceLevel,
      expires_at: new Date(participantDraft.expiresAt).toISOString(),
    }),
    onSuccess: async (participant) => {
      const relative = participant.access_url || null;
      setOneTimeAccessUrl(relative ? `${window.location.origin}${relative}` : null);
      setParticipantDraft(emptyExternalParticipant);
      setShowParticipantForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant could not be invited."),
  });

  const revokeMutation = useMutation({
    mutationFn: (participantId: string) => revokeExternalAuditParticipant(amoCode, auditId, participantId),
    onSuccess: async () => {
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant access could not be revoked."),
  });

  const requests = requestsQuery.data?.items || [];
  const participants = participantsQuery.data?.items || [];
  const context = contextQuery.data;
  const readiness = useMemo(() => {
    const required = requests.filter((request) => request.is_required && request.status !== "WAIVED");
    const accepted = required.filter((request) => request.status === "ACCEPTED").length;
    const total = required.length;
    return { accepted, total, percent: total ? Math.round((accepted / total) * 100) : 100 };
  }, [requests]);
  const documents = (controlledDocumentsQuery.data || []) as QMSDocumentOut[];
  const revisions = controlledRevisionsQuery.data || [];

  if (auditQuery.isLoading || contextQuery.isLoading || requestsQuery.isLoading || participantsQuery.isLoading) {
    return <div className="qms-audit-prepare qms-audit-prepare--loading">Loading governed preparation workspace…</div>;
  }

  const loadError = auditQuery.error || contextQuery.error || requestsQuery.error || participantsQuery.error;
  if (loadError || !auditQuery.data) {
    return <div className="qms-audit-prepare qms-audit-prepare--loading" role="alert"><AlertTriangle size={20} /> {loadError instanceof Error ? loadError.message : "Preparation workspace unavailable."}</div>;
  }

  return (
    <div className="qms-audit-prepare" role="region" aria-label="Pre-audit preparation workspace">
      <header className="qms-audit-prepare__header">
        <div><span>PREPARE · evidence before fieldwork</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1></div>
        <div className="qms-audit-prepare__actions">
          <span>{sessionQuery.data ? `Authoritative stage: ${sessionQuery.data.current_stage_label}` : "Verifying lifecycle…"}</span>
          <Link to={auditSessionPath(amoCode, auditKey, "setup")}><X size={16} /> Exit preparation</Link>
        </div>
      </header>

      {localError ? <div className="qms-audit-prepare__error" role="alert"><AlertTriangle size={16} /> {localError}</div> : null}

      <div className="qms-audit-prepare__body">
        <main>
          <section className="qms-audit-prepare__card qms-audit-prepare__basis">
            <header><BookOpenCheck size={18} /><div><strong>Frozen audit basis</strong><small>Scope, criteria and checklist lineage come from the governed audit occurrence.</small></div></header>
            <dl>
              <div><dt>Scope</dt><dd>{context?.regulatory_and_manual_basis.audit_scope || auditQuery.data.scope || "—"}</dd></div>
              <div><dt>Criteria</dt><dd>{context?.regulatory_and_manual_basis.audit_criteria || auditQuery.data.criteria || "—"}</dd></div>
              <div><dt>Checklist binding</dt><dd>{context?.controlled_preparation.checklist_bindings.length || 0} governed revision(s)</dd></div>
              <div><dt>Preparation revision</dt><dd>{context?.controlled_preparation.latest_revision ? `Rev ${context.controlled_preparation.latest_revision.revision_no} · ${context.controlled_preparation.latest_revision.status}` : "Not issued"}</dd></div>
            </dl>
          </section>

          <section className="qms-audit-prepare__card">
            <header>
              <FileClock size={18} />
              <div><strong>Document and record requests</strong><small>Each request states why it is needed, the criterion it supports and whether an auditee may upload or link a controlled DMS record.</small></div>
              {canManage ? <button type="button" onClick={() => setShowRequestForm((value) => !value)}><Plus size={15} /> New request</button> : null}
            </header>

            {showRequestForm ? (
              <form className="qms-audit-prepare__request-form" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }}>
                <label><span>Request type</span><select value={newRequest.requestType} onChange={(event) => setNewRequest((current) => ({ ...current, requestType: event.target.value as NewRequest["requestType"] }))}><option>DOCUMENT</option><option>RECORD</option><option>MANUAL</option><option>FORM</option><option>CERTIFICATE</option><option>REGISTER</option><option>OTHER</option></select></label>
                <label><span>Due date</span><input type="date" value={newRequest.dueDate} onChange={(event) => setNewRequest((current) => ({ ...current, dueDate: event.target.value }))} /></label>
                <label className="is-wide"><span>Request title</span><input required minLength={2} value={newRequest.title} onChange={(event) => setNewRequest((current) => ({ ...current, title: event.target.value }))} /></label>
                <label className="is-wide"><span>Purpose / records required</span><textarea rows={3} value={newRequest.description} onChange={(event) => setNewRequest((current) => ({ ...current, description: event.target.value }))} /></label>
                <label className="is-wide"><span>Linked criterion / requirement</span><textarea rows={2} value={newRequest.linkedCriterion} onChange={(event) => setNewRequest((current) => ({ ...current, linkedCriterion: event.target.value }))} placeholder="Exact regulation, manual paragraph, procedure or checklist criterion this evidence supports" /></label>
                <label><span>Submission source</span><select value={newRequest.sourceMode} onChange={(event) => setNewRequest((current) => ({ ...current, sourceMode: event.target.value as NewRequest["sourceMode"], controlledDocumentId: "", controlledRevisionId: "" }))}><option value="UPLOAD_OR_CONTROLLED">Upload or controlled DMS record</option><option value="UPLOAD">Upload only</option><option value="CONTROLLED_DMS">Controlled DMS record only</option></select></label>
                <label className="qms-audit-prepare__check"><input type="checkbox" checked={newRequest.isRequired} onChange={(event) => setNewRequest((current) => ({ ...current, isRequired: event.target.checked }))} /> Required before fieldwork</label>
                {newRequest.sourceMode !== "UPLOAD" ? <>
                  <label><span>Controlled document</span><select value={newRequest.controlledDocumentId} onChange={(event) => setNewRequest((current) => ({ ...current, controlledDocumentId: event.target.value, controlledRevisionId: "" }))}><option value="">No preselected document</option>{documents.map((document) => <option key={document.id} value={document.id}>{document.doc_code} · {document.title}</option>)}</select></label>
                  <label><span>Exact controlled revision</span><select disabled={!newRequest.controlledDocumentId} value={newRequest.controlledRevisionId} onChange={(event) => setNewRequest((current) => ({ ...current, controlledRevisionId: event.target.value }))}><option value="">Any authorised revision</option>{revisions.map((revision) => <option key={revision.id} value={revision.id}>Issue {revision.issue_no} · Rev {revision.rev_no} · {revision.lifecycle_status}{revision.sha256 ? ` · ${revision.sha256.slice(0, 10)}…` : ""}</option>)}</select></label>
                </> : null}
                <footer><button type="button" onClick={() => { setShowRequestForm(false); setNewRequest(emptyRequest); }}>Cancel</button><button type="submit" className="is-primary" disabled={createMutation.isPending || (newRequest.sourceMode === "CONTROLLED_DMS" && !newRequest.controlledDocumentId)}>{createMutation.isPending ? "Creating…" : "Create governed request"}</button></footer>
              </form>
            ) : null}

            <div className="qms-audit-prepare__request-list">
              {!requests.length ? <p className="qms-audit-prepare__empty">No pre-audit document requests have been recorded.</p> : null}
              {requests.map((request) => (
                <article key={request.id} data-status={request.status}>
                  <div className="qms-audit-prepare__request-main">
                    <span className="qms-audit-prepare__status">{statusLabel(request.status)}</span>
                    <strong>{request.title}</strong>
                    <p>{request.description || "No additional instructions."}</p>
                    <small>{request.request_type.replaceAll("_", " ")} · {request.is_required ? "Required" : "Optional"} · {request.source_mode.replaceAll("_", " ")}</small>
                    {request.linked_criterion ? <blockquote><strong>Criterion:</strong> {request.linked_criterion}</blockquote> : null}
                    <small>Due {request.due_date || "not specified"}{request.uploaded_at ? ` · submitted ${new Date(request.uploaded_at).toLocaleString()}` : ""}</small>
                    {request.controlled_document_id ? <code><Link2 size={13} /> DMS document {request.controlled_document_id}{request.controlled_revision_id ? ` · revision ${request.controlled_revision_id}` : ""}</code> : null}
                    {request.review_note ? <blockquote>{request.review_note}</blockquote> : null}
                  </div>
                  {canManage && ["UPLOADED", "REJECTED"].includes(request.status) ? (
                    <div className="qms-audit-prepare__review">
                      <textarea rows={2} value={reviewNotes[request.id] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [request.id]: event.target.value }))} placeholder="Review note / return instructions" />
                      <div><button type="button" onClick={() => reviewMutation.mutate({ request, status: "REJECTED" })} disabled={reviewMutation.isPending}>Return / reject</button><button type="button" className="is-primary" onClick={() => reviewMutation.mutate({ request, status: "ACCEPTED" })} disabled={reviewMutation.isPending}><CheckCircle2 size={14} /> Accept</button></div>
                    </div>
                  ) : null}
                  {canManage && request.status === "REQUESTED" && !request.is_required ? <button type="button" onClick={() => reviewMutation.mutate({ request, status: "WAIVED" })} disabled={reviewMutation.isPending}>Waive optional request</button> : null}
                </article>
              ))}
            </div>
          </section>

          <section className="qms-audit-prepare__card qms-audit-prepare__participants">
            <header>
              <UserPlus size={18} />
              <div><strong>External participants</strong><small>Scoped audit access without creating employee accounts.</small></div>
              {canManage ? <button type="button" onClick={() => setShowParticipantForm((value) => !value)}><UserPlus size={15} /> Invite</button> : null}
            </header>

            {oneTimeAccessUrl ? <div className="qms-audit-prepare__one-time-link" role="status"><div><strong>One-time invitation link created</strong><small>Copy it now. The server stores only its SHA-256 hash and cannot reveal this token again.</small></div><button type="button" onClick={() => void navigator.clipboard.writeText(oneTimeAccessUrl)}><Copy size={14} /> Copy link</button></div> : null}

            {showParticipantForm ? <form className="qms-audit-prepare__participant-form" onSubmit={(event) => { event.preventDefault(); participantMutation.mutate(); }}>
              <label><span>Participant type</span><select value={participantDraft.participantType} onChange={(event) => { const participantType = event.target.value as ExternalParticipantType; setParticipantDraft((current) => ({ ...current, participantType, role: participantType === "AUDITEE_GUEST" ? "AUDITEE" : "AUDITOR", assuranceLevel: participantType === "AUDITEE_GUEST" ? "EMAIL_LINK" : current.assuranceLevel })); }}><option value="AUDITEE_GUEST">Auditee guest</option><option value="EXTERNAL_AUDITOR">External auditor</option></select></label>
              <label><span>Role</span><input required value={participantDraft.role} onChange={(event) => setParticipantDraft((current) => ({ ...current, role: event.target.value }))} /></label>
              <label><span>Full name</span><input required minLength={2} value={participantDraft.displayName} onChange={(event) => setParticipantDraft((current) => ({ ...current, displayName: event.target.value }))} /></label>
              <label><span>Email</span><input required type="email" value={participantDraft.email} onChange={(event) => setParticipantDraft((current) => ({ ...current, email: event.target.value }))} /></label>
              <label><span>Organisation</span><input value={participantDraft.organisation} onChange={(event) => setParticipantDraft((current) => ({ ...current, organisation: event.target.value }))} /></label>
              <label><span>Access expires</span><input required type="datetime-local" value={participantDraft.expiresAt} onChange={(event) => setParticipantDraft((current) => ({ ...current, expiresAt: event.target.value }))} /></label>
              <label><span>Identity assurance</span><select value={participantDraft.assuranceLevel} onChange={(event) => setParticipantDraft((current) => ({ ...current, assuranceLevel: event.target.value as ExternalParticipantDraft["assuranceLevel"] }))}><option value="EMAIL_LINK">Email link</option>{participantDraft.participantType === "EXTERNAL_AUDITOR" ? <option value="PASSKEY">Passkey required</option> : null}</select></label>
              <fieldset className="is-wide"><legend>Scoped access</legend><label><input type="checkbox" checked={participantDraft.readProgress} onChange={(event) => setParticipantDraft((current) => ({ ...current, readProgress: event.target.checked }))} /> View fieldwork progress</label>{participantDraft.participantType === "AUDITEE_GUEST" ? <label><input type="checkbox" checked={participantDraft.readReleasedEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, readReleasedEvidence: event.target.checked }))} /> View evidence explicitly released with findings</label> : <><label><input type="checkbox" checked={participantDraft.executeChecklist} onChange={(event) => setParticipantDraft((current) => ({ ...current, executeChecklist: event.target.checked }))} /> Execute assigned checklist</label><label><input type="checkbox" checked={participantDraft.createEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, createEvidence: event.target.checked }))} /> Add audit evidence</label><label><input type="checkbox" checked={participantDraft.draftFinding} onChange={(event) => setParticipantDraft((current) => ({ ...current, draftFinding: event.target.checked }))} /> Draft findings</label></>}</fieldset>
              <p className="is-wide">Only implemented assurance modes are selectable. Auditees use purpose-bound email-link sessions; external auditors may additionally require a WebAuthn passkey. Unconfigured MFA is not presented as an operable choice.</p>
              <footer><button type="button" onClick={() => setShowParticipantForm(false)}>Cancel</button><button type="submit" className="is-primary" disabled={!participantDraft.expiresAt || participantMutation.isPending}>{participantMutation.isPending ? "Creating access…" : "Create invitation"}</button></footer>
            </form> : null}

            <div className="qms-audit-prepare__participant-list">
              {!participants.length ? <p className="qms-audit-prepare__empty">No external participants are assigned to this audit.</p> : participants.map((participant) => <article key={participant.id}><div><span>{participant.participant_type.replaceAll("_", " ")}</span><strong>{participant.display_name || participant.email || "External participant"}</strong><small>{participant.organisation || "No organisation"} · {participant.role} · {participant.assurance_level || "EMAIL_LINK"}</small><small>{participant.permissions.join(" · ")}</small><small>Expires {new Date(participant.expires_at).toLocaleString()} · {participant.status}</small></div>{canManage && participant.status !== "REVOKED" ? <button type="button" onClick={() => revokeMutation.mutate(participant.id)} disabled={revokeMutation.isPending}><UserX size={14} /> Revoke</button> : null}</article>)}
            </div>
          </section>
        </main>

        <aside className="qms-audit-prepare__sidebar">
          <section className="qms-audit-prepare__readiness"><span>Required evidence readiness</span><strong>{readiness.percent}%</strong><div><span style={{ width: `${readiness.percent}%` }} /></div><small>{readiness.accepted} of {readiness.total} required requests accepted</small></section>
          <section><ClipboardList size={17} /><strong>Checklist basis</strong><small>{context?.controlled_preparation.checklist_bindings.length || 0} frozen checklist revision(s) are bound to this occurrence.</small></section>
          <section><FileCheck2 size={17} /><strong>Preparation evidence</strong><small>Uploaded files and controlled-DMS references remain reviewable and attributable before fieldwork.</small></section>
          <section><History size={17} /><strong>Change control</strong><small>Issue a new preparation revision when the audit basis changes; do not silently mutate a frozen revision.</small></section>
          <Link className="qms-audit-prepare__next" to={auditSessionPath(amoCode, auditKey, "live")}><ArrowRight size={16} /> Open Live Audit</Link>
          {readiness.percent < 100 ? <div className="qms-audit-prepare__warning"><ShieldAlert size={15} /> Required document requests remain unresolved. The authoritative session determines whether fieldwork may advance.</div> : null}
        </aside>
      </div>
    </div>
  );
};

export default AuditPrepareWorkspace;

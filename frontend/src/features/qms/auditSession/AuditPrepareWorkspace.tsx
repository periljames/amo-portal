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
  Plus,
  ShieldAlert,
  UserPlus,
  UserX,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsResolveAudit } from "../../../services/qms";
import {
  createExternalAuditParticipant,
  listExternalAuditParticipants,
  revokeExternalAuditParticipant,
  type ExternalAuditAssuranceLevel,
  type ExternalParticipantType,
} from "../../../services/qmsAuditExternalAccess";
import {
  createAuditDocumentRequest,
  listAuditDocumentRequests,
  updateAuditDocumentRequest,
  type AuditDocumentRequest,
} from "../../../services/qmsAuditPreparationRoom";
import { getAuditPreparationContext } from "../../../services/qmsAuditPreparationContext";
import { getAuditSession } from "../../../services/qmsAuditSession";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-audit-prepare-workspace.css";

type Props = { amoCode: string; auditKey: string };

type NewRequest = {
  title: string;
  description: string;
  dueDate: string;
};

type ExternalParticipantDraft = {
  participantType: ExternalParticipantType;
  displayName: string;
  email: string;
  organisation: string;
  role: string;
  assuranceLevel: ExternalAuditAssuranceLevel;
  expiresAt: string;
  readProgress: boolean;
  readReleasedEvidence: boolean;
  executeChecklist: boolean;
  createEvidence: boolean;
  draftFinding: boolean;
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

const AuditPrepareWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [showParticipantForm, setShowParticipantForm] = useState(false);
  const [newRequest, setNewRequest] = useState<NewRequest>({ title: "", description: "", dueDate: "" });
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
    queryKey: ["qms-audit-document-requests", amoCode, auditId],
    queryFn: ({ signal }) => listAuditDocumentRequests(amoCode, auditId, signal),
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

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-external-participants", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: () => createAuditDocumentRequest(amoCode, auditId, {
      title: newRequest.title.trim(),
      description: newRequest.description.trim() || null,
      due_date: newRequest.dueDate || null,
    }),
    onSuccess: async () => {
      setNewRequest({ title: "", description: "", dueDate: "" });
      setShowRequestForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document request could not be created."),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ request, status }: { request: AuditDocumentRequest; status: "ACCEPTED" | "REJECTED" | "WAIVED" }) =>
      updateAuditDocumentRequest(amoCode, auditId, request.id, {
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

  const requests = requestsQuery.data || [];
  const participants = participantsQuery.data?.items || [];
  const context = contextQuery.data;
  const readiness = useMemo(() => {
    const required = requests.filter((request) => request.status !== "WAIVED");
    const accepted = required.filter((request) => request.status === "ACCEPTED").length;
    const total = required.length;
    return { accepted, total, percent: total ? Math.round((accepted / total) * 100) : 100 };
  }, [requests]);

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
            <header><BookOpenCheck size={18} /><div><strong>Frozen audit basis</strong><small>Scope and criteria come from the governed audit occurrence.</small></div></header>
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
              <div><strong>Document requests</strong><small>Request and review evidence before the field audit begins.</small></div>
              {canManage ? <button type="button" onClick={() => setShowRequestForm((value) => !value)}><Plus size={15} /> Request document</button> : null}
            </header>

            {showRequestForm ? (
              <form className="qms-audit-prepare__request-form" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }}>
                <label><span>Request title</span><input required minLength={2} value={newRequest.title} onChange={(event) => setNewRequest((current) => ({ ...current, title: event.target.value }))} /></label>
                <label><span>Due date</span><input type="date" value={newRequest.dueDate} onChange={(event) => setNewRequest((current) => ({ ...current, dueDate: event.target.value }))} /></label>
                <label className="is-wide"><span>Purpose / records required</span><textarea rows={3} value={newRequest.description} onChange={(event) => setNewRequest((current) => ({ ...current, description: event.target.value }))} /></label>
                <footer><button type="button" onClick={() => setShowRequestForm(false)}>Cancel</button><button type="submit" className="is-primary" disabled={createMutation.isPending}>{createMutation.isPending ? "Creating…" : "Create request"}</button></footer>
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
                    <small>Due {request.due_date || "not specified"}{request.uploaded_at ? ` · submitted ${new Date(request.uploaded_at).toLocaleString()}` : ""}</small>
                    {request.file_ref ? <code title={request.file_ref}>{request.file_ref}</code> : null}
                    {request.review_note ? <blockquote>{request.review_note}</blockquote> : null}
                  </div>
                  {canManage && ["UPLOADED", "REJECTED"].includes(request.status) ? (
                    <div className="qms-audit-prepare__review">
                      <textarea rows={2} value={reviewNotes[request.id] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [request.id]: event.target.value }))} placeholder="Review note / return instructions" />
                      <div><button type="button" onClick={() => reviewMutation.mutate({ request, status: "REJECTED" })} disabled={reviewMutation.isPending}>Return</button><button type="button" className="is-primary" onClick={() => reviewMutation.mutate({ request, status: "ACCEPTED" })} disabled={reviewMutation.isPending}><CheckCircle2 size={14} /> Accept</button></div>
                    </div>
                  ) : null}
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

            {oneTimeAccessUrl ? (
              <div className="qms-audit-prepare__one-time-link" role="status">
                <div><strong>One-time invitation link created</strong><small>Copy it now. The server stores only its SHA-256 hash and cannot reveal this token again.</small></div>
                <code>{oneTimeAccessUrl}</code>
                <button type="button" onClick={() => void navigator.clipboard.writeText(oneTimeAccessUrl)}><Copy size={15} /> Copy link</button>
                <button type="button" onClick={() => setOneTimeAccessUrl(null)}>Dismiss</button>
              </div>
            ) : null}

            {showParticipantForm ? (
              <form className="qms-audit-prepare__participant-form" onSubmit={(event) => { event.preventDefault(); participantMutation.mutate(); }}>
                <label><span>Participant type</span><select value={participantDraft.participantType} onChange={(event) => { const participantType = event.target.value as ExternalParticipantType; setParticipantDraft((current) => ({ ...current, participantType, role: participantType === "AUDITEE_GUEST" ? "AUDITEE" : "AUDITOR", readProgress: participantType === "EXTERNAL_AUDITOR" })); }}><option value="AUDITEE_GUEST">Auditee / external representative</option><option value="EXTERNAL_AUDITOR">External auditor</option></select></label>
                <label><span>Role</span><input required value={participantDraft.role} onChange={(event) => setParticipantDraft((current) => ({ ...current, role: event.target.value }))} /></label>
                <label><span>Full name</span><input required minLength={2} value={participantDraft.displayName} onChange={(event) => setParticipantDraft((current) => ({ ...current, displayName: event.target.value }))} /></label>
                <label><span>Email</span><input required type="email" value={participantDraft.email} onChange={(event) => setParticipantDraft((current) => ({ ...current, email: event.target.value }))} /></label>
                <label><span>Organisation</span><input value={participantDraft.organisation} onChange={(event) => setParticipantDraft((current) => ({ ...current, organisation: event.target.value }))} /></label>
                <label><span>Access expires</span><input required type="datetime-local" value={participantDraft.expiresAt} onChange={(event) => setParticipantDraft((current) => ({ ...current, expiresAt: event.target.value }))} /></label>
                <label><span>Identity assurance</span><select value={participantDraft.assuranceLevel} onChange={(event) => setParticipantDraft((current) => ({ ...current, assuranceLevel: event.target.value as ExternalAuditAssuranceLevel }))}><option value="EMAIL_LINK">Email link</option><option value="MFA">MFA required</option><option value="PASSKEY">Passkey required</option></select></label>
                <fieldset className="is-wide"><legend>Scoped access</legend><label><input type="checkbox" checked={participantDraft.readProgress} onChange={(event) => setParticipantDraft((current) => ({ ...current, readProgress: event.target.checked }))} /> View fieldwork progress</label>{participantDraft.participantType === "AUDITEE_GUEST" ? <label><input type="checkbox" checked={participantDraft.readReleasedEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, readReleasedEvidence: event.target.checked }))} /> View evidence explicitly released with findings</label> : <><label><input type="checkbox" checked={participantDraft.executeChecklist} onChange={(event) => setParticipantDraft((current) => ({ ...current, executeChecklist: event.target.checked }))} /> Execute assigned checklist</label><label><input type="checkbox" checked={participantDraft.createEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, createEvidence: event.target.checked }))} /> Add audit evidence</label><label><input type="checkbox" checked={participantDraft.draftFinding} onChange={(event) => setParticipantDraft((current) => ({ ...current, draftFinding: event.target.checked }))} /> Draft findings</label></>}</fieldset>
                <p className="is-wide">Auditees receive only released findings and their own preparation requests. External auditors receive only the capabilities explicitly selected here.</p>
                <footer><button type="button" onClick={() => setShowParticipantForm(false)}>Cancel</button><button type="submit" className="is-primary" disabled={!participantDraft.expiresAt || participantMutation.isPending}>{participantMutation.isPending ? "Creating access…" : "Create invitation"}</button></footer>
              </form>
            ) : null}

            <div className="qms-audit-prepare__participant-list">
              {!participants.length ? <p className="qms-audit-prepare__empty">No external audit participants have been invited.</p> : null}
              {participants.map((participant) => (
                <article key={participant.id}>
                  <div><span className="qms-audit-prepare__status">{statusLabel(participant.status)} · {statusLabel(participant.participant_type)}</span><strong>{participant.display_name || participant.email}</strong><small>{participant.role} · {participant.organisation || "External organisation not recorded"}</small><small>{participant.email} · expires {new Date(participant.expires_at).toLocaleString()}</small></div>
                  <div className="qms-audit-prepare__permission-tags">{participant.permissions.map((permission) => <span key={permission}>{permission}</span>)}</div>
                  {canManage && participant.status !== "REVOKED" ? <button type="button" onClick={() => revokeMutation.mutate(participant.id)} disabled={revokeMutation.isPending}><UserX size={15} /> Revoke</button> : null}
                </article>
              ))}
            </div>
          </section>
        </main>

        <aside>
          <section className="qms-audit-prepare__card qms-audit-prepare__readiness">
            <header><ClipboardList size={18} /><div><strong>Preparation readiness</strong><small>{readiness.accepted} of {readiness.total} requested items accepted</small></div></header>
            <div className="qms-audit-prepare__meter"><span style={{ width: `${readiness.percent}%` }} /></div>
            <strong>{readiness.percent}%</strong>
            <dl>
              <div><dt>Prior related audits</dt><dd>{context?.prior_audit_history.items.length || 0}</dd></div>
              <div><dt>Prior findings</dt><dd>{context?.prior_findings.total || 0}</dd></div>
              <div><dt>Open CAR exposure</dt><dd>{context?.car_exposure.open_count || 0}</dd></div>
              <div><dt>External participants</dt><dd>{participants.filter((participant) => participant.status !== "REVOKED").length}</dd></div>
            </dl>
          </section>

          <section className="qms-audit-prepare__card">
            <header><History size={18} /><div><strong>Prior audit intelligence</strong><small>Source-backed context only.</small></div></header>
            <ul>{context?.prior_audit_history.items.slice(0, 5).map((audit) => <li key={audit.id}><strong>{audit.audit_ref}</strong><small>{audit.title}</small></li>)}</ul>
            {!context?.prior_audit_history.items.length ? <p className="qms-audit-prepare__empty">No comparable prior audit was found.</p> : null}
          </section>

          <section className="qms-audit-prepare__card qms-audit-prepare__external-gap">
            <header><ShieldAlert size={18} /><div><strong>Released-data boundary</strong><small>Server enforced.</small></div></header>
            <p>External auditees do not receive private auditor notes, unreleased draft findings, internal assurance intelligence, or unrelated tenant records. A finding appears externally only after an explicit release event.</p>
          </section>

          <Link className="qms-audit-prepare__continue" to={auditSessionPath(amoCode, auditKey, "live")}>
            <FileCheck2 size={16} /> Open Live Audit <ArrowRight size={16} />
          </Link>
        </aside>
      </div>
    </div>
  );
};

export default AuditPrepareWorkspace;

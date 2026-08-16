import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  ClipboardList,
  FileCheck2,
  FileClock,
  History,
  Plus,
  ShieldAlert,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsResolveAudit } from "../../../services/qms";
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

function statusLabel(status: string) {
  return status.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

const AuditPrepareWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [newRequest, setNewRequest] = useState<NewRequest>({ title: "", description: "", dueDate: "" });
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

  const requests = requestsQuery.data || [];
  const context = contextQuery.data;
  const readiness = useMemo(() => {
    const required = requests.filter((request) => request.status !== "WAIVED");
    const accepted = required.filter((request) => request.status === "ACCEPTED").length;
    const total = required.length;
    return { accepted, total, percent: total ? Math.round((accepted / total) * 100) : 100 };
  }, [requests]);

  if (auditQuery.isLoading || contextQuery.isLoading || requestsQuery.isLoading) {
    return <div className="qms-audit-prepare qms-audit-prepare--loading">Loading governed preparation workspace…</div>;
  }

  const loadError = auditQuery.error || contextQuery.error || requestsQuery.error;
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
              <div><dt>Checklist bindings</dt><dd>{context?.controlled_preparation.checklist_bindings.length || 0}</dd></div>
            </dl>
          </section>

          <section className="qms-audit-prepare__card">
            <header><History size={18} /><div><strong>Prior audit intelligence</strong><small>Source-backed context only.</small></div></header>
            <ul>{context?.prior_audit_history.items.slice(0, 5).map((audit) => <li key={audit.id}><strong>{audit.audit_ref}</strong><small>{audit.title}</small></li>)}</ul>
            {!context?.prior_audit_history.items.length ? <p className="qms-audit-prepare__empty">No comparable prior audit was found.</p> : null}
          </section>

          <section className="qms-audit-prepare__card qms-audit-prepare__external-gap">
            <header><ShieldAlert size={18} /><div><strong>External auditee room</strong><small>Security boundary not yet enabled.</small></div></header>
            <p>The existing document-request records are now presented as one preparation queue. A guest upload/link flow will be enabled only after purpose-bound, expiring, server-authorized audit access grants are implemented.</p>
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

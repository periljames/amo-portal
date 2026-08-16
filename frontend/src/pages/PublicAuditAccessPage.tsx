import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, FileClock, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

import {
  acknowledgeGuestFinding,
  endAuditGuestSession,
  exchangeAuditGuestToken,
  getAuditGuestSession,
  type AuditGuestReadModel,
} from "../services/qmsAuditExternalAccess";
import "../styles/qms-public-audit-access.css";

function tokenFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/qms\/audit-access\/([^/]+)\/?$/i);
  return match ? decodeURIComponent(match[1]) : null;
}

function dateTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

const PublicAuditAccessPage: React.FC = () => {
  const location = useLocation();
  const inviteToken = useMemo(() => tokenFromPath(location.pathname), [location.pathname]);
  const [data, setData] = useState<AuditGuestReadModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (token: string | null = null) => {
    setLoading(true);
    setError(null);
    try {
      const next = token ? await exchangeAuditGuestToken(token) : await getAuditGuestSession();
      setData(next);
      if (token) {
        window.history.replaceState(window.history.state, document.title, "/qms/audit-access");
      }
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : "Audit access is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(inviteToken);
    // The raw invitation token is exchanged only when the URL changes. The
    // server then owns the HTTP-only guest session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inviteToken]);

  const acknowledge = async (findingId: string) => {
    setActionId(findingId);
    setError(null);
    try {
      await acknowledgeGuestFinding(findingId);
      await load(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Finding acknowledgement failed.");
    } finally {
      setActionId(null);
    }
  };

  const signOut = async () => {
    try {
      await endAuditGuestSession();
    } finally {
      setData(null);
      setError("This audit access session has ended. Reopen the original invitation link if access is still valid.");
    }
  };

  if (loading) {
    return <main className="qms-public-audit qms-public-audit--center" role="status">Opening secure audit workspace…</main>;
  }

  if (!data) {
    return (
      <main className="qms-public-audit qms-public-audit--center">
        <section className="qms-public-audit__message" role="alert">
          <AlertTriangle size={28} />
          <h1>Audit access unavailable</h1>
          <p>{error || "The invitation is invalid, expired, revoked, or no longer available."}</p>
        </section>
      </main>
    );
  }

  const canAcknowledge = data.permissions.includes("audit:acknowledge");
  const canSubmitDocuments = data.permissions.includes("audit:document_submit");

  return (
    <main className="qms-public-audit">
      <header className="qms-public-audit__header">
        <div>
          <span>SECURE AUDIT WORKSPACE</span>
          <h1>{data.audit.audit_ref || "Audit"} · {data.audit.title || "Quality audit"}</h1>
          <p>{data.participant.display_name}{data.participant.organisation ? ` · ${data.participant.organisation}` : ""}</p>
        </div>
        <div className="qms-public-audit__header-actions">
          <span>Access expires {dateTime(data.participant.expires_at)}</span>
          <button type="button" onClick={() => void load(null)}><RefreshCw size={15} /> Refresh</button>
          <button type="button" onClick={() => void signOut()}><LogOut size={15} /> End session</button>
        </div>
      </header>

      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={16} /> {error}</div> : null}

      <div className="qms-public-audit__content">
        <section className="qms-public-audit__card qms-public-audit__summary">
          <header><ShieldCheck size={19} /><div><strong>Audit scope shared with you</strong><small>This workspace is a server-filtered external view.</small></div></header>
          <dl>
            <div><dt>Scope</dt><dd>{data.audit.scope || "—"}</dd></div>
            <div><dt>Criteria</dt><dd>{data.audit.criteria || "—"}</dd></div>
            <div><dt>Planned start</dt><dd>{dateTime(data.audit.planned_start)}</dd></div>
            <div><dt>Planned end</dt><dd>{dateTime(data.audit.planned_end)}</dd></div>
          </dl>
          <p className="qms-public-audit__privacy-note">Private auditor notes, draft findings, internal Quality deliberations and unrelated assurance data are never sent to this page.</p>
        </section>

        {data.progress ? (
          <section className="qms-public-audit__card qms-public-audit__progress">
            <header><CheckCircle2 size={19} /><div><strong>Fieldwork progress</strong><small>{data.progress.completed} of {data.progress.total} checklist items completed</small></div></header>
            <div className="qms-public-audit__meter"><span style={{ width: `${data.progress.percent}%` }} /></div>
            <strong>{data.progress.percent}%</strong>
          </section>
        ) : null}

        <section className="qms-public-audit__card">
          <header><FileClock size={19} /><div><strong>Preparation requests</strong><small>Only requests assigned to this audit are shown.</small></div></header>
          {!data.document_requests.length ? <p className="qms-public-audit__empty">No preparation documents are currently requested.</p> : (
            <div className="qms-public-audit__requests">
              {data.document_requests.map((request) => (
                <article key={request.id}>
                  <div><strong>{request.title}</strong><p>{request.description || "No additional instructions."}</p><small>Due {request.due_date || "not specified"} · {request.status.replaceAll("_", " ")}</small>{request.review_note ? <blockquote>{request.review_note}</blockquote> : null}</div>
                  {canSubmitDocuments && !["ACCEPTED", "WAIVED"].includes(request.status) ? <span className="qms-public-audit__pending-control">Secure file submission is being connected to the governed evidence store.</span> : null}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="qms-public-audit__card">
          <header><AlertTriangle size={19} /><div><strong>Released findings</strong><small>Draft auditor findings do not appear here.</small></div></header>
          {!data.released_findings.length ? <p className="qms-public-audit__empty">No findings have been formally released to this workspace.</p> : (
            <div className="qms-public-audit__findings">
              {data.released_findings.map((finding) => (
                <article key={finding.id}>
                  <div className="qms-public-audit__finding-heading"><span>{finding.level.replaceAll("_", " ")} · {finding.severity}</span><strong>{finding.finding_ref || "Finding"}</strong></div>
                  <dl><div><dt>Requirement</dt><dd>{finding.requirement_ref || "—"}</dd></div></dl>
                  <p>{finding.description}</p>
                  {finding.objective_evidence ? <div className="qms-public-audit__released-evidence"><strong>Released objective evidence</strong><p>{finding.objective_evidence}</p></div> : null}
                  {finding.released_evidence_refs.length ? <ul>{finding.released_evidence_refs.map((evidence, index) => <li key={index}>{typeof evidence === "string" ? evidence : JSON.stringify(evidence)}</li>)}</ul> : null}
                  <footer>
                    {finding.acknowledged_at ? <span><CheckCircle2 size={14} /> Acknowledged {dateTime(finding.acknowledged_at)}</span> : canAcknowledge ? <button type="button" disabled={actionId === finding.id} onClick={() => void acknowledge(finding.id)}>{actionId === finding.id ? "Recording…" : "Acknowledge finding"}</button> : null}
                  </footer>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="qms-public-audit__card qms-public-audit__report-status">
          <strong>Issued report</strong>
          <span>{data.issued_report_available ? "An issued report exists for this audit." : "The governed report has not been issued yet."}</span>
        </section>
      </div>
    </main>
  );
};

export default PublicAuditAccessPage;

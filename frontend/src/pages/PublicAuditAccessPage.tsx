import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FileCheck2, FileClock, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

import ExternalAuditorFieldworkWorkspace from "../features/qms/auditSession/ExternalAuditorFieldworkWorkspace";
import GuestDocumentSubmit from "../features/qms/auditSession/GuestDocumentSubmit";
import {
  acknowledgeGuestFinding,
  acknowledgeIssuedAuditReport,
  downloadIssuedAuditReport,
  endAuditGuestSession,
  exchangeAuditGuestToken,
  getAuditGuestSession,
  getIssuedAuditReportStatus,
  type AuditGuestReadModel,
  type IssuedAuditReportStatus,
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

function shortHash(value?: string | null): string {
  if (!value) return "—";
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}

const PublicAuditAccessPage: React.FC = () => {
  const location = useLocation();
  const inviteToken = useMemo(() => tokenFromPath(location.pathname), [location.pathname]);
  const [data, setData] = useState<AuditGuestReadModel | null>(null);
  const [issuedReport, setIssuedReport] = useState<IssuedAuditReportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState<"download" | "acknowledge" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (token: string | null = null) => {
    setLoading(true);
    setError(null);
    try {
      const next = token ? await exchangeAuditGuestToken(token) : await getAuditGuestSession();
      setData(next);
      if (next.participant.participant_type === "AUDITEE_GUEST" && next.issued_report_available) {
        try {
          setIssuedReport(await getIssuedAuditReportStatus());
        } catch (cause) {
          setIssuedReport(null);
          setError(cause instanceof Error ? cause.message : "Issued report status could not be loaded.");
        }
      } else {
        setIssuedReport(null);
      }
      if (token) {
        window.history.replaceState(window.history.state, document.title, "/qms/audit-access");
      }
    } catch (cause) {
      setData(null);
      setIssuedReport(null);
      setError(cause instanceof Error ? cause.message : "Audit access is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(inviteToken);
    // The raw invitation token is exchanged only when the URL changes. The
    // server then owns the HTTP-only external audit session.
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

  const downloadReport = async () => {
    if (!issuedReport?.report) return;
    setReportBusy("download");
    setError(null);
    try {
      const blob = await downloadIssuedAuditReport();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = issuedReport.report.filename || `issued-audit-report-r${issuedReport.report.revision_no}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Issued report download failed.");
    } finally {
      setReportBusy(null);
    }
  };

  const acknowledgeReport = async () => {
    setReportBusy("acknowledge");
    setError(null);
    try {
      await acknowledgeIssuedAuditReport();
      setIssuedReport(await getIssuedAuditReportStatus());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Issued report acknowledgement failed.");
    } finally {
      setReportBusy(null);
    }
  };

  const signOut = async () => {
    try {
      await endAuditGuestSession();
    } finally {
      setData(null);
      setIssuedReport(null);
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

  const isExternalAuditor = data.participant.participant_type === "EXTERNAL_AUDITOR";
  const canAcknowledge = data.permissions.includes("audit:acknowledge");
  const canSubmitDocuments = data.permissions.includes("audit:document_submit");

  return (
    <main className="qms-public-audit">
      <header className="qms-public-audit__header">
        <div>
          <span>{isExternalAuditor ? "SECURE EXTERNAL AUDITOR WORKSPACE" : "SECURE AUDITEE WORKSPACE"}</span>
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
          <p className="qms-public-audit__privacy-note">
            {isExternalAuditor
              ? "Your assigned checklist, your own contributed notes/evidence, and explicitly scoped audit data are available here. Internal-only Quality deliberations and unrelated tenant data are not sent to this page."
              : "Private auditor notes, draft findings, internal Quality deliberations and unrelated assurance data are never sent to this page."}
          </p>
        </section>

        {data.progress ? (
          <section className="qms-public-audit__card qms-public-audit__progress">
            <header><CheckCircle2 size={19} /><div><strong>Fieldwork progress</strong><small>{data.progress.completed} of {data.progress.total} checklist items completed</small></div></header>
            <div className="qms-public-audit__meter"><span style={{ width: `${data.progress.percent}%` }} /></div>
            <strong>{data.progress.percent}%</strong>
          </section>
        ) : null}

        {isExternalAuditor ? <ExternalAuditorFieldworkWorkspace /> : (
          <>
            <section className="qms-public-audit__card">
              <header><FileClock size={19} /><div><strong>Preparation requests</strong><small>Only requests assigned to this audit are shown.</small></div></header>
              {!data.document_requests.length ? <p className="qms-public-audit__empty">No preparation documents are currently requested.</p> : (
                <div className="qms-public-audit__requests">
                  {data.document_requests.map((request) => (
                    <article key={request.id}>
                      <div><strong>{request.title}</strong><p>{request.description || "No additional instructions."}</p><small>Due {request.due_date || "not specified"} · {request.status.replaceAll("_", " ")}</small>{request.review_note ? <blockquote>{request.review_note}</blockquote> : null}</div>
                      {canSubmitDocuments && !["ACCEPTED", "WAIVED"].includes(request.status) ? <GuestDocumentSubmit requestId={request.id} onSubmitted={() => load(null)} /> : null}
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

            <section className="qms-public-audit__card qms-public-audit__report-status" aria-label="Issued audit report">
              <header><FileCheck2 size={19} /><div><strong>Issued audit report</strong><small>Only the formally issued immutable revision is exposed here.</small></div></header>
              {!data.issued_report_available || !issuedReport?.available || !issuedReport.report ? (
                <p className="qms-public-audit__empty">The governed report has not been issued yet.</p>
              ) : (
                <div className="qms-public-audit__issued-report">
                  <dl>
                    <div><dt>File</dt><dd>{issuedReport.report.filename || `Report revision ${issuedReport.report.revision_no}`}</dd></div>
                    <div><dt>Revision</dt><dd>{issuedReport.report.revision_no}</dd></div>
                    <div><dt>Issued</dt><dd>{dateTime(issuedReport.report.issued_at)}</dd></div>
                    <div><dt>SHA-256</dt><dd title={issuedReport.report.sha256}>{shortHash(issuedReport.report.sha256)}</dd></div>
                  </dl>
                  <div className="qms-public-audit__report-actions">
                    <button type="button" disabled={reportBusy !== null} onClick={() => void downloadReport()}>
                      <Download size={15} /> {reportBusy === "download" ? "Preparing…" : "Download issued report"}
                    </button>
                    {issuedReport.report.acknowledged_at ? (
                      <span><CheckCircle2 size={15} /> Receipt acknowledged {dateTime(issuedReport.report.acknowledged_at)}</span>
                    ) : canAcknowledge ? (
                      <div className="qms-public-audit__report-acknowledgement">
                        <p>{issuedReport.acknowledgement_statement}</p>
                        <button type="button" disabled={reportBusy !== null} onClick={() => void acknowledgeReport()}>
                          {reportBusy === "acknowledge" ? "Recording…" : "Acknowledge issued report"}
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
            </section>
          </>
        )}

        {isExternalAuditor ? (
          <section className="qms-public-audit__card qms-public-audit__report-status">
            <strong>Issued report</strong>
            <span>{data.issued_report_available ? "An issued report exists for this audit." : "The governed report has not been issued yet."}</span>
          </section>
        ) : null}
      </div>
    </main>
  );
};

export default PublicAuditAccessPage;

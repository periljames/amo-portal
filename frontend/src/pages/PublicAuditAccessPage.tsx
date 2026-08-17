import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  FileCheck2,
  FileClock,
  FileText,
  Fingerprint,
  LogOut,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useLocation } from "react-router-dom";

import ExternalAuditorFieldworkWorkspace from "../features/qms/auditSession/ExternalAuditorFieldworkWorkspace";
import GuestDocumentSubmit from "../features/qms/auditSession/GuestDocumentSubmit";
import { saveDownloadedFile } from "../utils/downloads";
import { downloadPublicReleasedAuditEvidence } from "../services/qmsAuditEvidence";
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
import {
  activateExternalAuditPasskeySession,
  ExternalPasskeyRequestError,
  getExternalAuditPasskeyStatus,
} from "../services/qmsAuditExternalPasskey";
import {
  getAuditGuestClosingContext,
  recordAuditGuestClosingAcknowledgement,
  type AuditGuestClosingAcknowledgement,
  type AuditGuestClosingContext,
} from "../services/qmsAuditGuestClosing";
import { heartbeatPublicAuditPresence } from "../services/qmsAuditPresence";
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

type ReleasedEvidenceArtifact = {
  artifactId: string;
  filename: string;
  sha256: string | null;
  sizeBytes: number | null;
  sourceType: string | null;
};

function releasedEvidenceArtifact(value: Record<string, unknown> | string): ReleasedEvidenceArtifact | null {
  if (!value || typeof value === "string") return null;
  const artifactId = typeof value.artifact_id === "string" ? value.artifact_id : "";
  if (!artifactId) return null;
  return {
    artifactId,
    filename: typeof value.filename === "string" && value.filename.trim() ? value.filename : "Released evidence",
    sha256: typeof value.sha256 === "string" ? value.sha256 : null,
    sizeBytes: typeof value.size_bytes === "number" ? value.size_bytes : null,
    sourceType: typeof value.source_type === "string" ? value.source_type : null,
  };
}

function auditSnapshotMetric(snapshot: Record<string, unknown> | undefined, key: string): string | number | null {
  const value = snapshot?.[key];
  return typeof value === "string" || typeof value === "number" ? value : null;
}

const PublicAuditAccessPage: React.FC = () => {
  const location = useLocation();
  const inviteToken = useMemo(() => tokenFromPath(location.pathname), [location.pathname]);
  const [data, setData] = useState<AuditGuestReadModel | null>(null);
  const [issuedReport, setIssuedReport] = useState<IssuedAuditReportStatus | null>(null);
  const [closing, setClosing] = useState<AuditGuestClosingContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState<"download" | "acknowledge" | null>(null);
  const [closingBusy, setClosingBusy] = useState(false);
  const [closingStatus, setClosingStatus] = useState<AuditGuestClosingAcknowledgement["acknowledgement_status"]>("ACKNOWLEDGED");
  const [closingComments, setClosingComments] = useState("");
  const [evidenceBusy, setEvidenceBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadSupplementary = async (next: AuditGuestReadModel) => {
    const isAuditee = next.participant.participant_type === "AUDITEE_GUEST";
    const canAcknowledge = next.permissions.includes("audit:acknowledge");
    const [reportResult, closingResult] = await Promise.allSettled([
      isAuditee && next.issued_report_available ? getIssuedAuditReportStatus() : Promise.resolve(null),
      isAuditee && canAcknowledge ? getAuditGuestClosingContext() : Promise.resolve(null),
    ]);

    if (reportResult.status === "fulfilled") setIssuedReport(reportResult.value);
    else {
      setIssuedReport(null);
      setError(reportResult.reason instanceof Error ? reportResult.reason.message : "Issued report status could not be loaded.");
    }

    if (closingResult.status === "fulfilled") setClosing(closingResult.value);
    else {
      setClosing(null);
      setError(closingResult.reason instanceof Error ? closingResult.reason.message : "Closing-meeting acknowledgement state could not be loaded.");
    }
  };

  const exchangeInvitation = async (token: string): Promise<AuditGuestReadModel> => {
    try {
      const assurance = await getExternalAuditPasskeyStatus(token);
      if (assurance.required) return activateExternalAuditPasskeySession(token);
      return exchangeAuditGuestToken(token);
    } catch (cause) {
      // The current assurance-discovery endpoint returns 403 for auditee tokens
      // and 409 for EMAIL_LINK external-auditor tokens. Those are expected
      // non-passkey invitations; all other failures remain fail-closed.
      if (cause instanceof ExternalPasskeyRequestError && [403, 409].includes(cause.status)) {
        return exchangeAuditGuestToken(token);
      }
      throw cause;
    }
  };

  const load = async (token: string | null = null) => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const next = token ? await exchangeInvitation(token) : await getAuditGuestSession();
      setData(next);
      await loadSupplementary(next);
      if (token) {
        // Remove the raw capability URL immediately after the server owns the
        // HTTP-only session. It is never copied to local/session storage.
        window.history.replaceState(window.history.state, document.title, "/qms/audit-access");
      }
    } catch (cause) {
      setData(null);
      setIssuedReport(null);
      setClosing(null);
      setError(cause instanceof Error ? cause.message : "Audit access is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(inviteToken);
    // The invitation capability is processed only when the route token changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inviteToken]);

  useEffect(() => {
    if (!data) return undefined;
    let cancelled = false;
    const heartbeat = async () => {
      try {
        if (!cancelled) await heartbeatPublicAuditPresence("audit-access");
      } catch {
        // Presence is intentionally non-blocking and the server records it only
        // when the purpose-bound grant explicitly permits progress visibility.
      }
    };
    void heartbeat();
    const timer = window.setInterval(() => void heartbeat(), 20_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [data?.audit.id, data?.participant.participant_type]);

  const acknowledge = async (findingId: string) => {
    setActionId(findingId);
    setError(null);
    setNotice(null);
    try {
      await acknowledgeGuestFinding(findingId);
      setNotice("Finding receipt recorded. This acknowledgement does not waive response, review or challenge rights.");
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
      saveDownloadedFile(
        await downloadIssuedAuditReport(),
        issuedReport.report.filename || `issued-audit-report-r${issuedReport.report.revision_no}.pdf`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Issued report download failed.");
    } finally {
      setReportBusy(null);
    }
  };

  const acknowledgeReport = async () => {
    setReportBusy("acknowledge");
    setError(null);
    setNotice(null);
    try {
      await acknowledgeIssuedAuditReport();
      setIssuedReport(await getIssuedAuditReportStatus());
      setNotice("Issued-report receipt recorded against the exact issued revision and checksum.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Issued report acknowledgement failed.");
    } finally {
      setReportBusy(null);
    }
  };

  const submitClosingAcknowledgement = async () => {
    if (!closing?.available || !closing.report || closingBusy) return;
    if (["COMMENTED", "DECLINED_TO_ACKNOWLEDGE"].includes(closingStatus) && closingComments.trim().length < 2) {
      setError("Enter the auditee comments before recording this closing-meeting response.");
      return;
    }
    setClosingBusy(true);
    setError(null);
    setNotice(null);
    try {
      await recordAuditGuestClosingAcknowledgement({
        reportRevisionId: closing.report.id,
        reportSha256: closing.report.sha256,
        acknowledgementStatus: closingStatus,
        comments: closingComments,
      });
      setClosing(await getAuditGuestClosingContext());
      setNotice("Closing-meeting response recorded against the exact draft revision and SHA-256. It does not waive any right or imply acceptance of the findings.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Closing-meeting acknowledgement failed.");
    } finally {
      setClosingBusy(false);
    }
  };

  const downloadEvidence = async (findingId: string, artifact: ReleasedEvidenceArtifact) => {
    setEvidenceBusy(artifact.artifactId);
    setError(null);
    try {
      saveDownloadedFile(await downloadPublicReleasedAuditEvidence(findingId, artifact.artifactId), artifact.filename);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Released evidence download failed.");
    } finally {
      setEvidenceBusy(null);
    }
  };

  const signOut = async () => {
    try {
      await endAuditGuestSession();
    } finally {
      setData(null);
      setIssuedReport(null);
      setClosing(null);
      setNotice(null);
      setError("This audit access session has ended. Reopen the original invitation link if access is still valid.");
    }
  };

  if (loading) return <main className="qms-public-audit qms-public-audit--center" role="status">Opening secure audit workspace…</main>;

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
  const canReadReleasedEvidence = data.permissions.includes("audit:read_released_evidence");
  const closingSnapshot = closing?.report?.report_snapshot || {};

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
          {isExternalAuditor ? <span><Fingerprint size={14} /> Purpose-bound external identity</span> : null}
          <button type="button" onClick={() => void load(null)}><RefreshCw size={15} /> Refresh</button>
          <button type="button" onClick={() => void signOut()}><LogOut size={15} /> End session</button>
        </div>
      </header>

      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={16} /> {error}</div> : null}
      {notice ? <div className="qms-public-audit__success" role="status"><CheckCircle2 size={16} /> {notice}</div> : null}

      <div className="qms-public-audit__content">
        <section className="qms-public-audit__card qms-public-audit__summary">
          <header><ShieldCheck size={19} /><div><strong>Audit scope shared with you</strong><small>This workspace is a server-filtered external projection, not an employee session.</small></div></header>
          <dl>
            <div><dt>Scope</dt><dd>{data.audit.scope || "—"}</dd></div>
            <div><dt>Criteria</dt><dd>{data.audit.criteria || "—"}</dd></div>
            <div><dt>Planned start</dt><dd>{dateTime(data.audit.planned_start)}</dd></div>
            <div><dt>Planned end</dt><dd>{dateTime(data.audit.planned_end)}</dd></div>
          </dl>
          <p className="qms-public-audit__privacy-note">
            {isExternalAuditor
              ? "Your assigned checklist, your own attributable contributions, and explicitly granted audit data are available here. Internal-only Quality deliberations and unrelated tenant data are not sent to this page."
              : "Private auditor notes, draft findings, internal Quality deliberations and unrelated assurance data are never sent to this page."}
          </p>
        </section>

        {data.progress ? (
          <section className="qms-public-audit__card qms-public-audit__progress">
            <header><Eye size={19} /><div><strong>Fieldwork progress</strong><small>{data.progress.completed} of {data.progress.total} checklist items completed</small></div></header>
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
              <header><AlertTriangle size={19} /><div><strong>Released findings</strong><small>Draft findings and private auditor notes do not appear here.</small></div></header>
              {!data.released_findings.length ? <p className="qms-public-audit__empty">No findings have been formally released to this workspace.</p> : (
                <div className="qms-public-audit__findings">
                  {data.released_findings.map((finding) => (
                    <article key={finding.id}>
                      <div className="qms-public-audit__finding-heading"><span>{finding.level.replaceAll("_", " ")} · {finding.severity}</span><strong>{finding.finding_ref || "Finding"}</strong></div>
                      <dl><div><dt>Requirement</dt><dd>{finding.requirement_ref || "—"}</dd></div></dl>
                      <p>{finding.description}</p>
                      {finding.objective_evidence ? <div className="qms-public-audit__released-evidence"><strong>Released objective evidence</strong><p>{finding.objective_evidence}</p></div> : null}
                      {finding.released_evidence_refs.length ? (
                        <div className="qms-public-audit__released-files">
                          <strong>Released evidence files</strong>
                          <ul>
                            {finding.released_evidence_refs.map((evidence, index) => {
                              const artifact = releasedEvidenceArtifact(evidence);
                              if (!artifact) return <li key={`legacy-${index}`}><FileText size={14} /><span>{typeof evidence === "string" ? evidence : "Legacy evidence reference"}</span></li>;
                              return (
                                <li key={artifact.artifactId}>
                                  <FileText size={14} />
                                  <span><b>{artifact.filename}</b><small>{artifact.sha256 ? `SHA ${shortHash(artifact.sha256)}` : "Governed artifact"}{artifact.sourceType ? ` · ${artifact.sourceType.replaceAll("_", " ")}` : ""}</small></span>
                                  {canReadReleasedEvidence ? <button type="button" disabled={evidenceBusy === artifact.artifactId} onClick={() => void downloadEvidence(finding.id, artifact)}><Download size={14} /> {evidenceBusy === artifact.artifactId ? "Opening…" : "Download"}</button> : null}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      ) : null}
                      <footer>
                        {finding.acknowledged_at ? <span><CheckCircle2 size={14} /> Finding receipt acknowledged {dateTime(finding.acknowledged_at)}</span> : canAcknowledge ? <button type="button" disabled={actionId === finding.id} onClick={() => void acknowledge(finding.id)}>{actionId === finding.id ? "Recording…" : "Acknowledge finding receipt"}</button> : null}
                      </footer>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {canAcknowledge ? (
              <section className="qms-public-audit__card qms-public-audit__closing-ack" aria-label="Closing meeting acknowledgement">
                <header><MessageSquareText size={19} /><div><strong>Closing-meeting report review</strong><small>Your response is recorded against the exact draft revision and checksum before Quality approval.</small></div></header>
                {!closing?.available || !closing.report ? (
                  <p className="qms-public-audit__empty">No governed closing report is currently awaiting your closing-meeting response.</p>
                ) : (
                  <>
                    <dl>
                      <div><dt>Draft</dt><dd>{closing.report.filename || `Report revision ${closing.report.revision_no}`}</dd></div>
                      <div><dt>Revision</dt><dd>R{closing.report.revision_no} · {closing.report.status.replaceAll("_", " ")}</dd></div>
                      <div><dt>Findings captured</dt><dd>{auditSnapshotMetric(closingSnapshot, "finding_count") ?? "—"}</dd></div>
                      <div><dt>Open findings</dt><dd>{auditSnapshotMetric(closingSnapshot, "open_finding_count") ?? "—"}</dd></div>
                      <div className="is-wide"><dt>Draft SHA-256</dt><dd><code>{closing.report.sha256}</code></dd></div>
                    </dl>
                    {closing.acknowledgement ? (
                      <div className="qms-public-audit__closing-recorded">
                        <CheckCircle2 size={16} />
                        <div><strong>{closing.acknowledgement.acknowledgement_status.replaceAll("_", " ")}</strong><small>Recorded {dateTime(closing.acknowledgement.created_at)} against SHA {shortHash(closing.acknowledgement.report_sha256)}</small>{closing.acknowledgement.comments ? <p>{closing.acknowledgement.comments}</p> : null}</div>
                      </div>
                    ) : closing.report.status === "DRAFT" ? (
                      <div className="qms-public-audit__closing-form">
                        <p><strong>This is a closing-meeting record, not a waiver.</strong> Acknowledging records that the draft conclusions were presented. Comments or declining to acknowledge do not waive any response, review, appeal or challenge right and do not imply acceptance of the findings.</p>
                        <label><span>Your closing-meeting response</span><select value={closingStatus} onChange={(event) => setClosingStatus(event.target.value as AuditGuestClosingAcknowledgement["acknowledgement_status"])}><option value="ACKNOWLEDGED">Acknowledged as presented</option><option value="COMMENTED">Comments provided</option><option value="DECLINED_TO_ACKNOWLEDGE">Decline to acknowledge</option></select></label>
                        <label><span>Comments{closingStatus === "ACKNOWLEDGED" ? " (optional)" : ""}</span><textarea rows={4} value={closingComments} onChange={(event) => setClosingComments(event.target.value)} maxLength={8000} placeholder="Record any disagreement, clarification or closing-meeting comment here." /></label>
                        <button type="button" disabled={closingBusy || (["COMMENTED", "DECLINED_TO_ACKNOWLEDGE"].includes(closingStatus) && closingComments.trim().length < 2)} onClick={() => void submitClosingAcknowledgement()}>{closingBusy ? "Recording…" : "Record response against this draft"}</button>
                      </div>
                    ) : <p>The draft is already in internal review. A new auditee response cannot be attached unless Quality returns it to draft.</p>}
                  </>
                )}
              </section>
            ) : null}

            <section className="qms-public-audit__card qms-public-audit__report-status" aria-label="Issued audit report">
              <header><FileCheck2 size={19} /><div><strong>Issued audit report</strong><small>This is separate from the closing-meeting response above. Only the formally issued immutable revision is exposed here.</small></div></header>
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
                    <button type="button" disabled={reportBusy !== null} onClick={() => void downloadReport()}><Download size={15} /> {reportBusy === "download" ? "Preparing…" : "Download issued report"}</button>
                    {issuedReport.report.acknowledged_at ? (
                      <span><CheckCircle2 size={15} /> Issued-report receipt acknowledged {dateTime(issuedReport.report.acknowledged_at)}</span>
                    ) : canAcknowledge ? (
                      <div className="qms-public-audit__report-acknowledgement">
                        <p>{issuedReport.acknowledgement_statement}</p>
                        <button type="button" disabled={reportBusy !== null} onClick={() => void acknowledgeReport()}>{reportBusy === "acknowledge" ? "Recording…" : "Acknowledge issued-report receipt"}</button>
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

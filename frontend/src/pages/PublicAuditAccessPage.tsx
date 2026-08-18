import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Download,
  Eye,
  FileCheck2,
  FileClock,
  FileText,
  Fingerprint,
  Link2,
  LogOut,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { useLocation } from "react-router-dom";

import ExternalAuditorFieldworkWorkspace from "../features/qms/auditSession/ExternalAuditorFieldworkWorkspace";
import GuestDocumentSubmit from "../features/qms/auditSession/GuestDocumentSubmit";
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
import {
  getPublicAuditCollaboration,
  linkPublicControlledDocumentRequest,
  listPublicGovernedAuditDocumentRequests,
  type PublicAuditCollaboration,
  type PublicGovernedAuditDocumentRequest,
} from "../services/qmsAuditOccurrenceCompletion";
import { heartbeatPublicAuditPresence } from "../services/qmsAuditPresence";
import { saveDownloadedFile } from "../utils/downloads";
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

function findingClassification(severity?: string | null, level?: string | null): string {
  const values = [severity?.trim(), level?.replaceAll("_", " ").trim()].filter((value): value is string => Boolean(value));
  return values.length ? values.join(" · ") : "Finding";
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

const PublicAuditAccessPage: React.FC = () => {
  const location = useLocation();
  const inviteToken = useMemo(() => tokenFromPath(location.pathname), [location.pathname]);
  const [data, setData] = useState<AuditGuestReadModel | null>(null);
  const [issuedReport, setIssuedReport] = useState<IssuedAuditReportStatus | null>(null);
  const [closing, setClosing] = useState<AuditGuestClosingContext | null>(null);
  const [collaboration, setCollaboration] = useState<PublicAuditCollaboration | null>(null);
  const [governedRequests, setGovernedRequests] = useState<PublicGovernedAuditDocumentRequest[]>([]);
  const [controlledComments, setControlledComments] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [controlledBusy, setControlledBusy] = useState<string | null>(null);
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
    const canSubmitDocuments = next.permissions.includes("audit:document_submit");
    const [reportResult, closingResult, collaborationResult, requestResult] = await Promise.allSettled([
      isAuditee && next.issued_report_available ? getIssuedAuditReportStatus() : Promise.resolve(null),
      isAuditee && canAcknowledge ? getAuditGuestClosingContext() : Promise.resolve(null),
      getPublicAuditCollaboration(),
      isAuditee && canSubmitDocuments ? listPublicGovernedAuditDocumentRequests() : Promise.resolve({ items: [] }),
    ]);

    if (reportResult.status === "fulfilled") setIssuedReport(reportResult.value);
    else setIssuedReport(null);
    if (closingResult.status === "fulfilled") setClosing(closingResult.value);
    else setClosing(null);
    if (collaborationResult.status === "fulfilled") setCollaboration(collaborationResult.value);
    else setCollaboration(null);
    if (requestResult.status === "fulfilled") setGovernedRequests(requestResult.value.items);
    else setGovernedRequests([]);

    const firstFailure = [reportResult, closingResult, collaborationResult, requestResult].find((result) => result.status === "rejected");
    if (firstFailure?.status === "rejected") setError(firstFailure.reason instanceof Error ? firstFailure.reason.message : "Some audit collaboration data could not be loaded.");
  };

  const exchangeInvitation = async (token: string): Promise<AuditGuestReadModel> => {
    try {
      const assurance = await getExternalAuditPasskeyStatus(token);
      if (assurance.required) return activateExternalAuditPasskeySession(token);
      return exchangeAuditGuestToken(token);
    } catch (cause) {
      if (cause instanceof ExternalPasskeyRequestError && [403, 409].includes(cause.status)) return exchangeAuditGuestToken(token);
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
      if (token) window.history.replaceState(window.history.state, document.title, "/qms/audit-access");
    } catch (cause) {
      setData(null);
      setIssuedReport(null);
      setClosing(null);
      setCollaboration(null);
      setGovernedRequests([]);
      setError(cause instanceof Error ? cause.message : "Audit access is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(inviteToken); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [inviteToken]);

  useEffect(() => {
    if (!data) return undefined;
    let cancelled = false;
    const heartbeat = async () => {
      try { if (!cancelled) await heartbeatPublicAuditPresence("audit-access"); } catch { /* presence is non-blocking */ }
    };
    void heartbeat();
    const timer = window.setInterval(() => void heartbeat(), 20_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [data?.audit.id, data?.participant.participant_type]);

  const acknowledge = async (findingId: string) => {
    setActionId(findingId); setError(null); setNotice(null);
    try {
      await acknowledgeGuestFinding(findingId);
      await load(null);
      setNotice("Finding receipt recorded. This does not waive response, review or challenge rights.");
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Finding acknowledgement failed."); }
    finally { setActionId(null); }
  };

  const linkControlled = async (request: PublicGovernedAuditDocumentRequest) => {
    if (!request.controlled_document_id) return;
    setControlledBusy(request.id); setError(null); setNotice(null);
    try {
      await linkPublicControlledDocumentRequest(request.id, {
        source_system: request.controlled_source_system,
        document_id: request.controlled_document_id,
        revision_id: request.controlled_revision_id,
        response_comment: controlledComments[request.id]?.trim() || null,
      });
      await load(null);
      setNotice("Controlled DMS record linked to the request. The audit team can review the exact governed document/revision without receiving an uploaded duplicate.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Controlled record could not be linked."); }
    finally { setControlledBusy(null); }
  };

  const downloadReport = async () => {
    if (!issuedReport?.report) return;
    setReportBusy("download"); setError(null);
    try { saveDownloadedFile(await downloadIssuedAuditReport(), issuedReport.report.filename || `issued-audit-report-r${issuedReport.report.revision_no}.pdf`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Issued report download failed."); }
    finally { setReportBusy(null); }
  };

  const acknowledgeReport = async () => {
    setReportBusy("acknowledge"); setError(null); setNotice(null);
    try { await acknowledgeIssuedAuditReport(); setIssuedReport(await getIssuedAuditReportStatus()); setNotice("Issued-report receipt recorded against the exact issued revision and checksum."); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Issued report acknowledgement failed."); }
    finally { setReportBusy(null); }
  };

  const submitClosingAcknowledgement = async () => {
    if (!closing?.available || !closing.report || closingBusy) return;
    if (["COMMENTED", "DECLINED_TO_ACKNOWLEDGE"].includes(closingStatus) && closingComments.trim().length < 2) { setError("Enter comments before recording this closing-meeting response."); return; }
    setClosingBusy(true); setError(null); setNotice(null);
    try {
      await recordAuditGuestClosingAcknowledgement({ reportRevisionId: closing.report.id, reportSha256: closing.report.sha256, acknowledgementStatus: closingStatus, comments: closingComments });
      setClosing(await getAuditGuestClosingContext());
      setNotice("Closing-meeting response recorded against the exact draft revision and SHA-256. It does not imply acceptance of the findings.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Closing-meeting acknowledgement failed."); }
    finally { setClosingBusy(false); }
  };

  const downloadEvidence = async (findingId: string, artifact: ReleasedEvidenceArtifact) => {
    setEvidenceBusy(artifact.artifactId); setError(null);
    try { saveDownloadedFile(await downloadPublicReleasedAuditEvidence(findingId, artifact.artifactId), artifact.filename); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Released evidence download failed."); }
    finally { setEvidenceBusy(null); }
  };

  const signOut = async () => {
    try { await endAuditGuestSession(); }
    finally {
      setData(null); setIssuedReport(null); setClosing(null); setCollaboration(null); setGovernedRequests([]); setNotice(null);
      setError("This audit access session has ended. Reopen the original invitation link if access is still valid.");
    }
  };

  if (loading) return <main className="qms-public-audit qms-public-audit--center" role="status">Opening secure audit workspace…</main>;
  if (!data) return <main className="qms-public-audit qms-public-audit--center"><section className="qms-public-audit__message" role="alert"><AlertTriangle size={28} /><h1>Audit access unavailable</h1><p>{error || "The invitation is invalid, expired, revoked, or no longer available."}</p></section></main>;

  const isExternalAuditor = data.participant.participant_type === "EXTERNAL_AUDITOR";
  const canAcknowledge = data.permissions.includes("audit:acknowledge");
  const canSubmitDocuments = data.permissions.includes("audit:document_submit");
  const canReadReleasedEvidence = data.permissions.includes("audit:read_released_evidence");
  const requestRows = governedRequests.length ? governedRequests : data.document_requests.map((row) => ({ ...row, request_type: "DOCUMENT" as const, linked_criterion: null, is_required: true, source_mode: "UPLOAD" as const, controlled_source_system: "QMS_LOCAL" as const, controlled_document_id: null, controlled_revision_id: null, controlled_submission: null }));

  return (
    <main className="qms-public-audit">
      <header className="qms-public-audit__header">
        <div><span>{isExternalAuditor ? "SECURE EXTERNAL AUDITOR WORKSPACE" : "SECURE AUDITEE WORKSPACE"}</span><h1>{data.audit.audit_ref || "Audit"} · {data.audit.title || "Quality audit"}</h1><p>{data.participant.display_name}{data.participant.organisation ? ` · ${data.participant.organisation}` : ""}</p></div>
        <div className="qms-public-audit__header-actions"><span>Access expires {dateTime(data.participant.expires_at)}</span>{isExternalAuditor ? <span><Fingerprint size={14} /> Purpose-bound external identity</span> : null}<button type="button" onClick={() => void load(null)}><RefreshCw size={15} /> Refresh</button><button type="button" onClick={() => void signOut()}><LogOut size={15} /> End session</button></div>
      </header>
      {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={16} /> {error}</div> : null}
      {notice ? <div className="qms-public-audit__success" role="status"><CheckCircle2 size={16} /> {notice}</div> : null}

      <div className="qms-public-audit__content">
        <section className="qms-public-audit__card qms-public-audit__summary"><header><ShieldCheck size={19} /><div><strong>Audit scope shared with you</strong><small>Server-filtered external projection; this is not an employee session.</small></div></header><dl><div><dt>Scope</dt><dd>{data.audit.scope || "—"}</dd></div><div><dt>Criteria</dt><dd>{data.audit.criteria || "—"}</dd></div><div><dt>Planned start</dt><dd>{dateTime(data.audit.planned_start)}</dd></div><div><dt>Planned end</dt><dd>{dateTime(data.audit.planned_end)}</dd></div></dl><p className="qms-public-audit__privacy-note">{isExternalAuditor ? "Only your assigned audit data and attributable contributions are available here." : "Private auditor notes, draft findings, internal Quality deliberations and unrelated tenant data are never sent to this page."}</p></section>

        {collaboration?.meetings.length ? <section className="qms-public-audit__card"><header><CalendarClock size={19} /><div><strong>Audit meetings</strong><small>Opening, closing and follow-up meetings explicitly scheduled for this occurrence.</small></div></header><div className="qms-public-audit__requests">{collaboration.meetings.map((meeting) => <article key={meeting.id}><div><strong>{meeting.meeting_type.replaceAll("_", " ")}</strong><p>{meeting.agenda || "No agenda published."}</p><small>{dateTime(meeting.scheduled_start)}{meeting.scheduled_end ? ` – ${dateTime(meeting.scheduled_end)}` : ""}</small><small>{meeting.location || "No physical location"}{meeting.conference_url ? ` · ${meeting.conference_url}` : ""} · {meeting.status.replaceAll("_", " ")}</small></div></article>)}</div></section> : null}

        {data.progress ? <section className="qms-public-audit__card qms-public-audit__progress"><header><Eye size={19} /><div><strong>Fieldwork progress</strong><small>{data.progress.completed} of {data.progress.total} checklist items completed</small></div></header><div className="qms-public-audit__meter"><span style={{ width: `${data.progress.percent}%` }} /></div><strong>{data.progress.percent}%</strong></section> : null}

        {isExternalAuditor ? <ExternalAuditorFieldworkWorkspace /> : <>
          <section className="qms-public-audit__card"><header><FileClock size={19} /><div><strong>Preparation requests</strong><small>Respond by secure upload or, where Quality preselected one, by linking the controlled DMS record without duplicating it.</small></div></header>{!requestRows.length ? <p className="qms-public-audit__empty">No preparation documents are currently requested.</p> : <div className="qms-public-audit__requests">{requestRows.map((request) => <article key={request.id}><div><strong>{request.title}</strong><p>{request.description || "No additional instructions."}</p><small>{request.request_type.replaceAll("_", " ")} · {request.is_required ? "Required" : "Optional"} · due {request.due_date || "not specified"} · {request.status.replaceAll("_", " ")}</small>{request.linked_criterion ? <blockquote><strong>Criterion:</strong> {request.linked_criterion}</blockquote> : null}{request.review_note ? <blockquote>Quality review: {request.review_note}</blockquote> : null}</div>{canSubmitDocuments && !["ACCEPTED", "WAIVED"].includes(request.status) ? <div>{request.source_mode !== "CONTROLLED_DMS" ? <GuestDocumentSubmit requestId={request.id} onSubmitted={() => load(null)} /> : null}{request.controlled_document_id && request.source_mode !== "UPLOAD" ? <div className="qms-public-audit__controlled-link"><Link2 size={15} /><strong>Controlled DMS record authorised for this request</strong><small>Document {request.controlled_document_id}{request.controlled_revision_id ? ` · revision ${request.controlled_revision_id}` : ""}</small>{request.controlled_submission ? <small>Linked {dateTime(request.controlled_submission.created_at)}</small> : <><textarea rows={2} value={controlledComments[request.id] || ""} onChange={(event) => setControlledComments((current) => ({ ...current, [request.id]: event.target.value }))} placeholder="Optional response note" /><button type="button" disabled={controlledBusy === request.id} onClick={() => void linkControlled(request)}>{controlledBusy === request.id ? "Linking…" : "Use this controlled record"}</button></>}</div> : null}</div> : null}</article>)}</div>}</section>

          <section className="qms-public-audit__card"><header><MessageSquareText size={19} /><div><strong>Released findings</strong><small>Only findings deliberately released by Quality are visible.</small></div></header>{!data.released_findings.length ? <p className="qms-public-audit__empty">No findings have been released to you.</p> : <div className="qms-public-audit__findings">{data.released_findings.map((finding) => { const artifacts = finding.released_evidence_refs.map(releasedEvidenceArtifact).filter((artifact): artifact is ReleasedEvidenceArtifact => Boolean(artifact)); return <article key={finding.id}><div><span>{findingClassification(finding.severity, finding.level)}</span><strong>{finding.finding_ref || "Finding"}</strong><small>{finding.requirement_ref || "No requirement reference"}</small><p>{finding.description}</p>{finding.objective_evidence ? <blockquote>{finding.objective_evidence}</blockquote> : null}{canReadReleasedEvidence && artifacts.length ? <div>{artifacts.map((artifact) => <button type="button" key={artifact.artifactId} disabled={evidenceBusy === artifact.artifactId} onClick={() => void downloadEvidence(finding.id, artifact)}><Download size={14} /> {artifact.filename}{artifact.sha256 ? ` · ${shortHash(artifact.sha256)}` : ""}</button>)}</div> : null}</div>{canAcknowledge && !finding.acknowledged_at ? <button type="button" disabled={actionId === finding.id} onClick={() => void acknowledge(finding.id)}>Acknowledge finding</button> : <small>{finding.acknowledged_at ? `Acknowledged · ${dateTime(finding.acknowledged_at)}` : ""}</small>}</article>; })}</div>}</section>

          {collaboration?.cars.length ? <section className="qms-public-audit__card"><header><Wrench size={19} /><div><strong>Corrective actions shared with you</strong><small>These CARs are linked only to findings that Quality explicitly released.</small></div></header><div className="qms-public-audit__requests">{collaboration.cars.map((car) => <article key={car.id}><div><strong>{car.car_number} · {car.title}</strong><p>{car.summary}</p><small>{car.finding_ref || "Finding"} · {car.priority || "Priority not stated"} · {car.status || "Open"}</small><small>Target closure {car.target_closure_date || car.due_date || "not set"}</small></div></article>)}</div></section> : null}

          {collaboration?.closing_narrative && (collaboration.closing_narrative.management_summary || collaboration.closing_narrative.conclusion || collaboration.closing_narrative.positive_practices) ? <section className="qms-public-audit__card"><header><FileText size={19} /><div><strong>Closing meeting narrative</strong><small>The narrative used by the governed report generator.</small></div></header>{collaboration.closing_narrative.management_summary ? <><strong>Management summary</strong><p>{collaboration.closing_narrative.management_summary}</p></> : null}{collaboration.closing_narrative.conclusion ? <><strong>Conclusion</strong><p>{collaboration.closing_narrative.conclusion}</p></> : null}{collaboration.closing_narrative.positive_practices ? <><strong>Positive practices</strong><p>{collaboration.closing_narrative.positive_practices}</p></> : null}</section> : null}

          {closing?.available && closing.report ? <section className="qms-public-audit__card" aria-label="Closing meeting acknowledgement"><header><FileCheck2 size={19} /><div><strong>Closing report response</strong><small>Bound to draft R{closing.report.revision_no} · SHA {shortHash(closing.report.sha256)}</small></div></header>{closing.acknowledgement ? <div className="qms-public-audit__success"><CheckCircle2 size={15} /> {closing.acknowledgement.acknowledgement_status.replaceAll("_", " ")}{closing.acknowledgement.comments ? ` · ${closing.acknowledgement.comments}` : ""}</div> : <><label><span>Response</span><select value={closingStatus} onChange={(event) => setClosingStatus(event.target.value as AuditGuestClosingAcknowledgement["acknowledgement_status"])}><option value="ACKNOWLEDGED">Acknowledge closing draft</option><option value="COMMENTED">Comment on closing draft</option><option value="DECLINED_TO_ACKNOWLEDGE">Decline acknowledgement</option></select></label><label><span>Comments</span><textarea rows={4} value={closingComments} onChange={(event) => setClosingComments(event.target.value)} /></label><button type="button" disabled={closingBusy} onClick={() => void submitClosingAcknowledgement()}>{closingBusy ? "Recording…" : "Record closing response"}</button><p className="qms-public-audit__privacy-note">This records your response to the exact draft. It is not a waiver and does not mean you accept the findings.</p></>}</section> : null}

          {issuedReport?.available && issuedReport.report ? <section className="qms-public-audit__card" aria-label="Issued audit report"><header><FileText size={19} /><div><strong>Issued audit report</strong><small>Formal issued revision and checksum.</small></div></header><dl><div><dt>File</dt><dd>{issuedReport.report.filename}</dd></div><div><dt>Revision</dt><dd>{issuedReport.report.revision_no}</dd></div><div><dt>SHA-256</dt><dd>{shortHash(issuedReport.report.sha256)}</dd></div><div><dt>Issued</dt><dd>{dateTime(issuedReport.report.issued_at)}</dd></div></dl><p>{issuedReport.acknowledgement_statement}</p><div><button type="button" disabled={reportBusy !== null} onClick={() => void downloadReport()}><Download size={15} /> {reportBusy === "download" ? "Downloading…" : "Download issued report"}</button>{!issuedReport.report.acknowledged_at ? <button type="button" disabled={reportBusy !== null} onClick={() => void acknowledgeReport()}>{reportBusy === "acknowledge" ? "Recording…" : "Acknowledge issued report"}</button> : <span>Receipt acknowledged {dateTime(issuedReport.report.acknowledged_at)}</span>}</div></section> : null}
        </>}
      </div>
    </main>
  );
};

export default PublicAuditAccessPage;

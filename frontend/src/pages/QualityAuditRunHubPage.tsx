import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarClock, ClipboardList, FileText, FolderKanban, MailCheck, PackageCheck, ShieldAlert, TimerReset, Users } from "lucide-react";
import AuditPageShell from "../components/QMS/AuditPageShell";
import { getCachedUser, getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import {
  downloadAuditEvidencePack,
  qmsCloseAudit,
  qmsGetAuditRegister,
  qmsGetAuditWorkflow,
  qmsIssueAuditNotice,
  qmsResolveAudit,
  qmsListCars,
  qmsListCarAttachmentsBulk,
  qmsUploadAuditChecklist,
  qmsUploadAuditReport,
} from "../services/qms";
import { saveDownloadedFile } from "../utils/downloads";
import { buildAuditWorkspacePath, isUuidLike, toAuditReferenceSlug } from "../utils/auditSlug";

const TABS = ["war-room", "checklist", "findings", "cars", "evidence", "report", "closeout"] as const;
type WorkspaceTab = typeof TABS[number];

const tabLabels: Record<WorkspaceTab, string> = {
  "war-room": "War room",
  checklist: "Checklist",
  findings: "Findings",
  cars: "CARs",
  evidence: "Evidence",
  report: "Report",
  closeout: "Closeout",
};

const safeTab = (value: string | null): WorkspaceTab => (TABS.includes((value ?? "") as WorkspaceTab) ? (value as WorkspaceTab) : "war-room");
const dateFmt = (value: string | null | undefined) => (value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");

function formatRelative(days: number): string {
  if (days === 0) return "today";
  if (days > 0) return `in ${days} day${days === 1 ? "" : "s"}`;
  const overdue = Math.abs(days);
  return `${overdue} day${overdue === 1 ? "" : "s"} overdue`;
}

function buildScheduleCard(audit: { audit_ref: string; status: string; planned_start: string | null; planned_end: string | null } | null, now: Date) {
  if (!audit) return { tone: "muted", label: "Schedule", value: "Not available", meta: "This audit has no schedule attached." };
  if (audit.status === "IN_PROGRESS") {
    return { tone: "progress", label: audit.audit_ref, value: "In progress", meta: `${dateFmt(audit.planned_start)} → ${dateFmt(audit.planned_end)}` };
  }
  const start = audit.planned_start ? new Date(audit.planned_start) : null;
  const end = audit.planned_end ? new Date(audit.planned_end) : start;
  if (start && !Number.isNaN(start.getTime())) {
    const startDays = Math.ceil((start.getTime() - now.getTime()) / 86_400_000);
    if (startDays >= 0) {
      return { tone: "planned", label: audit.audit_ref, value: `Starts ${dateFmt(audit.planned_start)}`, meta: formatRelative(startDays) };
    }
  }
  if (end && !Number.isNaN(end.getTime()) && audit.status !== "CLOSED") {
    const endDays = Math.ceil((end.getTime() - now.getTime()) / 86_400_000);
    if (endDays < 0) {
      return { tone: "overdue", label: audit.audit_ref, value: `Was due ${dateFmt(audit.planned_end || audit.planned_start)}`, meta: formatRelative(endDays) };
    }
  }
  return { tone: "muted", label: audit.audit_ref, value: `Scheduled ${dateFmt(audit.planned_start)}`, meta: `${dateFmt(audit.planned_start)} → ${dateFmt(audit.planned_end)}` };
}

const lifecycleGuide = [
  "Schedule the audit with participants, scope, criteria, and notice rules.",
  "Prepare the audit by loading the checklist and pre-audit information.",
  "Capture fieldwork findings and convert non-conformities into CARs.",
  "Review responses, verify evidence, and confirm corrective action closure.",
  "Upload the report and close the audit only when closure conditions are met.",
];

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const auditKey = params.auditId ?? "";
  const activeTab = safeTab(searchParams.get("tab"));
  const [tick, setTick] = useState(Date.now());
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [guideDismissed, setGuideDismissed] = useState(false);

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const key = `qms-audit-run-guide-dismissed:${amoCode}`;
    if (typeof window === "undefined") return;
    setGuideDismissed(window.localStorage.getItem(key) === "1");
  }, [amoCode]);

  const dismissGuide = () => {
    const key = `qms-audit-run-guide-dismissed:${amoCode}`;
    setGuideDismissed(true);
    if (typeof window !== "undefined") window.localStorage.setItem(key, "1");
  };

  const auditContextQuery = useQuery({
    queryKey: ["qms-audit-context", auditKey],
    queryFn: async () => {
      if (isUuidLike(auditKey)) {
        return qmsGetAuditWorkflow(auditKey, { silent: true });
      }
      const resolved = await qmsResolveAudit(auditKey, { silent: true });
      if (!resolved) return null;
      return qmsGetAuditWorkflow(resolved.id, { silent: true });
    },
    enabled: !!auditKey,
    staleTime: 30_000,
  });

  const audit = auditContextQuery.data?.audit ?? null;

  useEffect(() => {
    if (!audit) return;
    const canonical = toAuditReferenceSlug(audit.audit_ref);
    if (!canonical) return;
    if (auditKey !== canonical) {
      navigate(`${buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref })}?tab=${activeTab}`, { replace: true });
    }
  }, [activeTab, amoCode, audit, auditKey, department, navigate]);

  const registerQuery = useQuery({
    queryKey: ["qms-audit-register", "workspace", audit?.id],
    queryFn: () => qmsGetAuditRegister({ audit_id: audit!.id, limit: 200 }, { silent: true }),
    enabled: !!audit?.id,
    staleTime: 60_000,
  });

  const findings = registerQuery.data?.rows ?? [];
  const cars = useQuery({
    queryKey: ["qms-cars", "workspace", audit?.id],
    queryFn: () => qmsListCars({ audit_id: audit!.id, limit: 200 }, { silent: true }),
    staleTime: 60_000,
    enabled: !!audit?.id && ["war-room", "cars", "evidence", "closeout"].includes(activeTab),
  });
  const attachments = useQuery({
    queryKey: ["qms-car-attachments", "workspace", audit?.id],
    queryFn: () => qmsListCarAttachmentsBulk({ car_ids: (cars.data ?? []).map((car) => car.id) }),
    enabled: activeTab === "evidence" && (cars.data?.length ?? 0) > 0,
    staleTime: 60_000,
  });

  const carIdsForAudit = useMemo(() => new Set((cars.data ?? []).map((c) => c.id)), [cars.data]);

  const evidenceCount = useMemo(() => {
    const attachmentCount = (attachments.data ?? []).filter((a) => carIdsForAudit.has(a.car_id)).length;
    return attachmentCount + (audit?.checklist_file_ref ? 1 : 0) + (audit?.report_file_ref ? 1 : 0);
  }, [attachments.data, audit?.checklist_file_ref, audit?.report_file_ref, carIdsForAudit]);

  const canEditChecklist = useMemo(() => {
    if (!currentUser || !audit) return false;
    if (currentUser.is_superuser || currentUser.is_amo_admin) return true;
    return [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(currentUser.id);
  }, [audit, currentUser]);

  const scheduleCard = useMemo(() => buildScheduleCard(audit, new Date(tick)), [audit, tick]);
  const checklistUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist` : "";
  const reportUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/report` : "";
  const workflow = auditContextQuery.data?.workflow;
  const allCars = cars.data ?? [];
  const openCars = allCars.filter((car) => car.status !== "CLOSED");
  const openFindings = findings.filter((row) => !row.finding.closed_at);
  const assignedAuditors = [
    { label: "Lead", value: audit?.lead_auditor_user_id },
    { label: "Observer", value: audit?.observer_auditor_user_id },
    { label: "Assistant", value: audit?.assistant_auditor_user_id },
  ].filter((item) => item.value);

  const refetchAuditData = async () => {
    await auditContextQuery.refetch();
    await registerQuery.refetch();
    await cars.refetch();
  };

  const issueNotice = useMutation({
    mutationFn: () => audit ? qmsIssueAuditNotice(audit.id, { stage: "manual" }) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: () => { void refetchAuditData(); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to issue audit notice."),
  });

  const closeAudit = useMutation({
    mutationFn: () => audit ? qmsCloseAudit(audit.id) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: () => { void refetchAuditData(); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to close audit."),
  });

  const exportPack = useMutation({
    mutationFn: () => audit ? downloadAuditEvidencePack(audit.id) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: (file) => { saveDownloadedFile(file); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to export audit evidence pack."),
  });

  const setTab = (tab: WorkspaceTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={audit?.title || "Audit workspace"}
      subtitle={audit?.audit_ref || "Resolve audit"}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/qms`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/qms/audits`) },
        { label: audit?.audit_ref || auditKey },
      ]}
      toolbar={
        <div className={`audit-countdown-card audit-countdown-card--${scheduleCard.tone}`}>
          <div className="audit-countdown-card__label"><TimerReset size={13} /> {scheduleCard.label}</div>
          <div className="audit-countdown-card__value">{scheduleCard.value}</div>
          <div className="audit-countdown-card__meta">{scheduleCard.meta}</div>
        </div>
      }
      nav={
        <div className="audit-shell-segmented" role="tablist" aria-label="Audit workspace sections">
          {TABS.map((tab) => (
            <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={`audit-shell-segmented__button ${activeTab === tab ? "is-active" : ""}`} onClick={() => setTab(tab)}>
              {tabLabels[tab]}
            </button>
          ))}
        </div>
      }
    >
      {!audit ? <div className="qms-card">{isUuidLike(auditKey) ? "Resolving audit..." : "Audit not found."}</div> : null}
      {audit && (
        <>
          {!guideDismissed ? (
            <div className="qms-card audit-guide-card">
              <div className="audit-guide-card__header">
                <div>
                  <p className="audit-guide-card__eyebrow">Execution guide</p>
                  <h3 className="audit-guide-card__title">How this audit should move from plan to closure</h3>
                </div>
                <button type="button" className="secondary-chip-btn" onClick={dismissGuide}>Dismiss</button>
              </div>
              <div className="audit-guide-card__grid">
                {lifecycleGuide.map((item, index) => (
                  <div key={item} className="audit-guide-card__step">
                    <strong>{index + 1}</strong>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="qms-card audit-progress-card">
            <div className="audit-progress-card__header">
              <div>
                <p className="audit-progress-card__eyebrow">Audit progress</p>
                <h3 className="audit-progress-card__title">{workflow ? `${workflow.current_stage_label} · ${workflow.percent_complete}% complete` : "Loading workflow status..."}</h3>
              </div>
              <div className="audit-progress-card__stats">
                <span className="qms-pill">Findings open: {workflow?.findings_open ?? 0}</span>
                <span className="qms-pill">CARs open: {workflow?.cars_open ?? 0}</span>
                <span className="qms-pill">Checklist: {workflow?.checklist_uploaded ? "Ready" : "Pending"}</span>
                <span className="qms-pill">Report: {workflow?.report_uploaded ? "Ready" : "Pending"}</span>
              </div>
            </div>
            <div className="audit-progress-bar" aria-hidden="true">
              <div className="audit-progress-bar__fill" style={{ width: `${workflow?.percent_complete ?? 0}%` }} />
            </div>
            <div className="audit-progress-steps">
              {(workflow?.stages ?? []).map((stage) => (
                <div key={stage.id} className={`audit-progress-step${stage.complete ? " is-complete" : ""}${stage.active ? " is-active" : ""}`}>
                  <strong>{stage.label}</strong>
                  <span>{stage.metric || stage.helper || ""}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="qms-card">
            <div className="audit-chip-list" style={{ marginBottom: 10 }}>
              <span className="qms-pill">{audit.status}</span>
              <span className="qms-pill">{audit.kind}</span>
              <span className="qms-pill">Lead: {audit.lead_auditor_user_id || "Unassigned"}</span>
              <span className="qms-pill">Window: {dateFmt(audit.planned_start)} → {dateFmt(audit.planned_end)}</span>
            </div>
            {actionError ? <p className="text-danger">{actionError}</p> : null}

            {activeTab === "war-room" && (
              <div className="audit-war-room-grid">
                <section className="audit-war-room-card">
                  <h3><Users size={16} /> Audit team and notices</h3>
                  <p className="text-muted">Notices are sent through the existing backend dispatch, which creates portal notifications and email log entries for assigned auditors and auditees.</p>
                  <dl className="planner-review-list">
                    <div><dt>Lead auditor</dt><dd>{audit.lead_auditor_user_id || "Unassigned"}</dd></div>
                    <div><dt>Observer</dt><dd>{audit.observer_auditor_user_id || "Not assigned"}</dd></div>
                    <div><dt>Assistant</dt><dd>{audit.assistant_auditor_user_id || "Not assigned"}</dd></div>
                    <div><dt>Auditee</dt><dd>{audit.auditee || audit.auditee_email || audit.auditee_user_id || "Not set"}</dd></div>
                    <div><dt>Notice state</dt><dd>Upcoming: {audit.upcoming_notice_sent_at ? dateFmt(audit.upcoming_notice_sent_at) : "not sent"} · Day-of: {audit.day_of_notice_sent_at ? dateFmt(audit.day_of_notice_sent_at) : "not sent"}</dd></div>
                  </dl>
                  <div className="qms-header__actions">
                    <button type="button" className="secondary-chip-btn" onClick={() => issueNotice.mutate()} disabled={issueNotice.isPending || !assignedAuditors.length}>
                      <MailCheck size={14} /> {issueNotice.isPending ? "Sending…" : "Send notice now"}
                    </button>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/qms/audits/schedule`)}>Open planner</button>
                  </div>
                  {!assignedAuditors.length ? <p className="text-danger">Assign at least a lead auditor before sending notices.</p> : null}
                </section>
                <section className="audit-war-room-card">
                  <h3><PackageCheck size={16} /> Closure readiness</h3>
                  <div className="audit-progress-card__stats">
                    <span className="qms-pill">Open findings: {openFindings.length}</span>
                    <span className="qms-pill">Open CARs: {openCars.length}</span>
                    <span className="qms-pill">Checklist: {audit.checklist_file_ref ? "Ready" : "Missing"}</span>
                    <span className="qms-pill">Report: {audit.report_file_ref ? "Ready" : "Missing"}</span>
                  </div>
                  <p className="text-muted">Use findings and CAR tabs for fieldwork and corrective action. Closeout is blocked by the backend until report/checklist and CAR verification rules pass.</p>
                  <div className="qms-header__actions">
                    <button type="button" className="secondary-chip-btn" onClick={() => exportPack.mutate()} disabled={exportPack.isPending}>
                      <FolderKanban size={14} /> {exportPack.isPending ? "Packaging…" : "Export evidence pack"}
                    </button>
                    <button type="button" className="secondary-chip-btn" onClick={() => setTab("closeout")}>Go to closeout</button>
                  </div>
                </section>
              </div>
            )}

            {activeTab === "checklist" && (
              <div>
                <h3><ClipboardList size={16} /> Checklist</h3>
                <p className="text-muted">Checklist: {audit.checklist_file_ref ? "Available" : "Not uploaded"}</p>
                <div className="qms-header__actions" style={{ marginBottom: 8 }}>
                  <a className="secondary-chip-btn" href={checklistUrl} target="_blank" rel="noreferrer">Open checklist</a>
                  <a className={`secondary-chip-btn${!audit.report_file_ref ? " disabled" : ""}`} href={audit.report_file_ref ? reportUrl : undefined} target="_blank" rel="noreferrer" onClick={(e) => { if (!audit.report_file_ref) e.preventDefault(); }}>
                    Open report
                  </a>
                </div>
                <label className="qms-field" style={{ maxWidth: 460 }}>
                  Upload checklist (PDF / DOC / DOCX)
                  <input
                    type="file"
                    accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={!canEditChecklist || uploading}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file || !audit.id) return;
                      setUploading(true);
                      setUploadError(null);
                      qmsUploadAuditChecklist(audit.id, file)
                        .then(() => {
                          void auditContextQuery.refetch();
                          void registerQuery.refetch();
                        })
                        .catch((err: any) => setUploadError(err?.message || "Failed to upload checklist."))
                        .finally(() => setUploading(false));
                      e.currentTarget.value = "";
                    }}
                  />
                </label>
                {!canEditChecklist ? <p className="text-muted">Read-only for users who are not assigned to this audit.</p> : null}
                {uploadError ? <p className="text-danger">{uploadError}</p> : null}
              </div>
            )}

            {activeTab === "findings" && (
              <div>
                <h3><FileText size={16} /> Findings</h3>
                <p>{findings.length} findings are linked to this audit.</p>
              </div>
            )}
            {activeTab === "cars" && (
              <div>
                <h3><ShieldAlert size={16} /> CARs</h3>
                <p>{allCars.length || findings.flatMap((row) => row.linked_cars).length} CARs are linked to this audit. Open CARs: {openCars.length}.</p>
                <div className="audit-chip-list">
                  {(allCars.length ? allCars : findings.flatMap((row) => row.linked_cars)).map((car) => (
                    <button key={car.id} type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/qms/cars/${car.id}/overview`)}>
                      {car.car_number} · {car.status}
                    </button>
                  ))}
                </div>
                <p className="text-muted">Issue new CARs from finding records. Auditee responses and quality review stay on the CAR workspace and feed this audit closeout state.</p>
              </div>
            )}
            {activeTab === "evidence" && (
              <div>
                <h3><FolderKanban size={16} /> Evidence</h3>
                <p><strong>Audit scope:</strong> {`${audit.audit_ref} — ${audit.title}`}</p>
                <p>{evidenceCount} files are available for this audit context.</p>
              </div>
            )}
            {activeTab === "report" && (
              <div>
                <h3><FileText size={16} /> Report</h3>
                <p className="text-muted">{audit.report_file_ref ? "Report available" : "No report uploaded."}</p>
                <div className="qms-header__actions" style={{ marginBottom: 8 }}>
                  {audit.report_file_ref ? <a className="secondary-chip-btn" href={reportUrl} target="_blank" rel="noreferrer">Open report</a> : null}
                  <label className="secondary-chip-btn">
                    Upload report
                    <input
                      type="file"
                      style={{ display: "none" }}
                      accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      disabled={!canEditChecklist || uploading}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file || !audit.id) return;
                        setUploading(true);
                        setUploadError(null);
                        qmsUploadAuditReport(audit.id, file)
                          .then(() => void refetchAuditData())
                          .catch((err: any) => setUploadError(err?.message || "Failed to upload report."))
                          .finally(() => setUploading(false));
                        e.currentTarget.value = "";
                      }}
                    />
                  </label>
                </div>
                {uploadError ? <p className="text-danger">{uploadError}</p> : null}
              </div>
            )}
            {activeTab === "closeout" && (
              <div>
                <h3><CalendarClock size={16} /> Closeout Log</h3>
                <p>Open findings: {openFindings.length}</p>
                <p>Open CARs: {openCars.length}</p>
                <p className="text-muted">Closure follows the backend rules: checklist/report required, all NC findings must have CARs, CAR root cause/CAPA must be accepted, and required evidence must be verified.</p>
                <div className="qms-header__actions">
                  <button type="button" className="secondary-chip-btn" onClick={() => exportPack.mutate()} disabled={exportPack.isPending}>
                    <PackageCheck size={14} /> {exportPack.isPending ? "Packaging…" : "Package evidence"}
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => closeAudit.mutate()} disabled={closeAudit.isPending || audit.status === "CLOSED"}>
                    {closeAudit.isPending ? "Closing…" : audit.status === "CLOSED" ? "Audit closed" : "Close audit"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </AuditPageShell>
  );
};

export default QualityAuditRunHubPage;

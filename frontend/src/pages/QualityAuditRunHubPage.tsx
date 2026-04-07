import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ClipboardList, FileText, FolderKanban, ShieldAlert, TimerReset } from "lucide-react";
import AuditPageShell from "../components/QMS/AuditPageShell";
import { getCachedUser, getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import { qmsGetAuditRegister, qmsListAudits, qmsListCars, qmsListCarAttachmentsBulk, qmsListFindingsBulk, qmsUploadAuditChecklist } from "../services/qms";
import { buildAuditWorkspacePath, isUuidLike, toAuditReferenceSlug } from "../utils/auditSlug";

const TABS = ["checklist", "findings", "cars", "evidence", "report", "closeout"] as const;
type WorkspaceTab = typeof TABS[number];

const safeTab = (value: string | null): WorkspaceTab => (TABS.includes((value ?? "") as WorkspaceTab) ? (value as WorkspaceTab) : "checklist");

const dateFmt = (value: string | null | undefined) => (value ? new Date(value).toLocaleDateString() : "—");

const dueCard = (audit: { status: string; planned_start: string | null; planned_end: string | null } | null, now: Date) => {
  if (!audit) return { label: "No schedule", tone: "muted" };
  if (audit.status === "IN_PROGRESS") return { label: "In progress", tone: "progress" };
  const start = audit.planned_start ? new Date(audit.planned_start) : null;
  const end = audit.planned_end ? new Date(audit.planned_end) : start;
  if (start) {
    const days = Math.ceil((start.getTime() - now.getTime()) / 86_400_000);
    if (days > 0) return { label: `Starts in ${days} day${days === 1 ? "" : "s"}`, tone: "planned" };
    if (days === 0) return { label: "Starts today", tone: "planned" };
  }
  if (end && now.getTime() > end.getTime() && audit.status !== "CLOSED") {
    const days = Math.ceil((now.getTime() - end.getTime()) / 86_400_000);
    return { label: `Overdue by ${days} day${days === 1 ? "" : "s"}`, tone: "overdue" };
  }
  return { label: "Scheduled", tone: "muted" };
};

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

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "run-workspace", amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const audit = useMemo(() => {
    const rows = auditsQuery.data ?? [];
    const byId = rows.find((row) => row.id === auditKey);
    if (byId) return byId;
    const key = auditKey.toUpperCase();
    return rows.find((row) => toAuditReferenceSlug(row.audit_ref) === key) ?? null;
  }, [auditKey, auditsQuery.data]);

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
    queryFn: () => qmsGetAuditRegister({ domain: "AMO" }),
    enabled: !!audit?.id,
    staleTime: 60_000,
  });

  const findings = useMemo(() => (registerQuery.data?.rows ?? []).filter((row) => row.audit.id === audit?.id), [audit?.id, registerQuery.data?.rows]);
  const cars = useQuery({ queryKey: ["qms-cars", "workspace", audit?.id], queryFn: () => qmsListCars({}), staleTime: 60_000, enabled: activeTab === "evidence" && !!audit?.id });
  const findingsBulk = useQuery({ queryKey: ["qms-findings", "workspace", audit?.id], queryFn: () => qmsListFindingsBulk({ domain: "AMO", audit_ids: audit?.id ? [audit.id] : [] }), staleTime: 60_000, enabled: activeTab === "evidence" && !!audit?.id });
  const attachments = useQuery({
    queryKey: ["qms-car-attachments", "workspace", audit?.id],
    queryFn: () => qmsListCarAttachmentsBulk({ car_ids: (cars.data ?? []).map((car) => car.id) }),
    enabled: activeTab === "evidence" && (cars.data?.length ?? 0) > 0,
    staleTime: 60_000,
  });

  const carIdsForAudit = useMemo(() => {
    const findingIds = new Set((findingsBulk.data ?? []).map((f) => f.id));
    return new Set((cars.data ?? []).filter((c) => c.finding_id && findingIds.has(c.finding_id)).map((c) => c.id));
  }, [cars.data, findingsBulk.data]);

  const evidenceCount = useMemo(() => {
    const attachmentCount = (attachments.data ?? []).filter((a) => carIdsForAudit.has(a.car_id)).length;
    return attachmentCount + (audit?.checklist_file_ref ? 1 : 0) + (audit?.report_file_ref ? 1 : 0);
  }, [attachments.data, audit?.checklist_file_ref, audit?.report_file_ref, carIdsForAudit]);

  const canEditChecklist = useMemo(() => {
    if (!currentUser || !audit) return false;
    if (currentUser.is_superuser || currentUser.is_amo_admin) return true;
    return [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(currentUser.id);
  }, [audit, currentUser]);

  const statusCard = dueCard(audit, new Date(tick));
  const checklistUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist` : "";
  const reportUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/report` : "";

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
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits`) },
        { label: audit?.audit_ref || auditKey },
      ]}
      toolbar={
        <div className={`audit-countdown-card audit-countdown-card--${statusCard.tone}`}>
          <div className="audit-countdown-card__label"><TimerReset size={13} /> Audit clock</div>
          <div className="audit-countdown-card__value">{statusCard.label}</div>
          <div className="audit-countdown-card__meta">{dateFmt(audit?.planned_start)} → {dateFmt(audit?.planned_end)}</div>
        </div>
      }
      nav={
        <div className="audit-shell-segmented" role="tablist" aria-label="Audit workspace sections">
          {TABS.map((tab) => (
            <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={`audit-shell-segmented__button ${activeTab === tab ? "is-active" : ""}`} onClick={() => setTab(tab)}>
              {tab}
            </button>
          ))}
        </div>
      }
    >
      {!audit ? <div className="qms-card">{isUuidLike(auditKey) ? "Resolving audit..." : "Audit not found."}</div> : null}
      {audit && (
        <div className="qms-card">
          <div className="audit-chip-list" style={{ marginBottom: 10 }}>
            <span className="qms-pill">{audit.status}</span>
            <span className="qms-pill">{audit.kind}</span>
            <span className="qms-pill">Lead: {audit.lead_auditor_user_id || "Unassigned"}</span>
          </div>

          {activeTab === "checklist" && (
            <div>
              <h3><ClipboardList size={16} /> Checklist</h3>
              <p className="text-muted">Checklist: {audit.checklist_file_ref ? "Available" : "Not uploaded"}</p>
              <div className="qms-header__actions" style={{ marginBottom: 8 }}>
                <a className="secondary-chip-btn" href={checklistUrl} target="_blank" rel="noreferrer">Open checklist</a>
                <a className={`secondary-chip-btn${!audit.report_file_ref ? " disabled" : ""}`} href={audit.report_file_ref ? reportUrl : undefined} target="_blank" rel="noreferrer" onClick={(e) => { if (!audit.report_file_ref) e.preventDefault(); }}>Open report</a>
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
                      .then(() => auditsQuery.refetch())
                      .catch((err: any) => setUploadError(err?.message || "Failed to upload checklist."))
                      .finally(() => setUploading(false));
                    e.currentTarget.value = "";
                  }}
                />
              </label>
              {!canEditChecklist ? <p className="text-muted">Read-only for non-assigned users.</p> : null}
              {uploadError ? <p className="text-danger">{uploadError}</p> : null}
            </div>
          )}

          {activeTab === "findings" && <div><h3><FileText size={16} /> Findings</h3><p>{findings.length} findings linked to this audit.</p></div>}
          {activeTab === "cars" && <div><h3><ShieldAlert size={16} /> CARs</h3><p>{findings.flatMap((r) => r.linked_cars).length} CARs linked to findings in this audit.</p></div>}
          {activeTab === "evidence" && <div><h3><FolderKanban size={16} /> Evidence</h3><p><strong>Filtered by audit:</strong> {`${audit.audit_ref} — ${audit.title}`}</p><p>{evidenceCount} files available for this audit context.</p></div>}
          {activeTab === "report" && <div><h3><FileText size={16} /> Report</h3><p className="text-muted">{audit.report_file_ref ? "Report available" : "No report uploaded."}</p>{audit.report_file_ref ? <a className="secondary-chip-btn" href={reportUrl} target="_blank" rel="noreferrer">Open report</a> : null}</div>}
          {activeTab === "closeout" && <div><h3><CalendarClock size={16} /> Closeout Log</h3><p>Open findings: {findings.filter((row) => !row.finding.closed_at).length}</p></div>}
        </div>
      )}
    </AuditPageShell>
  );
};

export default QualityAuditRunHubPage;

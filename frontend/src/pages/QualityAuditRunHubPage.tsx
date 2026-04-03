import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getCachedUser, getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import { qmsListAudits, qmsUploadAuditChecklist } from "../services/qms";
import { getDueMessage } from "./qualityAudits/dueStatus";

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const auditId = params.auditId ?? "";
  const [tick, setTick] = useState(Date.now());
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const base = `/maintenance/${amoCode}/${department}/qms`;

  const auditQuery = useQuery({
    queryKey: ["qms-audits", "run-hub", auditId, amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 20_000,
    refetchInterval: 20_000,
    enabled: !!auditId,
  });

  const audit = useMemo(() => (auditQuery.data ?? []).find((row) => row.id === auditId) || null, [auditId, auditQuery.data]);
  const canEditChecklist = useMemo(() => {
    if (!currentUser || !audit) return false;
    if (currentUser.is_superuser || currentUser.is_amo_admin) return true;
    return [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(currentUser.id);
  }, [audit, currentUser]);

  const dueBanner = getDueMessage(new Date(tick), null, audit?.planned_start, audit?.planned_end);
  const checklistUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist` : "";
  const reportUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/report` : "";

  return (
    <QualityAuditsSectionLayout title="Audit Run Hub" subtitle="Checklist execution workspace for one audit.">
      {dueBanner ? <div className="qms-card" style={{ marginBottom: 12 }}><strong>{dueBanner.label}</strong></div> : null}
      <div className="qms-card" style={{ marginBottom: 12 }}>
        <div className="qms-nav__items">
          <button type="button" className="qms-nav__link is-active">Checklist</button>
          <button type="button" className="qms-nav__link" onClick={() => navigate(`${base}/audits/register?tab=findings&auditId=${auditId}`)}>Findings</button>
          <button type="button" className="qms-nav__link" onClick={() => navigate(`${base}/audits/register?tab=cars&auditId=${auditId}`)}>CARs</button>
          <button type="button" className="qms-nav__link" onClick={() => navigate(`${base}/evidence?auditId=${auditId}`)}>Evidence</button>
          <a className={`qms-nav__link${!audit?.report_file_ref ? " disabled" : ""}`} href={audit?.report_file_ref ? reportUrl : undefined} target="_blank" rel="noreferrer" onClick={(e) => { if (!audit?.report_file_ref) e.preventDefault(); }}>Report</a>
          <button type="button" className="qms-nav__link" onClick={() => navigate(`${base}/audits/register?tab=findings&auditId=${auditId}`)}>Closeout Log</button>
        </div>
      </div>

      <div className="qms-card">
        {audit ? (
          <>
            <p><strong>{audit.audit_ref}</strong> · {audit.title}</p>
            <p className="text-muted">Checklist: {audit.checklist_file_ref ? "Available" : "Not uploaded"} · Report: {audit.report_file_ref ? "Available" : "Not uploaded"}</p>
            <p className="text-muted">Upcoming notice: {audit.upcoming_notice_sent_at || "—"} · Day-of notice: {audit.day_of_notice_sent_at || "—"}</p>
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
                  if (!file || !auditId) return;
                  setUploading(true);
                  setUploadError(null);
                  qmsUploadAuditChecklist(auditId, file)
                    .then(() => auditQuery.refetch())
                    .catch((err: any) => setUploadError(err?.message || "Failed to upload checklist."))
                    .finally(() => setUploading(false));
                  e.currentTarget.value = "";
                }}
              />
            </label>
            {!canEditChecklist ? <p className="text-muted">Read-only for non-assigned users.</p> : null}
            {uploadError ? <p className="text-danger">{uploadError}</p> : null}
          </>
        ) : <p className="text-muted">Audit not found.</p>}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRunHubPage;

import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getCachedUser, getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import { qmsListAudits, qmsUploadAuditChecklist } from "../services/qms";

const tabs = [
  { key: "checklist", label: "Checklist" },
  { key: "findings", label: "Findings" },
  { key: "cars", label: "CARs" },
  { key: "evidence", label: "Evidence" },
  { key: "report", label: "Report" },
  { key: "closeout", label: "Closeout Log" },
] as const;

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const auditId = params.auditId ?? "";

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const base = `/maintenance/${amoCode}/${department}/qms`;

  const auditQuery = useQuery({
    queryKey: ["qms-audits", "run-hub", auditId],
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

  const checklistUrl = audit ? `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist` : "";
  const shareChecklistView = audit
    ? `${window.location.origin}/maintenance/${amoCode}/${department}/qms/evidence/checklist-${audit.id}?name=${encodeURIComponent(`${audit.audit_ref}-checklist`)}&mime=${encodeURIComponent("application/pdf")}&url=${encodeURIComponent(checklistUrl)}&source=${encodeURIComponent(`${audit.audit_ref} checklist`)}`
    : "";

  const openTab = (tab: (typeof tabs)[number]["key"]) => {
    if (tab === "evidence") {
      navigate(`${base}/audits/${auditId}/evidence`);
      return;
    }
    if (tab === "cars") {
      navigate(`${base}/audits/closeout/cars`);
      return;
    }
    if (tab === "findings") {
      navigate(`${base}/audits/${auditId}/findings`);
      return;
    }
    if (tab === "checklist") {
      return;
    }
    if (tab === "report") {
      navigate(`${base}/audits/${auditId}`);
      return;
    }
    if (tab === "closeout") {
      navigate(`${base}/audits/closeout/findings`);
    }
  };

  const handleChecklistUpload = async (file?: File) => {
    if (!file || !auditId) return;
    const lower = file.name.toLowerCase();
    const accepted = lower.endsWith(".pdf") || lower.endsWith(".doc") || lower.endsWith(".docx");
    if (!accepted) {
      setUploadError("Checklist must be PDF, DOC, or DOCX.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      await qmsUploadAuditChecklist(auditId, file);
      await auditQuery.refetch();
    } catch (e: any) {
      setUploadError(e?.message || "Failed to upload checklist.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <QualityAuditsSectionLayout title="Audit Run Hub" subtitle="Guided workflow from planning to evidence-backed closeout.">
      <div className="qms-card" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>Closeout workflow (no ambiguity)</h3>
        <ol>
          <li><strong>Plan / schedule:</strong> confirm scope, dates, and team in planner.</li>
          <li><strong>Checklist collaboration:</strong> upload checklist (PDF/DOC/DOCX), share read-only view to auditee in real time.</li>
          <li><strong>Issue CARs:</strong> raise and assign CARs for all NC findings.</li>
          <li><strong>Verify evidence:</strong> review inline evidence, add reviewer markup, and export reviewed copy.</li>
          <li><strong>Closeout:</strong> ensure CAR acceptance + verified evidence, then complete closeout log.</li>
        </ol>
        <div className="qms-header__actions">
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${base}/audits/plan`)}>Open planner</button>
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${base}/audits/register`)}>Open register</button>
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${base}/evidence`)}>Open evidence library</button>
        </div>
      </div>

      <div className="qms-card" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>Checklist sharing during fieldwork</h3>
        {audit ? (
          <>
            <p style={{ marginBottom: 8 }}>
              <strong>{audit.audit_ref}</strong> · {audit.title} · status <strong>{audit.status}</strong>
            </p>
            <p className="text-muted" style={{ marginTop: 0 }}>
              Sync refreshes every 20 seconds so auditor and auditee can stay aligned while fieldwork is active.
            </p>
            <div className="qms-header__actions" style={{ marginBottom: 8 }}>
              <a className="secondary-chip-btn" href={checklistUrl} target="_blank" rel="noreferrer">Open checklist file</a>
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => navigator.clipboard?.writeText(shareChecklistView)}
                disabled={!shareChecklistView}
              >
                Copy read-only share link
              </button>
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/evidence/checklist-${audit.id}?name=${encodeURIComponent(`${audit.audit_ref}-checklist`)}&mime=${encodeURIComponent("application/pdf")}&url=${encodeURIComponent(checklistUrl)}&source=${encodeURIComponent(`${audit.audit_ref} checklist`)}`)}
              >
                Open shared viewer
              </button>
            </div>

            <label className="qms-field" style={{ maxWidth: 460 }}>
              Upload checklist (PDF / DOC / DOCX)
              <input
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disabled={!canEditChecklist || uploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  void handleChecklistUpload(file);
                  e.currentTarget.value = "";
                }}
              />
            </label>
            {!canEditChecklist ? (
              <p className="text-muted">Read-only mode: only assigned auditors or admins can update checklist ticks/comments.</p>
            ) : null}
            {uploadError ? <p className="text-danger">{uploadError}</p> : null}
            {uploading ? <p>Uploading checklist…</p> : null}
          </>
        ) : (
          <p className="text-muted">Audit details unavailable. Open planner/register and select an audit run.</p>
        )}
      </div>

      <div className="qms-nav__items">
        {tabs.map((tab) => (
          <button type="button" key={tab.key} className="qms-nav__link" onClick={() => openTab(tab.key)}>{tab.label}</button>
        ))}
      </div>

      <div className="qms-card">
        <p>
          This run hub keeps planner, findings, CARs, and evidence connected so the closure decision is traceable and auditable.
        </p>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRunHubPage;

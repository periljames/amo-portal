import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getContext } from "../services/auth";

const tabs = [
  { key: "checklist", label: "Checklist" },
  { key: "findings", label: "Findings" },
  { key: "cars", label: "CARs" },
  { key: "evidence", label: "Evidence" },
  { key: "report", label: "Report" },
  { key: "closeout", label: "Closeout Log" },
] as const;

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const auditId = params.auditId ?? "";

  const openTab = (tab: (typeof tabs)[number]["key"]) => {
    if (tab === "evidence") {
      navigate(`/maintenance/${amoCode}/quality/audits/${auditId}/evidence`);
      return;
    }
    if (tab === "cars") {
      navigate(`/maintenance/${amoCode}/quality/qms/cars`);
      return;
    }
    if (tab === "findings") {
      navigate(`/maintenance/${amoCode}/quality/audits/closeout/findings`);
      return;
    }
  };

  return (
    <QualityAuditsSectionLayout title="Audit Run Hub" subtitle="Single place for checklist execution, findings, CARs, evidence and closeout logs.">
      <div className="qms-nav__items">
        {tabs.map((tab) => (
          <button type="button" key={tab.key} className="qms-nav__link" onClick={() => openTab(tab.key)}>{tab.label}</button>
        ))}
      </div>
      <div className="qms-card">
        <p>Select a tab to continue. Checklist, report, and closeout entries use existing audit data while Evidence routes to the first-class evidence page.</p>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRunHubPage;

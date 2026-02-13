import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";

const QualityAuditEvidencePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";

  return (
    <QMSLayout amoCode={amoCode} department="quality" title="Audit Evidence" subtitle="Audit-specific evidence review and attachments.">
      <div className="qms-card">
        <p>Audit: {params.auditId}</p>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/evidence`)}>Open global evidence library</button>
      </div>
    </QMSLayout>
  );
};

export default QualityAuditEvidencePage;

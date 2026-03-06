import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getContext } from "../services/auth";

const QualityAuditEvidencePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";

  return (
    <QualityAuditsSectionLayout title="Audit Evidence" subtitle="Review and validate audit evidence inline before closeout.">
      <div className="qms-card">
        <p><strong>Audit:</strong> {params.auditId}</p>
        <p>
          Use the evidence library viewer to open PDFs inline, add reviewer markups (page/point/reference), and export a reviewed copy for audit traceability.
        </p>
        <div className="qms-header__actions">
          <button type="button" className="btn btn-primary" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/evidence`)}>
            Open evidence library
          </button>
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/closeout/findings`)}>
            Back to closeout findings
          </button>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditEvidencePage;

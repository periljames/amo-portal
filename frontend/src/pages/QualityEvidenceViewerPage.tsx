import React from "react";
import { useParams } from "react-router-dom";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";

const QualityEvidenceViewerPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; evidenceId?: string }>();

  return (
    <QualityAuditsSectionLayout title="Evidence Viewer" subtitle="Inline review surface integrated with Action Panel workflows.">
      <div className="qms-card">
        <p><strong>Evidence ID:</strong> {params.evidenceId}</p>
        <p>Use this viewer to inspect supporting files and complete review decisions from closeout queues.</p>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceViewerPage;

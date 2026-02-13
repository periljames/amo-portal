import React from "react";
import { useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";

const QualityEvidenceViewerPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; evidenceId?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";

  return (
    <QMSLayout amoCode={amoCode} department="quality" title="Evidence Viewer" subtitle="Inline review surface integrated with Action Panel workflows.">
      <div className="qms-card">
        <p><strong>Evidence ID:</strong> {params.evidenceId}</p>
        <p>Use this viewer to inspect supporting files and complete review decisions from closeout queues.</p>
      </div>
    </QMSLayout>
  );
};

export default QualityEvidenceViewerPage;

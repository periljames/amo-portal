import React from "react";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { qmsListAudits, qmsListFindings } from "../services/qms";

const QualityCloseoutFindingsPage: React.FC = () => {
  const audits = useQuery({ queryKey: ["qms-audits"], queryFn: () => qmsListAudits({ domain: "AMO", status_: "IN_PROGRESS" }) });
  const firstAuditId = audits.data?.[0]?.id;
  const findings = useQuery({ queryKey: ["qms-findings", firstAuditId], queryFn: () => qmsListFindings(firstAuditId || ""), enabled: !!firstAuditId });

  return (
    <QualityAuditsSectionLayout title="Closeout Workbench · Findings" subtitle="Reviewer queue with inline evidence notes and decision logging.">
      <div className="qms-card">
        {(findings.data ?? []).map((row) => (
          <div key={row.id} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
            <strong>{row.finding_ref || row.id}</strong>
            <p>{row.description}</p>
            <small>Evidence: {row.objective_evidence || "None attached"}</small>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button type="button" className="btn btn-primary">Accept</button>
              <button type="button" className="secondary-chip-btn">Reject</button>
              <button type="button" className="secondary-chip-btn">Revoke</button>
            </div>
          </div>
        ))}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityCloseoutFindingsPage;

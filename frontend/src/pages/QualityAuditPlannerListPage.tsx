import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { qmsListAuditSchedules } from "../services/qms";

const QualityAuditPlannerListPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const query = useQuery({ queryKey: ["qms-audit-schedules", amoCode], queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }), staleTime: 60_000 });

  return (
    <QMSLayout amoCode={amoCode} department="quality" title="Audit Planner · List" subtitle="Schedules sorted for operational planning.">
      <div className="qms-header__actions">
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/calendar`)}>Calendar</button>
      </div>
      <div className="qms-card">
        <table className="data-table">
          <thead><tr><th>Title</th><th>Due</th><th>Frequency</th><th>Auditor</th><th/></tr></thead>
          <tbody>
            {(query.data ?? []).map((row) => (
              <tr key={row.id}><td>{row.title}</td><td>{row.next_due_date}</td><td>{row.frequency}</td><td>{row.lead_auditor_user_id ?? "Unassigned"}</td><td><button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/${row.id}`)}>View</button></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </QMSLayout>
  );
};

export default QualityAuditPlannerListPage;

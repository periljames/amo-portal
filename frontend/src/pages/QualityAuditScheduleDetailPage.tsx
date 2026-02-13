import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import EmptyState from "../components/shared/EmptyState";
import { getContext } from "../services/auth";
import { qmsListAuditSchedules } from "../services/qms";

const QualityAuditScheduleDetailPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; scheduleId?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const scheduleId = params.scheduleId ?? "";
  const query = useQuery({ queryKey: ["qms-audit-schedules", amoCode], queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }), staleTime: 60_000 });
  const schedule = (query.data ?? []).find((row) => row.id === scheduleId);

  return (
    <QualityAuditsSectionLayout title="Schedule Detail" subtitle="Scope, assignment and conflict insights for planners.">
      {!schedule ? <EmptyState title="Schedule not found" description="The schedule is missing or inactive." action={<button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/list`)}>Back to list</button>} /> : (
        <div className="qms-card">
          <h3>{schedule.title}</h3>
          <p>{schedule.scope || "No scope summary available."}</p>
          <p><strong>Next due:</strong> {schedule.next_due_date}</p>
          <p><strong>Lead auditor:</strong> {schedule.lead_auditor_user_id ?? "Unassigned"}</p>
          <p><strong>Observer:</strong> {schedule.observer_auditor_user_id ?? "None"}</p>
          <p><strong>Assistant:</strong> {schedule.assistant_auditor_user_id ?? "None"}</p>
        </div>
      )}
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditScheduleDetailPage;

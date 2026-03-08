import React from "react";
import { useParams } from "react-router-dom";
import { getContext } from "../services/auth";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import AuditDetailView from "./qualityAudits/AuditDetailView";

const QualityAuditScheduleDetailPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; scheduleId?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const scheduleId = params.scheduleId ?? "";

  return (
    <QualityAuditsSectionLayout title="Schedule Detail" subtitle="Compliance intelligence war room for audit execution.">
      <AuditDetailView amoCode={amoCode} department={department} scheduleId={scheduleId} />
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditScheduleDetailPage;

import React from "react";
import { Navigate, useParams } from "react-router-dom";

/**
 * Schedule templates are managed in the Quality Operations Planner. This route
 * remains only as a bookmark-safe redirect; no separate schedule-detail editing
 * lifecycle is retained.
 */
const QualityAuditScheduleDetailPage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string; scheduleId?: string }>();
  return <Navigate replace to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`} />;
};

export default QualityAuditScheduleDetailPage;

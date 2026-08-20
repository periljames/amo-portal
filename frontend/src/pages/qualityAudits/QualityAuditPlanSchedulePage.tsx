import React from "react";
import { Navigate, useParams } from "react-router-dom";

/**
 * Historical audit-plan URLs now resolve to the single authoritative Quality
 * Operations Planner. Keeping this tiny route target prevents stale bookmarks
 * from becoming dead links without retaining a second scheduling UI or API.
 */
export default function QualityAuditPlanSchedulePage(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  return <Navigate replace to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`} />;
}

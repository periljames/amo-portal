import React from "react";
import { Navigate, useLocation } from "react-router-dom";

import { hasQmsRolePermission } from "../app/routeGuards";
import QmsCanonicalPage from "./qms/QmsCanonicalPage";
import QualityAuditRunHubPageImpl from "./QualityAuditRunHubPageImpl";

const PROGRAMME_SCHEDULE_ROUTE = /\/maintenance\/([^/]+)\/(?:quality|qms)\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i;

/**
 * Reserve programme-governance URLs before the generic audit-run hub treats the
 * `program` path segment as an audit identifier. Scheduling mutates the governed
 * planner, so view-only assurance users are returned to the programme workspace
 * rather than being routed into an endpoint they cannot authorise.
 */
export default function QualityAuditRunHubPage(): React.ReactElement {
  const location = useLocation();
  const scheduleMatch = location.pathname.match(PROGRAMME_SCHEDULE_ROUTE);
  if (scheduleMatch) {
    if (!hasQmsRolePermission("qms.audit.manage")) {
      const amoCode = decodeURIComponent(scheduleMatch[1]);
      return <Navigate replace to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program`} />;
    }
    return <QmsCanonicalPage />;
  }
  return <QualityAuditRunHubPageImpl />;
}

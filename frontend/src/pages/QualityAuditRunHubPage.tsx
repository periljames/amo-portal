import React from "react";
import { useLocation } from "react-router-dom";

import QmsCanonicalPage from "./qms/QmsCanonicalPage";
import QualityAuditRunHubPageImpl from "./QualityAuditRunHubPageImpl";

const PROGRAMME_SCHEDULE_ROUTE = /\/maintenance\/[^/]+\/(?:quality|qms)\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i;

/**
 * Reserve programme-governance URLs before the generic audit-run hub treats the
 * `program` path segment as an audit identifier. The public route table keeps its
 * existing tenant and QMS permission guards; this wrapper only selects the
 * correct governed workspace after those guards have passed.
 */
export default function QualityAuditRunHubPage(): React.ReactElement {
  const location = useLocation();
  if (PROGRAMME_SCHEDULE_ROUTE.test(location.pathname)) {
    return <QmsCanonicalPage />;
  }
  return <QualityAuditRunHubPageImpl />;
}

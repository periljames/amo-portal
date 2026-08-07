import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityFormalReviewWorkspace from "./ReliabilityFormalReviewWorkspace";
import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityWorkspaceLegacy from "./ReliabilityWorkspaceLegacy";

const WORKBOOK_PARITY_ROUTES = new Set([
  "workbook-parity",
  "workbook-registers",
  "statistical-alerts",
  "workbook-mapping",
  "workbook-reports",
]);

const FORMAL_REPORTING_ROUTES = new Set([
  "formal-review",
  "formal-reports",
  "programme-reports",
]);

function reliabilitySurface(pathname: string): "analytics" | "formal" | "parity" | "legacy" {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  if (parts.length === 0 || parts[0] === "workbench") return "analytics";
  if (FORMAL_REPORTING_ROUTES.has(parts[0])) return "formal";
  if (WORKBOOK_PARITY_ROUTES.has(parts[0])) return "parity";
  return "legacy";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  const surface = reliabilitySurface(location.pathname);
  if (surface === "analytics") return <ReliabilityAnalyticsWorkspace />;
  if (surface === "formal") return <ReliabilityFormalReviewWorkspace />;
  if (surface === "parity") return <ReliabilityWorkbookParityWorkspace />;
  return <ReliabilityWorkspaceLegacy />;
};

export default ReliabilityWorkspacePage;

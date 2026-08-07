import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityWorkspaceLegacy from "./ReliabilityWorkspaceLegacy";

const WORKBOOK_PARITY_ROUTES = new Set([
  "workbook-parity",
  "workbook-registers",
  "statistical-alerts",
  "workbook-mapping",
  "workbook-reports",
]);

function reliabilitySurface(pathname: string): "analytics" | "parity" | "legacy" {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  if (parts.length === 0 || parts[0] === "workbench") return "analytics";
  if (WORKBOOK_PARITY_ROUTES.has(parts[0])) return "parity";
  return "legacy";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  const surface = reliabilitySurface(location.pathname);
  if (surface === "analytics") return <ReliabilityAnalyticsWorkspace />;
  if (surface === "parity") return <ReliabilityWorkbookParityWorkspace />;
  return <ReliabilityWorkspaceLegacy />;
};

export default ReliabilityWorkspacePage;
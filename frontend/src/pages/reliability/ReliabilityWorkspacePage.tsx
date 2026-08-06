import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityWorkspaceLegacy from "./ReliabilityWorkspaceLegacy";

function reliabilitySurface(pathname: string): "analytics" | "parity" | "legacy" {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  if (parts.length === 0 || parts[0] === "workbench") return "analytics";
  if (parts[0] === "workbook-parity") return "parity";
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

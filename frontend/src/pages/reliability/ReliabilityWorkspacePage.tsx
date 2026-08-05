import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityWorkspaceLegacy from "./ReliabilityWorkspaceLegacy";

function isAnalyticsWorkbench(pathname: string): boolean {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  return parts.length === 0 || parts[0] === "workbench";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  return isAnalyticsWorkbench(location.pathname)
    ? <ReliabilityAnalyticsWorkspace />
    : <ReliabilityWorkspaceLegacy />;
};

export default ReliabilityWorkspacePage;

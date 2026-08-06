import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityWorkspaceLegacy from "./ReliabilityWorkspaceLegacy";

function isWorkbookParity(pathname: string): boolean {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  return parts[0] === "workbook-parity";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  return isWorkbookParity(location.pathname)
    ? <ReliabilityWorkbookParityWorkspace />
    : <ReliabilityWorkspaceLegacy />;
};

export default ReliabilityWorkspacePage;

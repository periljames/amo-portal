import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityFormalGovernanceWorkspace from "./ReliabilityFormalGovernanceWorkspace";
import ReliabilityFormalReviewWorkspace from "./ReliabilityFormalReviewWorkspace";
import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityOperationsWorkspace from "./ReliabilityOperationsWorkspace";
import ReliabilityOCTMWorkspace from "./ReliabilityOCTMWorkspace";
import { ReliabilityModuleShell } from "./ReliabilityModuleShell";

const WORKBOOK_PARITY_ROUTES = new Set([
  "workbook-parity",
  "workbook-registers",
  "statistical-alerts",
  "workbook-mapping",
  "workbook-reports", "workbook-imports", "workbook-csv", "management-reports",
]);

const FORMAL_REVIEW_ROUTES = new Set(["formal-review"]);
const FORMAL_GOVERNANCE_ROUTES = new Set(["formal-reports", "programme-reports", "report-distribution"]);

function reliabilitySurface(pathname: string): "analytics" | "formal-review" | "formal-governance" | "parity" | "operations" {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  if (parts.length === 0 || parts[0] === "workbench" || parts[0] === "analytics") return "analytics";
  if (FORMAL_REVIEW_ROUTES.has(parts[0])) return "formal-review";
  if (FORMAL_GOVERNANCE_ROUTES.has(parts[0])) return "formal-governance";
  if (WORKBOOK_PARITY_ROUTES.has(parts[0])) return "parity";
  return "operations";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  const surface = reliabilitySurface(location.pathname);
  const first = location.pathname.split("/reliability/")[1]?.split("/")[0];
  const content = first === "octm" ? <ReliabilityOCTMWorkspace />
    : surface === "analytics" ? <ReliabilityAnalyticsWorkspace />
    : surface === "formal-review" ? <ReliabilityFormalReviewWorkspace />
    : surface === "formal-governance" ? <ReliabilityFormalGovernanceWorkspace />
    : surface === "parity" ? <ReliabilityWorkbookParityWorkspace />
    : <ReliabilityOperationsWorkspace />;
  return <ReliabilityModuleShell>{content}</ReliabilityModuleShell>;
};

export default ReliabilityWorkspacePage;

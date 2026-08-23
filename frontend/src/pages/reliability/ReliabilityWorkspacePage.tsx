import React from "react";
import { useLocation } from "react-router-dom";

import ReliabilityAnalyticsWorkspace from "./ReliabilityAnalyticsWorkspace";
import ReliabilityFormalGovernanceWorkspace from "./ReliabilityFormalGovernanceWorkspace";
import ReliabilityFormalReviewWorkspace from "./ReliabilityFormalReviewWorkspace";
import ReliabilityWorkbookParityWorkspace from "./ReliabilityWorkbookParityWorkspace";
import ReliabilityOperationsWorkspace from "./ReliabilityOperationsWorkspace";

const WORKBOOK_PARITY_ROUTES = new Set([
  "workbook-parity",
  "workbook-registers",
  "statistical-alerts",
  "workbook-mapping",
  "workbook-reports",
]);

const FORMAL_REVIEW_ROUTES = new Set(["formal-review"]);
const FORMAL_GOVERNANCE_ROUTES = new Set(["formal-reports", "programme-reports"]);

function reliabilitySurface(pathname: string): "analytics" | "formal-review" | "formal-governance" | "parity" | "operations" {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  if (parts.length === 0 || parts[0] === "workbench") return "analytics";
  if (FORMAL_REVIEW_ROUTES.has(parts[0])) return "formal-review";
  if (FORMAL_GOVERNANCE_ROUTES.has(parts[0])) return "formal-governance";
  if (WORKBOOK_PARITY_ROUTES.has(parts[0])) return "parity";
  return "operations";
}

const ReliabilityWorkspacePage: React.FC = () => {
  const location = useLocation();
  const surface = reliabilitySurface(location.pathname);
  if (surface === "analytics") return <ReliabilityAnalyticsWorkspace />;
  if (surface === "formal-review") return <ReliabilityFormalReviewWorkspace />;
  if (surface === "formal-governance") return <ReliabilityFormalGovernanceWorkspace />;
  if (surface === "parity") return <ReliabilityWorkbookParityWorkspace />;
  return <ReliabilityOperationsWorkspace />;
};

export default ReliabilityWorkspacePage;

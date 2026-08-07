import React from "react";
import { useLocation } from "react-router-dom";
import QualityCarsPage from "../QualityCarsPage";
import QmsCanonicalLegacyPage from "./QmsCanonicalLegacyPage";
import QmsRegisterPage from "./QmsRegisterPage";
import QmsPlannerLivePage from "./planner/QmsPlannerLivePage";

/**
 * Canonical compatibility dispatcher.
 *
 * Active list workspaces should have one owner. Calendar belongs to the planner,
 * evidence-vault list views use the bounded register workspace, CAR register and
 * creation routes stay on the established specialist CAR workflow, and remaining
 * legacy/detail paths stay on the compatibility surface until their specialist
 * replacement is explicitly wired.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const isPlannerRoute = /\/quality\/calendar(?:\/|$)/i.test(location.pathname)
    || /\/qms\/calendar(?:\/|$)/i.test(location.pathname);
  const isEvidenceRegister = /\/quality\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  const isCarWorkspace = /\/quality\/cars(?:\/(?:register|new|overdue|due-soon|awaiting-auditee|awaiting-quality-review|awaiting-effectiveness-review|closed))?\/?$/i.test(location.pathname);

  if (isPlannerRoute) return <QmsPlannerLivePage />;
  if (isEvidenceRegister) return <QmsRegisterPage />;
  if (isCarWorkspace) return <QualityCarsPage />;
  return <QmsCanonicalLegacyPage />;
}
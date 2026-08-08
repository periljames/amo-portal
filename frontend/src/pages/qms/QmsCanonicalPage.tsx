import React from "react";
import { useLocation } from "react-router-dom";
import QualityCarsPage from "../QualityCarsPage";
import QmsAuditProgrammeSchedulePage from "./QmsAuditProgrammeSchedulePage";
import QmsAuditProgrammeWorkspacePage from "./QmsAuditProgrammeWorkspacePage";
import QmsCanonicalLegacyPage from "./QmsCanonicalLegacyPage";
import QmsRegisterPage from "./QmsRegisterPage";
import QmsPlannerLivePage from "./planner/QmsPlannerLivePage";

/**
 * Canonical compatibility dispatcher.
 *
 * Active list workspaces should have one owner. Calendar belongs to the planner,
 * the governed Audit Programme owns /audits/program, evidence-vault list views
 * use the bounded register workspace, CAR routes stay on the established specialist
 * CAR workflow, and remaining legacy/detail paths stay on the compatibility surface
 * until their specialist replacement is wired.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const pathname = location.pathname.toLowerCase();

  // CAR/CAPA has a governed specialist workspace with creation, assignment,
  // auditee response, evidence, Quality review and closeout controls. Never let
  // a CAR route fall through to the generic canonical register reader.
  if (pathname.includes("/quality/cars") || pathname.includes("/qms/cars")) {
    return <QualityCarsPage />;
  }

  if (/\/(?:quality|qms)\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i.test(location.pathname)) {
    return <QmsAuditProgrammeSchedulePage />;
  }

  if (/\/(?:quality|qms)\/audits\/program\/?$/i.test(location.pathname)) {
    return <QmsAuditProgrammeWorkspacePage />;
  }

  if (pathname.includes("/quality/calendar") || pathname.includes("/qms/calendar")) {
    return <QmsPlannerLivePage />;
  }

  const isEvidenceRegister = /\/quality\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  if (isEvidenceRegister) return <QmsRegisterPage />;

  return <QmsCanonicalLegacyPage />;
}

import React from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import QualityCarsPage from "../QualityCarsPage";
import QmsAuditProgrammeSchedulePage from "./QmsAuditProgrammeSchedulePage";
import QmsAuditProgrammeWorkspacePage from "./QmsAuditProgrammeWorkspacePage";
import QmsCanonicalLegacyPage from "./QmsCanonicalLegacyPage";
import QmsCarControlLoopPage from "./QmsCarControlLoopPage";
import QmsCarPerformanceReportPage from "./QmsCarPerformanceReportPage";
import QmsRegisterPage from "./QmsRegisterPage";
import QmsPlannerLivePage from "./planner/QmsPlannerLivePage";

/**
 * Canonical compatibility dispatcher.
 *
 * Specialist workflows own operational work. The compatibility reader is only
 * retained for bounded legacy/register surfaces that do not yet have a dedicated
 * owner; it must never impersonate an audit workflow merely because a route exists.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const pathname = location.pathname.toLowerCase();

  if (searchParams.get("control") && (pathname.includes("/quality/cars") || pathname.includes("/qms/cars"))) {
    return <QmsCarControlLoopPage />;
  }

  if (pathname.includes("/quality/cars") || pathname.includes("/qms/cars")) {
    return <QualityCarsPage />;
  }

  if (/\/(?:quality|qms)\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i.test(location.pathname)) {
    return <QmsAuditProgrammeSchedulePage />;
  }

  if (/\/(?:quality|qms)\/audits\/program\/?$/i.test(location.pathname)) {
    return <QmsAuditProgrammeWorkspacePage />;
  }

  // Audit dates belong to the single shared Quality Planner. Retire the old
  // audit-only schedule/calendar shell rather than maintaining two calendars.
  if (/\/(?:quality|qms)\/audits\/(?:schedule|plan)\/?$/i.test(location.pathname)) {
    const target = location.pathname.replace(/\/audits\/(?:schedule|plan)\/?$/i, "/calendar/audits");
    return <Navigate to={target} replace />;
  }

  // The old "Active Audits" route was actually a findings/CAR closeout reader.
  // Send old bookmarks to the real Audit operations overview instead of exposing
  // a misleading register under an audit label.
  if (/\/(?:quality|qms)\/audits\/register\/?$/i.test(location.pathname)) {
    return <Navigate to={location.pathname.replace(/\/register\/?$/i, "/dashboard")} replace />;
  }

  // The checklist library is rendered by QualityChecklistTemplateHost as a
  // first-class inline workspace. Do not render the old generic register behind it.
  if (/\/(?:quality|qms)\/audits\/checklists\/?$/i.test(location.pathname)) {
    return <div className="qms-hosted-specialist-workspace" aria-hidden="true" />;
  }

  // Audit report approval/issue is part of each audit's canonical Closing stage.
  // The historical collection route was only a generic audit-row reader and gave
  // users a false "Reports" workspace, so retire it to the actual audit overview.
  if (/\/(?:quality|qms)\/audits\/reports\/?$/i.test(location.pathname)) {
    return <Navigate to={location.pathname.replace(/\/reports\/?$/i, "/dashboard")} replace />;
  }

  if (pathname.includes("/quality/calendar") || pathname.includes("/qms/calendar")) {
    return <QmsPlannerLivePage />;
  }

  if (/\/(?:quality|qms)\/reports\/car-performance\/?$/i.test(location.pathname)) {
    return <QmsCarPerformanceReportPage />;
  }

  const isEvidenceRegister = /\/quality\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  if (isEvidenceRegister) return <QmsRegisterPage />;

  return <QmsCanonicalLegacyPage />;
}

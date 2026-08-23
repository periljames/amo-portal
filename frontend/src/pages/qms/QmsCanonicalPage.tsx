import React from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import QualityChecklistTemplateHost from "../../components/QMS/QualityChecklistTemplateHost";
import QualityCarsPage from "../QualityCarsPage";
import QualityAuditsSectionLayout from "../qualityAudits/QualityAuditsSectionLayout";
import QmsAuditProgrammeSchedulePage from "./QmsAuditProgrammeSchedulePage";
import QmsAuditProgrammeWorkspacePage from "./QmsAuditProgrammeWorkspacePage";
import QmsCanonicalLegacyPage from "./QmsCanonicalLegacyPage";
import QmsCarControlLoopPage from "./QmsCarControlLoopPage";
import QmsCarPerformanceReportPage from "./QmsCarPerformanceReportPage";
import QmsExternalProvidersPage from "./QmsExternalProvidersPage";
import QmsRegisterPage from "./QmsRegisterPage";
import QmsPlannerLivePage from "./planner/QmsPlannerLivePage";

function assuranceWorkspace(title: string, subtitle: string, content: React.ReactNode): React.ReactElement {
  return (
    <QualityAuditsSectionLayout title={title} subtitle={subtitle}>
      {content}
    </QualityAuditsSectionLayout>
  );
}

/**
 * Canonical compatibility dispatcher.
 *
 * Specialist workflows own operational work. The compatibility reader is only
 * retained for bounded legacy/register surfaces that do not yet have a dedicated
 * owner; it must never impersonate an audit or provider workflow merely because a
 * route exists.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const pathname = location.pathname.toLowerCase();
  const amoCode = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1] || "";

  if (searchParams.get("control") && (pathname.includes("/quality/cars") || pathname.includes("/qms/cars"))) {
    return <QmsCarControlLoopPage />;
  }

  if (pathname.includes("/quality/cars") || pathname.includes("/qms/cars")) {
    return <QualityCarsPage />;
  }

  if (pathname.includes("/quality/suppliers") || pathname.includes("/qms/suppliers")) {
    return <QmsExternalProvidersPage />;
  }

  if (/\/(?:quality|qms)\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit programme",
      "Schedule governed programme work without leaving the Assurance Workspace.",
      <QmsAuditProgrammeSchedulePage />
    );
  }

  if (/\/(?:quality|qms)\/audits\/program\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit programme",
      "Govern the audit programme, commitments and planned assurance work.",
      <QmsAuditProgrammeWorkspacePage />
    );
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

  // The controlled checklist library is mounted as the workspace content itself.
  // QualityEnhancementsHost stays mounted for shared Quality support but omits its
  // duplicate checklist-template child on this route.
  if (/\/(?:quality|qms)\/audits\/checklists\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit checklists",
      "Use the controlled checklist library for audit preparation and execution.",
      <QualityChecklistTemplateHost amoCode={decodeURIComponent(amoCode)} />
    );
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

  // Evidence Vault is a first-class Quality evidence workspace, not an Audit
  // Assurance child. Keep its own bounded register header, navigation and
  // permission contract intact rather than embedding it inside the audit shell.
  const isEvidenceRegister = /\/(?:quality|qms)\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  if (isEvidenceRegister) return <QmsRegisterPage />;

  return <QmsCanonicalLegacyPage />;
}

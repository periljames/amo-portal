import React from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import QualityChecklistTemplateHost from "../../components/QMS/QualityChecklistTemplateHost";
import QualityCarsPage from "../QualityCarsPage";
import QualityAuditsSectionLayout from "../qualityAudits/QualityAuditsSectionLayout";
import QmsAuditProgrammeSchedulePage from "./QmsAuditProgrammeSchedulePage";
import QmsAuditProgrammeWorkspacePage from "./QmsAuditProgrammeWorkspacePage";
import QmsModuleWorkspacePage from "./QmsModuleWorkspacePage";
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
 * Canonical Quality module dispatcher.
 *
 * Specialist workflows own audit, CAR, provider, planning, and evidence work.
 * General register modules use the shared module workspace.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const pathname = location.pathname.toLowerCase();
  const amoCode = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1] || "";

  if (searchParams.get("control") && pathname.includes("/quality/cars")) {
    return <QmsCarControlLoopPage />;
  }

  if (pathname.includes("/quality/cars")) {
    return <QualityCarsPage />;
  }

  if (pathname.includes("/quality/suppliers")) {
    return <QmsExternalProvidersPage />;
  }

  if (/\/quality\/audits\/program\/[^/]+\/items\/[^/]+\/schedule\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit programme",
      "Schedule governed programme work without leaving the Assurance Workspace.",
      <QmsAuditProgrammeSchedulePage />
    );
  }

  if (/\/quality\/audits\/program\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit programme",
      "Govern the audit programme, commitments and planned assurance work.",
      <QmsAuditProgrammeWorkspacePage />
    );
  }

  // The controlled checklist library is mounted as the workspace content itself.
  // QualityEnhancementsHost stays mounted for shared Quality support but omits its
  // duplicate checklist-template child on this route.
  if (/\/quality\/audits\/checklists\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit checklists",
      "Use the controlled checklist library for audit preparation and execution.",
      <QualityChecklistTemplateHost amoCode={decodeURIComponent(amoCode)} />
    );
  }

  if (pathname.includes("/quality/calendar")) {
    return <QmsPlannerLivePage />;
  }

  if (/\/quality\/reports\/car-performance\/?$/i.test(location.pathname)) {
    return <QmsCarPerformanceReportPage />;
  }

  // Evidence Vault is a first-class Quality evidence workspace, not an Audit
  // Assurance child. Keep its own bounded register header, navigation and
  // permission contract intact rather than embedding it inside the audit shell.
  const isEvidenceRegister = /\/quality\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  if (isEvidenceRegister) return <QmsRegisterPage />;

  return <QmsModuleWorkspacePage />;
}

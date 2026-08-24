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
 *
 * Planner V2 remains the sole calendar owner at `/quality/calendar/*`.
 * When opened as an Audit Assurance destination it keeps Assurance chrome.
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
      "Audit Programme",
      "Schedule governed programme work without leaving the Assurance Workspace.",
      <QmsAuditProgrammeSchedulePage />
    );
  }

  if (/\/quality\/audits\/program\/?$/i.test(location.pathname)) {
    return assuranceWorkspace(
      "Audit Programme",
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
      "Controlled checklist library for audit preparation and fieldwork.",
      <QualityChecklistTemplateHost amoCode={decodeURIComponent(amoCode)} />
    );
  }

  // Sole Planner V2 owner — wrapped in Assurance chrome so rail destinations stay coherent.
  if (pathname.includes("/quality/calendar")) {
    return assuranceWorkspace(
      "Planner",
      "Dated Quality calendar — Planner V2 is the only scheduling surface.",
      <QmsPlannerLivePage embedded />
    );
  }

  if (/\/quality\/reports\/car-performance\/?$/i.test(location.pathname)) {
    return <QmsCarPerformanceReportPage />;
  }

  // Evidence Vault list/search stays the bounded register owner; when reached from the
  // Assurance rail it keeps Audit Assurance chrome instead of a bare register shell.
  const isEvidenceRegister = /\/quality\/evidence-vault(?:\/(?:search|audit-packages|car-packages|document-approval-packages|management-review-packages|regulator-packages|immutable-archive|retention|files))?\/?$/i.test(location.pathname);
  if (isEvidenceRegister) {
    return assuranceWorkspace(
      "Evidence",
      "Objective evidence and retained assurance records.",
      <QmsRegisterPage embedded />
    );
  }

  return <QmsModuleWorkspacePage />;
}

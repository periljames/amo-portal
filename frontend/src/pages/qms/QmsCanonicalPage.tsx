import React, { lazy, Suspense } from "react";
import { qmsPageLoaders } from "../../app/qmsRouteLoaders";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import QualityAuditsSectionLayout from "../qualityAudits/QualityAuditsSectionLayout";
const QualityChecklistTemplateHost = lazy(qmsPageLoaders.checklist);
const QualityCarsPage = lazy(qmsPageLoaders.cars);
const QmsAuditProgrammeSchedulePage = lazy(qmsPageLoaders.programmeSchedule);
const QmsAuditProgrammeWorkspacePage = lazy(qmsPageLoaders.programme);
const QmsModuleWorkspacePage = lazy(qmsPageLoaders.module);
const QmsCarControlLoopPage = lazy(qmsPageLoaders.carControl);
const QmsCarPerformanceReportPage = lazy(qmsPageLoaders.carReport);
const QmsExternalProvidersPage = lazy(qmsPageLoaders.providers);
const QmsRegisterPage = lazy(qmsPageLoaders.register);
const QmsPlannerLivePage = lazy(qmsPageLoaders.planner);

export default function QmsCanonicalPage(): React.ReactElement {
  return <Suspense fallback={<div role="status" className="qms-route-loading">Loading Quality workspace…</div>}><QmsCanonicalContent /></Suspense>;
}

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
function QmsCanonicalContent(): React.ReactElement {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const pathname = location.pathname.toLowerCase();
  const amoCode = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1] || "";

  if (/\/quality\/planner\/?$/i.test(location.pathname)) {
    return <Navigate to={`/maintenance/${amoCode}/quality/calendar/week`} replace />;
  }

  if (/\/quality\/calendar\/?$/i.test(location.pathname)) {
    return <Navigate to={`/maintenance/${amoCode}/quality/calendar/week`} replace />;
  }

  if (/\/quality\/findings(?:\/register)?\/?$/i.test(location.pathname)) {
    return <Navigate to={`/maintenance/${amoCode}/quality/audits/register`} replace />;
  }

  if (searchParams.get("control") && pathname.includes("/quality/cars")) {
    return <QmsCarControlLoopPage />;
  }

  const carListView = location.pathname.match(/\/quality\/cars(?:\/(register|overdue|due-soon|awaiting-auditee|awaiting-quality-review|awaiting-effectiveness-review|closed))?\/?$/i)?.[1]?.toLowerCase() || "";
  if (carListView || (/\/quality\/cars\/?$/i.test(location.pathname) && !searchParams.get("carId"))) {
    const filters: Record<string, string> = {
      overdue: "timing=overdue",
      "due-soon": "timing=due_soon",
      "awaiting-auditee": "stage=with_auditee",
      "awaiting-quality-review": "stage=needs_review",
      "awaiting-effectiveness-review": "stage=effectiveness",
      closed: "stage=closed",
    };
    const suffix = filters[carListView] ? `?${filters[carListView]}` : "";
    return <Navigate to={`/maintenance/${amoCode}/quality/audits/register${suffix}`} replace />;
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

  // Canonical Calendar surface — sole AA scheduling UI (Planner V2 engine remains underneath).
  if (pathname.includes("/quality/calendar")) {
    return assuranceWorkspace(
      "Calendar",
      "Dated Quality calendar — the only primary scheduling surface for Audit Assurance.",
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

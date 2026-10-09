import React, { Suspense, lazy, useEffect, useMemo } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCcw, ShieldAlert } from "lucide-react";

import AuditLifecycleRail from "../../features/qms/auditSession/AuditLifecycleRail";
import OccurrenceToolbarPortal, { AUDIT_OCCURRENCE_MOUNT_ID } from "../../features/qms/auditSession/OccurrenceToolbarPortal";
import MobileAuditDeepLinkState from "../../features/qms/auditSession/MobileAuditDeepLinkState";
import { auditSetupIssues } from "../../features/qms/auditSession/auditSetupModel";
import { auditSessionPath, auditSessionStageFromPath } from "../../features/qms/auditSession/auditSessionRoutes";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../services/qmsAuditOccurrenceResolver";
import { getAuditSession } from "../../services/qmsAuditSession";
import PortalTextScaleManager from "./PortalTextScaleManager";
import QualityContextTabs from "./QualityContextTabs";
import QualityDataFreshnessCoordinator from "./QualityDataFreshnessCoordinator";
import PortalErrorBoundary from "../feedback/PortalErrorBoundary";
import "../../styles/qms-text-scale-override.css";
import "../../styles/qms-audit-occurrence-shell.css";

const AuditSetupWorkspace = lazy(() => import("../../features/qms/auditSession/AuditSetupWorkspace"));
const AuditPrepareWorkspace = lazy(() => import("../../features/qms/auditSession/AuditPrepareWorkspace"));
const AuditDocumentSubmissionReviewPanel = lazy(() => import("../../features/qms/auditSession/AuditDocumentSubmissionReviewPanel"));
const LiveAuditWorkspace = lazy(() => import("../../features/qms/auditSession/LiveAuditWorkspace"));
const LiveFindingReleasePanel = lazy(() => import("../../features/qms/auditSession/LiveFindingReleasePanel"));
const ExternalFindingDraftReviewPanel = lazy(() => import("../../features/qms/auditSession/ExternalFindingDraftReviewPanel"));
const AuditClosingNarrativePanel = lazy(() => import("../../features/qms/auditSession/AuditClosingNarrativePanel"));
const AuditClosingWorkspace = lazy(() => import("../../features/qms/auditSession/AuditClosingWorkspace"));
const AuditFollowUpWorkspace = lazy(() => import("../../features/qms/auditSession/AuditFollowUpWorkspace"));
const AuditArchiveWorkspace = lazy(() => import("../../features/qms/auditSession/AuditArchiveWorkspace"));
const QualityAuditHandoffHost = lazy(() => import("./QualityAuditHandoffHost"));
const QualityAuditGovernancePanelHost = lazy(() => import("./QualityAuditGovernancePanelHost"));
const QualityEffectivenessResponseHost = lazy(() => import("./QualityEffectivenessResponseHost"));
const QualityPlannerStrategicHost = lazy(() => import("./QualityPlannerStrategicHost"));

type AuditRoute = { amoCode: string; auditKey: string };

function useQualityAmoCode(): string | null {
  const location = useLocation();
  return useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/|$)/i);
    return match ? decodeURIComponent(match[1]) : null;
  }, [location.pathname]);
}

function useAuditRoute(): AuditRoute | null {
  const location = useLocation();
  return useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/quality\/audits\/([^/]+)\/(?:setup|prepare|live|closing|follow-up|archive)\/?$/i);
    if (!match) return null;
    const auditKey = decodeURIComponent(match[2]);
    return { amoCode: decodeURIComponent(match[1]), auditKey };
  }, [location.pathname]);
}

const CarInviteResponsiveStyleLoader: React.FC = () => {
  useEffect(() => {
    let cancelled = false;
    let observer: MutationObserver | null = null;
    const loadOverrides = () => {
      if (cancelled) return;
      observer?.disconnect();
      observer = null;
      void import("../../styles/car-invite-responsive.css");
    };
    if (document.querySelector(".auth-layout--car-invite")) loadOverrides();
    else {
      observer = new MutationObserver(() => { if (document.querySelector(".auth-layout--car-invite")) loadOverrides(); });
      observer.observe(document.body, { childList: true, subtree: true });
    }
    return () => { cancelled = true; observer?.disconnect(); };
  }, []);
  return null;
};

const QualityDialogFocusRestorer: React.FC = () => {
  useEffect(() => {
    let activeDialog: HTMLElement | null = null;
    let opener: HTMLElement | null = null;
    let lastExternalFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || target.closest('[role="dialog"][aria-modal="true"]')) return;
      lastExternalFocus = target;
    };
    const canonicalDialogOpener = (dialog: HTMLElement): HTMLElement | null => dialog.classList.contains("qms-planner-create-modal") ? document.querySelector<HTMLElement>(".qms-planner-schedule-action") : null;
    const observer = new MutationObserver(() => {
      const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
      if (dialog && !activeDialog) {
        activeDialog = dialog;
        const canonicalOpener = canonicalDialogOpener(dialog);
        opener = canonicalOpener?.isConnected ? canonicalOpener : lastExternalFocus?.isConnected ? lastExternalFocus : null;
        return;
      }
      if (!dialog && activeDialog) {
        const restoreTarget = opener;
        activeDialog = null;
        opener = null;
        window.requestAnimationFrame(() => { if (restoreTarget?.isConnected) restoreTarget.focus({ preventScroll: true }); });
        return;
      }
      if (dialog) activeDialog = dialog;
    });
    document.addEventListener("focusin", onFocusIn, true);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { document.removeEventListener("focusin", onFocusIn, true); observer.disconnect(); };
  }, []);
  return null;
};

const WorkflowIntegrityGuard: React.FC<{ route: AuditRoute }> = ({ route }) => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const occurrenceKey = auditOccurrenceQueryKey(route.amoCode, route.auditKey);
  const occurrenceQuery = useQuery({
    queryKey: occurrenceKey,
    queryFn: ({ signal }) => resolveAuditOccurrence(route.amoCode, route.auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = occurrenceQuery.data?.id || "";
  const sessionKey = ["qms-audit-session", route.amoCode, auditId] as const;
  const sessionQuery = useQuery({
    queryKey: sessionKey,
    queryFn: ({ signal }) => getAuditSession(route.amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const degraded = occurrenceQuery.isError || sessionQuery.isError;
  useEffect(() => {
    document.documentElement.classList.toggle("quality-workflow-is-degraded", degraded);
    return () => document.documentElement.classList.remove("quality-workflow-is-degraded");
  }, [degraded]);
  const routeStage = auditSessionStageFromPath(location.pathname);
  // Preparation drafts can be composed while team eligibility is being resolved.
  // The server readiness checks still block issue and entry into fieldwork.
  if (sessionQuery.data?.current_stage_id === "setup" && routeStage && routeStage !== "setup" && routeStage !== "prepare" && occurrenceQuery.data) {
    const firstIssue = auditSetupIssues({
      title: occurrenceQuery.data.title || "",
      scope: occurrenceQuery.data.scope || "",
      criteria: occurrenceQuery.data.criteria || "",
      plannedStart: (occurrenceQuery.data.planned_start || "").slice(0, 10),
      plannedEnd: (occurrenceQuery.data.planned_end || "").slice(0, 10),
      plannedStartTime: (occurrenceQuery.data.planned_start_time || "").slice(0, 5),
      plannedEndTime: (occurrenceQuery.data.planned_end_time || "").slice(0, 5),
      auditee: occurrenceQuery.data.auditee || "",
      auditeeEmail: occurrenceQuery.data.auditee_email || "",
      leadAuditorUserId: occurrenceQuery.data.lead_auditor_user_id,
    })[0];
    const search = new URLSearchParams({ from: routeStage, setupRequired: "1" });
    if (firstIssue) search.set("required", firstIssue.field);
    return (
      <Navigate
        replace
        to={`${auditSessionPath(route.amoCode, route.auditKey, "setup")}?${search.toString()}#setup-required`}
      />
    );
  }
  if (!degraded) return null;
  return <div className="quality-workflow-integrity-blocker" role="alertdialog" aria-modal="true" aria-label="Audit workflow unavailable"><section><ShieldAlert size={28} /><div><p>Authoritative workflow unavailable</p><h2>Audit progress has been placed in safe read-only mode.</h2><span>The portal could not verify stage completion, CAR state, evidence gates or closeout readiness from the backend. It will not use locally invented completion values or permit workflow advancement.</span></div><div className="quality-workflow-integrity-blocker__actions"><button type="button" onClick={() => void Promise.all([queryClient.invalidateQueries({ queryKey: occurrenceKey }), queryClient.invalidateQueries({ queryKey: sessionKey })])}><RefreshCcw size={17} /> Retry workflow</button><a href={`/maintenance/${encodeURIComponent(route.amoCode)}/quality/audits/register`}>Open audit register</a></div></section></div>;
};

const QualityEnhancementsHost: React.FC = () => {
  const location = useLocation();
  const amoCode = useQualityAmoCode();
  const route = useAuditRoute();
  const auditSessionStage = auditSessionStageFromPath(location.pathname);
  const canonicalOccurrence = Boolean(route && auditSessionStage);
  const legacyAuditMatch = location.pathname.match(/^\/maintenance\/([^/]+)\/quality\/audits\/([^/]+)\/?$/i);
  const legacyAuditTab = new URLSearchParams(location.search).get("tab")?.toLowerCase() || "";

  useEffect(() => {
    document.documentElement.classList.toggle("quality-audit-canonical-occurrence", canonicalOccurrence);
    return () => document.documentElement.classList.remove("quality-audit-canonical-occurrence");
  }, [canonicalOccurrence]);

  if (/^\/car-invite\/?$/i.test(location.pathname)) return <CarInviteResponsiveStyleLoader />;

  // The pre-canonical mobile/report links remain supported as documented.
  // Do not infer mappings for other legacy tabs whose lifecycle meaning is
  // ambiguous; only closeout/report have an explicit canonical Closing contract.
  if (legacyAuditMatch && ["closeout", "report"].includes(legacyAuditTab)) {
    const amo = decodeURIComponent(legacyAuditMatch[1]);
    const auditKey = decodeURIComponent(legacyAuditMatch[2]);
    return <Navigate replace to={auditSessionPath(amo, auditKey, "closing")} />;
  }

  return <>
    <PortalTextScaleManager />
    <QualityContextTabs />
    <QualityDataFreshnessCoordinator />
    <QualityDialogFocusRestorer />

    {amoCode ? <Suspense fallback={null}>
      <QualityAuditHandoffHost amoCode={amoCode} />
      <QualityEffectivenessResponseHost amoCode={amoCode} />
      <QualityPlannerStrategicHost amoCode={amoCode} />
      {/* Checklist library is owned by QmsCanonicalPage on /audits/checklists; Prepare owns bind. */}
    </Suspense> : null}

    {route && auditSessionStage ? (
      <OccurrenceToolbarPortal containerId={AUDIT_OCCURRENCE_MOUNT_ID}>
      <div className="qms-audit-occurrence-shell">
        <AuditLifecycleRail amoCode={route.amoCode} auditKey={route.auditKey} />
        <div className="qms-audit-occurrence-shell__body">
          <WorkflowIntegrityGuard route={route} />
          <MobileAuditDeepLinkState />

          {auditSessionStage === "setup" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading audit setup…</div>}>
              <AuditSetupWorkspace amoCode={route.amoCode} auditKey={route.auditKey} />
            </Suspense>
          ) : null}
          {auditSessionStage === "prepare" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading prepare workspace…</div>}>
              <PortalErrorBoundary inline title="Preparation workspace unavailable"><AuditPrepareWorkspace amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
              <PortalErrorBoundary inline title="Document review unavailable"><AuditDocumentSubmissionReviewPanel amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
              <PortalErrorBoundary inline title="Audit governance controls unavailable"><QualityAuditGovernancePanelHost amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
            </Suspense>
          ) : null}
          {auditSessionStage === "live" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading live audit workspace…</div>}>
              <PortalErrorBoundary inline title="Fieldwork workspace unavailable" exitHref={auditSessionPath(route.amoCode, route.auditKey, "prepare")} exitLabel="Back to Prepare"><LiveAuditWorkspace amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
              <PortalErrorBoundary inline title="Auditee release controls unavailable"><LiveFindingReleasePanel amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
              <PortalErrorBoundary inline title="External finding review unavailable"><ExternalFindingDraftReviewPanel amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
            </Suspense>
          ) : null}
          {auditSessionStage === "closing" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading closing workspace…</div>}>
              <PortalErrorBoundary inline title="Closing narrative unavailable"><AuditClosingNarrativePanel amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
              <PortalErrorBoundary inline title="Closing workspace unavailable" exitHref={auditSessionPath(route.amoCode, route.auditKey, "live")} exitLabel="Back to Fieldwork"><AuditClosingWorkspace amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
            </Suspense>
          ) : null}
          {auditSessionStage === "follow-up" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading follow-up workspace…</div>}>
              <PortalErrorBoundary inline title="Follow-up workspace unavailable" exitHref={auditSessionPath(route.amoCode, route.auditKey, "closing")} exitLabel="Back to Closing"><AuditFollowUpWorkspace amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
            </Suspense>
          ) : null}
          {auditSessionStage === "archive" ? (
            <Suspense fallback={<div className="qms-audit-stage-suspense" role="status">Loading archive workspace…</div>}>
              <PortalErrorBoundary inline title="Archive workspace unavailable" exitHref={auditSessionPath(route.amoCode, route.auditKey, "follow-up")} exitLabel="Back to Follow-up"><AuditArchiveWorkspace amoCode={route.amoCode} auditKey={route.auditKey} /></PortalErrorBoundary>
            </Suspense>
          ) : null}
        </div>
      </div>
      </OccurrenceToolbarPortal>
    ) : null}
  </>;
};

export default QualityEnhancementsHost;

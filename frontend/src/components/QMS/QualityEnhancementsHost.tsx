import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCcw, ShieldAlert } from "lucide-react";

import AuditLifecycleRail from "../../features/qms/auditSession/AuditLifecycleRail";
import PortalTextScaleManager from "./PortalTextScaleManager";
import QualityContextTabs from "./QualityContextTabs";
import QualityDataFreshnessCoordinator from "./QualityDataFreshnessCoordinator";
import "../../styles/qms-text-scale-override.css";

const QualityChecklistPdfFormEditorHost = lazy(
  () => import("./QualityChecklistPdfFormEditorHost"),
);
const QualityChecklistExecutionGovernanceHost = lazy(
  () => import("./QualityChecklistExecutionGovernanceHost"),
);
const QualityAuditGovernancePanelHost = lazy(
  () => import("./QualityAuditGovernancePanelHost"),
);
const QualityAuditPreparationContextHost = lazy(
  () => import("./QualityAuditPreparationContextHost"),
);
const QualityAuditReportCloseoutHost = lazy(
  () => import("./QualityAuditReportCloseoutHost"),
);
const QualityChecklistTemplateHost = lazy(
  () => import("./QualityChecklistTemplateHost"),
);
const QualityAuditHandoffHost = lazy(
  () => import("./QualityAuditHandoffHost"),
);
const QualityEffectivenessResponseHost = lazy(
  () => import("./QualityEffectivenessResponseHost"),
);
const QualityPlannerStrategicHost = lazy(
  () => import("./QualityPlannerStrategicHost"),
);
const QualityProgrammeOccurrenceHost = lazy(
  () => import("./QualityProgrammeOccurrenceHost"),
);

type AuditRoute = {
  amoCode: string;
  auditKey: string;
  activeTab: string;
};

function useQualityAmoCode(): string | null {
  const location = useLocation();
  return useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/(?:quality|qms)(?:\/|$)/i);
    return match ? decodeURIComponent(match[1]) : null;
  }, [location.pathname]);
}

function useAuditRoute(): AuditRoute | null {
  const location = useLocation();
  return useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/(?:quality|qms)\/audits\/([^/]+)/i);
    if (!match) return null;
    const auditKey = decodeURIComponent(match[2]);
    if (["dashboard", "program", "programme", "schedule", "plan", "register", "checklists", "reports", "templates", "new", "bin", "schedules"].includes(auditKey.toLowerCase())) {
      return null;
    }
    return {
      amoCode: decodeURIComponent(match[1]),
      auditKey,
      activeTab: new URLSearchParams(location.search).get("tab") || "war-room",
    };
  }, [location.pathname, location.search]);
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

    if (document.querySelector(".auth-layout--car-invite")) {
      loadOverrides();
    } else {
      observer = new MutationObserver(() => {
        if (document.querySelector(".auth-layout--car-invite")) loadOverrides();
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }

    return () => {
      cancelled = true;
      observer?.disconnect();
    };
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
      if (!(target instanceof HTMLElement)) return;
      if (target.closest('[role="dialog"][aria-modal="true"]')) return;
      lastExternalFocus = target;
    };

    const canonicalDialogOpener = (dialog: HTMLElement): HTMLElement | null => {
      if (dialog.classList.contains("qms-planner-create-modal")) {
        return document.querySelector<HTMLElement>(".qms-planner-quick-schedule");
      }
      return null;
    };

    const observer = new MutationObserver(() => {
      const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
      if (dialog && !activeDialog) {
        activeDialog = dialog;
        const canonicalOpener = canonicalDialogOpener(dialog);
        opener = canonicalOpener?.isConnected
          ? canonicalOpener
          : lastExternalFocus?.isConnected
            ? lastExternalFocus
            : null;
        return;
      }
      if (!dialog && activeDialog) {
        const restoreTarget = opener;
        activeDialog = null;
        opener = null;
        window.requestAnimationFrame(() => {
          if (restoreTarget?.isConnected) restoreTarget.focus({ preventScroll: true });
        });
        return;
      }
      if (dialog) activeDialog = dialog;
    });

    document.addEventListener("focusin", onFocusIn, true);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      document.removeEventListener("focusin", onFocusIn, true);
      observer.disconnect();
    };
  }, []);
  return null;
};

const WorkflowIntegrityGuard: React.FC<{ route: AuditRoute }> = ({ route }) => {
  const queryClient = useQueryClient();
  const [cacheRevision, setCacheRevision] = useState(0);
  const queryKey = useMemo(() => ["qms-audit-context", route.auditKey] as const, [route.auditKey]);

  useEffect(() => queryClient.getQueryCache().subscribe(() => {
    setCacheRevision((current) => current + 1);
  }), [queryClient]);

  const state = queryClient.getQueryState(queryKey);
  const data = queryClient.getQueryData<{ degraded?: boolean }>(queryKey);
  const degraded = data?.degraded === true || state?.status === "error";
  void cacheRevision;

  useEffect(() => {
    document.documentElement.classList.toggle("quality-workflow-is-degraded", degraded);
    return () => document.documentElement.classList.remove("quality-workflow-is-degraded");
  }, [degraded]);

  if (!degraded) return null;

  return (
    <div className="quality-workflow-integrity-blocker" role="alertdialog" aria-modal="true" aria-label="Audit workflow unavailable">
      <section>
        <ShieldAlert size={28} />
        <div>
          <p>Authoritative workflow unavailable</p>
          <h2>Audit progress has been placed in safe read-only mode.</h2>
          <span>
            The portal could not verify stage completion, CAR state, evidence gates or closeout readiness from the backend.
            It will not use locally invented completion values or permit workflow advancement.
          </span>
        </div>
        <div className="quality-workflow-integrity-blocker__actions">
          <button type="button" onClick={() => void queryClient.invalidateQueries({ queryKey })}>
            <RefreshCcw size={17} /> Retry workflow
          </button>
          <a href={`/maintenance/${encodeURIComponent(route.amoCode)}/quality/audits/register`}>Open audit register</a>
        </div>
      </section>
    </div>
  );
};

const QualityEnhancementsHost: React.FC = () => {
  const location = useLocation();
  const amoCode = useQualityAmoCode();
  const route = useAuditRoute();

  if (/^\/car-invite\/?$/i.test(location.pathname)) {
    return <CarInviteResponsiveStyleLoader />;
  }

  return (
    <>
      <PortalTextScaleManager />
      <QualityContextTabs />
      <QualityDataFreshnessCoordinator />
      <QualityDialogFocusRestorer />

      {amoCode ? (
        <Suspense fallback={null}>
          <QualityAuditHandoffHost amoCode={amoCode} />
          <QualityEffectivenessResponseHost amoCode={amoCode} />
          <QualityPlannerStrategicHost amoCode={amoCode} />
          <QualityProgrammeOccurrenceHost amoCode={amoCode} />
          <QualityChecklistTemplateHost amoCode={amoCode} auditKey={route?.auditKey} activeTab={route?.activeTab} />
        </Suspense>
      ) : null}

      {route ? (
        <>
          <AuditLifecycleRail amoCode={route.amoCode} auditKey={route.auditKey} />
          <WorkflowIntegrityGuard route={route} />
          <Suspense fallback={null}>
            <QualityAuditGovernancePanelHost amoCode={route.amoCode} auditKey={route.auditKey} />
            <QualityAuditPreparationContextHost amoCode={route.amoCode} auditKey={route.auditKey} />
            {route.activeTab === "report" || route.activeTab === "closeout" ? (
              <QualityAuditReportCloseoutHost amoCode={route.amoCode} auditKey={route.auditKey} />
            ) : null}
          </Suspense>
          {route.activeTab === "checklist" ? (
            <Suspense fallback={null}>
              <QualityChecklistExecutionGovernanceHost amoCode={route.amoCode} auditKey={route.auditKey} activeTab={route.activeTab} />
              <QualityChecklistPdfFormEditorHost />
            </Suspense>
          ) : null}
        </>
      ) : null}
    </>
  );
};

export default QualityEnhancementsHost;

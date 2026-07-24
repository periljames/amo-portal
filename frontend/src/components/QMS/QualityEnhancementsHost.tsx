import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCcw, ShieldAlert } from "lucide-react";
import "../../styles/quality-checklist-pdf-form-editor.css";

type AuditRoute = {
  amoCode: string;
  auditKey: string;
};

function useAuditRoute(): AuditRoute | null {
  const location = useLocation();
  return useMemo(() => {
    const match = location.pathname.match(/^\/maintenance\/([^/]+)\/quality\/audits\/([^/]+)/i);
    if (!match) return null;
    return {
      amoCode: decodeURIComponent(match[1]),
      auditKey: decodeURIComponent(match[2]),
    };
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

const WorkflowIntegrityGuard: React.FC<{ route: AuditRoute }> = ({ route }) => {
  const queryClient = useQueryClient();
  const [cacheRevision, setCacheRevision] = useState(0);
  const lifecycleQueries = useMemo(() => [
    ["qms-audit-resolve-v2", route.auditKey] as const,
    ["qms-audit-lifecycle"] as const,
  ], [route.auditKey]);

  useEffect(() => queryClient.getQueryCache().subscribe(() => {
    setCacheRevision((current) => current + 1);
  }), [queryClient]);

  const resolveState = queryClient.getQueryState(lifecycleQueries[0]);
  const lifecycleStates = queryClient.getQueryCache().findAll({ queryKey: lifecycleQueries[1] });
  const lifecycleFailed = lifecycleStates.some((query) => query.state.status === "error");
  const degraded = resolveState?.status === "error" || lifecycleFailed;
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
            The portal could not verify lifecycle state, CAR issuance, evidence review or closeout readiness from the backend.
            It will not use locally invented completion values or permit workflow advancement.
          </span>
        </div>
        <div className="quality-workflow-integrity-blocker__actions">
          <button type="button" onClick={() => void queryClient.invalidateQueries({ queryKey: ["qms-audit-lifecycle"] })}>
            <RefreshCcw size={17} /> Retry lifecycle
          </button>
          <a href={`/maintenance/${encodeURIComponent(route.amoCode)}/quality/audits/register`}>Open audit register</a>
        </div>
      </section>
    </div>
  );
};

const QualityEnhancementsHost: React.FC = () => {
  const location = useLocation();
  const route = useAuditRoute();

  if (/^\/car-invite\/?$/i.test(location.pathname)) {
    return <CarInviteResponsiveStyleLoader />;
  }
  if (!route) return null;

  // Fillable PDF controls now live inside the Checklist toolbar. The global host
  // only protects the page when the authoritative lifecycle query fails.
  return <WorkflowIntegrityGuard route={route} />;
};

export default QualityEnhancementsHost;

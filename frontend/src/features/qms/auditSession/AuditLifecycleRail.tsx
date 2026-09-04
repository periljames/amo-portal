import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Circle } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { getAuditSession, type AuditSessionStageId } from "../../../services/qmsAuditSession";
import {
  AUDIT_SESSION_STAGES,
  auditOccurrenceFunctionalPath,
  auditOccurrenceFunctionalTabFromLocation,
  auditOccurrenceFunctionalTabsForStage,
  auditSessionPath,
  auditSessionStageFromPath,
} from "./auditSessionRoutes";
import "../../../styles/qms-audit-session.css";

const STAGE_LABELS: Record<AuditSessionStageId, string> = {
  setup: "Setup",
  prepare: "Prepare",
  live: "Fieldwork",
  closing: "Closing",
  "follow-up": "Follow-up",
  archive: "Archive",
};

type Props = { amoCode: string; auditKey: string };

const AuditLifecycleRail: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const routeStage = auditSessionStageFromPath(location.pathname);
  const functionalTab = auditOccurrenceFunctionalTabFromLocation(location.pathname, location.hash);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const sessionQuery = useQuery({
    queryKey: ["qms-audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
    refetchInterval: routeStage === "live" ? 5_000 : 15_000,
  });

  const stageState = useMemo(() => {
    const serverStages = new Map(sessionQuery.data?.stages.map((stage) => [stage.id, stage]) || []);
    return AUDIT_SESSION_STAGES.map((id) => ({ id, server: serverStages.get(id) }));
  }, [sessionQuery.data?.stages]);

  const authoritativeId = sessionQuery.data?.current_stage_id as AuditSessionStageId | undefined;
  const viewingOtherStage = Boolean(routeStage && authoritativeId && routeStage !== authoritativeId);
  const nextStageHref = authoritativeId ? auditSessionPath(amoCode, auditKey, authoritativeId) : null;
  const nextStageIndex = authoritativeId ? AUDIT_SESSION_STAGES.indexOf(authoritativeId) : -1;

  const stageTabs = auditOccurrenceFunctionalTabsForStage(routeStage);
  const auditRef = auditQuery.data?.audit_ref || auditKey;
  const auditTitle = (auditQuery.data?.title || "").trim() || auditRef;
  const stageChip =
    routeStage && STAGE_LABELS[routeStage]
      ? STAGE_LABELS[routeStage]
      : sessionQuery.data?.current_stage_label || null;

  return (
    <section className="qms-audit-session-rail qms-audit-session-rail--progress" aria-label="Audit occurrence progress">
      <div className="qms-audit-session-rail__meta">
        <div className="qms-audit-session-rail__identity">
          <h1 className="qms-audit-session-rail__title" title={auditTitle}>
            {auditTitle}
          </h1>
          <div className="qms-audit-session-rail__meta-row">
            <span className="qms-audit-session-rail__ref">{auditRef}</span>
            {stageChip ? <span className="qms-audit-session-rail__stage-chip">{stageChip}</span> : null}
            {sessionQuery.isError || auditQuery.isError ? (
              <span className="qms-audit-session-rail__degraded" title="Authoritative session state could not be verified.">
                State unavailable
              </span>
            ) : (
              <span className="qms-audit-session-rail__progress-pct">
                {sessionQuery.data ? `${sessionQuery.data.percent_complete}% complete` : "Loading…"}
              </span>
            )}
          </div>
        </div>
      </div>

      <nav className="qms-audit-session-rail__steps" aria-label="Lifecycle progress">
        {stageState.map(({ id, server }, index) => {
          const selected = routeStage === id || (!routeStage && server?.active === true);
          const complete = server?.complete === true;
          const authoritative = authoritativeId === id;
          const isNext =
            Boolean(authoritativeId) &&
            nextStageIndex >= 0 &&
            index === nextStageIndex + 1 &&
            !complete &&
            !authoritative;
          const muted = !selected && !authoritative && !isNext && !complete;
          return (
            <React.Fragment key={id}>
              <Link
                to={auditSessionPath(amoCode, auditKey, id)}
                className={[
                  "qms-audit-session-step",
                  selected ? "is-selected" : "",
                  complete ? "is-complete" : "",
                  authoritative ? "is-authoritative" : "",
                  isNext ? "is-next" : "",
                  muted ? "is-muted" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={selected ? "step" : undefined}
                title={
                  server?.helper ||
                  (authoritative
                    ? `Current stage: ${STAGE_LABELS[id]}`
                    : `View ${STAGE_LABELS[id]} (does not change lifecycle)`)
                }
              >
                <span className="qms-audit-session-step__icon" aria-hidden="true">
                  {complete ? <Check size={12} /> : <Circle size={8} />}
                </span>
                <span className="qms-audit-session-step__label">{STAGE_LABELS[id]}</span>
              </Link>
              {index < stageState.length - 1 ? <span className="qms-audit-session-step__line" aria-hidden="true" /> : null}
            </React.Fragment>
          );
        })}
      </nav>

      {sessionQuery.data && viewingOtherStage ? (
        <div className="qms-audit-session-rail__authority" role="status">
          <span>
            Current: <strong>{sessionQuery.data.current_stage_label}</strong>
            {routeStage ? (
              <span className="qms-audit-session-rail__viewing"> · Viewing {STAGE_LABELS[routeStage]}</span>
            ) : null}
          </span>
          {nextStageHref ? (
            <Link to={nextStageHref} className="qms-audit-session-rail__next-action">
              Go to {sessionQuery.data.current_stage_label}
              <ArrowRight size={14} aria-hidden />
            </Link>
          ) : null}
        </div>
      ) : null}

      {stageTabs.length > 1 ? (
        <nav className="qms-audit-session-rail__functional" aria-label={`${stageChip || "Current stage"} workspace`}>
          <span className="qms-audit-session-rail__functional-label">This stage</span>
          {stageTabs.map((tab) => {
          const selected = functionalTab === tab.id;
          return (
            <Link
              key={tab.id}
              to={auditOccurrenceFunctionalPath(amoCode, auditKey, tab.id)}
              className={`qms-audit-session-rail__functional-link${selected ? " is-selected" : ""}`}
              aria-current={selected ? "page" : undefined}
            >
              {tab.label}
            </Link>
          );
          })}
        </nav>
      ) : null}
    </section>
  );
};

export default AuditLifecycleRail;

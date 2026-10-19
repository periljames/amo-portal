import React, { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Archive, Check, ClipboardCheck, FileCheck2, ListChecks, RotateCcw, Settings2 } from "lucide-react";
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

const STAGE_PRESENTATION = {
  setup: { icon: Settings2, detail: "Scope & team" },
  prepare: { icon: ClipboardCheck, detail: "Checklist & evidence" },
  live: { icon: ListChecks, detail: "Assess & record" },
  closing: { icon: FileCheck2, detail: "Report & approve" },
  "follow-up": { icon: RotateCcw, detail: "Corrective actions" },
  archive: { icon: Archive, detail: "Retention & records" },
};

type Props = { amoCode: string; auditKey: string };

const AuditLifecycleRail: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const routeStage = auditSessionStageFromPath(location.pathname);
  const functionalTab = auditOccurrenceFunctionalTabFromLocation(location.pathname, location.hash);
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const nav = navigation.current;
      const active = nav?.querySelector<HTMLElement>('[aria-current="step"]');
      if (nav && active && nav.scrollWidth > nav.clientWidth) {
        nav.scrollLeft = active.offsetLeft - nav.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [routeStage]);

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
    refetchInterval: routeStage === "live" ? 5_000 : 60_000,
  });

  const stageState = useMemo(() => {
    const serverStages = new Map(sessionQuery.data?.stages.map((stage) => [stage.id, stage]) || []);
    return AUDIT_SESSION_STAGES.map((id) => ({ id, server: serverStages.get(id) }));
  }, [sessionQuery.data?.stages]);

  const authoritativeId = sessionQuery.data?.current_stage_id as AuditSessionStageId | undefined;
  const viewingOtherStage = Boolean(routeStage && authoritativeId && routeStage !== authoritativeId);
  const nextStageIndex = authoritativeId ? AUDIT_SESSION_STAGES.indexOf(authoritativeId) : -1;

  const stageTabs = auditOccurrenceFunctionalTabsForStage(routeStage);
  const auditRef = auditQuery.data?.audit_ref || auditKey;
  const auditTitle = (auditQuery.data?.title || "").trim() || auditRef;
  const stageChip =
    routeStage && STAGE_LABELS[routeStage]
      ? STAGE_LABELS[routeStage]
      : sessionQuery.data?.current_stage_label || null;

  if (routeStage === "live") return null;

  return (
    <section className="qms-audit-session-rail qms-audit-session-rail--progress" aria-label="Audit occurrence progress">
      <div className="qms-audit-session-rail__meta">
        <div className="qms-audit-session-rail__identity">
          <h1 className="qms-audit-session-rail__title" title={auditTitle} aria-label={`${auditRef} · ${auditTitle}`}>
            {auditTitle}
          </h1>
          <div className="qms-audit-session-rail__meta-row">
            <span className="qms-audit-session-rail__ref">{auditRef}</span>
            {stageChip ? <span className="qms-audit-session-rail__stage-chip">{stageChip}</span> : null}
            {viewingOtherStage && authoritativeId ? <span className="audit-workflow-current">Current: {STAGE_LABELS[authoritativeId]}</span> : null}
            {sessionQuery.isError || auditQuery.isError ? (
              <span className="qms-audit-session-rail__degraded" title="Authoritative session state could not be verified.">
                State unavailable
              </span>
            ) : (
              <span className="qms-audit-session-rail__progress-pct">
                {sessionQuery.data ? `${sessionQuery.data.stages.filter((stage) => stage.complete).length} of ${AUDIT_SESSION_STAGES.length} stages complete` : "Loading…"}
              </span>
            )}
          </div>
        </div>
      </div>

      <nav ref={navigation} className="qms-audit-session-rail__steps" aria-label="Lifecycle progress">
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
          const StageIcon = STAGE_PRESENTATION[id].icon;
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
                  {complete ? <Check size={17} /> : <StageIcon size={17} />}
                </span>
                <span className="qms-audit-session-step__copy"><span className="qms-audit-session-step__label">{STAGE_LABELS[id]}</span><small>{STAGE_PRESENTATION[id].detail}</small></span>
                <span className="qms-audit-session-step__number" aria-hidden>{String(index + 1).padStart(2, "0")}</span>
              </Link>
              {index < stageState.length - 1 ? <span className="qms-audit-session-step__line" aria-hidden="true" /> : null}
            </React.Fragment>
          );
        })}
      </nav>

      {stageTabs.length > 1 ? (
        <nav className="qms-audit-session-rail__functional" aria-label={`${stageChip || "Current stage"} workspace`}>
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

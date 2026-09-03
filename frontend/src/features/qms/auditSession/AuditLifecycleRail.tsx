import React, { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Circle } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import {
  buildAuditProgrammeLinkIndex,
  programmeLabelForAudit,
} from "../../../pages/qualityAudits/auditsWorkspaceModel";
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import {
  getAuditProgramme,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammes,
} from "../../../services/qmsAuditProgramme";
import { getAuditSession, type AuditSessionStageId } from "../../../services/qmsAuditSession";
import {
  AUDIT_OCCURRENCE_FUNCTIONAL_TABS,
  AUDIT_SESSION_STAGES,
  auditOccurrenceFunctionalPath,
  auditOccurrenceFunctionalTabFromLocation,
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
    queryKey: ["qms-audit-session-resolve", amoCode, auditKey],
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

  const programmeYear = new Date().getUTCFullYear();
  const programmesQuery = useQuery({
    queryKey: ["qms-audits-workspace-programmes", amoCode, programmeYear],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, programmeYear, signal),
    staleTime: 60_000,
    enabled: Boolean(auditQuery.data?.title),
  });
  const programmeSummaries = (programmesQuery.data?.items ?? []).filter(
    (programme) => (programme.metrics?.scheduled_audit_count || 0) > 0 || (programme.readiness?.requirement_count || 0) > 0,
  ).slice(0, 8);

  const programmeDetailQueries = useQueries({
    queries: programmeSummaries.map((programme) => ({
      queryKey: ["qms-audit-programme", amoCode, programme.id],
      queryFn: ({ signal }: { signal?: AbortSignal }) => getAuditProgramme(amoCode, programme.id, signal),
      staleTime: 60_000,
      enabled: Boolean(programme.id && auditQuery.data?.title),
    })),
  });
  const scheduleLinkQueries = useQueries({
    queries: programmeSummaries.map((programme) => ({
      queryKey: ["qms-audit-programme-schedule-links", amoCode, programme.id],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        listAuditProgrammeScheduleLinks(amoCode, programme.id, signal),
      staleTime: 60_000,
      enabled: Boolean(programme.id && auditQuery.data?.title),
    })),
  });

  const programmeLabel = useMemo(() => {
    if (!auditQuery.data) return null;
    const detailed = programmeDetailQueries
      .map((query) => query.data)
      .filter((programme): programme is NonNullable<typeof programme> => Boolean(programme));
    if (!detailed.length && !programmeSummaries.length) return null;
    const programmes = detailed.length ? detailed : programmeSummaries;
    const linksByProgrammeId = new Map(
      programmeSummaries.map((programme, index) => [
        programme.id,
        scheduleLinkQueries[index]?.data?.items ?? [],
      ]),
    );
    const label = programmeLabelForAudit(
      auditQuery.data,
      buildAuditProgrammeLinkIndex(programmes, linksByProgrammeId),
    );
    return label === "Direct audit" ? null : label;
  }, [auditQuery.data, programmeDetailQueries, programmeSummaries, scheduleLinkQueries]);

  const stageState = useMemo(() => {
    const serverStages = new Map(sessionQuery.data?.stages.map((stage) => [stage.id, stage]) || []);
    return AUDIT_SESSION_STAGES.map((id) => ({ id, server: serverStages.get(id) }));
  }, [sessionQuery.data?.stages]);

  const authoritativeId = sessionQuery.data?.current_stage_id as AuditSessionStageId | undefined;
  const viewingOtherStage = Boolean(routeStage && authoritativeId && routeStage !== authoritativeId);
  const nextStageHref = authoritativeId ? auditSessionPath(amoCode, auditKey, authoritativeId) : null;
  const nextStageIndex = authoritativeId ? AUDIT_SESSION_STAGES.indexOf(authoritativeId) : -1;

  const programmeParts = programmeLabel?.split(" · ") ?? [];
  const programmeRef = programmeParts[0] || null;
  const requirementTitle = programmeParts.length > 1 ? programmeParts.slice(1).join(" · ") : null;
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
          {programmeRef ? (
            <small className="qms-audit-session-rail__programme">
              Programme {programmeRef}
              {requirementTitle ? ` · ${requirementTitle}` : ""}
            </small>
          ) : null}
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

      <nav className="qms-audit-session-rail__functional" aria-label="Occurrence workspace">
        {AUDIT_OCCURRENCE_FUNCTIONAL_TABS.map((tab) => {
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
    </section>
  );
};

export default AuditLifecycleRail;

import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Circle, ShieldAlert } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { getAuditSession, type AuditSessionStageId } from "../../../services/qmsAuditSession";
import {
  AUDIT_SESSION_STAGES,
  auditSessionPath,
  auditSessionStageFromPath,
} from "./auditSessionRoutes";
import "../../../styles/qms-audit-session.css";

const STAGE_LABELS: Record<AuditSessionStageId, string> = {
  setup: "Setup",
  prepare: "Prepare",
  live: "Live",
  closing: "Closing",
  "follow-up": "Follow-up",
  archive: "Archive",
};

type Props = { amoCode: string; auditKey: string };

const AuditLifecycleRail: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const routeStage = auditSessionStageFromPath(location.pathname);

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

  const stageState = useMemo(() => {
    const serverStages = new Map(sessionQuery.data?.stages.map((stage) => [stage.id, stage]) || []);
    return AUDIT_SESSION_STAGES.map((id) => ({ id, server: serverStages.get(id) }));
  }, [sessionQuery.data?.stages]);

  return <section className="qms-audit-session-rail" aria-label="Audit lifecycle">
    <div className="qms-audit-session-rail__meta"><div><span>Audit occurrence</span><strong>{auditQuery.data?.audit_ref || auditKey}</strong></div>{sessionQuery.isError || auditQuery.isError ? <span className="qms-audit-session-rail__degraded" title="Authoritative session state could not be verified."><ShieldAlert size={14} /> State unavailable</span> : <span>{sessionQuery.data ? `${sessionQuery.data.percent_complete}% governed lifecycle` : "Loading governed lifecycle…"}</span>}</div>
    <nav className="qms-audit-session-rail__steps" aria-label="Audit occurrence stages">
      {stageState.map(({ id, server }, index) => {
        const selected = routeStage === id || (!routeStage && server?.active === true);
        const complete = server?.complete === true;
        return <React.Fragment key={id}><Link to={auditSessionPath(amoCode, auditKey, id)} className={`qms-audit-session-step${selected ? " is-selected" : ""}${complete ? " is-complete" : ""}`} aria-current={selected ? "step" : undefined} title={server?.helper || `Open ${STAGE_LABELS[id]}`}><span className="qms-audit-session-step__icon" aria-hidden="true">{complete ? <Check size={14} /> : <Circle size={10} />}</span><span>{STAGE_LABELS[id]}</span></Link>{index < stageState.length - 1 ? <span className="qms-audit-session-step__line" aria-hidden="true" /> : null}</React.Fragment>;
      })}
    </nav>
    {sessionQuery.data ? <div className="qms-audit-session-rail__authority" role="note">Authoritative next stage: <strong>{sessionQuery.data.current_stage_label}</strong>{routeStage && routeStage !== sessionQuery.data.current_stage_id ? <span> · Viewing {STAGE_LABELS[routeStage]} without changing lifecycle state.</span> : null}</div> : null}
  </section>;
};

export default AuditLifecycleRail;

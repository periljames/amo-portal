import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, ShieldAlert } from "lucide-react";

import { getRosterWorkflowGates } from "../../../services/rosteringCompliance";
import type { RosterWorkflowGateRead } from "../../../types/rosteringCompliance";
import { errorMessage, formatDateTime } from "../rosterUi";
import { StatusPill } from "./RosterShell";

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function DutyTimeline({ gate }: { gate: RosterWorkflowGateRead }) {
  const windowStart = asString(gate.details.window_start);
  const windowEnd = asString(gate.details.window_end);
  const intervals = Array.isArray(gate.details.duty_intervals) ? gate.details.duty_intervals : [];
  if (!windowStart || !windowEnd) return null;
  const start = Date.parse(windowStart);
  const end = Date.parse(windowEnd);
  const span = Math.max(1, end - start);
  return (
    <div className="wr-timeline" aria-label="Exact 168-hour duty and rest timeline">
      <div className="wr-timeline__labels"><span>{formatDateTime(windowStart)}</span><strong>168h rolling window</strong><span>{formatDateTime(windowEnd)}</span></div>
      <div className="wr-timeline__track">
        {intervals.map((raw, index) => {
          if (!raw || typeof raw !== "object") return null;
          const row = raw as Record<string, unknown>;
          const dutyStart = asString(row.starts_at || row.start);
          const dutyEnd = asString(row.ends_at || row.end);
          if (!dutyStart || !dutyEnd) return null;
          const left = Math.max(0, Math.min(100, ((Date.parse(dutyStart) - start) / span) * 100));
          const width = Math.max(0.5, Math.min(100 - left, ((Date.parse(dutyEnd) - Date.parse(dutyStart)) / span) * 100));
          return <span key={`${dutyStart}:${index}`} className="wr-timeline__duty" style={{ left: `${left}%`, width: `${width}%` }} title={`Duty ${formatDateTime(dutyStart)} → ${formatDateTime(dutyEnd)}`} />;
        })}
      </div>
      <div className="wr-timeline__legend"><span><i className="wr-timeline__legend-duty" /> Duty / on-site standby</span><span>Blank = duty-free interval</span></div>
    </div>
  );
}

function GateCard({ gate }: { gate: RosterWorkflowGateRead }) {
  const protectedRest = gate.code === "ROSTER_PROTECTED_REST_VIOLATION";
  const longest = asNumber(gate.details.longest_rest_minutes);
  const required = asNumber(gate.details.required_rest_minutes);
  return (
    <article className={`wr-recommendation wr-governance-gate wr-governance-gate--${gate.severity.toLowerCase()}`}>
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">{gate.severity.replace(/_/g, " ")}</span>
          <h3>{protectedRest ? "Protected Rest Required — Publication Blocked" : gate.code.replace(/_/g, " ")}</h3>
          <p>{gate.message}</p>
        </div>
        <StatusPill value={gate.severity} tone={gate.severity === "HARD_BLOCK" ? "blocker" : gate.severity === "CONDITIONAL_BLOCK" ? "warning" : undefined} />
      </div>
      <div className="wr-form-grid wr-form-grid--inspector">
        {gate.personnel_id ? <div><span className="wr-eyebrow">Personnel</span><strong>{gate.personnel_id}</strong></div> : null}
        {gate.assignment_id ? <div><span className="wr-eyebrow">Assignment</span><strong>{gate.assignment_id}</strong></div> : null}
        {asString(gate.details.window_start) ? <div><span className="wr-eyebrow">Rolling window starts</span><strong>{formatDateTime(String(gate.details.window_start))}</strong></div> : null}
        {asString(gate.details.window_end) ? <div><span className="wr-eyebrow">Rolling window ends</span><strong>{formatDateTime(String(gate.details.window_end))}</strong></div> : null}
        {longest !== null ? <div><span className="wr-eyebrow">Longest uninterrupted rest</span><strong>{Math.floor(longest / 60)}h {longest % 60}m</strong></div> : null}
        {required !== null ? <div><span className="wr-eyebrow">Required uninterrupted rest</span><strong>{Math.floor(required / 60)}h {required % 60}m</strong></div> : null}
      </div>
      {protectedRest ? <DutyTimeline gate={gate} /> : null}
      {gate.severity === "HARD_BLOCK" ? <div className="wr-inline-warning"><ShieldAlert size={15} /><span>This is a statutory hard block. Personnel consent and managerial approval cannot cure it. The roster must be changed or a verified in-scope Authority exemption must apply where legally available.</span></div> : null}
      {gate.remediation_actions.length ? <div className="wr-actions wr-actions--wrap">{gate.remediation_actions.map((action) => <span key={action} className="wr-pill">{action.replace(/_/g, " ")}</span>)}</div> : null}
    </article>
  );
}

export function RosterComplianceControlPanel({ versionId }: { versionId: string }) {
  const query = useQuery({
    queryKey: ["rostering", "workflow-gates", versionId],
    queryFn: () => getRosterWorkflowGates(versionId),
    enabled: Boolean(versionId),
    staleTime: 10_000,
  });
  const groups = useMemo(() => {
    const gates = query.data?.gates || [];
    return {
      hard: gates.filter((row) => row.severity === "HARD_BLOCK"),
      conditional: gates.filter((row) => row.severity === "CONDITIONAL_BLOCK"),
      warning: gates.filter((row) => row.severity === "WARNING"),
    };
  }, [query.data?.gates]);

  return (
    <section className="wr-panel" aria-labelledby="roster-compliance-control-title">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Authoritative workflow gate</span><h2 id="roster-compliance-control-title">Compliance and publication readiness</h2><p>Every lifecycle action is recalculated from the current duty timestamps. A previous PASS is never reused after the roster changes.</p></div>{query.data ? <StatusPill value={query.data.workflow_state.replace(/_/g, " ")} tone={query.data.hard_block_count ? "blocker" : query.data.conditional_block_count ? "warning" : "good"} /> : null}</div>
      {query.isPending ? <div className="wr-recommendation-loading"><RefreshCw size={14} className="is-spinning" /> Loading current workflow gates…</div> : null}
      {query.error ? <div className="wr-inline-error">{errorMessage(query.error)}</div> : null}
      {query.data ? <div className="wr-inline-counts"><span className="wr-pill wr-pill--blocker">{query.data.hard_block_count} hard blocks</span><span className="wr-pill wr-pill--warning">{query.data.conditional_block_count} conditional blocks</span><span className="wr-pill">{query.data.warning_count} warnings</span></div> : null}
      {query.data && !query.data.gates.length ? <div className="wr-success-note"><CheckCircle2 size={17} /> No unresolved compliance or workflow gates.</div> : null}
      {groups.hard.length ? <><div className="wr-section-heading"><div><span className="wr-eyebrow">Statutory</span><h3>Hard blocks</h3></div><AlertTriangle size={18} /></div>{groups.hard.map((gate, index) => <GateCard key={`${gate.code}:${gate.assignment_id || index}`} gate={gate} />)}</> : null}
      {groups.conditional.length ? <><div className="wr-section-heading"><div><span className="wr-eyebrow">Workflow</span><h3>Conditional blocks</h3></div><Clock3 size={18} /></div>{groups.conditional.map((gate, index) => <GateCard key={`${gate.code}:${gate.consent_id || gate.extension_id || index}`} gate={gate} />)}</> : null}
      {groups.warning.length ? <><div className="wr-section-heading"><div><span className="wr-eyebrow">Fatigue / operational</span><h3>Warnings</h3></div></div>{groups.warning.map((gate, index) => <GateCard key={`${gate.code}:${index}`} gate={gate} />)}</> : null}
      {query.data ? <div className="wr-form-grid wr-form-grid--inspector"><div><span className="wr-eyebrow">Submit</span><strong>{query.data.can_submit ? "Available" : "Blocked / not applicable"}</strong></div><div><span className="wr-eyebrow">Approve</span><strong>{query.data.can_approve ? "Available" : "Blocked / not applicable"}</strong></div><div><span className="wr-eyebrow">Publish</span><strong>{query.data.can_publish ? "Available" : "Blocked / not applicable"}</strong></div></div> : null}
    </section>
  );
}

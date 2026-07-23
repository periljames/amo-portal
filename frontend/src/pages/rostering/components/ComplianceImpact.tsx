import { useCallback, useEffect, useMemo, useState } from "react";
import { addDays } from "date-fns";
import {
  AlertTriangle,
  BadgeCheck,
  BookOpenCheck,
  CalendarRange,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { getPlanningBoard } from "../../../services/rostering";
import type { RosterPlanningBoardResponse, RosterValidationFindingRead } from "../../../types/rostering";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, MetricCard, RosterError, RosterLoading, StatusPill } from "./RosterShell";

function rangeDefaults() {
  const from = new Date();
  return { from: isoDate(from), to: isoDate(addDays(from, 60)) };
}

function category(finding: RosterValidationFindingRead): "training" | "licence" | "authorisation" | "other" {
  const key = `${finding.source} ${finding.code}`.toUpperCase();
  if (key.includes("TRAIN")) return "training";
  if (key.includes("LICENCE")) return "licence";
  if (key.includes("AUTHORISATION") || key.includes("CERTIFY")) return "authorisation";
  return "other";
}

export function ComplianceImpact() {
  const [range, setRange] = useState(rangeDefaults);
  const [data, setData] = useState<RosterPlanningBoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getPlanningBoard(range));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { void load(); }, [load]);

  const openFindings = useMemo(() => (data?.findings || []).filter((row) => !row.resolved), [data]);
  const groups = useMemo(() => ({
    training: openFindings.filter((row) => category(row) === "training"),
    licence: openFindings.filter((row) => category(row) === "licence"),
    authorisation: openFindings.filter((row) => category(row) === "authorisation"),
    other: openFindings.filter((row) => category(row) === "other"),
  }), [openFindings]);

  if (loading && !data) return <RosterLoading label="Calculating roster compliance impact…" />;
  if (error && !data) return <RosterError message={error} onRetry={load} />;
  if (!data) return null;

  const blockerCount = openFindings.filter((row) => row.severity === "BLOCKER").length;

  const renderGroup = (title: string, description: string, icon: React.ReactNode, findings: RosterValidationFindingRead[]) => (
    <section className="wr-panel wr-compliance-group">
      <div className="wr-section-heading">
        <div className="wr-heading-with-icon">{icon}<div><span className="wr-eyebrow">Compliance gate</span><h2>{title}</h2><p>{description}</p></div></div>
        <span className={`wr-count-badge${findings.some((row) => row.severity === "BLOCKER") ? " is-danger" : ""}`}>{findings.length}</span>
      </div>
      {findings.length === 0 ? <div className="wr-success-note"><ShieldCheck size={17} /> No open findings in this category.</div> : (
        <div className="wr-finding-table">
          {findings.map((finding) => (
            <article key={finding.id} className="wr-finding-row">
              <StatusPill value={finding.severity} />
              <div><strong>{finding.code.replace(/_/g, " ")}</strong><p>{finding.message}</p><small>{finding.user_id ? `Person ${finding.user_id}` : "Coverage rule"}</small></div>
              {finding.overridable ? <StatusPill value="OVERRIDABLE" tone="warning" /> : <StatusPill value="MANDATORY" tone="blocker" />}
            </article>
          ))}
        </div>
      )}
    </section>
  );

  return (
    <div className="wr-compliance">
      <section className="wr-filter-bar">
        <label><span>From</span><input type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} /></label>
        <label><span>To</span><input type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} /></label>
        <button type="button" className="wr-button wr-button--secondary" onClick={load}><RefreshCw size={16} className={loading ? "is-spinning" : ""} /> Recalculate</button>
        <span className="wr-range-label"><CalendarRange size={15} /> Published rosters only</span>
      </section>

      <section className="wr-metric-grid">
        <MetricCard label="Compliance blockers" value={blockerCount} detail="Prevent safe assignment" tone={blockerCount ? "danger" : "good"} />
        <MetricCard label="Training impact" value={groups.training.length} detail="Missing, expired or conflicting" tone={groups.training.length ? "warning" : "good"} />
        <MetricCard label="Licence impact" value={groups.licence.length} detail="Invalid or due soon" tone={groups.licence.length ? "warning" : "good"} />
        <MetricCard label="Authorisation impact" value={groups.authorisation.length} detail="Scope or coverage gaps" tone={groups.authorisation.length ? "warning" : "good"} />
      </section>

      {openFindings.length === 0 ? <EmptyState title="Roster compliance is clear" description="Published assignments in the selected range have no open training, licence or authorisation findings." /> : null}

      <div className="wr-two-column">
        {renderGroup("Training validity and events", "Mandatory course validity and scheduled training conflicts.", <BookOpenCheck size={22} />, groups.training)}
        {renderGroup("Maintenance licence", "Licence presence, expiry and duty-date validity.", <BadgeCheck size={22} />, groups.licence)}
        {renderGroup("AMO authorisations", "Current authorisation scope and certifying coverage.", <ShieldAlert size={22} />, groups.authorisation)}
        {groups.other.length ? renderGroup("Related controls", "Other validation controls that affect compliant staffing.", <AlertTriangle size={22} />, groups.other) : null}
      </div>
    </div>
  );
}

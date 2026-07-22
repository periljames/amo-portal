import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  ClipboardCheck,
  Clock3,
  RefreshCw,
  UsersRound,
} from "lucide-react";
import { motion } from "framer-motion";

import { getRosterDashboard } from "../../../services/rostering";
import { errorMessage, monthBounds } from "../rosterUi";
import { EmptyState, MetricCard, RosterError, RosterLoading, StatusPill } from "./RosterShell";

const DASHBOARD_STALE_MS = 2 * 60_000;
const DASHBOARD_GC_MS = 7 * 24 * 60 * 60_000;

export function RosterDashboard() {
  const { amoCode = "" } = useParams();
  const range = useMemo(() => monthBounds(), []);
  const root = `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
  const query = useQuery({
    queryKey: ["rostering", "dashboard", range.from, range.to],
    queryFn: () => getRosterDashboard(range),
    staleTime: DASHBOARD_STALE_MS,
    gcTime: DASHBOARD_GC_MS,
    networkMode: "offlineFirst",
  });
  const data = query.data;

  if (query.isPending && !data) return <RosterLoading label="Loading duty command centre…" />;
  if (query.error && !data) return <RosterError message={errorMessage(query.error)} onRetry={() => void query.refetch()} />;
  if (!data) return null;

  const operationalTone = data.blocker_count > 0 ? "danger" : data.warning_count > 0 ? "warning" : "good";

  return (
    <div className="wr-dashboard">
      <section className="wr-metric-grid" aria-label="Rostering key performance indicators">
        <MetricCard label="Open periods" value={data.active_period_count} detail={`${data.draft_version_count} drafts`} tone="info" />
        <MetricCard label="Awaiting control" value={data.submitted_version_count} detail="Submitted versions" tone={data.submitted_version_count ? "warning" : "neutral"} />
        <MetricCard label="Published" value={data.published_version_count} detail="Current month" tone="good" />
        <MetricCard label="Capacity gap" value={`${data.capacity_gap_hours.toFixed(1)}h`} detail="Uncovered demand" tone={data.capacity_gap_hours > 0 ? "danger" : "good"} />
        <MetricCard label="Pending leave" value={data.pending_leave_count} detail="Supervisor or HR action" tone={data.pending_leave_count ? "warning" : "neutral"} />
        <MetricCard label="Acknowledgements" value={data.unacknowledged_publication_count} detail="Still outstanding" tone={data.unacknowledged_publication_count ? "warning" : "good"} />
      </section>

      <div className="wr-dashboard-grid">
        <section className="wr-panel wr-panel--priority">
          <div className="wr-section-heading">
            <div>
              <span className="wr-eyebrow">Operational pulse</span>
              <h2>Roster control</h2>
            </div>
            <button type="button" className="wr-icon-button" onClick={() => void query.refetch()} aria-label="Refresh command centre"><RefreshCw size={17} className={query.isFetching ? "is-spinning" : ""} /></button>
          </div>
          <div className={`wr-readiness wr-tone-${operationalTone}`}>
            <div className="wr-readiness__score">
              {data.blocker_count > 0 ? <AlertTriangle size={28} /> : <ClipboardCheck size={28} />}
              <strong>{data.blocker_count > 0 ? "Action required" : data.warning_count > 0 ? "Review warnings" : "Ready"}</strong>
            </div>
            <div className="wr-readiness__facts">
              <span><b>{data.blocker_count}</b> blockers</span>
              <span><b>{data.warning_count}</b> warnings</span>
              <span><b>{data.capacity_gap_hours.toFixed(1)}h</b> gap</span>
            </div>
          </div>
          <div className="wr-command-actions">
            <Link className="wr-command-link" to={`${root}/calendar`}>
              <CalendarDays size={19} />
              <span><strong>Open duty planner</strong><small>Create, validate and publish versions</small></span>
              <ArrowRight size={16} />
            </Link>
            <Link className="wr-command-link" to={`${root}/planning-board`}>
              <UsersRound size={19} />
              <span><strong>Review manpower capacity</strong><small>Compare available hours with work demand</small></span>
              <ArrowRight size={16} />
            </Link>
            <Link className="wr-command-link" to={`${root}/my-roster`}>
              <Clock3 size={19} />
              <span><strong>Open employee self-service</strong><small>Duty, leave, attendance and timesheets</small></span>
              <ArrowRight size={16} />
            </Link>
          </div>
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading">
            <div>
              <span className="wr-eyebrow">Control queue</span>
              <h2>Highest priority findings</h2>
            </div>
            <Link to={`${root}/calendar`} className="wr-text-link">View all <ArrowRight size={14} /></Link>
          </div>
          {data.top_findings.length === 0 ? (
            <EmptyState title="No unresolved findings" description="Current roster versions have no blocker or warning findings." />
          ) : (
            <div className="wr-finding-table">
              {data.top_findings.map((finding) => (
                <motion.article key={finding.id} layout className="wr-finding-row">
                  <StatusPill value={finding.severity} />
                  <div>
                    <strong>{finding.code.replace(/_/g, " ")}</strong>
                    <p>{finding.message}</p>
                  </div>
                </motion.article>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div>
            <span className="wr-eyebrow">Planning horizon</span>
            <h2>Roster periods and versions</h2>
          </div>
        </div>
        {data.upcoming_periods.length === 0 ? (
          <EmptyState title="No roster periods" description="Create the first roster period from the planner or setup workspace." />
        ) : (
          <div className="wr-period-list">
            {data.upcoming_periods.map((period) => {
              const latest = [...period.versions].sort((a, b) => b.version_no - a.version_no)[0];
              return (
                <article className="wr-period-row" key={period.id}>
                  <div className="wr-period-row__date">
                    <CalendarDays size={18} />
                    <span><strong>{period.period_code}</strong><small>{period.starts_on} → {period.ends_on}</small></span>
                  </div>
                  <div className="wr-period-row__name"><strong>{period.name}</strong><small>{period.timezone_name}</small></div>
                  <StatusPill value={period.status} />
                  <div className="wr-period-row__version">{latest ? <>v{latest.version_no} <StatusPill value={latest.status} /></> : "No version"}</div>
                  <Link className="wr-icon-button" to={`${root}/calendar`} aria-label={`Open ${period.name}`}><ArrowRight size={17} /></Link>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

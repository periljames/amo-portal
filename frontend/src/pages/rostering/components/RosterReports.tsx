import { useCallback, useEffect, useMemo, useState } from "react";
import { addDays } from "date-fns";
import {
  BarChart3,
  Download,
  FileDown,
  FileSpreadsheet,
  RefreshCw,
  UsersRound,
} from "lucide-react";

import { exportRosterReport, getRosterReportSummary } from "../../../services/rostering";
import type { RosterReportSummary } from "../../../types/rostering";
import { errorMessage, hoursLabel, isoDate } from "../rosterUi";
import { EmptyState, MetricCard, RosterError, RosterLoading } from "./RosterShell";

function defaults() {
  const from = new Date();
  return { from: isoDate(from), to: isoDate(addDays(from, 30)) };
}

export function RosterReports() {
  const [range, setRange] = useState(defaults);
  const [data, setData] = useState<RosterReportSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getRosterReportSummary(range));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { void load(); }, [load]);

  const download = async (format: "csv" | "xlsx" | "pdf" | "ics") => {
    setExporting(format);
    setError(null);
    try {
      await exportRosterReport({ ...range, format });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setExporting(null);
    }
  };

  const utilisation = useMemo(() => data?.planned_minutes ? Math.min((Number(data.productive_minutes || 0) / data.planned_minutes) * 100, 100) : 0, [data]);

  if (loading && !data) return <RosterLoading label="Loading roster reports…" />;
  if (error && !data) return <RosterError message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="wr-reports">
      <section className="wr-filter-bar">
        <label><span>From</span><input type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} /></label>
        <label><span>To</span><input type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} /></label>
        <button type="button" className="wr-button wr-button--secondary" onClick={load}><RefreshCw size={16} className={loading ? "is-spinning" : ""} /> Refresh</button>
        <div className="wr-export-group" aria-label="Export roster report">
          <button type="button" onClick={() => download("csv")} disabled={!!exporting}><FileDown size={15} /> CSV</button>
          <button type="button" onClick={() => download("xlsx")} disabled={!!exporting}><FileSpreadsheet size={15} /> XLSX</button>
          <button type="button" onClick={() => download("pdf")} disabled={!!exporting}><Download size={15} /> PDF</button>
          <button type="button" onClick={() => download("ics")} disabled={!!exporting}><Download size={15} /> ICS</button>
        </div>
      </section>
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}

      <section className="wr-metric-grid">
        <MetricCard label="Planned" value={hoursLabel(data.planned_minutes)} detail={`${data.assignment_count} assignments`} tone="info" />
        <MetricCard label="Attendance" value={hoursLabel(data.attendance_minutes)} detail={`${data.assigned_people} people`} tone="neutral" />
        <MetricCard label="Productive" value={hoursLabel(data.productive_minutes)} detail={`${utilisation.toFixed(0)}% of planned`} tone={utilisation >= 80 ? "good" : "warning"} />
        <MetricCard label="Overtime" value={hoursLabel(data.overtime_minutes)} detail="Approved and generated" tone={data.overtime_minutes ? "warning" : "neutral"} />
        <MetricCard label="Acknowledged" value={`${data.acknowledgement_rate.toFixed(0)}%`} detail="Published roster receipt" tone={data.acknowledgement_rate >= 95 ? "good" : "warning"} />
        <MetricCard label="Validation" value={`${data.blocker_count}/${data.warning_count}`} detail="Blockers / warnings" tone={data.blocker_count ? "danger" : data.warning_count ? "warning" : "good"} />
      </section>

      <div className="wr-two-column wr-two-column--wide">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Time mix</span><h2>Planned activity</h2></div><BarChart3 size={20} /></div>
          <div className="wr-time-mix">
            {[
              ["Duty", Math.max(data.planned_minutes - data.standby_minutes - data.training_minutes - data.leave_minutes, 0), "duty"],
              ["Standby", data.standby_minutes, "standby"],
              ["Training", data.training_minutes, "training"],
              ["Leave", data.leave_minutes, "leave"],
            ].map(([label, minutes, tone]) => {
              const numeric = Number(minutes);
              const percentage = data.planned_minutes ? (numeric / data.planned_minutes) * 100 : 0;
              return <article key={String(label)}><div><strong>{label}</strong><span>{hoursLabel(numeric)}</span></div><div className="wr-progress"><span className={`is-${tone}`} style={{ width: `${Math.min(percentage, 100)}%` }} /></div><small>{percentage.toFixed(1)}%</small></article>;
            })}
          </div>
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Base comparison</span><h2>Capacity distribution</h2></div><UsersRound size={20} /></div>
          {data.by_base.length === 0 ? <EmptyState title="No base data" description="Published roster assignments will populate this comparison." /> : <div className="wr-data-list">{data.by_base.map((row, index) => <article className="wr-data-row" key={String(row.base_code || index)}><div><strong>{String(row.base_code || "UNASSIGNED")}</strong><small>{Number(row.assigned_people || 0)} people</small></div><span>{Number(row.assignment_count || 0)} assignments</span><span>{hoursLabel(Number(row.planned_minutes || 0))}</span></article>)}</div>}
        </section>
      </div>

      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Person-level reconciliation</span><h2>Planned, attended and productive time</h2></div></div>
        {data.by_user.length === 0 ? <EmptyState title="No person-level data" description="Published assignments and generated timesheets are required." /> : (
          <div className="wr-table-wrap">
            <table className="wr-table">
              <thead><tr><th>Person</th><th>Assignments</th><th>Planned</th><th>Attendance</th><th>Productive</th><th>Overtime</th><th>Variance</th></tr></thead>
              <tbody>{data.by_user.map((row, index) => <tr key={String(row.user_id || index)}><td><strong>{String(row.full_name || row.user_id)}</strong><small>{String(row.staff_code || "")}</small></td><td>{Number(row.assignment_count || 0)}</td><td>{hoursLabel(Number(row.planned_minutes || 0))}</td><td>{hoursLabel(Number(row.attendance_minutes || 0))}</td><td>{hoursLabel(Number(row.productive_minutes || 0))}</td><td>{hoursLabel(Number(row.overtime_minutes || 0))}</td><td className={Number(row.variance_minutes || 0) < 0 ? "is-negative" : ""}>{hoursLabel(Math.abs(Number(row.variance_minutes || 0)))}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

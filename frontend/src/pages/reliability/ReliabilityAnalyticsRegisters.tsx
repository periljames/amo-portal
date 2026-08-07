import React from "react";
import { Link } from "react-router-dom";

import type { DashboardResponse, DrilldownDescriptor, DrilldownResponse } from "./reliabilityAnalyticsTypes";
import { badgeClass, formatDate, formatNumber } from "./reliabilityAnalyticsUtils";

type Props = {
  data: DashboardResponse;
  basePath: string;
  drilldown: DrilldownResponse | null;
  drilldownTitle: string;
  drilldownLoading: boolean;
  openDrilldown: (descriptor: DrilldownDescriptor, title: string) => Promise<void>;
};

export function ReliabilityAnalyticsRegisters({ data, basePath, drilldown, drilldownTitle, drilldownLoading, openDrilldown }: Props): React.ReactElement {
  return <>
    <section className="reliability-analytics__register">
      <div className="reliability-analytics__register-heading">
        <div><p className="reliability-v2__eyebrow">Ranked fleet evidence</p><h2>Aircraft comparison register</h2></div>
        <span>{data.aircraft_performance.length} aircraft / allocations</span>
      </div>
      <div className="reliability-v2__table-wrap">
        <table className="reliability-v2__table">
          <thead><tr><th>Aircraft</th><th>Events</th><th>FH</th><th>FC</th><th>Rate /100 FH</th><th>Dispatch reliability</th><th>Repeat defects</th><th>Unscheduled removals</th></tr></thead>
          <tbody>
            {data.aircraft_performance.map((point) => (
              <tr
                key={point.key}
                onClick={() => void openDrilldown(point.drilldown, `Aircraft: ${point.label}`)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    void openDrilldown(point.drilldown, `Aircraft: ${point.label}`);
                  }
                }}
                tabIndex={0}
              >
                <td><strong>{point.label}</strong></td>
                <td>{formatNumber(point.metrics.events, 0)}</td>
                <td>{formatNumber(point.metrics.flight_hours, 1)}</td>
                <td>{formatNumber(point.metrics.flight_cycles, 0)}</td>
                <td>{formatNumber(point.metrics.event_rate_per_100_fh, 3)}</td>
                <td>{point.metrics.dispatch_reliability_pct == null ? "—" : `${formatNumber(point.metrics.dispatch_reliability_pct, 2)}%`}</td>
                <td>{formatNumber(point.metrics.repeat_defects, 0)}</td>
                <td>{formatNumber(point.metrics.unscheduled_removals, 0)}</td>
              </tr>
            ))}
            {data.aircraft_performance.length === 0 && <tr><td colSpan={8}>No aircraft-level exposure and events are available for this selection.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>

    <section className="reliability-analytics__register" id="reliability-dashboard-evidence">
      <div className="reliability-analytics__register-heading">
        <div><p className="reliability-v2__eyebrow">Chart drill-down</p><h2>{drilldownTitle || "Supporting controlled records"}</h2></div>
        {drilldown && <span>{drilldown.total} records</span>}
      </div>
      {drilldownLoading && <div className="reliability-analytics__loading reliability-analytics__loading--compact" role="status"><span /><strong>Resolving chart selection to source records…</strong></div>}
      {!drilldownLoading && !drilldown && <div className="reliability-analytics__empty reliability-analytics__empty--register"><strong>Select a KPI, graph point, bar or slice</strong><span>The exact canonical or controlled source records will appear here.</span></div>}
      {!drilldownLoading && drilldown && (
        <div className="reliability-v2__table-wrap">
          <table className="reliability-v2__table">
            <thead><tr><th>When</th><th>Record</th><th>Aircraft</th><th>Category</th><th>ATA</th><th>Status</th><th>Summary</th></tr></thead>
            <tbody>
              {drilldown.records.map((record) => (
                <tr key={`${record.record_type}-${record.id}`}>
                  <td>{formatDate(record.occurred_at)}</td>
                  <td>{record.route ? <Link to={`${basePath}/${record.route}`}>{record.reference || record.id}</Link> : record.reference || record.id}<small>{record.record_type.replaceAll("_", " ")}</small></td>
                  <td>{record.aircraft_serial_number || "Fleet"}</td>
                  <td>{record.category?.replaceAll("_", " ") || "—"}</td>
                  <td>{record.ata_chapter || "—"}</td>
                  <td><span className={badgeClass(record.status || record.severity)}>{record.status || record.severity || "—"}</span></td>
                  <td>{record.summary}</td>
                </tr>
              ))}
              {drilldown.records.length === 0 && <tr><td colSpan={7}>No controlled records matched this chart selection.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  </>;
}

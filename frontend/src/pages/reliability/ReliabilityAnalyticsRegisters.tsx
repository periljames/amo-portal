import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { DashboardResponse, DrilldownDescriptor, DrilldownResponse } from "./reliabilityAnalyticsTypes";
import { badgeClass, formatDate, formatNumber } from "./reliabilityAnalyticsUtils";
import "./ReliabilityDataTables.css";

type Props = {
  data: DashboardResponse;
  basePath: string;
  drilldown: DrilldownResponse | null;
  drilldownTitle: string;
  drilldownLoading: boolean;
  openDrilldown: (descriptor: DrilldownDescriptor, title: string) => Promise<void>;
};
const PAGE_SIZES = [25, 50, 100] as const;
function exportVisibleCsv(filename: string, headers: string[], values: Array<Array<string | number | null | undefined>>) {
  // Prevent spreadsheet formula evaluation when a source field is opened in Excel.
  const safe = (cell: string | number | null | undefined): string => {
    let value = cell == null ? "" : String(cell);
    if (typeof cell === "string" && /^[\s]*[=+\-@]/.test(value)) value = "'" + value;
    return '"' + value.replaceAll('"', '""') + '"';
  };
  const content = [headers.map(safe).join(","), ...values.map((row) => row.map(safe).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
function PageControls({ page, pageSize, total, setPage, setPageSize }: {
  page: number; pageSize: number; total: number;
  setPage: (value: number) => void; setPageSize: (value: number) => void;
}) {
  const count = Math.max(1, Math.ceil(total / pageSize));
  return <div className="rel-table__pager" aria-label="Table pagination">
    <span>{total ? page * pageSize + 1 : 0}–{Math.min(total, (page + 1) * pageSize)} of {total} loaded</span>
    <label>Rows <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0); }}>
      {PAGE_SIZES.map((size) => <option value={size} key={size}>{size}</option>)}</select></label>
    <button type="button" disabled={!page} onClick={() => setPage(Math.max(0, page - 1))}>Previous</button>
    <span>Page {page + 1} / {count}</span>
    <button type="button" disabled={page + 1 >= count} onClick={() => setPage(page + 1)}>Next</button>
  </div>;
}
export function ReliabilityAnalyticsRegisters({ data, basePath, drilldown, drilldownTitle, drilldownLoading, openDrilldown }: Props): React.ReactElement {
  const [aircraftQuery, setAircraftQuery] = useState("");
  const [sortKey, setSortKey] = useState("event_rate_per_100_fh");
  const [descending, setDescending] = useState(true);
  const [aircraftPage, setAircraftPage] = useState(0);
  const [aircraftPageSize, setAircraftPageSize] = useState(50);
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourcePage, setSourcePage] = useState(0);
  const [sourcePageSize, setSourcePageSize] = useState(50);
  const [selectedRecord, setSelectedRecord] = useState<number | null>(null);
  const aircraftRows = useMemo(() => data.aircraft_performance
    .filter((point) => point.label.toLowerCase().includes(aircraftQuery.toLowerCase()))
    .slice().sort((a, b) => {
      const aValue = sortKey === "aircraft" ? a.label : a.metrics[sortKey];
      const bValue = sortKey === "aircraft" ? b.label : b.metrics[sortKey];
      if (typeof aValue === "number" && typeof bValue === "number") return (descending ? -1 : 1) * (aValue - bValue);
      return (descending ? -1 : 1) * String(aValue ?? "").localeCompare(String(bValue ?? ""));
    }), [data.aircraft_performance, aircraftQuery, sortKey, descending]);
  const displayedAircraft = aircraftRows.slice(aircraftPage * aircraftPageSize, (aircraftPage + 1) * aircraftPageSize);
  const sourceRows = useMemo(() => (drilldown?.records || []).filter((record) =>
    [record.reference, record.id, record.aircraft_serial_number, record.category, record.ata_chapter,
      record.status, record.summary, record.record_type].some((field) =>
        String(field ?? "").toLowerCase().includes(sourceQuery.toLowerCase()))),
  [drilldown, sourceQuery]);
  const displayedSources = sourceRows.slice(sourcePage * sourcePageSize, (sourcePage + 1) * sourcePageSize);
  const sort = (key: string) => {
    setDescending((before) => key === sortKey ? !before : true);
    setSortKey(key);
    setAircraftPage(0);
  };
  const headers: Array<[string, string]> = [
    ["aircraft", "Aircraft"], ["events", "Events"], ["flight_hours", "FH"], ["flight_cycles", "FC"],
    ["event_rate_per_100_fh", "Rate /100 FH"], ["dispatch_reliability_pct", "Dispatch reliability"],
    ["repeat_defects", "Repeat defects"], ["unscheduled_removals", "Unscheduled removals"],
  ];
  const inspected = drilldown?.records[selectedRecord ?? 0];
  return <div className="rel-table__workspace">
    <div className="rel-table__summary-layout">
    <section className="reliability-analytics__register">
      <div className="reliability-analytics__register-heading">
        <div><p className="reliability-v2__eyebrow">Ranked fleet evidence</p><h2>Aircraft performance matrix</h2></div>
        <span>{data.aircraft_performance.length} returned aircraft / allocations</span>
      </div>
      <div className="rel-table__toolbar">
        <label>Find aircraft <input value={aircraftQuery} placeholder="Aircraft registration or label"
          onChange={(event) => { setAircraftQuery(event.target.value); setAircraftPage(0); }} /></label>
        <button type="button" onClick={() => exportVisibleCsv("reliability-aircraft-visible.csv",
          headers.map((x) => x[1]), displayedAircraft.map((row) =>
            headers.map(([key]) => key === "aircraft" ? row.label : row.metrics[key])))}>
          Export displayed rows
        </button>
      </div>
      <div className="rel-table__viewport" tabIndex={0} role="region" aria-label="Scrollable aircraft matrix">
        <table className="reliability-v2__table rel-table__dense">
          <thead><tr>{headers.map(([key, label]) => <th scope="col" key={key}>
            <button type="button" className="rel-table__sort" onClick={() => sort(key)}
              aria-label={"Sort by " + label} aria-sort={sortKey === key ? descending ? "descending" : "ascending" : "none"}>
              {label}{sortKey === key ? descending ? " ↓" : " ↑" : ""}
            </button></th>)}</tr></thead>
          <tbody>{displayedAircraft.map((point) => <tr key={point.key}>
            <td><button type="button" className="rel-table__record-link"
              onClick={() => void openDrilldown(point.drilldown, "Aircraft: " + point.label)}>{point.label}</button></td>
            <td>{formatNumber(point.metrics.events, 0)}</td><td>{formatNumber(point.metrics.flight_hours, 1)}</td>
            <td>{formatNumber(point.metrics.flight_cycles, 0)}</td>
            <td>{formatNumber(point.metrics.event_rate_per_100_fh, 3)}</td>
            <td>{point.metrics.dispatch_reliability_pct == null ? "—" : formatNumber(point.metrics.dispatch_reliability_pct, 2) + "%"}</td>
            <td>{formatNumber(point.metrics.repeat_defects, 0)}</td>
            <td>{formatNumber(point.metrics.unscheduled_removals, 0)}</td>
          </tr>)}
          {!displayedAircraft.length && <tr><td colSpan={8}>No aircraft-level data matches the current filter.</td></tr>}</tbody>
        </table>
      </div>
      <PageControls page={aircraftPage} pageSize={aircraftPageSize} total={aircraftRows.length}
        setPage={setAircraftPage} setPageSize={setAircraftPageSize} />
    </section>
    <aside className="rel-table__inspector" aria-label="Selected evidence summary">
      <div className="rel-table__inspector-head"><span className="reliability-v2__eyebrow">Evidence inspector</span>
        <h2>{drilldownTitle || "No evidence selected"}</h2></div>
      {drilldown ? <>
        <dl>
          <div><dt>Matching source records</dt><dd>{drilldown.total.toLocaleString()}</dd></div>
          <div><dt>Currently loaded</dt><dd>{drilldown.records.length.toLocaleString()}</dd></div>
          {inspected && <>
            <div><dt>Record reference</dt><dd>{inspected.reference || inspected.id}</dd></div>
            <div><dt>Record type</dt><dd>{inspected.record_type.replaceAll("_", " ")}</dd></div>
            <div><dt>Aircraft</dt><dd>{inspected.aircraft_serial_number || "Fleet-level"}</dd></div>
            <div><dt>ATA chapter</dt><dd>{inspected.ata_chapter || "Not recorded"}</dd></div>
            <div><dt>Status / severity</dt><dd>{inspected.status || inspected.severity || "Not classified"}</dd></div>
          </>}
        </dl>
        {drilldown.total > drilldown.records.length && <p className="rel-table__inspector-warning">
          This view contains a bounded subset. Open the canonical register for full history.
        </p>}
        {inspected?.route && <Link to={basePath + "/" + inspected.route}>Open original source record →</Link>}
      </> : <p>Choose a fleet metric, chart point or aircraft row to retrieve the source-backed drilldown.
        Only data returned by the backend is displayed.</p>}
      <nav aria-label="Source record shortcuts">
        <Link to={basePath + "/events"}>Occurrence register</Link>
        <Link to={basePath + "/workbook-registers"}>Controlled datasets</Link>
      </nav>
    </aside>
    </div>
    <section className="reliability-analytics__register" id="reliability-dashboard-evidence">
      <div className="reliability-analytics__register-heading">
        <div><p className="reliability-v2__eyebrow">Chart-to-source lineage</p><h2>{drilldownTitle || "Supporting controlled records"}</h2></div>
        {drilldown && <span>{drilldown.total} matching source records</span>}
      </div>
      {drilldownLoading && <div className="reliability-analytics__loading reliability-analytics__loading--compact" role="status">
        <span /><strong>Resolving selected point to source records…</strong></div>}
      {!drilldownLoading && !drilldown && <div className="reliability-analytics__empty reliability-analytics__empty--register">
        <strong>Select a metric or graph point</strong>
        <span>Follow a chart, KPI, or aircraft row to inspect evidence. You can also open the full
          <Link to={basePath + "/events"}> occurrence register</Link> or <Link to={basePath + "/workbook-registers"}> controlled source registers</Link>.</span>
      </div>}
      {drilldown && <>
        {drilldown.total > drilldown.records.length && <p className="rel-table__limited" role="status">
          Showing {drilldown.records.length} of {drilldown.total} matches returned by the evidence API.
          These controls page only the loaded subset. Use the canonical source register for complete retrieval.
        </p>}
        <div className="rel-table__toolbar">
          <label>Search loaded source records <input value={sourceQuery}
            onChange={(event) => { setSourceQuery(event.target.value); setSourcePage(0); }}
            placeholder="Reference, aircraft, ATA, status…" /></label>
          <button type="button" onClick={() => exportVisibleCsv("reliability-evidence-visible.csv",
            ["Date", "Reference", "Aircraft", "Type", "ATA", "Status", "Summary"],
            displayedSources.map((row) => [row.occurred_at, row.reference || row.id,
              row.aircraft_serial_number, row.record_type, row.ata_chapter,
              row.status || row.severity, row.summary]))}>Export displayed rows</button>
        </div>
        <div className="rel-table__viewport" tabIndex={0} role="region" aria-label="Scrollable supporting source records">
          <table className="reliability-v2__table rel-table__dense">
            <thead><tr><th>When</th><th>Reference</th><th>Aircraft</th><th>Category</th><th>ATA</th><th>Status</th><th>Summary</th></tr></thead>
            <tbody>{displayedSources.map((row) => <tr key={row.record_type + "-" + row.id}>
              <td>{formatDate(row.occurred_at)}</td>
              <td>{row.route ? <Link to={basePath + "/" + row.route}>{row.reference || row.id}</Link> : row.reference || row.id}
                <small>{row.record_type.replaceAll("_", " ")}</small></td>
              <td>{row.aircraft_serial_number || "Fleet"}</td>
              <td>{row.category?.replaceAll("_", " ") || "—"}</td><td>{row.ata_chapter || "—"}</td>
              <td><span className={badgeClass(row.status || row.severity)}>{row.status || row.severity || "—"}</span></td>
              <td><button type="button" className="rel-table__inspect" onClick={() =>
                setSelectedRecord(drilldown?.records.indexOf(row) ?? null)}
                aria-label={"Inspect evidence " + (row.reference || row.id)}>Inspect</button>
                {" "}{row.summary}</td>
            </tr>)}
            {!displayedSources.length && <tr><td colSpan={7}>No loaded records match this search.</td></tr>}</tbody>
          </table>
        </div>
        <PageControls page={sourcePage} pageSize={sourcePageSize} total={sourceRows.length}
          setPage={setSourcePage} setPageSize={setSourcePageSize} />
      </>}
    </section>
  </div>;
}

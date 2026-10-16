import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowDownToLine, ArrowLeft, ArrowRight, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import {
  listEngineTrendStatuses, listFracasCases, listReliabilityAlerts, listReliabilityEvents,
  type EngineTrend, type FracasCase, type ReliabilityAlert, type ReliabilityEvent,
  type ReliabilityAlertStatus, type FracasStatus, type EngineTrendStatus,
} from "../../services/reliability";
import "./ReliabilityBackendRegisters.css";

type View = "events" | "alerts" | "cases" | "engines";
type Row = ReliabilityEvent | ReliabilityAlert | FracasCase | EngineTrend;
const PAGE_SIZE = 75;
const ALERT_STATES: ReliabilityAlertStatus[] = ["OPEN", "ACKNOWLEDGED", "CLOSED"];
const CASE_STATES: FracasStatus[] = ["OPEN", "IN_ANALYSIS", "ACTIONS", "MONITORING", "CLOSED"];
const ENGINE_STATES: EngineTrendStatus[] = ["Trend Normal", "Trend Shift"];
const SORT_COLUMNS: Record<View, Array<string | null>> = {
  events: ["occurred_at", "aircraft", "severity", "ata", "source", null, null],
  alerts: ["code", "severity", "status", "triggered_at", null],
  cases: ["title", "aircraft", "severity", "status", "opened_at", null],
  engines: ["aircraft", null, "engine_serial", "status", "last_upload", "last_review"],
};
const DEFAULT_SORT: Record<View, string> = {
  events: "occurred_at", alerts: "triggered_at", cases: "updated_at", engines: "status",
};
const names: Record<View, string> = {
  events: "Occurrence register", alerts: "Technical alerts", cases: "FRACAS case register", engines: "Engine trend status",
};
const descriptions: Record<View, string> = {
  events: "Canonical technical occurrences with source-system evidence and event lineage.",
  alerts: "Alert dispositions, severity and current response state.",
  cases: "Investigation, root cause, corrective action and effectiveness status.",
  engines: "Engine serial, installed aircraft, condition shift and last monitoring dates.",
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^\s*[=+\-@]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function csvDownload(name: string, header: string[], values: string[][]): void {
  const contents = [header.map(csvCell), ...values.map((row) => row.map(csvCell))]
    .map((row) => row.join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([contents], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); anchor.remove();
  URL.revokeObjectURL(url);
}

export default function ReliabilityBackendRegisters({ view }: { view: View }): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const root = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  const [page, setPage] = useState(0);
  const [typedQuery, setTypedQuery] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sortKey, setSortKey] = useState(DEFAULT_SORT[view]);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<Row[]>([]);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    const offset = page * PAGE_SIZE;
    const limit = PAGE_SIZE + 1;
    const request: Promise<Row[]> = view === "events"
      ? listReliabilityEvents({ limit, offset, q: query || undefined, sortKey, sortDir })
      : view === "alerts"
        ? listReliabilityAlerts({ limit, offset, status: (status || undefined) as ReliabilityAlertStatus | undefined, q: query || undefined, sortKey, sortDir })
        : view === "cases"
          ? listFracasCases({ limit, offset, status: (status || undefined) as FracasStatus | undefined, q: query || undefined, sortKey, sortDir })
          : listEngineTrendStatuses({ limit, offset, currentStatus: (status || undefined) as EngineTrendStatus | undefined, q: query || undefined, sortKey, sortDir });
    void request.then((items) => {
      if (active) { setHasNext(items.length > PAGE_SIZE); setRows(items.slice(0, PAGE_SIZE)); setLoading(false); }
    }).catch((cause: unknown) => {
      if (active) { setError(cause instanceof Error ? cause.message : "Register could not be loaded"); setLoading(false); }
    });
    return () => { active = false; };
  }, [view, page, query, status, sortKey, sortDir, refresh]);

  const results = useMemo(() => rows, [rows]);
  const startLoading = () => { setLoading(true); setError(""); };
  const setSort = (key: string) => {
    startLoading();
    setPage(0);
    setSortDir((current) => sortKey === key ? (current === "asc" ? "desc" : "asc") : "asc");
    setSortKey(key);
  };
  const columns = view === "events" ? ["Recorded", "Aircraft", "Event / severity", "ATA", "Source", "Description", "Reference"]
    : view === "alerts" ? ["Alert", "Severity", "Status", "Triggered", "Disposition"]
      : view === "cases" ? ["Case", "Aircraft", "Severity", "Status", "Opened", "Classification"]
        : ["Aircraft", "Position", "Engine serial", "Trend status", "Last upload", "Last review"];
  const tableRows = results.map((row): string[] => {
    if (view === "events") {
      const item = row as ReliabilityEvent;
      return [formatDate(item.occurred_at), item.aircraft_serial_number || "Fleet",
        item.event_type + " / " + (item.severity || "—"), item.ata_chapter || "—",
        item.source_system || "—", item.description || "—", item.reference_code || "—"];
    }
    if (view === "alerts") {
      const item = row as ReliabilityAlert;
      return [item.alert_code, item.severity, item.status, formatDate(item.triggered_at), item.message || "—"];
    }
    if (view === "cases") {
      const item = row as FracasCase;
      return [item.title, item.aircraft_serial_number || "Fleet", item.severity || "—",
        item.status, formatDate(item.opened_at), item.classification || "—"];
    }
    const item = row as EngineTrend;
    return [item.aircraft_serial_number, item.engine_position,
      item.engine_serial_number || "Unrecorded", item.current_status || "Unclassified",
      formatDate(item.last_upload_date), formatDate(item.last_review_date)];
  });
  return <section className="rel-backend-register" aria-label={names[view]}>
    <header className="rel-backend-register__header">
      <div><p className="reliability-v2__eyebrow">Reliability / Authoritative register</p>
        <h1>{names[view]}</h1><p>{descriptions[view]}</p></div>
      <button type="button" onClick={() => { startLoading(); setRefresh((v) => v + 1); }} disabled={loading}>
        <RefreshCw size={15} aria-hidden="true" /> Refresh</button>
    </header>
    <div className="rel-backend-register__tools">
      <form onSubmit={(event) => { event.preventDefault(); if (page !== 0 || query !== typedQuery.trim()) startLoading(); setPage(0); setQuery(typedQuery.trim()); }}>
        <label><Search size={16} aria-hidden="true" /><span className="sr-only">Search all {names[view]} records</span>
          <input type="search" placeholder={view === "events" ? "Search source occurrences…" : view === "alerts" ?
            "Search alert code or message…" : view === "cases" ? "Search FRACAS case, aircraft or classification…" :
            "Search aircraft or engine serial…"} value={typedQuery}
            onChange={(event) => setTypedQuery(event.target.value)} /></label>
        <button type="submit">Search all records</button>
      </form>
      {view !== "events" && <label className="rel-backend-register__status"><SlidersHorizontal size={16} aria-hidden="true" />
        <span>Filter status</span><select value={status} onChange={(event) => { startLoading(); setStatus(event.target.value); setPage(0); }}>
          <option value="">All statuses</option>
          {(view === "alerts" ? ALERT_STATES : view === "cases" ? CASE_STATES : ENGINE_STATES).map((value) =>
            <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
        </select></label>}
      <button type="button" disabled={!rows.length || loading}
        onClick={() => csvDownload("reliability-" + view + "-page-" + (page + 1) + ".csv", columns, tableRows)}>
        <ArrowDownToLine size={16} aria-hidden="true" /> Export loaded page
      </button>
    </div>
    <p className="rel-backend-register__scope"><strong>Database pagination and sorting</strong> · Up to {PAGE_SIZE} source records per page.
      Search, status filters and column ordering are applied by the server. CSV exports only the visible loaded page.
      There is no inferred total record count.</p>
    {error && <div className="rel-backend-register__error" role="alert">{error}
      <button type="button" onClick={() => { startLoading(); setRefresh((v) => v + 1); }}>Retry</button></div>}
    {loading && <p role="status" className="rel-backend-register__loading">Loading source records…</p>}
    {!loading && !error && <>
      <div className="rel-backend-register__viewport" role="region" aria-label={"Scrollable " + names[view]} tabIndex={0}>
        <table><thead><tr>{columns.map((column, index) => {
          const key = SORT_COLUMNS[view][index];
          return <th key={column} scope="col" aria-sort={key && key === sortKey ?
            (sortDir === "asc" ? "ascending" : "descending") : undefined}>
            {key ? <button type="button" className="rel-backend-register__sort"
              onClick={() => setSort(key)} disabled={loading}
              aria-label={"Sort all " + names[view] + " by " + column}>
              {column}{key === sortKey ? (sortDir === "asc" ? " ↑" : " ↓") : " ↕"}
            </button> : column}
          </th>;
        })}</tr></thead>
          <tbody>{results.map((row, i) => <tr key={row.id}>
            {tableRows[i].map((value, column) => <td key={columns[column]}>
              {column === 0 && view !== "engines" ?
                <Link to={root + "/" + view + "/" + row.id}>{value}</Link>
                : column === 0 && view === "engines" ? <strong>{value}</strong>
                  : value}
            </td>)}
          </tr>)}</tbody></table>
        {!results.length && <p className="rel-backend-register__empty">No records match this server-side filter.</p>}
      </div>
      <footer className="rel-backend-register__pager">
        <span>{results.length ? page * PAGE_SIZE + 1 : 0}–{page * PAGE_SIZE + results.length} loaded · Page {page + 1}</span>
        <div><button type="button" disabled={page === 0} onClick={() => { startLoading(); setPage((v) => Math.max(0, v - 1)); }}>
          <ArrowLeft size={16} aria-hidden="true" /> Previous</button>
          <button type="button" disabled={!hasNext} onClick={() => { startLoading(); setPage((v) => v + 1); }}>
            Next page <ArrowRight size={16} aria-hidden="true" /></button></div>
      </footer>
    </>}
  </section>;
}

/* eslint-disable react-refresh/only-export-components */
import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ChartCardProps, ChartPoint, ChartTableRow, DashboardFilters, DashboardMetric, DashboardResponse, EngineSeriesResponse, MetricStatus, SavedView } from "./reliabilityAnalyticsTypes";

export const SAVED_VIEW_KEY = "amo.reliability.analytics.saved-views.v1";
export const CHART_HEIGHT = 320;
export const PIE_COLORS = [
  "var(--reliability-chart-1)",
  "var(--reliability-chart-2)",
  "var(--reliability-chart-3)",
  "var(--reliability-chart-4)",
  "var(--reliability-chart-5)",
  "var(--reliability-chart-6)",
];

export function dateInput(value: Date): string {
  const adjusted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 10);
}

export function defaultFilters(): DashboardFilters {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 89);
  return {
    periodStart: dateInput(start),
    periodEnd: dateInput(end),
    bucket: "AUTO",
    aircraft: "",
    aircraftType: "",
    ataChapter: "",
    station: "",
    eventType: "",
    severity: "",
    sourceSystem: "",
  };
}

export function statusClass(status: MetricStatus): string {
  return `reliability-analytics__metric reliability-analytics__metric--${status.toLowerCase().replaceAll("_", "-")}`;
}

export function badgeClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll("_", "-").replaceAll(" ", "-")}`;
}

export function formatNumber(value: number | null | undefined, maximumFractionDigits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

export function formatMetric(metric: DashboardMetric): string {
  if (metric.value == null) return "No exposure";
  if (metric.unit === "%") return `${formatNumber(metric.value, 2)}%`;
  if (metric.unit === "/100 FH") return `${formatNumber(metric.value, 3)} /100 FH`;
  if (metric.unit === "min") return `${formatNumber(metric.value, 1)} min`;
  if (metric.unit === "FH/removal") return `${formatNumber(metric.value, 1)} FH`;
  if (metric.unit === "count") return formatNumber(metric.value, 0);
  return `${formatNumber(metric.value, 2)} ${metric.unit}`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function buildSearch(filters: DashboardFilters): URLSearchParams {
  const params = new URLSearchParams({
    period_start: filters.periodStart,
    period_end: filters.periodEnd,
    bucket: filters.bucket,
  });
  if (filters.aircraft) params.append("aircraft", filters.aircraft);
  if (filters.aircraftType) params.append("aircraft_types", filters.aircraftType);
  if (filters.ataChapter) params.append("ata_chapters", filters.ataChapter);
  if (filters.station) params.append("stations", filters.station);
  if (filters.eventType) params.append("event_types", filters.eventType);
  if (filters.severity) params.append("severities", filters.severity);
  if (filters.sourceSystem) params.append("source_systems", filters.sourceSystem);
  return params;
}

export function readSavedViews(): SavedView[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SAVED_VIEW_KEY) || "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((item): SavedView[] => {
      if (!item || typeof item !== "object") return [];
      const candidate = item as Partial<SavedView>;
      if (typeof candidate.id !== "string" || typeof candidate.name !== "string" || !candidate.filters) return [];
      return [{
        id: candidate.id,
        name: candidate.name,
        filters: { ...defaultFilters(), ...candidate.filters },
      }];
    });
  } catch {
    return [];
  }
}

function isChartPoint(value: unknown): value is ChartPoint {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ChartPoint>;
  return typeof candidate.key === "string" && typeof candidate.label === "string" && Boolean(candidate.metrics);
}

export function chartPointFromEvent(value: unknown): ChartPoint | null {
  if (isChartPoint(value)) return value;
  if (!value || typeof value !== "object") return null;
  const candidate = value as { payload?: unknown; activePayload?: Array<{ payload?: unknown }> };
  if (isChartPoint(candidate.payload)) return candidate.payload;
  const active = candidate.activePayload?.find((item) => isChartPoint(item.payload));
  return active && isChartPoint(active.payload) ? active.payload : null;
}

export function chartLabelFromEvent(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { activeLabel?: unknown; label?: unknown };
  const label = candidate.activeLabel ?? candidate.label;
  return typeof label === "string" && label ? label : null;
}

function downloadBlob(content: BlobPart, mimeType: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeCsv(value: unknown): string {
  const text = value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function chartRows(section: string, rows: ChartPoint[]): string[] {
  const metricKeys = Array.from(new Set(rows.flatMap((row) => Object.keys(row.metrics))));
  return [
    ["section", "key", "label", ...metricKeys].map(escapeCsv).join(","),
    ...rows.map((row) => [section, row.key, row.label, ...metricKeys.map((key) => row.metrics[key])].map(escapeCsv).join(",")),
  ];
}

export function exportRowsCsv(rows: ChartTableRow[], filename: string): void {
  if (!rows.length) return;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const lines = [
    columns.map(escapeCsv).join(","),
    ...rows.map((row) => columns.map((column) => escapeCsv(row[column])).join(",")),
  ];
  downloadBlob(lines.join("\n"), "text/csv;charset=utf-8", `${filename}.csv`);
}

export function exportDashboardCsv(data: DashboardResponse): void {
  const sections: Array<[string, ChartPoint[]]> = [
    ["time_series", data.time_series],
    ["event_mix", data.event_mix],
    ["ata_pareto", data.ata_pareto],
    ["aircraft_performance", data.aircraft_performance],
    ["station_delay", data.station_delay],
    ["route_delay", data.route_delay],
    ["component_reliability", data.component_reliability],
    ["component_removal_age", data.component_removal_age],
    ["shop_visit_trend", data.shop_visit_trend],
    ["oil_consumption", data.oil_consumption],
    ["deferral_status", data.deferral_status],
    ["deferral_expiry", data.deferral_expiry],
    ["deferral_categories", data.deferral_categories],
    ["deferral_extensions", data.deferral_extensions],
    ["deferral_repeats", data.deferral_repeats],
    ["deferral_closure", data.deferral_closure],
    ["fracas_stages", data.fracas_stages],
    ["fracas_ageing", data.fracas_ageing],
    ["root_causes", data.root_causes],
    ["effectiveness", data.effectiveness],
    ["fracas_actions", data.fracas_actions],
    ["fracas_action_trend", data.fracas_action_trend],
    ["fracas_reopened", data.fracas_reopened],
    ["engine_status", data.engine_status],
    ["source_health", data.source_health],
    ["data_quality", data.data_quality],
  ];
  const lines = [
    ["metric", "value", "unit", "delta_pct", "denominator", "formula_code", "detail"].map(escapeCsv).join(","),
    ...data.summary.map((metric) => [metric.label, metric.value, metric.unit, metric.delta_pct, metric.denominator, metric.formula_code, metric.detail].map(escapeCsv).join(",")),
    "",
    ...sections.flatMap(([name, rows]) => [...chartRows(name, rows), ""]),
  ];
  downloadBlob(lines.join("\n"), "text/csv;charset=utf-8", `reliability-dashboard-${data.period_start}-${data.period_end}.csv`);
}

export function exportChartSvg(containerId: string, filename: string): void {
  const element = document.getElementById(containerId);
  const svg = element?.querySelector("svg");
  if (!svg) return;
  const clone = svg.cloneNode(true) as SVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const source = new XMLSerializer().serializeToString(clone);
  downloadBlob(source, "image/svg+xml;charset=utf-8", `${filename}.svg`);
}

export function flattenEngineSeries(response: EngineSeriesResponse | null): Array<Record<string, number | string>> {
  if (!response) return [];
  const buckets = new Map<string, Record<string, number | string>>();
  for (const [seriesName, points] of Object.entries(response.series)) {
    for (const point of points) {
      const key = point.timestamp.slice(0, 10);
      const row = buckets.get(key) || { date: key };
      row[seriesName] = point.value;
      buckets.set(key, row);
    }
  }
  return Array.from(buckets.values()).sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

function primitiveColumns(rows: ChartTableRow[]): string[] {
  return Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).filter((column) =>
    rows.some((row) => {
      const value = row[column];
      return value == null || ["string", "number", "boolean"].includes(typeof value);
    }),
  );
}

function displayCell(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ChartCard({ id, eyebrow, title, description, empty, children, onExport, wide = false, tableRows = [], formulaCodes = [] }: ChartCardProps): React.ReactElement {
  const [showTable, setShowTable] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const cardRef = useRef<HTMLElement | null>(null);
  const columns = useMemo(() => primitiveColumns(tableRows), [tableRows]);

  useEffect(() => {
    const update = () => setIsFullscreen(document.fullscreenElement === cardRef.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  const toggleFullscreen = async () => {
    if (document.fullscreenElement === cardRef.current) {
      await document.exitFullscreen();
      return;
    }
    await cardRef.current?.requestFullscreen();
  };

  return (
    <section ref={cardRef} className={`reliability-analytics__chart-card${wide ? " reliability-analytics__chart-card--wide" : ""}${isFullscreen ? " reliability-analytics__chart-card--fullscreen" : ""}`}>
      <div className="reliability-analytics__chart-heading">
        <div>
          <p className="reliability-v2__eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p>{description}</p>
          {formulaCodes.length > 0 && <div className="reliability-analytics__formula-links" aria-label="Chart formula links">{formulaCodes.map((code) => <a href={`#formula-${code}`} key={code}>Formula: {code}</a>)}</div>}
        </div>
        <div className="reliability-analytics__chart-actions">
          {tableRows.length > 0 && <button className="reliability-analytics__icon-button" type="button" aria-expanded={showTable} onClick={() => setShowTable((value) => !value)}>{showTable ? "Hide data" : "Data table"}</button>}
          {tableRows.length > 0 && <button className="reliability-analytics__icon-button" type="button" onClick={() => exportRowsCsv(tableRows, `${id}-data`)}>Export CSV</button>}
          {onExport && <button className="reliability-analytics__icon-button" type="button" onClick={onExport}>Export SVG</button>}
          <button className="reliability-analytics__icon-button" type="button" onClick={() => void toggleFullscreen()}>{isFullscreen ? "Exit full screen" : "Full screen"}</button>
        </div>
      </div>
      <div className="reliability-analytics__chart" id={id}>
        {empty ? <div className="reliability-analytics__empty"><strong>No measured data</strong><span>Change the period or filters, or resolve the relevant source coverage gap.</span></div> : children}
      </div>
      {showTable && tableRows.length > 0 && (
        <div className="reliability-analytics__chart-table" role="region" aria-label={`${title} data table`} tabIndex={0}>
          <table>
            <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
            <tbody>{tableRows.map((row, index) => <tr key={`${id}-row-${index}`}>{columns.map((column) => <td key={column}>{displayCell(row[column])}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }): React.ReactElement {
  return (
    <label className="reliability-analytics__filter">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
      </select>
    </label>
  );
}

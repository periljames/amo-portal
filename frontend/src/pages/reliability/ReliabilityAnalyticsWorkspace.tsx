import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { apiRequest } from "../../services/apiClient";
import ReliabilityCommandOverview from "./ReliabilityCommandOverview";
import ReliabilityEngineSpotlight from "./ReliabilityEngineSpotlight";
import type { DashboardFilters, DashboardResponse, DrilldownDescriptor, DrilldownResponse, EngineSeriesResponse, SavedView } from "./reliabilityAnalyticsTypes";
import { buildSearch, chartLabelFromEvent, chartPointFromEvent, dateInput, defaultFilters, exportDashboardCsv, flattenEngineSeries, formatDate, formatMetric, formatNumber, readSavedViews, SAVED_VIEW_KEY, statusClass } from "./reliabilityAnalyticsUtils";
import { ReliabilityAnalyticsControlCharts } from "./ReliabilityAnalyticsControlCharts";
import { ReliabilityAnalyticsHealthCharts } from "./ReliabilityAnalyticsHealthCharts";
import { ReliabilityAnalyticsOperationalCharts } from "./ReliabilityAnalyticsOperationalCharts";
import { ReliabilityAnalyticsRegisters } from "./ReliabilityAnalyticsRegisters";
import { ReliabilityAnalyticsToolbar } from "./ReliabilityAnalyticsToolbar";
import { ReliabilityCalculationEvidence } from "./ReliabilityCalculationEvidence";
import { ReliabilityFormulaAdministration } from "./ReliabilityFormulaAdministration";
import { ReliabilityFormulaLibrary } from "./ReliabilityFormulaLibrary";
import { ReliabilityFormulaLifecycleControls } from "./ReliabilityFormulaLifecycleControls";
import "../../styles/reliability-v2.css";
import "./ReliabilityAnalyticsWorkspace.css";
import "./ReliabilityFormulaWorkbench.css";

type Area = "overview" | "operational" | "network" | "components" | "oil" | "engineering"
  | "deferrals" | "fracas" | "data" | "evidence" | "formulae" | "administration" | "governance" | "calculations";
const AREA_LABELS: Record<Area, string> = {
  overview: "Fleet reliability overview", operational: "Fleet performance trends",
  network: "Network delay analysis", components: "Component reliability",
  oil: "Oil consumption trends", engineering: "Engine health monitoring",
  deferrals: "Deferred defect controls", fracas: "FRACAS analysis",
  data: "Source confidence", evidence: "Analytical evidence register",
  formulae: "Formula library", administration: "Metric administration",
  governance: "Approval and effectivity", calculations: "Calculation snapshots",
};
const CHART_AREAS: Array<{ key: Area; label: string }> = [
  { key: "operational", label: "Fleet" }, { key: "network", label: "Network" },
  { key: "components", label: "Components" }, { key: "oil", label: "Oil" },
  { key: "engineering", label: "Engines" }, { key: "deferrals", label: "Deferrals" },
  { key: "fracas", label: "FRACAS" }, { key: "data", label: "Source health" },
];
function filtersFromUrl(): DashboardFilters {
  const defaults = defaultFilters();
  const search = new URLSearchParams(window.location.search);
  const result = { ...defaults };
  const fields: Array<[Exclude<keyof DashboardFilters, "bucket">, string]> = [
    ["periodStart", "period_start"], ["periodEnd", "period_end"],
    ["aircraft", "aircraft"], ["aircraftType", "aircraft_types"], ["ataChapter", "ata_chapters"],
    ["station", "stations"], ["eventType", "event_types"], ["severity", "severities"],
    ["sourceSystem", "source_systems"],
  ];
  fields.forEach(([name, key]) => { if (search.has(key)) result[name] = search.get(key) || ""; });
  const bucket = search.get("bucket");
  if (bucket === "AUTO" || bucket === "DAY" || bucket === "WEEK" || bucket === "MONTH") result.bucket = bucket;
  return result.periodStart <= result.periodEnd ? result : defaults;
}

const ReliabilityAnalyticsWorkspace: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const routeKey = location.pathname.split("/reliability/analytics/")[1]?.split("/")[0] || "overview";
  const area: Area = Object.prototype.hasOwnProperty.call(AREA_LABELS, routeKey) ? routeKey as Area : "overview";
  const isChartArea = CHART_AREAS.some((item) => item.key === area);
  const dashboardRequired = area !== "calculations" && area !== "governance";
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const [filters, setFilters] = useState<DashboardFilters>(filtersFromUrl);
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilters>(filtersFromUrl);
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [savedViews, setSavedViews] = useState<SavedView[]>(() => readSavedViews());
  const [selectedViewId, setSelectedViewId] = useState("");
  const [savedViewName, setSavedViewName] = useState("");
  const [drilldown, setDrilldown] = useState<DrilldownResponse | null>(null);
  const [drilldownTitle, setDrilldownTitle] = useState("");
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [engineMetric, setEngineMetric] = useState("");
  const [engineSeries, setEngineSeries] = useState<EngineSeriesResponse | null>(null);
  const [engineLoading, setEngineLoading] = useState(false);
  const requestSequence = useRef(0);

  const loadDashboard = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<DashboardResponse>(`/reliability/analytics-dashboard?${buildSearch(appliedFilters).toString()}`, {
        cacheTtlMs: refreshToken ? 0 : 20_000,
        persistCache: true,
      });
      if (requestId !== requestSequence.current) return;
      setData(response);
      setEngineMetric((current) => current && response.filters.engine_metrics.includes(current) ? current : response.filters.engine_metrics[0] || "");
    } catch (caught: unknown) {
      if (requestId !== requestSequence.current) return;
      setError(caught instanceof Error ? caught.message : "The Reliability analytics dashboard could not be loaded.");
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [appliedFilters, refreshToken]);

  useEffect(() => { if (dashboardRequired) void loadDashboard(); }, [loadDashboard, dashboardRequired]);

  useEffect(() => {
    let active = true;
    if (!engineMetric || area !== "engineering") {
      setEngineSeries(null);
      return () => { active = false; };
    }
    const load = async () => {
      setEngineLoading(true);
      try {
        const params = new URLSearchParams({
          period_start: appliedFilters.periodStart,
          period_end: appliedFilters.periodEnd,
          metric: engineMetric,
        });
        if (appliedFilters.aircraft) params.append("aircraft", appliedFilters.aircraft);
        const response = await apiRequest<EngineSeriesResponse>(`/reliability/analytics-dashboard/engine-series?${params.toString()}`, { cacheTtlMs: 20_000 });
        if (active) setEngineSeries(response);
      } catch {
        if (active) setEngineSeries(null);
      } finally {
        if (active) setEngineLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [appliedFilters.aircraft, appliedFilters.periodEnd, appliedFilters.periodStart, engineMetric, area]);

  const applyFilters = () => {
    setDrilldown(null);
    setAppliedFilters(filters);
    navigate({ pathname: location.pathname, search: buildSearch(filters).toString() }, { replace: true });
  };

  const applyRange = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(end.getDate() - (days - 1));
    const next = { ...filters, periodStart: dateInput(start), periodEnd: dateInput(end) };
    setFilters(next);
    setAppliedFilters(next);
    setDrilldown(null);
    navigate({ pathname: location.pathname, search: buildSearch(next).toString() }, { replace: true });
  };

  const resetFilters = () => {
    const next = defaultFilters();
    setFilters(next);
    setAppliedFilters(next);
    setSelectedViewId("");
    setDrilldown(null);
    navigate({ pathname: location.pathname, search: "" }, { replace: true });
  };

  const saveView = () => {
    const name = savedViewName.trim();
    if (!name) {
      setError("Enter a name before saving this Reliability view.");
      return;
    }
    const id = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `reliability-view-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const view: SavedView = { id, name, filters };
    const next = [...savedViews.filter((candidate) => candidate.name.toLowerCase() !== name.toLowerCase()), view];
    setSavedViews(next);
    setSelectedViewId(view.id);
    setSavedViewName("");
    setError(null);
    localStorage.setItem(SAVED_VIEW_KEY, JSON.stringify(next));
  };

  const applySavedView = (id: string) => {
    setSelectedViewId(id);
    const view = savedViews.find((candidate) => candidate.id === id);
    if (!view) return;
    setFilters(view.filters);
    setAppliedFilters(view.filters);
    setDrilldown(null);
    navigate({ pathname: location.pathname, search: buildSearch(view.filters).toString() }, { replace: true });
  };

  const deleteSavedView = () => {
    if (!selectedViewId) return;
    const next = savedViews.filter((view) => view.id !== selectedViewId);
    setSavedViews(next);
    setSelectedViewId("");
    localStorage.setItem(SAVED_VIEW_KEY, JSON.stringify(next));
  };

  const openDrilldown = useCallback(async (descriptor: DrilldownDescriptor, title: string) => {
    if (!descriptor.dimension || !descriptor.key) return;
    setDrilldownTitle(title);
    setDrilldownLoading(true);
    setDrilldown(null);
    try {
      const params = buildSearch(appliedFilters);
      params.set("dimension", descriptor.dimension);
      params.set("key", descriptor.key);
      if (descriptor.bucket) params.set("bucket", descriptor.bucket);
      params.set("limit", "200");
      const response = await apiRequest<DrilldownResponse>(`/reliability/analytics-dashboard/drilldown?${params.toString()}`, { cacheTtlMs: 0 });
      setDrilldown(response);
      navigate({ pathname: basePath + "/analytics/evidence", search: buildSearch(appliedFilters).toString() });
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The supporting records could not be loaded.");
    } finally {
      setDrilldownLoading(false);
    }
  }, [appliedFilters, basePath, navigate]);

  const handleChartClick = (value: unknown, title: string) => {
    const point = chartPointFromEvent(value);
    if (point) void openDrilldown(point.drilldown, `${title}: ${point.label}`);
  };

  const handleEngineChartClick = (value: unknown) => {
    const label = chartLabelFromEvent(value);
    if (!label || !engineMetric) return;
    void openDrilldown(
      { dimension: "engine_reading", key: `${engineMetric}::${label}` },
      `${engineMetric} engine readings: ${label}`,
    );
  };

  const trendRows = data?.time_series.map((point) => ({ ...point, ...point.metrics })) || [];
  const eventMixRows = data?.event_mix.map((point) => ({ ...point, ...point.metrics })) || [];
  const ataRows = data?.ata_pareto.map((point) => ({ ...point, ...point.metrics })) || [];
  const aircraftRows = data?.aircraft_performance.map((point) => ({ ...point, ...point.metrics })) || [];
  const stationRows = data?.station_delay.map((point) => ({ ...point, ...point.metrics })) || [];
  const routeRows = data?.route_delay.map((point) => ({ ...point, ...point.metrics })) || [];
  const componentRows = data?.component_reliability.map((point) => ({ ...point, ...point.metrics })) || [];
  const removalAgeRows = data?.component_removal_age.map((point) => ({ ...point, ...point.metrics })) || [];
  const shopVisitRows = data?.shop_visit_trend.map((point) => ({ ...point, ...point.metrics })) || [];
  const oilRows = data?.oil_consumption.map((point) => ({ ...point, ...point.metrics })) || [];
  const engineRows = flattenEngineSeries(engineSeries);
  const engineSeriesNames = engineSeries ? Object.keys(engineSeries.series) : [];

  return (
    <main className="reliability-v2 reliability-analytics rel-analytics-dashboard">
      <header className="reliability-v2__header reliability-analytics__header">
        <div>
          <p className="reliability-v2__eyebrow">Measured performance / {area === "overview" ? "Command" : "Analysis"}</p>
          <h1>{AREA_LABELS[area]}</h1>
          <p>Exposure-normalised analysis with controlled source evidence, repeatable calculations and defined decision authority.</p>
        </div>
        <div className="reliability-v2__actions">
          <Link className="btn btn-primary" to={basePath + "/octm"}>Oil source entries</Link>
          <Link className="btn btn-secondary" to={basePath + "/formal-review"}>Formal reports</Link>
        </div>
      </header>
      {isChartArea && <nav className="rel-analytics-dashboard__categories" aria-label="Chart category">
        {CHART_AREAS.map((item) => <Link key={item.key}
          className={item.key === area ? "is-active" : ""}
          aria-current={item.key === area ? "page" : undefined}
          to={basePath + "/analytics/" + item.key + "?" + buildSearch(appliedFilters).toString()}>{item.label}</Link>)}
      </nav>}
      {dashboardRequired && <details className="rel-analytics-dashboard__filters">
        <summary>Filter analysis by period, aircraft or technical category
          <span>{appliedFilters.periodStart} – {appliedFilters.periodEnd}</span>
        </summary>
        <ReliabilityAnalyticsToolbar
          filters={filters} data={data} loading={loading} savedViews={savedViews}
          selectedViewId={selectedViewId} savedViewName={savedViewName}
          setFilters={setFilters} setSavedViewName={setSavedViewName}
          applyFilters={applyFilters} applyRange={applyRange} resetFilters={resetFilters}
          refresh={() => setRefreshToken((value) => value + 1)}
          saveView={saveView} applySavedView={applySavedView} deleteSavedView={deleteSavedView}
          exportCsv={() => data && exportDashboardCsv(data)}
        />
      </details>}
      {loading && dashboardRequired && <div className="reliability-analytics__loading" role="status"><span /><strong>Loading Reliability analysis…</strong></div>}
      {error && <div className="reliability-v2__error" role="alert"><strong>Reliability request failed.</strong><span>{error}</span><button type="button" className="btn btn-secondary" onClick={() => setRefreshToken((value) => value + 1)}>Retry</button></div>}
      {area === "overview" && <ReliabilityCommandOverview />}
      {area === "calculations" && <ReliabilityCalculationEvidence />}
      {area === "governance" && <ReliabilityFormulaLifecycleControls />}
      {!loading && data && dashboardRequired && <>
        <section className="reliability-analytics__period-strip" aria-label="Analysis provenance">
          <span><strong>Measured</strong>{data.period_start} → {data.period_end}</span>
          <span><strong>Comparison</strong>{data.comparison_start} → {data.comparison_end}</span>
          <span><strong>Resolution</strong>{data.bucket.toLowerCase()}</span>
          <span><strong>Formulae</strong>{data.formulae.length} definitions</span>
          <span><strong>Generated</strong>{formatDate(data.generated_at)}</span>
        </section>
        {data.warnings.length > 0 && <section className="reliability-analytics__warnings" aria-label="Analysis limitations">
          {data.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </section>}
        {area === "overview" && <>
          <details className="rel-analytics-dashboard__kpi-details">
            <summary>Measured period indicators — {data.summary.length} exposure-normalised metrics
              <span>Expand to inspect values and source evidence</span></summary>
          <section className="reliability-analytics__metrics" aria-label="Reliability KPIs">
            {data.summary.map((metric) => <button type="button" className={statusClass(metric.status)}
              key={metric.code} onClick={() => void openDrilldown(metric.drilldown, metric.label)}>
              <span>{metric.label}</span><strong>{formatMetric(metric)}</strong>
              <small>{metric.delta_pct == null ? metric.detail : (metric.delta_pct > 0 ? "+" : "") + formatNumber(metric.delta_pct, 1) + "% vs prior period"}</small>
              {metric.denominator != null && <em>Exposure / sample: {formatNumber(metric.denominator, 1)}</em>}
              {metric.formula_code && <em>Formula: {metric.formula_code}</em>}
            </button>)}
          </section>
          </details>
          <nav className="rel-analytics-dashboard__shortcuts" aria-label="Analysis workspaces">
            <Link to={basePath + "/analytics/operational"}>Fleet trends <span>Rates and ATA</span></Link>
            <Link to={basePath + "/analytics/engineering"}>Engine monitoring <span>EHM parameters</span></Link>
            <Link to={basePath + "/analytics/deferrals"}>Deferrals <span>Expiry and recurrence</span></Link>
            <Link to={basePath + "/analytics/fracas"}>FRACAS <span>Effectiveness</span></Link>
            <Link to={basePath + "/analytics/evidence"}>Source evidence <span>Ranked registers</span></Link>
          </nav>
          <section className="reliability-analytics__graph-workspace" aria-label="Fleet trend">
            <div className="reliability-analytics__graph-heading">
              <div><p className="reliability-v2__eyebrow">At a glance</p><h2>Measured fleet trend</h2></div>
              <Link to={basePath + "/analytics/operational"}>Explore fleet charts →</Link>
            </div>
            <div className="reliability-analytics__grid">
              <ReliabilityAnalyticsOperationalCharts group="overview" trendRows={trendRows} eventMixRows={eventMixRows}
                ataRows={ataRows} aircraftRows={aircraftRows} stationRows={stationRows} routeRows={routeRows}
                componentRows={componentRows} removalAgeRows={removalAgeRows} shopVisitRows={shopVisitRows}
                oilRows={oilRows} onPoint={handleChartClick} />
            </div>
          </section>
        </>}
        {isChartArea && <section className="reliability-analytics__graph-workspace" aria-label={AREA_LABELS[area]}>
          <div className="reliability-analytics__graph-heading">
            <div><p className="reliability-v2__eyebrow">Chart workspace</p><h2>{AREA_LABELS[area]}</h2>
              <p>Interact, zoom, full-screen, export underlying data or select a plotted record for traceable drill-down.</p></div>
            <Link to={basePath + "/analytics/evidence"}>Evidence register →</Link>
          </div>
          <div className="reliability-analytics__grid">
            {(["operational", "network", "components", "oil"] as Area[]).includes(area) && <ReliabilityAnalyticsOperationalCharts
              group={area === "network" ? "network" : area === "components" ? "components" : area === "oil" ? "oil" : "fleet"}
              trendRows={trendRows} eventMixRows={eventMixRows} ataRows={ataRows} aircraftRows={aircraftRows}
              stationRows={stationRows} routeRows={routeRows} componentRows={componentRows} removalAgeRows={removalAgeRows}
              shopVisitRows={shopVisitRows} oilRows={oilRows} onPoint={handleChartClick} />}
            {(["deferrals", "fracas"] as Area[]).includes(area) &&
              <ReliabilityAnalyticsControlCharts data={data} onPoint={handleChartClick}
                group={area === "deferrals" ? "deferrals" : "fracas"} />}
            {(["engineering", "data"] as Area[]).includes(area) &&
              <ReliabilityAnalyticsHealthCharts data={data} onPoint={handleChartClick}
                group={area === "engineering" ? "engines" : "data"}
                onEnginePoint={handleEngineChartClick} engineMetric={engineMetric} setEngineMetric={setEngineMetric}
                engineSeries={engineSeries} engineRows={engineRows} engineSeriesNames={engineSeriesNames} engineLoading={engineLoading} />}
          </div>
          {area === "engineering" && <ReliabilityEngineSpotlight />}
        </section>}
        {area === "formulae" && <ReliabilityFormulaLibrary formulae={data.formulae} />}
        {area === "administration" && <ReliabilityFormulaAdministration formulae={data.formulae} />}
        {area === "evidence" && <ReliabilityAnalyticsRegisters
          data={data} basePath={basePath} drilldown={drilldown} drilldownTitle={drilldownTitle}
          drilldownLoading={drilldownLoading} openDrilldown={openDrilldown} />}
      </>}
    </main>
  );
};

export default ReliabilityAnalyticsWorkspace;

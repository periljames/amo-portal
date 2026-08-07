import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest } from "../../services/apiClient";
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

const ReliabilityAnalyticsWorkspace: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const [filters, setFilters] = useState<DashboardFilters>(() => defaultFilters());
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilters>(() => defaultFilters());
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

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  useEffect(() => {
    let active = true;
    if (!engineMetric) {
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
  }, [appliedFilters.aircraft, appliedFilters.periodEnd, appliedFilters.periodStart, engineMetric]);

  const applyFilters = () => {
    setDrilldown(null);
    setAppliedFilters(filters);
  };

  const applyRange = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(end.getDate() - (days - 1));
    const next = { ...filters, periodStart: dateInput(start), periodEnd: dateInput(end) };
    setFilters(next);
    setAppliedFilters(next);
    setDrilldown(null);
  };

  const resetFilters = () => {
    const next = defaultFilters();
    setFilters(next);
    setAppliedFilters(next);
    setSelectedViewId("");
    setDrilldown(null);
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
      window.requestAnimationFrame(() => document.getElementById("reliability-dashboard-evidence")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The supporting records could not be loaded.");
    } finally {
      setDrilldownLoading(false);
    }
  }, [appliedFilters]);

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
    <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
      <main className="reliability-v2 reliability-analytics">
        <header className="reliability-v2__header reliability-analytics__header">
          <div>
            <p className="reliability-v2__eyebrow">Measured fleet performance</p>
            <h1>Reliability intelligence</h1>
            <p>Exposure-normalised trends, operational consequences, technical recurrence and closed-loop effectiveness.</p>
          </div>
          <div className="reliability-v2__actions">
            <Link className="btn btn-primary" to={`${basePath}/operations`}>Operational sources</Link>
            <Link className="btn btn-secondary" to={`${basePath}/workbook-registers`}>Workbook parity</Link>
            <Link className="btn btn-secondary" to={`${basePath}/events`}>Occurrence register</Link>
            <Link className="btn btn-secondary" to={`${basePath}/reports`}>Controlled reports</Link>
          </div>
        </header>

        <nav className="reliability-analytics__section-nav" aria-label="Reliability analytics sections">
          <a href="#reliability-analytics-graphs">Interactive graphs</a>
          <a href="#reliability-formula-library">Formula library</a>
          <a href="#reliability-formula-administration">Metric administration</a>
          <a href="#reliability-formula-lifecycle-heading">Approval and effectivity</a>
          <a href="#reliability-calculation-evidence-heading">Calculation snapshots</a>
          <a href="#reliability-dashboard-evidence">Evidence register</a>
        </nav>

        <ReliabilityAnalyticsToolbar
          filters={filters}
          data={data}
          loading={loading}
          savedViews={savedViews}
          selectedViewId={selectedViewId}
          savedViewName={savedViewName}
          setFilters={setFilters}
          setSavedViewName={setSavedViewName}
          applyFilters={applyFilters}
          applyRange={applyRange}
          resetFilters={resetFilters}
          refresh={() => setRefreshToken((value) => value + 1)}
          saveView={saveView}
          applySavedView={applySavedView}
          deleteSavedView={deleteSavedView}
          exportCsv={() => data && exportDashboardCsv(data)}
        />

        {loading && <div className="reliability-analytics__loading" role="status"><span /><strong>Calculating denominator-aware Reliability analytics…</strong></div>}
        {error && <div className="reliability-v2__error" role="alert"><strong>Analytics could not be completed.</strong><span>{error}</span><button type="button" className="btn btn-secondary" onClick={() => setRefreshToken((value) => value + 1)}>Retry</button></div>}

        {!loading && data && <>
          <section className="reliability-analytics__period-strip">
            <span><strong>Measured period</strong>{data.period_start} → {data.period_end}</span>
            <span><strong>Comparison</strong>{data.comparison_start} → {data.comparison_end}</span>
            <span><strong>Resolution</strong>{data.bucket.toLowerCase()}</span>
            <span><strong>Formulae</strong>{data.formulae.length} controlled definitions</span>
            <span><strong>Generated</strong>{formatDate(data.generated_at)}</span>
          </section>

          {data.warnings.length > 0 && <section className="reliability-analytics__warnings" aria-label="Analytics limitations">{data.warnings.map((warning) => <p key={warning}>{warning}</p>)}</section>}

          <section className="reliability-analytics__metrics" aria-label="Reliability key performance indicators">
            {data.summary.map((metric) => <button type="button" className={statusClass(metric.status)} key={metric.code} onClick={() => void openDrilldown(metric.drilldown, metric.label)}>
              <span>{metric.label}</span>
              <strong>{formatMetric(metric)}</strong>
              <small>{metric.delta_pct == null ? metric.detail : `${metric.delta_pct > 0 ? "+" : ""}${formatNumber(metric.delta_pct, 1)}% vs prior period`}</small>
              {metric.denominator != null && <em>Exposure / sample: {formatNumber(metric.denominator, 1)}</em>}
              {metric.formula_code && <em>Formula: {metric.formula_code}</em>}
            </button>)}
          </section>

          <section id="reliability-analytics-graphs" className="reliability-analytics__graph-workspace" aria-label="Interactive Reliability graphs">
            <div className="reliability-analytics__graph-heading">
              <div><p className="reliability-v2__eyebrow">Interactive evidence</p><h2>Operational and engineering graphs</h2><p>Hover for values, select records, zoom ordered trends, control engine series, open full screen, export the visual or inspect the underlying table.</p></div>
            </div>
            <div className="reliability-analytics__grid">
              <ReliabilityAnalyticsOperationalCharts trendRows={trendRows} eventMixRows={eventMixRows} ataRows={ataRows} aircraftRows={aircraftRows} stationRows={stationRows} routeRows={routeRows} componentRows={componentRows} removalAgeRows={removalAgeRows} shopVisitRows={shopVisitRows} oilRows={oilRows} onPoint={handleChartClick} />
              <ReliabilityAnalyticsControlCharts data={data} onPoint={handleChartClick} />
              <ReliabilityAnalyticsHealthCharts data={data} onPoint={handleChartClick} onEnginePoint={handleEngineChartClick} engineMetric={engineMetric} setEngineMetric={setEngineMetric} engineSeries={engineSeries} engineRows={engineRows} engineSeriesNames={engineSeriesNames} engineLoading={engineLoading} />
            </div>
          </section>

          <ReliabilityFormulaLibrary formulae={data.formulae} />
          <ReliabilityFormulaAdministration formulae={data.formulae} />
          <ReliabilityFormulaLifecycleControls />
          <ReliabilityCalculationEvidence />

          <ReliabilityAnalyticsRegisters
            data={data}
            basePath={basePath}
            drilldown={drilldown}
            drilldownTitle={drilldownTitle}
            drilldownLoading={drilldownLoading}
            openDrilldown={openDrilldown}
          />
        </>}
      </main>
    </DepartmentLayout>
  );
};

export default ReliabilityAnalyticsWorkspace;

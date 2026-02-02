// src/pages/ehm/EhmTrendsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import Plot from "react-plotly.js";
import { useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { useEhmDemoMode } from "../../hooks/useEhmDemoMode";
import { demoTrendSeries } from "../../demo/ehmDemoData";
import {
  getEngineTrendSeries,
  listEngineTrendStatus,
  type EngineTrendSeries,
  type EngineTrendStatus,
} from "../../services/ehm";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import "../../styles/ehm.css";

const EhmTrendsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const amoSlug = params.amoCode ?? "UNKNOWN";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [metricFilter, setMetricFilter] = useState("ITT");
  const [overlay, setOverlay] = useState("ISA");
  const [engineOptions, setEngineOptions] = useState<EngineTrendStatus[]>([]);
  const [selectedEngineId, setSelectedEngineId] = useState<string>("");
  const [series, setSeries] = useState<EngineTrendSeries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { isDemoMode, canToggleDemo, setDemoMode } = useEhmDemoMode();

  const metricKeyMap: Record<string, string> = {
    ITT: "ITT_C",
    NG: "NG_PCT",
    NH: "NH_PCT",
    FF: "FF_PPH",
    OAT: "OAT_C",
  };
  const metricKey = metricKeyMap[metricFilter] ?? metricFilter;

  const markers = useMemo(
    () => [
      { label: "Compressor wash", date: "2024-05-18" },
      { label: "Chip light", date: "2024-06-02" },
      { label: "Borescope", date: "2024-06-12" },
    ],
    []
  );

  useEffect(() => {
    if (isDemoMode) return;
    listEngineTrendStatus()
      .then((rows) => {
        setEngineOptions(rows);
        if (rows.length > 0) {
          const first = rows[0];
          setSelectedEngineId(
            `${first.aircraft_serial_number}|${first.engine_position}|${first.engine_serial_number ?? ""}`
          );
        }
      })
      .catch((err) => {
        setError(err?.message || "Unable to load engine list.");
        setEngineOptions([]);
      });
  }, [isDemoMode]);

  useEffect(() => {
    if (isDemoMode) return;
    if (!selectedEngineId) return;
    const [aircraft, position, serial] = selectedEngineId.split("|");
    setLoading(true);
    setError(null);
    getEngineTrendSeries({
      aircraft_serial_number: aircraft,
      engine_position: position,
      engine_serial_number: serial || undefined,
      metric: metricKey,
    })
      .then((data) => setSeries(data))
      .catch((err) => {
        setError(err?.message || "Unable to load trend series.");
        setSeries(null);
      })
      .finally(() => setLoading(false));
  }, [isDemoMode, selectedEngineId, metricFilter, metricKey]);

  const demoSeries = useMemo(() => demoTrendSeries[metricFilter] ?? null, [metricFilter]);
  const activeSeries = isDemoMode ? demoSeries : series;

  const chartData = useMemo(() => {
    if (!activeSeries) return null;
    const points = activeSeries.points ?? [];
    const dates = points.map((point) => point.date);
    const rawValues = points.map((point) => point.raw);
    const correctedValues = points.map((point) => point.corrected);
    const baselineValues =
      activeSeries.baseline !== null ? points.map(() => activeSeries.baseline) : [];
    const controlValues =
      activeSeries.control_limit !== null ? points.map(() => activeSeries.control_limit) : [];
    const eventDates = (activeSeries.events ?? []).map((event) => event.date);
    const eventLabels = (activeSeries.events ?? []).map(
      (event) => event.description || event.event_type
    );

    return {
      dates,
      rawValues,
      correctedValues,
      baselineValues,
      controlValues,
      eventDates,
      eventLabels,
    };
  }, [activeSeries]);

  const chartLayout = useMemo(
    () => ({
      autosize: true,
      height: 360,
      margin: { l: 48, r: 20, t: 18, b: 40 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "var(--text-primary)" },
      xaxis: {
        title: "Date",
        type: "date",
        gridcolor: "rgba(148, 163, 184, 0.2)",
        zerolinecolor: "rgba(148, 163, 184, 0.3)",
      },
      yaxis: {
        title: metricFilter,
        gridcolor: "rgba(148, 163, 184, 0.2)",
        zerolinecolor: "rgba(148, 163, 184, 0.3)",
      },
      hovermode: "x unified",
      showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.2 },
    }),
    [metricFilter]
  );

  const chartConfig = useMemo(
    () => ({
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
      modeBarButtonsToAdd: ["drawline", "eraseshape"],
      toImageButtonOptions: {
        format: "png",
        filename: "engine-trend",
        scale: 2,
      },
    }),
    []
  );

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="reliability">
      <header className="ehm-hero ehm-hero--compact">
        <div>
          <p className="ehm-eyebrow">Engine Health Monitoring</p>
          <h1>Trend Graphs · {amoDisplay}</h1>
          <p className="ehm-subtitle">
            Corrected trend series with event markers, zoom controls, and export options.
          </p>
        </div>
        <div className="ehm-hero__actions">
          {canToggleDemo && (
            <label className="ehm-toggle">
              <input
                type="checkbox"
                checked={isDemoMode}
                onChange={(event) => setDemoMode(event.target.checked)}
              />
              Demo mode
            </label>
          )}
          <div className="ehm-muted">
            Use the chart toolbar to zoom, pan, download, and inspect values.
          </div>
        </div>
      </header>

      <section className="ehm-surface">
        <div className="ehm-surface__header">
          <div>
            <h2>Engine trend view</h2>
            <p className="ehm-muted">
              {isDemoMode
                ? "Engine PCE-17777 · Pos 1 · Program EHM-DEMO6"
                : "Select an engine to load the trend series."}
            </p>
          </div>
          <div className="ehm-toolbar">
            {!isDemoMode && (
              <label className="ehm-control">
                Engine
                <select
                  value={selectedEngineId}
                  onChange={(event) => setSelectedEngineId(event.target.value)}
                >
                  {engineOptions.map((engine) => {
                    const key = `${engine.aircraft_serial_number}|${engine.engine_position}|${engine.engine_serial_number ?? ""}`;
                    return (
                      <option key={key} value={key}>
                        {engine.aircraft_serial_number} · {engine.engine_position} ·{" "}
                        {engine.engine_serial_number ?? "—"}
                      </option>
                    );
                  })}
                </select>
              </label>
            )}
            <label className="ehm-control">
              Metric
              <select value={metricFilter} onChange={(e) => setMetricFilter(e.target.value)}>
                <option value="ITT">ITT</option>
                <option value="NG">NG</option>
                <option value="NH">NH</option>
                <option value="FF">Fuel Flow</option>
                <option value="OAT">OAT / ISA</option>
              </select>
            </label>
            <label className="ehm-control">
              Overlay
              <select value={overlay} onChange={(e) => setOverlay(e.target.value)}>
                <option value="ISA">ISA deviation</option>
                <option value="OAT">OAT</option>
                <option value="NONE">None</option>
              </select>
            </label>
            <label className="ehm-control">
              Range
              <select defaultValue="90d">
                <option value="30d">30 days</option>
                <option value="90d">90 days</option>
                <option value="1y">12 months</option>
              </select>
            </label>
          </div>
        </div>

        <div className="ehm-chart">
          <div className="ehm-chart__header">
            <div>
              <span className="badge badge--success">Trend Normal</span>
              <span className="ehm-muted"> · Metric: {metricFilter}</span>
            </div>
            <div className="ehm-chart__actions ehm-muted">
              Hover to inspect values. Use the chart toolbar to zoom, pan, and export.
            </div>
          </div>
          <div className="ehm-chart__canvas">
            {loading && !isDemoMode && (
              <div className="ehm-chart__placeholder">
                <p>Loading trend series…</p>
              </div>
            )}
            {!loading && error && (
              <div className="ehm-chart__placeholder">
                <p className="ehm-muted">{error}</p>
              </div>
            )}
            {!loading && !error && chartData && (
              <Plot
                data={[
                  {
                    x: chartData.dates,
                    y: chartData.rawValues,
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Raw",
                    line: { color: "#38bdf8", width: 2 },
                    marker: { size: 4 },
                  },
                  {
                    x: chartData.dates,
                    y: chartData.correctedValues,
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Corrected",
                    line: { color: "#a78bfa", width: 2 },
                    marker: { size: 4 },
                  },
                  ...(chartData.baselineValues.length
                    ? [
                        {
                          x: chartData.dates,
                          y: chartData.baselineValues,
                          type: "scatter",
                          mode: "lines",
                          name: "Baseline",
                          line: { color: "#22c55e", width: 2, dash: "dash" },
                        },
                      ]
                    : []),
                  ...(chartData.controlValues.length
                    ? [
                        {
                          x: chartData.dates,
                          y: chartData.controlValues,
                          type: "scatter",
                          mode: "lines",
                          name: "Control limit",
                          line: { color: "#f97316", width: 2, dash: "dot" },
                        },
                      ]
                    : []),
                  ...(chartData.eventDates.length
                    ? [
                        {
                          x: chartData.eventDates,
                          y: chartData.eventDates.map(() =>
                            Math.max(
                              ...chartData.rawValues.map((value) => value ?? 0),
                              ...chartData.correctedValues.map((value) => value ?? 0),
                              0
                            )
                          ),
                          type: "scatter",
                          mode: "markers",
                          name: "Events",
                          marker: { size: 8, color: "#facc15", symbol: "diamond" },
                          text: chartData.eventLabels,
                          hovertemplate: "%{text}<br>%{x}<extra></extra>",
                        },
                      ]
                    : []),
                ]}
                layout={chartLayout}
                config={chartConfig}
                style={{ width: "100%", height: "100%" }}
                useResizeHandler
              />
            )}
            {!loading && !error && !chartData && (
              <div className="ehm-chart__placeholder">
                <p>No trend series available yet.</p>
                <p className="ehm-muted">Overlay: {overlay}</p>
              </div>
            )}
          </div>
          <div className="ehm-chart__footer">
            <div>
              <strong>Markers</strong>
              <div className="ehm-marker-list">
                {(isDemoMode && demoSeries ? demoSeries.events : markers).map((marker) => (
                  <span key={marker.date} className="badge badge--neutral">
                    {"label" in marker ? marker.label : marker.description} · {marker.date}
                  </span>
                ))}
              </div>
            </div>
            <div className="ehm-chart__legend">
              <span>Raw</span>
              <span>Corrected</span>
              <span>Baseline</span>
            </div>
          </div>
        </div>
      </section>

      <section className="ehm-grid">
        <div className="ehm-stat">
          <p className="ehm-stat__label">EWMA</p>
          <p className="ehm-stat__value">0.18</p>
          <p className="ehm-stat__meta">Alpha 0.2 · Control limit 3.0</p>
        </div>
        <div className="ehm-stat">
          <p className="ehm-stat__label">CUSUM</p>
          <p className="ehm-stat__value">1.6</p>
          <p className="ehm-stat__meta">k=0.5 · Window 30 points</p>
        </div>
        <div className="ehm-stat">
          <p className="ehm-stat__label">Slope</p>
          <p className="ehm-stat__value">0.04</p>
          <p className="ehm-stat__meta">5-point slope trend</p>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default EhmTrendsPage;

// src/pages/ehm/EhmTrendsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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

type TrendRow = {
  date: string;
  raw: number | null;
  corrected: number | null;
  baseline: number | null;
  control: number | null;
};

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
  const [focusDate, setFocusDate] = useState<string | null>(null);

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
    if (isDemoMode || !selectedEngineId) return;
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
  }, [isDemoMode, selectedEngineId, metricKey]);

  const activeSeries = useMemo(
    () => (isDemoMode ? demoTrendSeries[metricFilter] ?? null : series),
    [isDemoMode, metricFilter, series]
  );

  const chartRows = useMemo<TrendRow[]>(() => {
    const points = activeSeries?.points ?? [];
    return points.map((point) => ({
      date: point.date,
      raw: point.raw,
      corrected: point.corrected,
      baseline: activeSeries?.baseline ?? null,
      control: activeSeries?.control_limit ?? null,
    }));
  }, [activeSeries]);

  const eventRows = useMemo(() => {
    const map = new Map((activeSeries?.events ?? []).map((event) => [event.date, event.description || event.event_type]));
    return chartRows
      .filter((row) => map.has(row.date))
      .map((row) => ({ ...row, eventLabel: map.get(row.date) }));
  }, [activeSeries?.events, chartRows]);

  const spikeRows = useMemo(() => {
    if (!activeSeries) return [];
    return activeSeries.points.filter((point) => {
      if (point.status && /shift|spike/i.test(point.status)) return true;
      if (point.delta == null) return false;
      return Math.abs(point.delta) >= 0.5;
    });
  }, [activeSeries]);

  const handleExport = () => {
    const csv = ["date,raw,corrected,baseline,control", ...chartRows.map((row) => `${row.date},${row.raw ?? ""},${row.corrected ?? ""},${row.baseline ?? ""},${row.control ?? ""}`)].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `engine-trend-${metricFilter.toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="reliability">
      <header className="ehm-hero ehm-hero--compact">
        <div>
          <p className="ehm-eyebrow">Engine Health Monitoring</p>
          <h1>Trend Graphs · {amoDisplay}</h1>
          <p className="ehm-subtitle">Corrected trend series with event markers, zoom-focused review, and CSV export.</p>
        </div>
        <div className="ehm-hero__actions">
          {canToggleDemo && (
            <label className="ehm-toggle">
              <input type="checkbox" checked={isDemoMode} onChange={(event) => setDemoMode(event.target.checked)} />
              Demo mode
            </label>
          )}
          <div className="ehm-actions">
            <button className="btn btn-secondary" type="button" onClick={handleExport}>Download CSV</button>
            <button className="btn btn-secondary" type="button" onClick={() => window.print()}>Print A4</button>
          </div>
          <div className="ehm-muted">Hover chart for values; select rows below to focus specific trend dates.</div>
        </div>
      </header>

      <section className="ehm-surface">
        <div className="ehm-surface__header">
          <div>
            <h2>Engine trend view</h2>
            <p className="ehm-muted">{isDemoMode ? "Engine PCE-17777 · Pos 1 · Program EHM-DEMO6" : "Select an engine to load the trend series."}</p>
          </div>
          <div className="ehm-toolbar">
            {!isDemoMode && (
              <label className="ehm-control">Engine
                <select value={selectedEngineId} onChange={(event) => setSelectedEngineId(event.target.value)}>
                  {engineOptions.map((engine) => {
                    const key = `${engine.aircraft_serial_number}|${engine.engine_position}|${engine.engine_serial_number ?? ""}`;
                    return <option key={key} value={key}>{engine.aircraft_serial_number} · {engine.engine_position} · {engine.engine_serial_number ?? "—"}</option>;
                  })}
                </select>
              </label>
            )}
            <label className="ehm-control">Metric
              <select value={metricFilter} onChange={(e) => setMetricFilter(e.target.value)}>
                <option value="ITT">ITT</option><option value="NG">NG</option><option value="NH">NH</option><option value="FF">Fuel Flow</option><option value="OAT">OAT / ISA</option>
              </select>
            </label>
            <label className="ehm-control">Overlay
              <select value={overlay} onChange={(e) => setOverlay(e.target.value)}>
                <option value="ISA">ISA deviation</option><option value="OAT">OAT</option><option value="NONE">None</option>
              </select>
            </label>
          </div>
        </div>

        <div className="ehm-chart">
          <div className="ehm-chart__header"><div><span className="badge badge--success">Trend Normal</span><span className="ehm-muted"> · Metric: {metricFilter}</span></div></div>
          <div className="ehm-chart__canvas">
            {loading && !isDemoMode ? <div className="ehm-chart__placeholder"><p>Loading trend series…</p></div> : null}
            {!loading && error ? <div className="ehm-chart__placeholder"><p className="ehm-muted">{error}</p></div> : null}
            {!loading && !error && chartRows.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartRows} margin={{ left: 16, right: 16, top: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
                  <XAxis dataKey="date" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
                  <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
                  <Tooltip />
                  {focusDate ? <ReferenceLine x={focusDate} stroke="#f97316" strokeDasharray="4 4" /> : null}
                  <Line type="monotone" dataKey="raw" name="Raw" stroke="#38bdf8" dot={{ r: 2 }} strokeWidth={2} />
                  <Line type="monotone" dataKey="corrected" name="Corrected" stroke="#a78bfa" dot={{ r: 2 }} strokeWidth={2} />
                  <Line type="monotone" dataKey="baseline" name="Baseline" stroke="#22c55e" dot={false} strokeDasharray="6 6" />
                  <Line type="monotone" dataKey="control" name="Control limit" stroke="#f97316" dot={false} strokeDasharray="2 4" />
                  <Scatter data={eventRows} dataKey="raw" fill="#facc15" name="Events" />
                </LineChart>
              </ResponsiveContainer>
            ) : null}
            {!loading && !error && chartRows.length === 0 ? <div className="ehm-chart__placeholder"><p>No trend series available yet.</p><p className="ehm-muted">Overlay: {overlay}</p></div> : null}
          </div>
          <div className="ehm-chart__footer">
            <div>
              <strong>Markers</strong>
              <div className="ehm-marker-list">{(isDemoMode && activeSeries ? activeSeries.events : markers).map((marker) => <span key={marker.date} className="badge badge--neutral">{"label" in marker ? marker.label : marker.description} · {marker.date}</span>)}</div>
            </div>
          </div>
        </div>

        <div className="ehm-surface__section">
          <div className="ehm-surface__header"><div><h3>Trend shifts & spikes</h3><p className="ehm-muted">Click a row to focus the chart on the exact point that shifted.</p></div></div>
          <div className="ehm-table">
            <table><thead><tr><th>Date</th><th>Raw</th><th>Corrected</th><th>Delta</th><th>Status</th><th>Action</th></tr></thead>
              <tbody>
                {spikeRows.length === 0 ? <tr><td colSpan={6} className="ehm-muted">No spikes detected. Trend shifts will appear here as they occur.</td></tr> : null}
                {spikeRows.map((point) => (
                  <tr key={point.date}><td>{point.date}</td><td>{point.raw ?? "—"}</td><td>{point.corrected ?? "—"}</td><td>{point.delta ?? "—"}</td><td>{point.status ?? "Observed"}</td>
                    <td><button className="btn btn-secondary" type="button" onClick={() => setFocusDate(point.date)}>Focus</button></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default EhmTrendsPage;

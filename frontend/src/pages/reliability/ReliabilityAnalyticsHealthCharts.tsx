import React, { useEffect, useState } from "react";
import { Bar, BarChart, Brush, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPoint, DashboardResponse, EngineSeriesResponse } from "./reliabilityAnalyticsTypes";
import { CHART_HEIGHT, ChartCard, PIE_COLORS, exportChartSvg } from "./reliabilityAnalyticsUtils";

type PointHandler = (value: unknown, title: string) => void;

function rows(points: ChartPoint[]): Array<ChartPoint & Record<string, unknown>> {
  return points.map((point) => ({ ...point, ...point.metrics }));
}

export function ReliabilityAnalyticsHealthCharts({ data, onPoint, onEnginePoint, engineMetric, setEngineMetric, engineSeries, engineRows, engineSeriesNames, engineLoading }: { data: DashboardResponse; onPoint: PointHandler; onEnginePoint: (value: unknown) => void; engineMetric: string; setEngineMetric: (value: string) => void; engineSeries: EngineSeriesResponse | null; engineRows: Array<Record<string, number | string>>; engineSeriesNames: string[]; engineLoading: boolean }): React.ReactElement {
  const [visibleSeries, setVisibleSeries] = useState<string[]>([]);
  const handleChartClick = onPoint;
  const handleEngineChartClick = onEnginePoint;
  const engineStatusRows = rows(data.engine_status);
  const sourceRows = rows(data.source_health);
  const dataQualityRows = rows(data.data_quality);

  useEffect(() => {
    setVisibleSeries(engineSeriesNames);
  }, [engineSeriesNames]);

  const toggleSeries = (seriesName: string) => {
    setVisibleSeries((current) => current.includes(seriesName)
      ? current.filter((item) => item !== seriesName)
      : [...current, seriesName]);
  };

  return <>
    <ChartCard id="rel-chart-engine-status" eyebrow="Condition monitoring" title="Engine status distribution" description="Current fleet engine trend classification." empty={data.engine_status.length === 0} tableRows={engineStatusRows} onExport={() => exportChartSvg("rel-chart-engine-status", "reliability-engine-status")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <PieChart>
          <Pie data={engineStatusRows} dataKey="count" nameKey="label" innerRadius={72} outerRadius={116} paddingAngle={2} onClick={(value: unknown) => handleChartClick(value, "Engine status")}>
            {data.engine_status.map((point, index) => <Cell key={point.key} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-engine-parameter" eyebrow="Engine health" title="Engine parameter trend" description="Select a parsed numeric EHM/ECTM parameter, control visible engine series and zoom the measured period." empty={!engineMetric || engineRows.length === 0} wide tableRows={engineRows} onExport={() => exportChartSvg("rel-chart-engine-parameter", `reliability-engine-${engineMetric || "parameter"}`)}>
      <div className="reliability-analytics__chart-control">
        <label><span>Parameter</span><select value={engineMetric} onChange={(event) => setEngineMetric(event.target.value)}><option value="">No numeric parameters available</option>{data.filters.engine_metrics.map((metric) => <option value={metric} key={metric}>{metric}</option>)}</select></label>
        {engineLoading && <span>Loading parameter records…</span>}
      </div>
      {engineSeriesNames.length > 0 && <fieldset className="reliability-analytics__series-control"><legend>Visible engine series</legend>{engineSeriesNames.slice(0, 12).map((seriesName) => <label key={seriesName}><input type="checkbox" checked={visibleSeries.includes(seriesName)} onChange={() => toggleSeries(seriesName)} />{seriesName}</label>)}</fieldset>}
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={engineRows} onClick={handleEngineChartClick}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" minTickGap={18} />
          <YAxis label={{ value: engineSeries?.unit || engineMetric, angle: -90, position: "insideLeft" }} />
          <Tooltip />
          <Legend />
          {engineSeries?.thresholds.map((threshold) => <ReferenceLine key={`${threshold.label}-${threshold.value}`} y={threshold.value} label={{ value: threshold.label, position: "insideTopRight" }} strokeDasharray="6 4" />)}
          {engineSeries?.markers.map((marker) => <ReferenceLine key={`${marker.timestamp}-${marker.aircraft_serial_number}-${marker.engine_position}`} x={marker.timestamp.slice(0, 10)} label={{ value: marker.status, position: "top" }} strokeDasharray="3 3" />)}
          {engineSeriesNames.slice(0, 12).filter((seriesName) => visibleSeries.includes(seriesName)).map((seriesName, index) => <Line key={seriesName} type="monotone" dataKey={seriesName} name={seriesName} stroke={PIE_COLORS[index % PIE_COLORS.length]} strokeWidth={2} dot={false} connectNulls />)}
          {engineRows.length > 12 && <Brush dataKey="date" height={24} travellerWidth={10} />}
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-source-health" eyebrow="Data confidence" title="Authoritative source health" description="Volume, invalid rate, freshness and failed ingestion batches by source." empty={data.source_health.length === 0} tableRows={sourceRows} formulaCodes={["source_invalid_rate_pct"]} onExport={() => exportChartSvg("rel-chart-source-health", "reliability-source-health")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="age_days" name="Age" unit=" d" />
          <YAxis type="number" dataKey="invalid_rate_pct" name="Invalid rate" unit="%" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Scatter name="Sources" data={sourceRows} onClick={(value: unknown) => handleChartClick(value, "Source")} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-data-quality" eyebrow="Validation control" title="Open data-quality issues" description="Issue types ranked by unresolved count and severity." empty={data.data_quality.length === 0} tableRows={dataQualityRows} onExport={() => exportChartSvg("rel-chart-data-quality", "reliability-data-quality")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={dataQualityRows} layout="vertical" margin={{ left: 48 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={170} />
          <Tooltip />
          <Legend />
          <Bar dataKey="open" name="Open" radius={[0, 4, 4, 0]} onClick={(value: unknown) => handleChartClick(value, "Data-quality issue")} />
          <Bar dataKey="critical" name="Critical" radius={[0, 4, 4, 0]} />
          <Bar dataKey="high" name="High" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  </>;
}

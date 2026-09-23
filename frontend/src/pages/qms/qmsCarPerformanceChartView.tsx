import React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartDatum, DepartmentExposureDatum } from "./qmsCarPerformanceCharts";

export type AnalysisMetricId = "qpi" | "workload" | "exposure" | "conversion" | "ageing";
export type AnalysisChartKind = "bar" | "hbar" | "line" | "area" | "pie" | "donut" | "radial";

/* eslint-disable-next-line react-refresh/only-export-components -- shared immutable chart configuration. */
export const ANALYSIS_METRICS: ReadonlyArray<{ id: AnalysisMetricId; label: string; hint: string }> = [
  { id: "qpi", label: "QPI vs target", hint: "On-time closure against the 80% requirement." },
  { id: "workload", label: "Workload", hint: "Open, overdue, review and closed volume." },
  { id: "exposure", label: "Department exposure", hint: "Open and overdue concentration by department." },
  { id: "conversion", label: "Finding conversion", hint: "Observations versus NC with and without CAR." },
  { id: "ageing", label: "Overdue ageing", hint: "Pareto buckets for overdue corrective actions." },
];

/* eslint-disable-next-line react-refresh/only-export-components -- shared immutable chart configuration. */
export const ANALYSIS_CHART_KINDS: ReadonlyArray<{ id: AnalysisChartKind; label: string }> = [
  { id: "bar", label: "Bar" },
  { id: "hbar", label: "Horizontal" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
  { id: "pie", label: "Pie" },
  { id: "donut", label: "Donut" },
  { id: "radial", label: "Radial" },
];

const GRID = "color-mix(in srgb, var(--qms-muted, #94a3b8) 55%, transparent)";
const AXIS = "var(--qms-muted, #94a3b8)";
const FALLBACK_FILLS = [
  "var(--accent-primary, #2563eb)",
  "var(--accent-danger, #dc2626)",
  "var(--accent-warning, #d97706)",
  "var(--accent-success, #15803d)",
  "var(--assurance-observation, #059669)",
  "var(--accent-secondary, #7c3aed)",
];

function fillFor(index: number, explicit?: string): string {
  return explicit || FALLBACK_FILLS[index % FALLBACK_FILLS.length];
}

/* eslint-disable-next-line react-refresh/only-export-components -- deterministic chart transformation exported for tests. */
export function exposureToSeries(rows: DepartmentExposureDatum[]): ChartDatum[] {
  return rows.map((row, index) => ({
    name: row.department,
    value: row.open + row.overdue,
    fill: fillFor(index),
  }));
}

type Props = {
  metric: AnalysisMetricId;
  chartKind: AnalysisChartKind;
  series: ChartDatum[];
  stacked?: DepartmentExposureDatum[];
  percentScale?: boolean;
};

const AnalysisFlexibleChart: React.FC<Props> = ({
  metric,
  chartKind,
  series,
  stacked,
  percentScale = false,
}) => {
  const useStack = metric === "exposure" && Array.isArray(stacked) && stacked.length > 0
    && (chartKind === "bar" || chartKind === "hbar");
  const pieData = series.filter((row) => row.value > 0);
  const radialData = series.map((row, index) => ({
    ...row,
    fill: fillFor(index, row.fill),
  }));
  const seriesMax = Math.max(0, ...series.map((row) => row.value));
  const yDomain = percentScale
    ? ([0, 100] as [number, number])
    : ([0, Math.max(seriesMax, 1)] as [number, number]);
  const noPositiveValues = !useStack && series.every((row) => row.value <= 0);

  if ((chartKind === "pie" || chartKind === "donut" || chartKind === "radial") && (pieData.length === 0 || noPositiveValues)) {
    return (
      <p className="qms-car-perf-chart-empty muted">
        No positive values for a {chartKind} chart yet. Switch to Bar, Line or Area to inspect zeros and targets.
      </p>
    );
  }

  if (useStack && stacked) {
    const horizontal = chartKind === "hbar";
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={stacked}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, left: horizontal ? 8 : 0, bottom: 4 }}
        >
          <CartesianGrid vertical={!horizontal} horizontal={horizontal} stroke={GRID} />
          {horizontal ? (
            <>
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} fontSize={11} />
              <YAxis type="category" dataKey="department" width={120} tickLine={false} axisLine={false} fontSize={11} />
            </>
          ) : (
            <>
              <XAxis dataKey="department" tickLine={false} axisLine={false} fontSize={11} interval={0} angle={-18} textAnchor="end" height={48} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={11} width={36} />
            </>
          )}
          <Tooltip />
          <Legend />
          <Bar dataKey="open" name="Open" stackId="exposure" maxBarSize={horizontal ? 22 : 48} fill="var(--accent-primary, #2563eb)" />
          <Bar dataKey="overdue" name="Overdue" stackId="exposure" maxBarSize={horizontal ? 22 : 48} fill="var(--accent-danger, #dc2626)" radius={horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (chartKind === "pie" || chartKind === "donut") {
    const inner = chartKind === "donut" ? "42%" : 0;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={pieData.length ? pieData : series}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={inner}
            outerRadius="72%"
            paddingAngle={2}
          >
            {(pieData.length ? pieData : series).map((entry, index) => (
              <Cell key={entry.name} fill={fillFor(index, entry.fill)} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (chartKind === "radial") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="18%"
          outerRadius="90%"
          data={radialData}
          startAngle={90}
          endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={percentScale ? [0, 100] : [0, "auto"]} tick={false} />
          <RadialBar background dataKey="value" cornerRadius={4}>
            {radialData.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </RadialBar>
          <Legend />
          <Tooltip />
        </RadialBarChart>
      </ResponsiveContainer>
    );
  }

  if (chartKind === "line") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} tick={{ fill: AXIS }} />
          <YAxis domain={yDomain} allowDecimals={!percentScale} tickLine={false} axisLine={false} fontSize={11} width={40} unit={percentScale ? "%" : undefined} tick={{ fill: AXIS }} />
          <Tooltip formatter={(value: number) => (percentScale ? [`${value}%`, "Rate"] : value)} />
          <Legend />
          <Line type="monotone" dataKey="value" name="Count" stroke="var(--accent-primary, #2563eb)" strokeWidth={2.5} dot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (chartKind === "area") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} tick={{ fill: AXIS }} />
          <YAxis domain={yDomain} allowDecimals={!percentScale} tickLine={false} axisLine={false} fontSize={11} width={40} unit={percentScale ? "%" : undefined} tick={{ fill: AXIS }} />
          <Tooltip formatter={(value: number) => (percentScale ? [`${value}%`, "Rate"] : value)} />
          <Legend />
          <Area type="monotone" dataKey="value" name="Count" stroke="var(--accent-primary, #2563eb)" fill="color-mix(in srgb, var(--accent-primary, #2563eb) 28%, transparent)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  const horizontal = chartKind === "hbar";
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={series}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 8, right: 16, left: horizontal ? 8 : 0, bottom: 4 }}
      >
        <CartesianGrid vertical={!horizontal} horizontal={horizontal} stroke={GRID} />
        {horizontal ? (
          <>
            <XAxis type="number" domain={yDomain} allowDecimals={!percentScale} tickLine={false} axisLine={false} fontSize={11} unit={percentScale ? "%" : undefined} tick={{ fill: AXIS }} />
            <YAxis type="category" dataKey="name" width={110} tickLine={false} axisLine={false} fontSize={11} tick={{ fill: AXIS }} />
          </>
        ) : (
          <>
            <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} tick={{ fill: AXIS }} />
            <YAxis domain={yDomain} allowDecimals={!percentScale} tickLine={false} axisLine={false} fontSize={11} width={40} unit={percentScale ? "%" : undefined} tick={{ fill: AXIS }} />
          </>
        )}
        <Tooltip formatter={(value: number) => (percentScale ? [`${value}%`, "Rate"] : value)} />
        <Legend />
        <Bar dataKey="value" name="Count" maxBarSize={horizontal ? 28 : 56} minPointSize={3} radius={horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0]}>
          {series.map((entry, index) => (
            <Cell key={entry.name} fill={fillFor(index, entry.fill)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

export default AnalysisFlexibleChart;

import React, { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import DashboardCard from "../DashboardCard";
import type { QualityCockpitVisualData } from "../QualityCockpitCanvas";

type NamedValue = { name: string; value: number; route: string };
type TrendPoint = { month: string; value: number; route: string };
type ScatterPoint = { name: string; samples: number; defects: number; route: string };

const ACCENT = {
  green: "var(--qms-accent-green)",
  rose: "var(--qms-accent-rose)",
  amber: "var(--qms-accent-amber)",
};

const PIE_COLORS = [
  "var(--qms-accent-rose)",
  "var(--qms-accent-green)",
  "var(--qms-accent-amber)",
  "var(--qms-accent-info)",
  "var(--qms-accent-indigo)",
];

const QmsTooltip: React.FC<{ active?: boolean; payload?: Array<{ dataKey: string; value: number; name?: string }>; label?: string }> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="qms-chart-tooltip">
      <strong>{label ?? payload[0].name}</strong>
      {payload.map((item) => (
        <div key={`${item.dataKey}-${item.value}`}>{item.dataKey}: {item.value}</div>
      ))}
    </div>
  );
};

const DeferredChart: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!hostRef.current || ready) return;
    const node = hostRef.current;
    const onVisible = () => {
      if ((window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback) {
        (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback?.(() => setReady(true));
      } else {
        window.setTimeout(() => setReady(true), 0);
      }
    };

    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        onVisible();
        observer.disconnect();
      }
    }, { threshold: 0.2 });

    observer.observe(node);
    return () => observer.disconnect();
  }, [ready]);

  return <div ref={hostRef} className="qms-chart-host">{ready ? children : <div className="qms-chart-skeleton" />}</div>;
};

const QualityScoreGauge = memo(function QualityScoreGauge({ value }: { value: number }) {
  const data = useMemo(() => [{ name: "score", value }], [value]);
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={220}>
        <RadialBarChart innerRadius="72%" outerRadius="100%" data={data} startAngle={180} endAngle={0}>
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar dataKey="value" cornerRadius={10} fill={ACCENT.green} background isAnimationActive={false} />
          <Tooltip content={<QmsTooltip />} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="qms-gauge-value">{value.toFixed(2)}%</div>
    </DeferredChart>
  );
});

const DonutChartCard = memo(function DonutChartCard({ data, onNavigate }: { data: NamedValue[]; onNavigate: (route: string) => void }) {
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={82} onClick={(v: { payload?: NamedValue }) => v?.payload?.route && onNavigate(v.payload.route)} isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<QmsTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </DeferredChart>
  );
});

const RolePieChart = memo(function RolePieChart({ data, onNavigate }: { data: NamedValue[]; onNavigate: (route: string) => void }) {
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={85} onClick={(v: { payload?: NamedValue }) => v?.payload?.route && onNavigate(v.payload.route)} isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<QmsTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </DeferredChart>
  );
});

const TrendAreaChart = memo(function TrendAreaChart({ data, findingLabel, onNavigate }: { data: TrendPoint[]; findingLabel: string; onNavigate: (route: string) => void }) {
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} onClick={(state: { activePayload?: Array<{ payload?: TrendPoint }> }) => state?.activePayload?.[0]?.payload?.route && onNavigate(state.activePayload[0].payload.route)}>
          <defs>
            <linearGradient id="qmsFatalGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={ACCENT.rose} stopOpacity={0.35} />
              <stop offset="95%" stopColor={ACCENT.rose} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
          <XAxis dataKey="month" stroke="var(--qms-axis)" />
          <YAxis stroke="var(--qms-axis)" />
          <Tooltip content={<QmsTooltip />} />
          <Area type="monotone" dataKey="value" name={findingLabel} stroke={ACCENT.rose} fill="url(#qmsFatalGrad)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </DeferredChart>
  );
});

const EmployeeScatter = memo(function EmployeeScatter({ data, onNavigate }: { data: ScatterPoint[]; onNavigate: (route: string) => void }) {
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart>
          <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
          <XAxis type="number" dataKey="samples" name="Samples" stroke="var(--qms-axis)" />
          <YAxis type="number" dataKey="defects" name="Defects" stroke="var(--qms-axis)" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<QmsTooltip />} />
          <Scatter data={data} fill={ACCENT.amber} onClick={(value: ScatterPoint) => value?.route && onNavigate(value.route)} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </DeferredChart>
  );
});

const EmployeeBars = memo(function EmployeeBars({ data, onNavigate }: { data: NamedValue[]; onNavigate: (route: string) => void }) {
  return (
    <DeferredChart>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 24 }} onClick={(state: { activePayload?: Array<{ payload?: NamedValue }> }) => state?.activePayload?.[0]?.payload?.route && onNavigate(state.activePayload[0].payload.route)}>
          <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
          <XAxis type="number" stroke="var(--qms-axis)" />
          <YAxis type="category" dataKey="name" width={110} stroke="var(--qms-axis)" />
          <Tooltip content={<QmsTooltip />} />
          <Bar dataKey="value" fill={ACCENT.rose} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </DeferredChart>
  );
});

const QualityCockpitCharts: React.FC<{ data: QualityCockpitVisualData; onNavigate: (route: string) => void }> = ({ data, onNavigate }) => {
  return (
    <>
      <section className="qms-pro-grid qms-pro-grid--row2">
        <DashboardCard title="Quality Score"><div className="qms-chart-box"><QualityScoreGauge value={data.qualityScore} /></div></DashboardCard>
        <DashboardCard title="Manpower Allocation (2D)" isEmpty={!data.manpowerByRole.length} emptyMessage="No manpower data.">
          <div className="qms-chart-box">{data.manpowerByRole.length ? <RolePieChart data={data.manpowerByRole} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
        <DashboardCard title="Fatal Errors by Supervisor" isEmpty={!data.fatalErrorsBySupervisor.length} emptyMessage="No supervisor errors.">
          <div className="qms-chart-box">{data.fatalErrorsBySupervisor.length ? <DonutChartCard data={data.fatalErrorsBySupervisor} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
        <DashboardCard title="Fatal Errors by Location" isEmpty={!data.fatalErrorsByLocation.length} emptyMessage="No location errors.">
          <div className="qms-chart-box">{data.fatalErrorsByLocation.length ? <DonutChartCard data={data.fatalErrorsByLocation} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
      </section>

      <section className="qms-pro-grid qms-pro-grid--single">
        <DashboardCard title="Most Common Finding Trend (12M)" isEmpty={!data.mostCommonFindingTrend.length} emptyMessage="No trend data.">
          <div className="qms-chart-box">{data.mostCommonFindingTrend.length ? <TrendAreaChart data={data.mostCommonFindingTrend} findingLabel={data.mostCommonFindingTypeLabel ?? "Most common finding"} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
      </section>

      <section className="qms-pro-grid qms-pro-grid--row4">
        <DashboardCard title="Samples vs Defects by Employee" isEmpty={!data.samplesVsDefects.length} emptyMessage="No scatter data.">
          <div className="qms-chart-box">{data.samplesVsDefects.length ? <EmployeeScatter data={data.samplesVsDefects} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
        <DashboardCard title="Fatal Errors by EMP Name" isEmpty={!data.fatalErrorsByEmployee.length} emptyMessage="No employee error data.">
          <div className="qms-chart-box qms-chart-box--compact">{data.fatalErrorsByEmployee.length ? <EmployeeBars data={data.fatalErrorsByEmployee} onNavigate={onNavigate} /> : null}</div>
        </DashboardCard>
      </section>
    </>
  );
};

export default memo(QualityCockpitCharts);

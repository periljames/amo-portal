import React from "react";
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
import type { ActionItem, ActivityItem } from "./DashboardScaffold";

type KpiCard = {
  id: string;
  label: string;
  value: number;
  accent: "green" | "rose" | "amber" | "navy";
  onClick: () => void;
};

type NamedValue = { name: string; value: number; route: string };

type TrendPoint = { month: string; value: number; route: string };

type ScatterPoint = { name: string; samples: number; defects: number; route: string };

type Manpower = { on_duty_total: number; engineers: number; technicians: number; inspectors: number };

export type QualityCockpitVisualData = {
  kpis: KpiCard[];
  qualityScore: number;
  fatalErrorsBySupervisor: NamedValue[];
  fatalErrorsByLocation: NamedValue[];
  fatalErrorsByMonth: TrendPoint[];
  mostCommonFindingTrend: TrendPoint[];
  mostCommonFindingTypeLabel: string | null;
  samplesVsDefects: ScatterPoint[];
  fatalErrorsByEmployee: NamedValue[];
  manpowerByRole: NamedValue[];
  manpower: Manpower;
};

type Props = {
  data: QualityCockpitVisualData;
  actionItems: ActionItem[];
  activity: ActivityItem[];
  onOpenActionPanel: (actionId: string) => void;
};

const ACCENT = {
  navy: "var(--qms-accent-navy)",
  green: "var(--qms-accent-green)",
  rose: "var(--qms-accent-rose)",
  amber: "var(--qms-accent-amber)",
};

const PIE_COLORS = ["#F43F5E", "#10B981", "#F59E0B", "#3B82F6", "#8B5CF6"];

const Empty: React.FC<{ label: string }> = ({ label }) => (
  <div className="qms-empty-state">No data for selected auditor/date range ({label}).</div>
);

const QmsTooltip: React.FC<any> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="qms-chart-tooltip">
      <strong>{label ?? payload[0].name}</strong>
      {payload.map((item: any) => (
        <div key={item.dataKey}>{item.dataKey}: {item.value}</div>
      ))}
    </div>
  );
};

const QualityCockpitCanvas: React.FC<Props> = ({ data, actionItems, activity, onOpenActionPanel }) => {
  return (
    <div className="qms-pro-dashboard">
      <section className="qms-pro-kpis">
        {data.kpis.map((kpi) => (
          <button key={kpi.id} type="button" className="qms-pro-kpi" onClick={kpi.onClick}>
            <span className={`qms-pro-kpi__accent qms-pro-kpi__accent--${kpi.accent}`} />
            <div className="qms-pro-kpi__label">{kpi.label}</div>
            <div className="qms-pro-kpi__value">{kpi.value.toLocaleString()}</div>
          </button>
        ))}
      </section>

      <section className="qms-pro-grid qms-pro-grid--row2">
        <article className="qms-pro-card">
          <h3>Quality Score</h3>
          <div className="qms-chart-box">
            <ResponsiveContainer width="100%" height={220}>
              <RadialBarChart innerRadius="72%" outerRadius="100%" data={[{ name: "score", value: data.qualityScore }]} startAngle={180} endAngle={0}>
                <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                <RadialBar dataKey="value" cornerRadius={10} fill={ACCENT.green} background />
                <Tooltip content={<QmsTooltip />} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="qms-gauge-value">{data.qualityScore.toFixed(2)}%</div>
          </div>
        </article>

        <article className="qms-pro-card">
          <h3>Manpower Allocation (2D)</h3>
          <div className="qms-chart-box">
            {data.manpowerByRole.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={data.manpowerByRole} dataKey="value" nameKey="name" outerRadius={85} onClick={(v: any) => v?.payload?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: v.payload.route }))}>
                    {data.manpowerByRole.map((entry, index) => (
                      <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<QmsTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty label="manpower allocation" />}
          </div>
        </article>

        <article className="qms-pro-card">
          <h3>Fatal Errors by Supervisor</h3>
          <div className="qms-chart-box">
            {data.fatalErrorsBySupervisor.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={data.fatalErrorsBySupervisor} dataKey="value" nameKey="name" innerRadius={55} outerRadius={82} onClick={(v: any) => v?.payload?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: v.payload.route }))}>
                    {data.fatalErrorsBySupervisor.map((entry, index) => (
                      <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<QmsTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty label="supervisor donut" />}
          </div>
        </article>

        <article className="qms-pro-card">
          <h3>Fatal Errors by Location</h3>
          <div className="qms-chart-box">
            {data.fatalErrorsByLocation.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={data.fatalErrorsByLocation} dataKey="value" nameKey="name" innerRadius={55} outerRadius={82} onClick={(v: any) => v?.payload?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: v.payload.route }))}>
                    {data.fatalErrorsByLocation.map((entry, index) => (
                      <Cell key={entry.name} fill={PIE_COLORS[(index + 2) % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<QmsTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty label="location donut" />}
          </div>
        </article>
      </section>

      <section className="qms-pro-grid qms-pro-grid--single">
        <article className="qms-pro-card">
          <h3>Most Common Finding Trend (12M)</h3>
          <div className="qms-chart-box">
            {data.mostCommonFindingTrend.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={data.mostCommonFindingTrend} onClick={(state: any) => state?.activePayload?.[0]?.payload?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: state.activePayload[0].payload.route }))}>
                  <defs>
                    <linearGradient id="fatalGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={ACCENT.rose} stopOpacity={0.35} />
                      <stop offset="95%" stopColor={ACCENT.rose} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
                  <XAxis dataKey="month" stroke="var(--qms-axis)" />
                  <YAxis stroke="var(--qms-axis)" />
                  <Tooltip content={<QmsTooltip />} />
                  <Area type="monotone" dataKey="value" name={data.mostCommonFindingTypeLabel ?? "Most common finding"} stroke={ACCENT.rose} fill="url(#fatalGrad)" />
                </AreaChart>
              </ResponsiveContainer>
             ) : <Empty label="most common finding trend (12m)" />}
          </div>
        </article>
      </section>

      <section className="qms-pro-grid qms-pro-grid--row4">
        <article className="qms-pro-card">
          <h3>Samples vs Defects by Employee</h3>
          <div className="qms-chart-box">
            {data.samplesVsDefects.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <ScatterChart>
                  <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="samples" name="Samples" stroke="var(--qms-axis)" />
                  <YAxis type="number" dataKey="defects" name="Defects" stroke="var(--qms-axis)" />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<QmsTooltip />} />
                  <Scatter data={data.samplesVsDefects} fill={ACCENT.amber} onClick={(value: any) => value?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: value.route }))} />
                </ScatterChart>
              </ResponsiveContainer>
            ) : <Empty label="employee scatter" />}
          </div>
        </article>

        <article className="qms-pro-card">
          <h3>Fatal Errors by EMP Name</h3>
          <div className="qms-chart-box qms-chart-box--compact">
            {data.fatalErrorsByEmployee.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.fatalErrorsByEmployee} layout="vertical" margin={{ left: 24 }} onClick={(state: any) => state?.activePayload?.[0]?.payload?.route && window.dispatchEvent(new CustomEvent("qms-nav", { detail: state.activePayload[0].payload.route }))}>
                  <CartesianGrid stroke="var(--qms-grid)" strokeDasharray="3 3" />
                  <XAxis type="number" stroke="var(--qms-axis)" />
                  <YAxis type="category" dataKey="name" width={110} stroke="var(--qms-axis)" />
                  <Tooltip content={<QmsTooltip />} />
                  <Bar dataKey="value" fill={ACCENT.rose} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty label="employee bars" />}
          </div>
        </article>
      </section>

      <section className="qms-pro-grid qms-pro-grid--single">
        <article className="qms-pro-card">
          <h3>Action Queue</h3>
          <div className="qms-action-list">
            {actionItems.map((item) => (
              <div key={item.id} role="button" tabIndex={0} className="qms-action-list__row" onClick={item.onClick} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") item.onClick?.(); }}>
                <span>{item.title}</span>
                <span>{item.status}</span>
                <button type="button" className="secondary-chip-btn" onClick={(event) => { event.stopPropagation(); onOpenActionPanel(item.id); }}>
                  Act
                </button>
              </div>
            ))}
            {!actionItems.length && <Empty label="action queue" />}
          </div>
        </article>
      </section>

      <section className="qms-pro-grid qms-pro-grid--single">
        <article className="qms-pro-card">
          <h3>Activity Feed</h3>
          <div className="qms-activity-list">
            {activity.slice(0, 14).map((item) => (
              <button key={item.id} type="button" className="qms-activity-list__row" onClick={item.onClick}>
                <strong>{item.summary}</strong>
                <span>{item.timestamp}</span>
              </button>
            ))}
            {!activity.length && <Empty label="activity" />}
          </div>
        </article>
      </section>
    </div>
  );
};

export default QualityCockpitCanvas;

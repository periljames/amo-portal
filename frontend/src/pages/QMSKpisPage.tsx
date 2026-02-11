import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, FlaskConical, ShieldAlert } from "lucide-react";
import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { fetchCockpitData, type DashboardFilter } from "../services/qmsCockpit";

const DONUT_COLORS = ["#0ea5e9", "#6366f1", "#14b8a6", "#f97316", "#ef4444"];

const QMSKpisPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [filters, setFilters] = useState<DashboardFilter>({ auditor: "All", dateRange: "30d" });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["qms-cockpit", filters],
    queryFn: () => fetchCockpitData(filters),
  });

  const kpiIcons = useMemo(
    () => [ClipboardList, FlaskConical, AlertTriangle, ShieldAlert],
    []
  );

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Interactive Cockpit"
      subtitle="Live quality cockpit with responsive KPI, distribution, and trend analytics."
      actions={
        <div className="qms-cockpit-filters">
          <select value={filters.auditor} onChange={(e) => setFilters((p) => ({ ...p, auditor: e.target.value }))}>
            <option>All</option>
            <option>Auditor A</option>
            <option>Auditor B</option>
          </select>
          <select value={filters.dateRange} onChange={(e) => setFilters((p) => ({ ...p, dateRange: e.target.value }))}>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
          <button type="button" className="primary-chip-btn" onClick={() => refetch()}>
            Refresh
          </button>
        </div>
      }
    >
      {isLoading && <div className="qms-card">Loading cockpit metrics…</div>}
      {error && <div className="qms-card">Unable to load cockpit data.</div>}
      {data && (
        <section className="cockpit-grid">
          {data.kpis.map((kpi, index) => {
            const Icon = kpiIcons[index] ?? ClipboardList;
            return (
              <article key={kpi.label} className="cockpit-card">
                <div className="cockpit-kpi-top">
                  <span>{kpi.label}</span>
                  <Icon size={18} />
                </div>
                <p className="cockpit-kpi-value">{kpi.value}</p>
                <p className={kpi.changePct >= 0 ? "cockpit-change up" : "cockpit-change down"}>
                  {kpi.changePct >= 0 ? "+" : ""}
                  {kpi.changePct}% vs previous period
                </p>
              </article>
            );
          })}

          <article className="cockpit-card cockpit-card--gauge">
            <h3>Quality Score</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={[
                    { name: "Score", value: data.qualityScore },
                    { name: "Remaining", value: 100 - data.qualityScore },
                  ]}
                  startAngle={180}
                  endAngle={0}
                  cx="50%"
                  cy="100%"
                  innerRadius={70}
                  outerRadius={95}
                  dataKey="value"
                >
                  <Cell fill="#2563eb" />
                  <Cell fill="#e2e8f0" />
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <p className="cockpit-gauge-score">{data.qualityScore}%</p>
          </article>

          <article className="cockpit-card cockpit-card--distribution">
            <h3>Error Distribution</h3>
            <div className="cockpit-donuts">
              <div>
                <h4>Fatal by Supervisor</h4>
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={data.fatalBySupervisor} innerRadius={48} outerRadius={80} dataKey="value" nameKey="name">
                      {data.fatalBySupervisor.map((row, i) => (
                        <Cell key={row.name} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div>
                <h4>Fatal by Location</h4>
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={data.fatalByLocation} innerRadius={48} outerRadius={80} dataKey="value" nameKey="name">
                      {data.fatalByLocation.map((row, i) => (
                        <Cell key={row.name} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </article>

          <article className="cockpit-card cockpit-card--trend">
            <h3>Monthly Trend</h3>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={data.trends}>
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="tasks" stroke="#2563eb" fill="#bfdbfe" strokeWidth={2} />
                <Area type="monotone" dataKey="samples" stroke="#10b981" fill="#bbf7d0" strokeWidth={2} />
                <Area type="monotone" dataKey="defects" stroke="#f97316" fill="#fed7aa" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </article>
        </section>
      )}
    </QMSLayout>
  );
};

export default QMSKpisPage;

import React from "react";
import { Activity, Gauge, ShieldCheck, Wrench } from "lucide-react";
import DashboardCard from "./DashboardCard";

type Props = {
  departmentLabel: string;
};

const DepartmentLandingScaffold: React.FC<Props> = ({ departmentLabel }) => {
  return (
    <section className="department-landing" aria-label={`${departmentLabel} landing`}>
      <header className="department-landing__header">
        <div>
          <h1 className="department-landing__title">{departmentLabel} Dashboard</h1>
          <p className="department-landing__subtitle">Full-width operations overview with no glass overlays.</p>
        </div>
      </header>

      <div className="department-grid">
        <div className="department-grid__left">
          <DashboardCard title="Operations Pulse" subtitle="Live stack status">
            <div className="department-metric-list">
              <div><Activity size={14} /> Work queue nominal</div>
              <div><ShieldCheck size={14} /> Compliance checks green</div>
              <div><Wrench size={14} /> Tooling uptime 99.9%</div>
            </div>
          </DashboardCard>
        </div>

        <div className="department-grid__center">
          <DashboardCard title="Department KPI Cluster" subtitle="One-page no-scroll layout">
            <div className="department-kpi-row">
              <div className="department-kpi"><span>Open Tasks</span><strong>24</strong></div>
              <div className="department-kpi"><span>Due This Week</span><strong>11</strong></div>
              <div className="department-kpi"><span>Blocked</span><strong>2</strong></div>
              <div className="department-kpi"><span>Throughput</span><strong>92%</strong></div>
            </div>
          </DashboardCard>
        </div>

        <div className="department-grid__right">
          <DashboardCard title="Navigator" subtitle="Jump to active modules">
            <div className="department-metric-list">
              <button type="button" className="department-nav-btn"><Gauge size={14} /> Dashboard Home</button>
              <button type="button" className="department-nav-btn"><Activity size={14} /> Activity</button>
              <button type="button" className="department-nav-btn"><Wrench size={14} /> Work Orders</button>
            </div>
          </DashboardCard>
        </div>
      </div>
    </section>
  );
};

export default DepartmentLandingScaffold;

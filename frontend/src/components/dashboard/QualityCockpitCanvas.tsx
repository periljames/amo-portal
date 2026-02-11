import React, { Suspense, lazy, useCallback } from "react";
import type { ActionItem, ActivityItem } from "./DashboardScaffold";
import DashboardCard from "./DashboardCard";

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

const LazyQualityCharts = lazy(() => import("./charts/QualityCockpitCharts"));

const QualityCockpitCanvas: React.FC<Props> = ({ data, actionItems, activity, onOpenActionPanel }) => {
  const handleRouteNav = useCallback((route: string) => {
    window.dispatchEvent(new CustomEvent("qms-nav", { detail: route }));
  }, []);

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

      <Suspense fallback={<div className="qms-skeleton-block">Loading charts…</div>}>
        <LazyQualityCharts data={data} onNavigate={handleRouteNav} />
      </Suspense>

      <section className="qms-pro-grid qms-pro-grid--single">
        <DashboardCard title="Action Queue" bodyClassName="qms-action-list" isEmpty={!actionItems.length} emptyMessage="No queued actions.">
          {actionItems.map((item) => (
            <div key={item.id} role="button" tabIndex={0} className="qms-action-list__row" onClick={item.onClick} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") item.onClick?.(); }}>
              <span>{item.title}</span>
              <span>{item.status}</span>
              <button type="button" className="secondary-chip-btn" onClick={(event) => { event.stopPropagation(); onOpenActionPanel(item.id); }}>
                Act
              </button>
            </div>
          ))}
        </DashboardCard>
      </section>

      <section className="qms-pro-grid qms-pro-grid--single">
        <DashboardCard title="Activity Feed" bodyClassName="qms-activity-list" isEmpty={!activity.length} emptyMessage="No activity received yet.">
          {activity.slice(0, 14).map((item) => (
            <button key={item.id} type="button" className="qms-activity-list__row" onClick={item.onClick}>
              <strong>{item.summary}</strong>
              <span>{item.timestamp}</span>
            </button>
          ))}
        </DashboardCard>
      </section>
    </div>
  );
};

export default React.memo(QualityCockpitCanvas);

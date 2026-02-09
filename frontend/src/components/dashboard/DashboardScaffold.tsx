import React, { useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import { useVirtualizer } from "@tanstack/react-virtual";

export type KpiTile = {
  id: string;
  label: string;
  value: string | number;
  timeframe?: string;
  updatedAt?: string;
  onClick?: () => void;
};

export type DriverCard = {
  id: string;
  title: string;
  subtitle?: string;
  option: Record<string, unknown>;
  onClick?: () => void;
};

export type ActionItem = {
  id: string;
  type: string;
  title: string;
  owner?: string;
  ownerId?: string | null;
  onOwnerClick?: () => void;
  due?: string;
  status?: string;
  priority?: string;
  onClick?: () => void;
  action?: () => void;
};

export type ActivityItem = {
  id: string;
  summary: string;
  timestamp: string;
  onClick?: () => void;
};

type Props = {
  title: string;
  subtitle?: string;
  kpis: KpiTile[];
  drivers: DriverCard[];
  actionItems: ActionItem[];
  activity: ActivityItem[];
};

const DashboardScaffold: React.FC<Props> = ({
  title,
  subtitle,
  kpis,
  drivers,
  actionItems,
  activity,
}) => {
  const actionParentRef = useRef<HTMLDivElement | null>(null);
  const rowVirtualizer = useVirtualizer({
    count: actionItems.length,
    getScrollElement: () => actionParentRef.current,
    estimateSize: () => 48,
  });

  const driverCharts = useMemo(
    () =>
      drivers.map((driver) => (
        <div key={driver.id} className="dashboard-card" onClick={driver.onClick}>
          <div className="dashboard-card__header">
            <div>
              <h3 className="dashboard-card__title">{driver.title}</h3>
              {driver.subtitle && <div className="dashboard-card__meta">{driver.subtitle}</div>}
            </div>
          </div>
          <div className="dashboard-chart">
            <ReactECharts
              option={driver.option}
              style={{ height: "100%", width: "100%" }}
              opts={{ renderer: "canvas", devicePixelRatio: window.devicePixelRatio || 1 }}
            />
          </div>
        </div>
      )),
    [drivers]
  );

  return (
    <div className="dashboard-cockpit">
      <div className="dashboard-cockpit__header">
        <div>
          <h1 className="dashboard-cockpit__title">{title}</h1>
          {subtitle && <div className="dashboard-cockpit__subtitle">{subtitle}</div>}
        </div>
      </div>

      <section className="dashboard-kpis">
        {kpis.map((kpi) => (
          <button key={kpi.id} type="button" className="dashboard-kpi" onClick={kpi.onClick}>
            <div className="dashboard-kpi__value">{kpi.value}</div>
            <div className="dashboard-kpi__label">{kpi.label}</div>
            <div className="dashboard-kpi__meta">
              <span>{kpi.timeframe}</span>
              <span>{kpi.updatedAt ? `Updated ${kpi.updatedAt}` : ""}</span>
            </div>
          </button>
        ))}
      </section>

      <section className="dashboard-layer">
        <div className="dashboard-layer__main">
          <div className="dashboard-card">
            <div className="dashboard-card__header">
              <h3 className="dashboard-card__title">Action queue</h3>
              <span className="dashboard-card__meta">Next up</span>
            </div>
            <div
              ref={actionParentRef}
              style={{ height: 260, overflow: "auto" }}
              className="dashboard-action-queue"
            >
              {actionItems.length === 0 && (
                <div className="dashboard-action-queue__empty">All clear for now.</div>
              )}
              <div style={{ height: rowVirtualizer.getTotalSize(), position: "relative" }}>
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = actionItems[virtualRow.index];
                  return (
                    <div
                      key={item.id}
                      className="dashboard-action-queue__row"
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                      onClick={item.onClick}
                    >
                      <strong>{item.type}</strong>
                      <span>{item.title}</span>
                      {item.owner && item.onOwnerClick ? (
                        <button
                          type="button"
                          className="link-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            item.onOwnerClick?.();
                          }}
                        >
                          {item.owner}
                        </button>
                      ) : (
                        <span>{item.owner ?? "—"}</span>
                      )}
                      <span>{item.due ?? "—"}</span>
                      <span>{item.status ?? "—"}</span>
                      <button
                        type="button"
                        className="secondary-chip-btn"
                        onClick={(event) => {
                          event.stopPropagation();
                          item.action?.();
                        }}
                      >
                        Act
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          {driverCharts}
        </div>
        <aside className="dashboard-layer__rail">
          <div className="dashboard-card">
            <div className="dashboard-card__header">
              <h3 className="dashboard-card__title">Activity feed</h3>
              <span className="dashboard-card__meta">Live</span>
            </div>
            <div className="dashboard-activity">
              {activity.length === 0 && (
                <div className="dashboard-action-queue__empty">No recent activity.</div>
              )}
              {activity.map((item) => (
                <div
                  key={item.id}
                  className="dashboard-activity__item"
                  onClick={item.onClick}
                >
                  <strong>{item.summary}</strong>
                  <div>{item.timestamp}</div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
};

export default DashboardScaffold;

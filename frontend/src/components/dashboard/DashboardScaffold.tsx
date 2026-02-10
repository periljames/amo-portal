import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { isCursorLayerEnabled, isUiShellV2Enabled } from "../../utils/featureFlags";

const LazyEChart = lazy(() => import("echarts-for-react"));

export type KpiTile = {
  id: string;
  label: string;
  value: string | number;
  icon?: LucideIcon;
  status?: "overdue" | "due-today" | "due-week" | "noncompliance" | "awaiting-evidence" | "closed";
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
  occurredAt?: string;
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

type FeedRow =
  | { kind: "header"; id: string; label: string }
  | { kind: "item"; id: string; item: ActivityItem };

function getBucketLabel(date: Date): string {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startWeek = new Date(startToday);
  startWeek.setDate(startWeek.getDate() - 7);
  const startMonth = new Date(startToday);
  startMonth.setDate(startMonth.getDate() - 30);
  if (date >= startToday) return "Today";
  if (date >= startWeek) return "This Week";
  if (date >= startMonth) return "This Month";
  return "Older";
}

const DashboardScaffold: React.FC<Props> = ({ title, subtitle, kpis, drivers, actionItems, activity }) => {
  const actionParentRef = useRef<HTMLDivElement | null>(null);
  const activityParentRef = useRef<HTMLDivElement | null>(null);
  const cockpitRef = useRef<HTMLDivElement | null>(null);
  const prefersReduced = useReducedMotion();
  const [pointer, setPointer] = useState({ x: 0, y: 0, visible: false });

  const enableCursorLayer = useMemo(() => {
    if (!isUiShellV2Enabled()) return false;
    if (!isCursorLayerEnabled()) return false;
    if (typeof window === "undefined") return false;
    const touch = window.matchMedia("(hover: none), (pointer: coarse)").matches;
    return !touch && !prefersReduced;
  }, [prefersReduced]);

  useEffect(() => {
    if (!enableCursorLayer || !cockpitRef.current) return;
    let raf = 0;
    const target = cockpitRef.current;
    const onMove = (event: PointerEvent) => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        const bounds = target.getBoundingClientRect();
        setPointer({ x: event.clientX - bounds.left, y: event.clientY - bounds.top, visible: true });
        raf = 0;
      });
    };
    const onLeave = () => setPointer((prev) => ({ ...prev, visible: false }));
    target.addEventListener("pointermove", onMove, { passive: true });
    target.addEventListener("pointerleave", onLeave, { passive: true });
    return () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerleave", onLeave);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, [enableCursorLayer]);

  useEffect(() => {
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
    if (idle) {
      const id = idle(() => void import("echarts-for-react"));
      return () => {
        if ((window as Window & { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback) {
          (window as Window & { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback?.(id);
        }
      };
    }
    const timer = window.setTimeout(() => void import("echarts-for-react"), 900);
    return () => window.clearTimeout(timer);
  }, []);

  const actionVirtualizer = useVirtualizer({
    count: actionItems.length,
    getScrollElement: () => actionParentRef.current,
    estimateSize: () => 56,
  });

  const feedRows = useMemo<FeedRow[]>(() => {
    const rows: FeedRow[] = [];
    let currentBucket = "";
    for (const item of activity) {
      const source = item.occurredAt ?? item.timestamp;
      const date = new Date(source);
      const bucket = Number.isNaN(date.getTime()) ? "Older" : getBucketLabel(date);
      if (bucket !== currentBucket) {
        rows.push({ kind: "header", id: `h-${bucket}-${item.id}`, label: bucket });
        currentBucket = bucket;
      }
      rows.push({ kind: "item", id: item.id, item });
    }
    return rows;
  }, [activity]);

  const activityVirtualizer = useVirtualizer({
    count: feedRows.length,
    getScrollElement: () => activityParentRef.current,
    estimateSize: (index) => (feedRows[index]?.kind === "header" ? 32 : 58),
    overscan: 10,
  });

  return (
    <div className="dashboard-cockpit" ref={cockpitRef}>
      {enableCursorLayer && (
        <div
          className={`dashboard-cursor-halo${pointer.visible ? " is-visible" : ""}`}
          style={{ transform: `translate3d(${pointer.x}px, ${pointer.y}px, 0)` }}
          aria-hidden
        />
      )}
      <div className="dashboard-cockpit__header">
        <div>
          <h1 className="dashboard-cockpit__title">{title}</h1>
          {subtitle && <div className="dashboard-cockpit__subtitle">{subtitle}</div>}
        </div>
      </div>

      <section className="dashboard-kpis">
        {kpis.map((kpi, idx) => {
          const Icon = kpi.icon;
          return (
            <motion.button
              key={kpi.id}
              type="button"
              className="dashboard-kpi dashboard-interactive"
              data-status={kpi.status}
              onClick={kpi.onClick}
              initial={prefersReduced ? false : { opacity: 0, y: 8 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 26, delay: idx * 0.03 }}
              whileHover={prefersReduced ? undefined : { scale: 1.01, y: -2 }}
              whileTap={prefersReduced ? undefined : { scale: 0.99 }}
            >
              <div className="dashboard-kpi__top">
                {Icon ? <Icon size={16} aria-hidden /> : null}
                {kpi.status ? <span className={`status-pill status-pill--${kpi.status}`}>{kpi.status.replace("-", " ")}</span> : null}
              </div>
              <div className="dashboard-kpi__value">{kpi.value}</div>
              <div className="dashboard-kpi__label">{kpi.label}</div>
              <div className="dashboard-kpi__meta">
                <span>{kpi.timeframe}</span>
                <span>{kpi.updatedAt ? `Updated ${kpi.updatedAt}` : ""}</span>
              </div>
            </motion.button>
          );
        })}
      </section>

      <section className="dashboard-layer">
        <div className="dashboard-layer__main">
          <div className="dashboard-card">
            <div className="dashboard-card__header">
              <h3 className="dashboard-card__title">Action queue</h3>
              <span className="dashboard-card__meta">Next up</span>
            </div>
            <div ref={actionParentRef} style={{ height: 280, overflow: "auto" }} className="dashboard-action-queue">
              {actionItems.length === 0 && <div className="dashboard-action-queue__empty">All clear for now.</div>}
              <div style={{ height: actionVirtualizer.getTotalSize(), position: "relative" }}>
                {actionVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = actionItems[virtualRow.index];
                  return (
                    <div
                      key={item.id}
                      className="dashboard-action-queue__row dashboard-interactive"
                      style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                      onClick={item.onClick}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") item.onClick?.();
                      }}
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

          {drivers.map((driver, index) => (
            <motion.div
              key={driver.id}
              className="dashboard-card dashboard-interactive"
              onClick={driver.onClick}
              initial={prefersReduced ? false : { opacity: 0, y: 8 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.22, delay: index * 0.05 }}
            >
              <div className="dashboard-card__header">
                <div>
                  <h3 className="dashboard-card__title">{driver.title}</h3>
                  {driver.subtitle && <div className="dashboard-card__meta">{driver.subtitle}</div>}
                </div>
              </div>
              <div className="dashboard-chart">
                <Suspense fallback={<div className="dashboard-chart__skeleton" /> }>
                  <LazyEChart
                    option={driver.option}
                    style={{ height: "100%", width: "100%" }}
                    opts={{ renderer: "canvas", devicePixelRatio: window.devicePixelRatio || 1 }}
                  />
                </Suspense>
              </div>
            </motion.div>
          ))}
        </div>
        <aside className="dashboard-layer__rail">
          <div className="dashboard-card">
            <div className="dashboard-card__header">
              <h3 className="dashboard-card__title">Activity feed</h3>
              <span className="dashboard-card__meta">Live</span>
            </div>
            <div ref={activityParentRef} className="dashboard-activity dashboard-activity--virtual" style={{ height: 420, overflow: "auto" }}>
              {feedRows.length === 0 && <div className="dashboard-action-queue__empty">No recent activity.</div>}
              <div style={{ height: activityVirtualizer.getTotalSize(), position: "relative" }}>
                {activityVirtualizer.getVirtualItems().map((virtualRow) => {
                  const row = feedRows[virtualRow.index];
                  if (!row) return null;
                  if (row.kind === "header") {
                    return (
                      <div
                        key={row.id}
                        className="dashboard-activity__header"
                        style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                      >
                        {row.label}
                      </div>
                    );
                  }
                  return (
                    <button
                      key={row.id}
                      type="button"
                      className="dashboard-activity__item dashboard-interactive"
                      style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                      onClick={row.item.onClick}
                    >
                      <strong>{row.item.summary}</strong>
                      <div>{row.item.timestamp}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
};

export default DashboardScaffold;

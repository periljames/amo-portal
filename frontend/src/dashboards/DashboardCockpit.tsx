import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ClipboardList,
  FileSearch,
  GraduationCap,
  ListChecks,
  NotebookTabs,
  RefreshCcw,
  ShieldAlert,
  Siren,
} from "lucide-react";
import { Pie, PieChart, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { useNavigate, useParams } from "react-router-dom";

import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getContext } from "../services/auth";
import { listEventHistory } from "../services/events";
import { useRealtime } from "../components/realtime/realtimeContext";
import { qmsGetCockpitSnapshot, type CARStatus, type QMSCockpitSnapshotOut } from "../services/qms";
import type { ActionItem, ActivityItem } from "../components/dashboard/DashboardScaffold";
import type { QualityCockpitVisualData } from "../components/dashboard/QualityCockpitCanvas";
import { deepEqual } from "../utils/deepEqual";
import { isPortalGoLive } from "../services/runtimeMode";

const LazyQualityCockpitCanvas = lazy(() => import("../components/dashboard/QualityCockpitCanvas"));
const ENV_FORCE_MOCK_COCKPIT = import.meta.env.VITE_QMS_MOCK_COCKPIT === "true";

const PIE_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6"];

type TileDef = {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  route: string;
  value: number | null;
  lines: string[];
};

type PriorityState = "normal" | "due-soon" | "overdue";

const numberOrDash = (n: number | null | undefined) => (typeof n === "number" ? String(n) : "—");

const DashboardCockpit: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const qmsEnabled = department === "quality";
  const queryClient = useQueryClient();
  useRealtime();
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);
  const [manpowerSlide, setManpowerSlide] = useState(0);

  const useMockCockpit = ENV_FORCE_MOCK_COCKPIT && !isPortalGoLive();

  const { data: activityHistory } = useInfiniteQuery({
    queryKey: ["activity-history", amoCode, department],
    queryFn: ({ pageParam }) => listEventHistory({ cursor: pageParam as string | undefined, limit: 50 }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const snapshotQuery = useQuery({
    queryKey: ["qms-dashboard", amoCode, department],
    queryFn: async () => {
      const next = await qmsGetCockpitSnapshot();
      const cached = queryClient.getQueryData<QMSCockpitSnapshotOut>(["qms-dashboard", amoCode, department]);
      if (cached && deepEqual(cached, next)) return cached;
      return next;
    },
    enabled: qmsEnabled && !useMockCockpit,
    staleTime: 60_000,
    gcTime: 15 * 60_000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    retry: 1,
  });

  const snapshot = snapshotQuery.data;

  useEffect(() => {
    if (!qmsEnabled) {
      navigate(`/maintenance/${amoCode}/${department}`, { replace: true });
    }
  }, [amoCode, department, navigate, qmsEnabled]);

  const nav = (route: string) => navigate(route);

  const navigatorTiles = useMemo<TileDef[]>(() => {
    if (!snapshot) return [];
    const refresh = snapshot.generated_at ? new Date(snapshot.generated_at).toLocaleTimeString() : "—";
    return [
      {
        id: "documents",
        label: "Documents",
        icon: FileSearch,
        route: `/maintenance/${amoCode}/${department}/qms/documents`,
        value: snapshot.documents_active,
        lines: [
          `Drafts: ${numberOrDash(snapshot.documents_draft)}`,
          `Pending ack: ${numberOrDash(snapshot.pending_acknowledgements)}`,
        ],
      },
      {
        id: "audits",
        label: "Audits",
        icon: NotebookTabs,
        route: `/maintenance/${amoCode}/${department}/qms/audits`,
        value: snapshot.audits_open,
        lines: [
          `In progress/open: ${numberOrDash(snapshot.audits_open)}`,
          `Overdue findings: ${numberOrDash(snapshot.findings_overdue)}`,
        ],
      },
      {
        id: "cars",
        label: "CARs / CAPA",
        icon: ShieldAlert,
        route: `/maintenance/${amoCode}/${department}/qms/cars`,
        value: snapshot.cars_open_total,
        lines: [
          `Overdue: ${numberOrDash(snapshot.cars_overdue)}`,
          `Open total: ${numberOrDash(snapshot.cars_open_total)}`,
        ],
      },
      {
        id: "training",
        label: "Training",
        icon: GraduationCap,
        route: `/maintenance/${amoCode}/${department}/qms/training`,
        value: snapshot.training_records_expired,
        lines: [
          `Expired: ${numberOrDash(snapshot.training_records_expired)}`,
          `Expiring 30d: ${numberOrDash(snapshot.training_records_expiring_30d)}`,
        ],
      },
      {
        id: "change",
        label: "Change control",
        icon: ClipboardList,
        route: `/maintenance/${amoCode}/${department}/qms/change-requests`,
        value: snapshot.change_requests_open,
        lines: [
          `Pending approvals: ${numberOrDash(snapshot.change_control_pending_approvals ?? snapshot.change_requests_open)}`,
          `Open requests: ${numberOrDash(snapshot.change_requests_open)}`,
        ],
      },
      {
        id: "tasks",
        label: "Tasks",
        icon: ListChecks,
        route: `/maintenance/${amoCode}/${department}/tasks`,
        value: snapshot.tasks_overdue ?? null,
        lines: [
          `Due today: ${numberOrDash(snapshot.tasks_due_today)}`,
          `Overdue: ${numberOrDash(snapshot.tasks_overdue)}`,
        ],
      },
      {
        id: "events",
        label: "Events",
        icon: Siren,
        route: `/maintenance/${amoCode}/${department}/qms/events`,
        value: snapshot.events_hold_count ?? null,
        lines: [
          `Holds: ${numberOrDash(snapshot.events_hold_count)}`,
          `New: ${numberOrDash(snapshot.events_new_count)}`,
        ],
      },
      {
        id: "kpis",
        label: "KPIs",
        icon: AlertTriangle,
        route: `/maintenance/${amoCode}/${department}/qms/kpis`,
        value: snapshot.findings_overdue,
        lines: [
          `Overdue findings: ${numberOrDash(snapshot.findings_overdue)}`,
          `Last refresh: ${refresh}`,
        ],
      },
    ];
  }, [amoCode, department, snapshot]);

  const priority = useMemo(() => {
    if (!snapshot) return null;
    if (snapshot.cars_overdue > 0) {
      return { label: "CAR overdue", route: `/maintenance/${amoCode}/${department}/qms/cars?status=overdue`, count: snapshot.cars_overdue, state: "overdue" as PriorityState };
    }
    if (snapshot.findings_overdue > 0) {
      return { label: "Findings overdue", route: `/maintenance/${amoCode}/${department}/qms/audits?finding=overdue`, count: snapshot.findings_overdue, state: "overdue" as PriorityState };
    }
    if ((snapshot.training_records_expiring_30d ?? 0) > 0) {
      return { label: "Training due soon", route: `/maintenance/${amoCode}/${department}/qms/training?window=30d`, count: snapshot.training_records_expiring_30d, state: "due-soon" as PriorityState };
    }
    return { label: "System stable", route: `/maintenance/${amoCode}/${department}/qms/kpis`, count: 0, state: "normal" as PriorityState };
  }, [amoCode, department, snapshot]);

  const visualData: QualityCockpitVisualData = useMemo(() => {
    if (!snapshot) {
      return {
        kpis: [], qualityScore: 0, fatalErrorsBySupervisor: [], fatalErrorsByLocation: [], fatalErrorsByMonth: [],
        mostCommonFindingTrend: [], mostCommonFindingTypeLabel: null, samplesVsDefects: [], fatalErrorsByEmployee: [], manpowerByRole: [],
        manpower: { on_duty_total: 0, engineers: 0, technicians: 0, inspectors: 0 },
      };
    }
    return {
      kpis: [
        { id: "pending_ack", label: "Pending acknowledgements", value: snapshot.pending_acknowledgements, accent: "amber", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`) },
        { id: "cars_overdue", label: "CAR overdue", value: snapshot.cars_overdue, accent: "rose", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue`) },
        { id: "findings", label: "Open findings", value: snapshot.findings_open_total, accent: "navy", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits`) },
      ],
      qualityScore: Math.max(0, 100 - snapshot.findings_overdue * 2 - snapshot.cars_overdue * 3),
      fatalErrorsBySupervisor: [],
      fatalErrorsByLocation: [],
      fatalErrorsByMonth: [],
      mostCommonFindingTrend: snapshot.most_common_finding_trend_12m?.map((row) => ({
        month: new Date(row.period_start).toLocaleDateString(undefined, { month: "short", year: "2-digit" }),
        value: row.count,
        route: `/maintenance/${amoCode}/${department}/qms/audits?finding_type=${encodeURIComponent(row.finding_type)}`,
      })) ?? [],
      mostCommonFindingTypeLabel: snapshot.most_common_finding_trend_12m?.[0]?.finding_type?.replaceAll("_", " ") ?? null,
      samplesVsDefects: [],
      fatalErrorsByEmployee: [],
      manpowerByRole: Object.entries(snapshot.manpower?.by_role || {}).map(([name, value]) => ({ name, value, route: `/maintenance/${amoCode}/${department}/qms/training` })),
      manpower: {
        on_duty_total: snapshot.manpower?.availability?.on_duty ?? 0,
        engineers: snapshot.manpower?.by_role?.ENGINEER ?? 0,
        technicians: snapshot.manpower?.by_role?.TECHNICIAN ?? 0,
        inspectors: snapshot.manpower?.by_role?.QUALITY_INSPECTOR ?? 0,
      },
    };
  }, [amoCode, department, snapshot]);

  const actionItems = useMemo<ActionItem[]>(() => (snapshot?.action_queue || []).map((item) => ({
    id: item.id,
    type: item.kind,
    title: item.title,
    status: item.status,
    ownerId: item.assignee_user_id || undefined,
    onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/cars?carId=${item.id}`),
  })), [amoCode, department, snapshot]);

  const historyRows = activityHistory?.pages.flatMap((p) => p.items || []) || [];
  const activityItems = useMemo<ActivityItem[]>(() => {
    const mapped = historyRows.slice(0, 24).map((row) => ({
      id: `${row.id}`,
      summary: row.action || row.entityType || "Activity",
      timestamp: row.timestamp || "",
      occurredAt: row.timestamp || undefined,
      onClick: () => {},
    }));
    return mapped;
  }, [historyRows]);


  const manpower = snapshot?.manpower;
  const roleSlices = useMemo(() => Object.entries(manpower?.by_role || {}).map(([name, value]) => ({ name, value })), [manpower?.by_role]);
  const availability = manpower?.availability;
  const deptDistribution = manpower?.by_department || [];

  const slides = [
    {
      key: "on-duty",
      title: "On duty",
      body: <>
        <div className="qms-manpower-module__stat">{numberOrDash(availability?.on_duty)}</div>
        <div className="qms-manpower-module__sub">Total currently on duty</div>
        <div className="qms-manpower-module__chart">{roleSlices.length ? (
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={roleSlices} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} isAnimationActive={false}>
                {roleSlices.map((entry, index) => <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        ) : <span className="qms-na">Not available</span>}</div>
      </>,
    },
    { key: "away", title: "Away", body: <><div className="qms-manpower-module__stat">{numberOrDash(availability?.away)}</div><div className="qms-manpower-module__sub">Users currently away</div></> },
    { key: "leave", title: "On leave", body: <><div className="qms-manpower-module__stat">{numberOrDash(availability?.on_leave)}</div><div className="qms-manpower-module__sub">Users currently on leave</div></> },
    { key: "dept", title: "Department distribution", body: <div className="qms-manpower-module__dept-list">{deptDistribution.length ? deptDistribution.map((row) => <div key={row.department} className="qms-manpower-module__dept-row"><span>{row.department}</span><strong>{row.count}</strong></div>) : <span className="qms-na">Not available</span>}</div> },
  ];

  return (
    <div className="qms-cockpit-shell qms-cockpit-shell--onepage">
      <div className={`qms-priority-pill qms-priority-pill--${priority?.state || "normal"}`} role="button" tabIndex={0} onClick={() => priority && nav(priority.route)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && priority && nav(priority.route)}>
        <span>{priority?.label || "System stable"}</span>
        <strong>{priority?.count ?? 0}</strong>
      </div>

      <section className="quality-navigator quality-navigator--operational" aria-label="Quality Navigator">
        <div className="quality-navigator__grid quality-navigator__grid--dense">
          {navigatorTiles.map((tile) => {
            const Icon = tile.icon;
            return (
              <button key={tile.id} type="button" className="quality-op-tile" onClick={() => nav(tile.route)}>
                <div className="quality-op-tile__header"><Icon size={15} /><span>{tile.label}</span></div>
                <div className="quality-op-tile__value">{numberOrDash(tile.value)}</div>
                {tile.lines.map((line) => <div className="quality-op-tile__line" key={line}>{line}</div>)}
              </button>
            );
          })}
        </div>
      </section>

      <section className="qms-manpower-module" aria-label="Manpower module">
        <div className="qms-manpower-module__head">
          <div>
            <h3>Manpower</h3>
            <p>{manpower?.scope === "tenant" ? "Tenant scope" : "Department scope"}</p>
          </div>
          <div className="qms-manpower-module__controls">
            <button type="button" onClick={() => setManpowerSlide((s) => (s - 1 + slides.length) % slides.length)} aria-label="Previous manpower slide">‹</button>
            <button type="button" onClick={() => setManpowerSlide((s) => (s + 1) % slides.length)} aria-label="Next manpower slide">›</button>
          </div>
        </div>
        <div className="qms-manpower-module__viewport">
          <div className="qms-manpower-module__track" style={{ transform: `translateX(-${manpowerSlide * 100}%)` }}>
            {slides.map((slide) => <article key={slide.key} className="qms-manpower-module__slide"><h4>{slide.title}</h4>{slide.body}</article>)}
          </div>
        </div>
        <div className="qms-manpower-module__dots">{slides.map((slide, idx) => <button key={slide.key} type="button" className={idx === manpowerSlide ? "is-active" : ""} onClick={() => setManpowerSlide(idx)} aria-label={`Show ${slide.title} slide`} />)}</div>
      </section>

      <div className="qms-cockpit-main-grid">
        <Suspense fallback={<div className="qms-skeleton-block">Loading charts…</div>}>
          <LazyQualityCockpitCanvas
            data={visualData}
            actionItems={actionItems}
            activity={activityItems}
            onOpenActionPanel={(id) => {
              const item = actionItems.find((row) => row.id === id);
              if (!item) return;
              setPanelContext({ type: "car", id, title: item.title, status: (item.status || "OPEN") as CARStatus, ownerId: item.ownerId || undefined });
            }}
          />
        </Suspense>
      </div>

      <div className="qms-cockpit-refresh">
        <button type="button" className="secondary-chip-btn" onClick={() => void snapshotQuery.refetch()} disabled={snapshotQuery.isFetching}>
          <RefreshCcw size={14} /> Refresh
        </button>
      </div>

      <ActionPanel isOpen={!!panelContext} context={panelContext} onClose={() => setPanelContext(null)} />
    </div>
  );
};

export default DashboardCockpit;

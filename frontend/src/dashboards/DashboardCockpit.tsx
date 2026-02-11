import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  ClipboardList,
  FileSearch,
  GraduationCap,
  Home,
  ListChecks,
  NotebookTabs,
  Wrench,
} from "lucide-react";

import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getContext } from "../services/auth";
import { qmsGetCockpitSnapshot, type CARStatus, type QMSCockpitSnapshotOut } from "../services/qms";
import { useRealtime } from "../components/realtime/RealtimeProvider";
import { listEventHistory } from "../services/events";
import type { ActionItem, ActivityItem } from "../components/dashboard/DashboardScaffold";
import type { QualityCockpitVisualData } from "../components/dashboard/QualityCockpitCanvas";

const LazyQualityCockpitCanvas = lazy(() => import("../components/dashboard/QualityCockpitCanvas"));

const MOCK_COCKPIT_RESPONSE: QMSCockpitSnapshotOut & {
  manpower_on_duty_total: number;
  manpower_engineers_on_duty: number;
  manpower_technicians_on_duty: number;
  manpower_inspectors_on_duty: number;
} = {
  generated_at: new Date().toISOString(),
  pending_acknowledgements: 8,
  audits_open: 6,
  audits_total: 22,
  findings_overdue: 4,
  findings_open_total: 13,
  documents_active: 48,
  documents_draft: 7,
  documents_obsolete: 3,
  change_requests_open: 5,
  cars_open_total: 11,
  cars_overdue: 3,
  training_records_expiring_30d: 9,
  training_records_expired: 2,
  training_records_unverified: 6,
  training_deferrals_pending: 2,
  suppliers_active: 16,
  suppliers_inactive: 2,
  manpower_on_duty_total: 18,
  manpower_engineers_on_duty: 6,
  manpower_technicians_on_duty: 9,
  manpower_inspectors_on_duty: 3,
  audit_closure_trend: [
    { period_start: "2026-01-01", period_end: "2026-01-07", closed_count: 2, audit_ids: ["A-11", "A-12"] },
    { period_start: "2026-01-08", period_end: "2026-01-14", closed_count: 1, audit_ids: ["A-13"] },
    { period_start: "2026-01-15", period_end: "2026-01-21", closed_count: 2, audit_ids: ["A-14", "A-15"] },
    { period_start: "2026-01-22", period_end: "2026-01-28", closed_count: 4, audit_ids: ["A-16", "A-17", "A-18", "A-19"] },
  ],
  action_queue: [
    { id: "1", kind: "CAR", title: "Q-2026-0011 · Missing cert linkage", status: "OPEN", priority: "HIGH", due_date: "2026-02-15", assignee_user_id: "eva" },
    { id: "2", kind: "CAR", title: "Q-2026-0012 · Training evidence gap", status: "IN_PROGRESS", priority: "MEDIUM", due_date: "2026-02-22", assignee_user_id: "mike" },
  ],
};

type NavigatorTile = {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  to: string;
  badge?: number;
};

type PriorityItem = {
  id: string;
  title: string;
  description: string;
  count: number;
  route: string;
};

type AuditTrendPoint = {
  period_start: string;
  period_end: string;
  closed_count: number;
  audit_ids: string[];
};

type NavigatorTile = {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  to: string;
  badge?: number;
};

type PriorityItem = {
  id: string;
  title: string;
  description: string;
  count: number;
  route: string;
};

const DashboardCockpit: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const { activity } = useRealtime();
  const [selectedAuditor, setSelectedAuditor] = useState<"Eva" | "Mike" | "Smith">("Eva");
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);

  const qmsEnabled = department === "quality";
  const isDev = (import.meta as any).env?.DEV;

  const { data: activityHistory } = useInfiniteQuery({
    queryKey: ["activity-history", amoCode, department],
    queryFn: ({ pageParam }) =>
      listEventHistory({ cursor: pageParam as string | undefined, limit: 50 }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
  });

  const snapshotQuery = useQuery({
    queryKey: ["qms-cockpit-snapshot", amoCode],
    queryFn: () => qmsGetCockpitSnapshot(),
    enabled: qmsEnabled,
    staleTime: 15_000,
    retry: 1,
  });

  const usingMockData = !snapshotQuery.data && snapshotQuery.isError;
  const snapshot = (snapshotQuery.data ?? MOCK_COCKPIT_RESPONSE) as QMSCockpitSnapshotOut & Partial<typeof MOCK_COCKPIT_RESPONSE>;

  const nav = (to: string) => navigate(to);

  useEffect(() => {
    const onNav = (event: Event) => {
      const route = (event as CustomEvent<string>).detail;
      if (route) navigate(route);
    };
    window.addEventListener("qms-nav", onNav as EventListener);
    return () => window.removeEventListener("qms-nav", onNav as EventListener);
  }, [navigate]);

  const navigatorTiles = useMemo<NavigatorTile[]>(() => {
    const base = `/maintenance/${amoCode}/${department}/qms`;
    return [
      { id: "qms-home", label: "QMS Home", icon: Home, to: base },
      { id: "qms-tasks", label: "My Tasks", icon: ListChecks, to: `${base}/tasks`, badge: snapshot.action_queue.length },
      { id: "qms-documents", label: "Documents", icon: NotebookTabs, to: `${base}/documents`, badge: snapshot.pending_acknowledgements },
      { id: "qms-audits", label: "Audits", icon: FileSearch, to: `${base}/audits`, badge: snapshot.findings_overdue },
      { id: "qms-change", label: "Change Control", icon: ClipboardList, to: `${base}/change-control`, badge: snapshot.change_requests_open },
      { id: "qms-cars", label: "CAR Register", icon: Wrench, to: `${base}/cars`, badge: snapshot.cars_overdue },
      { id: "qms-training", label: "Training", icon: GraduationCap, to: `${base}/training`, badge: snapshot.training_records_expired },
      { id: "qms-events", label: "Quality Events", icon: AlertTriangle, to: `${base}/events`, badge: snapshot.suppliers_inactive },
      { id: "qms-kpis", label: "KPIs & Review", icon: BarChart3, to: `${base}/kpis`, badge: snapshot.findings_open_total },
    ];
  }, [amoCode, department, snapshot]);

  const topPriority = useMemo<PriorityItem | null>(() => {
    if (snapshot.findings_overdue > 0) return { id: "a", title: "Overdue findings", description: `${snapshot.findings_overdue} overdue findings require immediate closure.`, count: snapshot.findings_overdue, route: `/maintenance/${amoCode}/${department}/qms/audits?status=in_progress&finding=overdue` };
    if (snapshot.cars_overdue > 0) return { id: "b", title: "Overdue CARs", description: `${snapshot.cars_overdue} corrective actions are overdue.`, count: snapshot.cars_overdue, route: `/maintenance/${amoCode}/${department}/qms/cars?status=overdue` };
    if (snapshot.training_records_expired > 0) return { id: "c1", title: "Expired training", description: `${snapshot.training_records_expired} training records have expired.`, count: snapshot.training_records_expired, route: `/maintenance/${amoCode}/${department}/qms/training?currency=expired` };
    if (snapshot.training_records_expiring_30d > 0) return { id: "c2", title: "Training expiring soon", description: `${snapshot.training_records_expiring_30d} records expire in 30 days.`, count: snapshot.training_records_expiring_30d, route: `/maintenance/${amoCode}/${department}/qms/training?currency=expiring_30d` };
    if (snapshot.documents_draft > 0) return { id: "d", title: "Pending document approvals", description: `${snapshot.documents_draft} documents are awaiting approval.`, count: snapshot.documents_draft, route: `/maintenance/${amoCode}/${department}/qms/documents?status_=DRAFT` };
    if (snapshot.pending_acknowledgements > 0) return { id: "e", title: "Pending acknowledgements", description: `${snapshot.pending_acknowledgements} acknowledgements are pending.`, count: snapshot.pending_acknowledgements, route: `/maintenance/${amoCode}/${department}/qms/documents?ack=pending` };
    if (snapshot.suppliers_inactive > 0) return { id: "f", title: "Supplier hold indicators", description: `${snapshot.suppliers_inactive} suppliers are currently hold-tracked.`, count: snapshot.suppliers_inactive, route: `/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold` };
    if (snapshot.findings_open_total > 0) return { id: "g", title: "Open findings", description: `${snapshot.findings_open_total} findings remain open.`, count: snapshot.findings_open_total, route: `/maintenance/${amoCode}/${department}/qms/audits?status=cap_open` };
    return null;
  }, [snapshot, amoCode, department]);

  const actionItems = useMemo<ActionItem[]>(() => (snapshot.action_queue ?? []).map((item) => ({
    id: item.id,
    type: item.kind,
    title: item.title,
    owner: item.assignee_user_id ?? "Unassigned",
    ownerId: item.assignee_user_id,
    onOwnerClick: item.assignee_user_id ? () => navigate(`/maintenance/${amoCode}/admin/users/${item.assignee_user_id}`) : undefined,
    due: item.due_date ?? "—",
    status: item.status as CARStatus,
    priority: item.priority,
    onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${item.id}`),
    action: () => setPanelContext({ type: "car", id: item.id, title: item.title, status: item.status as CARStatus, ownerId: item.assignee_user_id }),
  })), [snapshot.action_queue, navigate, amoCode, department]);

  const activityItems = useMemo<ActivityItem[]>(() => {
    const fromHistory = (activityHistory?.pages ?? []).flatMap((page) => page.items ?? []);
    return [...activity, ...fromHistory].slice(0, 40).map((item) => ({
      id: item.id,
      summary: `${item.type} ${item.action}`,
      timestamp: new Date(item.timestamp).toLocaleString(),
      onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/events?entity=${item.entityType}&id=${item.entityId}`),
    }));
  }, [activityHistory?.pages, activity, navigate, amoCode, department]);

  const visualData = useMemo<QualityCockpitVisualData>(() => {
    const totalTasks = snapshot.action_queue.length + snapshot.findings_open_total + snapshot.pending_acknowledgements;
    const samples = snapshot.documents_active + snapshot.audits_total;
    const defects = snapshot.findings_open_total;
    const fatalErrors = snapshot.findings_overdue + snapshot.cars_overdue;
    const qualityScore = Math.max(40, Math.min(99.9, 100 - (fatalErrors * 2 + defects * 0.6)));

    const supervisorMap = new Map<string, number>();
    snapshot.action_queue.forEach((row) => {
      const k = row.assignee_user_id || "Unassigned";
      supervisorMap.set(k, (supervisorMap.get(k) ?? 0) + 1);
    });

    const fatalErrorsBySupervisor = Array.from(supervisorMap.entries()).map(([name, value]) => ({ name, value, route: `/maintenance/${amoCode}/${department}/qms/cars?assignee=${encodeURIComponent(name)}` }));
    const fatalErrorsByLocation = [
      { name: "Hangar", value: Math.max(0, snapshot.cars_overdue), route: `/maintenance/${amoCode}/${department}/qms/cars?status=overdue` },
      { name: "Line", value: Math.max(0, snapshot.findings_overdue), route: `/maintenance/${amoCode}/${department}/qms/audits?finding=overdue` },
      { name: "Stores", value: Math.max(0, snapshot.suppliers_inactive), route: `/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold` },
    ].filter((x) => x.value > 0);

    return {
      kpis: [
        { id: "total_tasks", label: "Total Tasks", value: totalTasks, accent: "navy", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/tasks`) },
        { id: "samples", label: "Samples", value: samples, accent: "green", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents`) },
        { id: "defects", label: "Defects", value: defects, accent: "amber", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=cap_open`) },
        { id: "fatal_errors", label: "Fatal Errors", value: fatalErrors, accent: "rose", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue`) },
      ],
      qualityScore,
      fatalErrorsBySupervisor,
      fatalErrorsByLocation,
      fatalErrorsByMonth: snapshot.audit_closure_trend.map((p) => ({ month: p.period_start.slice(5), value: p.closed_count, route: `/maintenance/${amoCode}/${department}/qms/audits?status=closed&closed_from=${p.period_start}&closed_to=${p.period_end}` })),
      samplesVsDefects: fatalErrorsBySupervisor.map((row, idx) => ({ name: row.name, samples: (idx + 1) * 8 + snapshot.documents_active, defects: row.value, route: row.route })),
      fatalErrorsByEmployee: fatalErrorsBySupervisor.sort((a, b) => b.value - a.value),
      manpower: {
        on_duty_total: snapshot.manpower_on_duty_total ?? Math.max(0, snapshot.cars_open_total + snapshot.findings_open_total),
        engineers: snapshot.manpower_engineers_on_duty ?? Math.max(0, snapshot.cars_open_total),
        technicians: snapshot.manpower_technicians_on_duty ?? Math.max(0, snapshot.findings_open_total),
        inspectors: snapshot.manpower_inspectors_on_duty ?? Math.max(0, snapshot.findings_overdue),
      },
    };
  }, [snapshot, amoCode, department, selectedAuditor]);

  const loading = snapshotQuery.isLoading;

  return (
    <div className="qms-cockpit-shell">
      <header className="qms-cockpit-head">
        <div>
          <h1>Quality Control Dashboard</h1>
          <p>Operational controls, trend watch, and deterministic drilldowns.</p>
        </div>
        <div className="qms-cockpit-head__actions">
          <div className="qms-segmented" role="tablist" aria-label="Auditor selection">
            {(["Eva", "Mike", "Smith"] as const).map((auditor) => (
              <button key={auditor} type="button" role="tab" aria-selected={selectedAuditor === auditor} className={selectedAuditor === auditor ? "is-active" : ""} onClick={() => setSelectedAuditor(auditor)}>
                {auditor}
              </button>
            ))}
          </div>
          <button type="button" className="secondary-chip-btn" onClick={() => snapshotQuery.refetch()}>
            Refresh
          </button>
          {isDev && usingMockData ? <span className="qms-mock-pill">Using mock data</span> : null}
        </div>
      </header>

      <section className="qms-manpower-card" aria-label="Current manpower on duty">
        <div>
          <strong>Manpower On Duty</strong>
          <p>{visualData.manpower.on_duty_total}</p>
        </div>
        <div className="qms-manpower-card__split">
          <span>Engineers {visualData.manpower.engineers}</span>
          <span>Technicians {visualData.manpower.technicians}</span>
          <span>Inspectors {visualData.manpower.inspectors}</span>
        </div>
      </section>

      <section className="quality-navigator" aria-label="Quality Navigator">
        <div className="quality-navigator__header">
          <h2 className="quality-navigator__title">Quality Navigator</h2>
          <span className="quality-navigator__subtitle">All QMS destinations</span>
        </div>
        <div className="quality-navigator__grid">
          {navigatorTiles.map((tile) => {
            const Icon = tile.icon;
            return (
              <button key={tile.id} type="button" className="quality-navigator__tile" onClick={() => nav(tile.to)} aria-label={`Open ${tile.label}`}>
                <div className="quality-navigator__tile-top">
                  <Icon size={16} />
                  {typeof tile.badge === "number" ? <span className="quality-navigator__badge">{tile.badge}</span> : null}
                </div>
                <span>{tile.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {loading ? <div className="qms-skeleton-row"><div /><div /><div /><div /></div> : null}
      {snapshotQuery.isError && !usingMockData ? <div className="alert alert-error">Unable to load cockpit snapshot.</div> : null}

      {topPriority ? (
        <section className="priority-gate" aria-live="polite">
          <div className="priority-gate__eyebrow">Top priority</div>
          <h2 className="priority-gate__title">{topPriority.title}</h2>
          <p className="priority-gate__description">{topPriority.description}</p>
          <div className="priority-gate__actions">
            <span className="priority-gate__count">Count: {topPriority.count}</span>
            <button type="button" className="btn btn-primary" onClick={() => nav(topPriority.route)}>
              Resolve now
            </button>
          </div>
        </section>
      ) : (
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
      )}

      <ActionPanel isOpen={!!panelContext} context={panelContext} onClose={() => setPanelContext(null)} />
    </div>
  );
};

export default DashboardCockpit;

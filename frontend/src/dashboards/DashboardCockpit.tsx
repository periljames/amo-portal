import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  BookOpenCheck,
  ClipboardCheck,
  FileClock,
  FileSearch,
  GraduationCap,
  Home,
  ListChecks,
  NotebookText,
  ShieldCheck,
  Truck,
  Wrench,
} from "lucide-react";

import DashboardScaffold, { type KpiTile } from "../components/dashboard/DashboardScaffold";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getContext } from "../services/auth";
import { qmsGetCockpitSnapshot, type CARStatus } from "../services/qms";
import { useRealtime } from "../components/realtime/RealtimeProvider";
import { listEventHistory } from "../services/events";

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

  const { data: activityHistory } = useInfiniteQuery({
    queryKey: ["activity-history", amoCode, department],
    queryFn: ({ pageParam }) =>
      listEventHistory({ cursor: pageParam as string | undefined, limit: 50 }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
  });
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);

  const qmsEnabled = department === "quality";

  const { data: snapshot } = useQuery({
    queryKey: ["qms-cockpit-snapshot", amoCode],
    queryFn: () => qmsGetCockpitSnapshot(),
    enabled: qmsEnabled,
    staleTime: 15_000,
  });

  const nav = (to: string) => navigate(to);

  const navigatorTiles = useMemo<NavigatorTile[]>(() => {
    const base = `/maintenance/${amoCode}/${department}/qms`;
    return [
      { id: "nav-home", label: "QMS Home", icon: Home, to: base },
      {
        id: "nav-tasks",
        label: "My Tasks",
        icon: ListChecks,
        to: `${base}/tasks`,
        badge: snapshot?.action_queue?.length,
      },
      {
        id: "nav-docs",
        label: "Documents",
        icon: NotebookText,
        to: `${base}/documents`,
        badge: snapshot?.pending_acknowledgements,
      },
      {
        id: "nav-audits",
        label: "Audits",
        icon: FileSearch,
        to: `${base}/audits`,
        badge: snapshot?.findings_overdue,
      },
      {
        id: "nav-change",
        label: "Change Control",
        icon: ClipboardCheck,
        to: `${base}/change-control`,
        badge: snapshot?.change_requests_open,
      },
      {
        id: "nav-cars",
        label: "CAR Register",
        icon: Wrench,
        to: `${base}/cars`,
        badge: snapshot?.cars_overdue,
      },
      {
        id: "nav-training",
        label: "Training",
        icon: GraduationCap,
        to: `${base}/training`,
        badge: snapshot?.training_records_expired,
      },
      {
        id: "nav-events",
        label: "Quality Events",
        icon: AlertTriangle,
        to: `${base}/events`,
        badge: snapshot?.suppliers_inactive,
      },
      {
        id: "nav-kpis",
        label: "KPIs & Review",
        icon: BarChart3,
        to: `${base}/kpis`,
        badge: snapshot?.findings_open_total,
      },
    ];
  }, [amoCode, department, snapshot]);

  const topPriority = useMemo<PriorityItem | null>(() => {
    const findingsOverdue = snapshot?.findings_overdue ?? 0;
    if (findingsOverdue > 0) {
      return {
        id: "priority-findings-overdue",
        title: "Overdue findings require immediate closure",
        description: `${findingsOverdue} overdue findings are still open in active audits.`,
        count: findingsOverdue,
        route: `/maintenance/${amoCode}/${department}/qms/audits?status=in_progress&finding=overdue`,
      };
    }

    const carsOverdue = snapshot?.cars_overdue ?? 0;
    if (carsOverdue > 0) {
      return {
        id: "priority-cars-overdue",
        title: "Overdue corrective actions",
        description: `${carsOverdue} CARs are overdue and need owner action.`,
        count: carsOverdue,
        route: `/maintenance/${amoCode}/${department}/qms/cars?status=overdue`,
      };
    }

    const trainingExpired = snapshot?.training_records_expired ?? 0;
    if (trainingExpired > 0) {
      return {
        id: "priority-training-expired",
        title: "Expired training records",
        description: `${trainingExpired} training records are expired.`,
        count: trainingExpired,
        route: `/maintenance/${amoCode}/${department}/qms/training?currency=expired`,
      };
    }

    const trainingExpiring = snapshot?.training_records_expiring_30d ?? 0;
    if (trainingExpiring > 0) {
      return {
        id: "priority-training-expiring",
        title: "Training expiring in 30 days",
        description: `${trainingExpiring} training records expire within 30 days.`,
        count: trainingExpiring,
        route: `/maintenance/${amoCode}/${department}/qms/training?currency=expiring_30d`,
      };
    }

    const docApprovals = snapshot?.documents_draft ?? 0;
    if (docApprovals > 0) {
      return {
        id: "priority-doc-approvals",
        title: "Pending document approvals",
        description: `${docApprovals} documents are waiting for draft/review approval.`,
        count: docApprovals,
        route: `/maintenance/${amoCode}/${department}/qms/documents?status_=DRAFT`,
      };
    }

    const pendingAcks = snapshot?.pending_acknowledgements ?? 0;
    if (pendingAcks > 0) {
      return {
        id: "priority-acks",
        title: "Pending acknowledgements",
        description: `${pendingAcks} controlled distribution acknowledgements are still pending.`,
        count: pendingAcks,
        route: `/maintenance/${amoCode}/${department}/qms/documents?ack=pending`,
      };
    }

    const supplierHold = snapshot?.suppliers_inactive ?? 0;
    if (supplierHold > 0) {
      return {
        id: "priority-supplier-hold",
        title: "Supplier quality hold indicators",
        description: `${supplierHold} suppliers are currently inactive/hold-tracked.`,
        count: supplierHold,
        route: `/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold`,
      };
    }

    const findingsOpen = snapshot?.findings_open_total ?? 0;
    if (findingsOpen > 0) {
      return {
        id: "priority-findings-open",
        title: "Open findings pending closure",
        description: `${findingsOpen} findings remain open across QMS audits.`,
        count: findingsOpen,
        route: `/maintenance/${amoCode}/${department}/qms/audits?status=cap_open`,
      };
    }

    return null;
  }, [snapshot, amoCode, department]);

  const kpis = useMemo(() => {
    const auditsClosed = Math.max(
      (snapshot?.audits_total ?? 0) - (snapshot?.audits_open ?? 0),
      0
    );
    const carsOverdue = snapshot?.cars_overdue ?? 0;
    const carsOpen = snapshot?.cars_open_total ?? 0;
    const tiles: KpiTile[] = [
      {
        id: "findings-overdue",
        icon: AlertTriangle,
        status: "overdue",
        label: "Overdue findings",
        value: snapshot?.findings_overdue ?? 0,
        timeframe: "Now",
        updatedAt: "risk queue",
        onClick: () =>
          nav(
            `/maintenance/${amoCode}/${department}/qms/audits?status=in_progress&finding=overdue`
          ),
      },
      {
        id: "findings-open",
        icon: FileClock,
        status: "awaiting-evidence",
        label: "Open findings",
        value: snapshot?.findings_open_total ?? 0,
        timeframe: "Now",
        updatedAt: "all levels",
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=cap_open`),
      },
      {
        id: "acks",
        icon: ClipboardCheck,
        status: "awaiting-evidence",
        label: "Pending acknowledgements",
        value: snapshot?.pending_acknowledgements ?? 0,
        timeframe: "Now",
        updatedAt: "document control",
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`),
      },
      {
        id: "doc-pending-approvals",
        icon: BookOpenCheck,
        status: "due-week",
        label: "Pending doc approvals",
        value: snapshot?.documents_draft ?? 0,
        timeframe: "Now",
        updatedAt: "draft/review",
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents?status_=DRAFT`),
      },
      {
        id: "cars-overdue",
        icon: Wrench,
        status: carsOverdue > 0 ? "overdue" : "closed",
        label: "Overdue CARs",
        value: `${carsOverdue}/${carsOpen}`,
        timeframe: "Now",
        updatedAt: "corrective actions",
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue`),
      },
      {
        id: "training-currency",
        icon: GraduationCap,
        status: (snapshot?.training_records_expired ?? 0) > 0 ? "overdue" : "due-week",
        label: "Training currency",
        value: `${snapshot?.training_records_expired ?? 0}/${snapshot?.training_records_expiring_30d ?? 0}`,
        timeframe: "expired / 30d",
        updatedAt: "records",
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/training?currency=expiring_30d`),
      },
      {
        id: "training-pending",
        icon: GraduationCap,
        status: "awaiting-evidence",
        label: "Pending training controls",
        value: `${snapshot?.training_records_unverified ?? 0}/${snapshot?.training_deferrals_pending ?? 0}`,
        timeframe: "verify / deferrals",
        updatedAt: "quality review",
        onClick: () =>
          nav(
            `/maintenance/${amoCode}/${department}/qms/training?verification=pending&deferral=pending`
          ),
      },
      {
        id: "supplier-control",
        icon: Truck,
        status: (snapshot?.suppliers_inactive ?? 0) > 0 ? "noncompliance" : "closed",
        label: "Suppliers quality hold",
        value: `${snapshot?.suppliers_inactive ?? 0}/${snapshot?.suppliers_active ?? 0}`,
        timeframe: "hold / active",
        updatedAt: "subcontractors",
        onClick: () =>
          nav(`/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold`),
      },
      {
        id: "audit-closure",
        icon: ShieldCheck,
        status: "closed",
        label: "Audit closures",
        value: auditsClosed,
        timeframe: "last 90d",
        updatedAt: `${snapshot?.audits_open ?? 0} open`,
        onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=closed`),
      },
    ];
    return tiles;
  }, [snapshot, amoCode, department, navigate]);

  const drivers = useMemo(() => {
    const trend: AuditTrendPoint[] = snapshot?.audit_closure_trend ?? [];
    const xData = trend.map((point) => point.period_start.slice(5));
    const seriesData = trend.map((point) => ({ value: point.closed_count, ...point }));

    const docCount = snapshot?.documents_active ?? 0;
    const carCount = snapshot?.cars_open_total ?? 0;
    const trainingCount = (snapshot?.training_records_expired ?? 0) + (snapshot?.training_records_expiring_30d ?? 0);
    const supplierCount = snapshot?.suppliers_inactive ?? 0;

    return [
      {
        id: "audit-closure",
        title: "Audit closure rate",
        subtitle: `${snapshot?.audits_open ?? 0} open audits · click any point for drilldown`,
        onChartClick: (event: { data?: unknown }) => {
          const datum = event.data as AuditTrendPoint | undefined;
          if (!datum?.period_start || !datum?.period_end) return;
          const ids = datum.audit_ids?.length
            ? `&auditIds=${encodeURIComponent(datum.audit_ids.join(","))}`
            : "";
          nav(
            `/maintenance/${amoCode}/${department}/qms/audits?status=closed&closed_from=${datum.period_start}&closed_to=${datum.period_end}${ids}`
          );
        },
        option: {
          tooltip: {
            trigger: "axis",
            confine: true,
            formatter: (items: Array<{ data: AuditTrendPoint }>) => {
              const point = items?.[0]?.data;
              if (!point) return "No data";
              return `Closed audits: <b>${point.closed_count}</b><br/>Window: ${point.period_start} → ${point.period_end}<br/>Audit IDs: ${point.audit_ids.length}`;
            },
          },
          grid: { left: 38, right: 20, top: 24, bottom: 52 },
          xAxis: {
            type: "category",
            data: xData,
            boundaryGap: false,
            axisLine: { lineStyle: { color: "var(--border-subtle)" } },
            axisLabel: { color: "var(--text-secondary)" },
          },
          yAxis: {
            type: "value",
            minInterval: 1,
            axisLabel: { color: "var(--text-secondary)" },
            splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
          },
          dataZoom: [
            { type: "inside", zoomOnMouseWheel: true, moveOnMouseMove: true },
            { type: "slider", height: 20, bottom: 8 },
          ],
          series: [
            {
              data: seriesData,
              type: "line",
              smooth: true,
              symbol: "circle",
              symbolSize: 8,
              lineStyle: { width: 3 },
              areaStyle: { opacity: 0.14 },
              animationDuration: 420,
            },
          ],
        },
      },
      {
        id: "qms-control-mix",
        title: "QMS control mix",
        subtitle: "Click a segment for immediate drilldown",
        onChartClick: (event: { name?: string | number }) => {
          const name = String(event.name ?? "");
          if (name === "Documents") return nav(`/maintenance/${amoCode}/${department}/qms/documents`);
          if (name === "CARs") return nav(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue`);
          if (name === "Training") return nav(`/maintenance/${amoCode}/${department}/qms/training?currency=expiring_30d`);
          if (name === "Suppliers") return nav(`/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold`);
        },
        option: {
          tooltip: {
            trigger: "item",
            confine: true,
            formatter: "{b}: <b>{c}</b> ({d}%)",
          },
          legend: {
            bottom: 0,
            textStyle: { color: "var(--text-secondary)" },
          },
          series: [
            {
              name: "QMS Controls",
              type: "pie",
              radius: ["44%", "72%"],
              avoidLabelOverlap: true,
              itemStyle: { borderColor: "var(--surface)", borderWidth: 2 },
              label: { color: "var(--text-secondary)", formatter: "{b}" },
              data: [
                { value: docCount, name: "Documents" },
                { value: carCount, name: "CARs" },
                { value: trainingCount, name: "Training" },
                { value: supplierCount, name: "Suppliers" },
              ],
            },
          ],
        },
      },
    ];
  }, [snapshot, amoCode, department, navigate]);

  const actionItems = useMemo(
    () =>
      (snapshot?.action_queue ?? []).map((item) => ({
        id: item.id,
        type: item.kind,
        title: item.title,
        owner: item.assignee_user_id ?? "Unassigned",
        ownerId: item.assignee_user_id,
        onOwnerClick: item.assignee_user_id
          ? () => navigate(`/maintenance/${amoCode}/admin/users/${item.assignee_user_id}`)
          : undefined,
        due: item.due_date ?? "—",
        status: item.status as CARStatus,
        priority: item.priority,
        onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${item.id}`),
        action: () =>
          setPanelContext({
            type: "car",
            id: item.id,
            title: item.title,
            status: item.status as CARStatus,
            ownerId: item.assignee_user_id,
          }),
      })),
    [snapshot?.action_queue, amoCode, department, navigate]
  );

  const activityItems = useMemo(() => {
    const fromHistory = (activityHistory?.pages ?? []).flatMap((page) => page.items ?? []);
    const merged = [...activity, ...fromHistory];
    const seen = new Set<string>();
    return merged
      .filter((item) => {
        if (seen.has(item.id)) return false;
        seen.add(item.id);
        return true;
      })
      .map((item) => ({
        id: item.id,
        summary: `${item.type.split(".").join(" · ")} ${item.action}`,
        timestamp: new Date(item.timestamp).toLocaleString(),
        occurredAt: item.timestamp,
        onClick: () => {
          if (item.entityType === "user")
            return navigate(`/maintenance/${amoCode}/admin/users/${item.entityId}`);
          if (item.entityType === "task")
            return navigate(`/maintenance/${amoCode}/${department}/tasks/${item.entityId}`);
          if (item.entityType === "qms_document")
            return navigate(
              `/maintenance/${amoCode}/${department}/qms/documents?documentId=${item.entityId}`
            );
          if (item.entityType === "qms_audit")
            return navigate(`/maintenance/${amoCode}/${department}/qms/audits?auditId=${item.entityId}`);
          if (item.entityType === "qms_car")
            return navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${item.entityId}`);
          if (item.entityType.toLowerCase().includes("training"))
            return navigate(`/maintenance/${amoCode}/${department}/qms/training?userId=${item.entityId}`);
          return navigate(
            `/maintenance/${amoCode}/${department}/qms/events?entity=${item.entityType}&id=${item.entityId}`
          );
        },
      }));
  }, [activity, activityHistory?.pages, amoCode, department, navigate]);

  return (
    <>
      <section className="quality-navigator" aria-label="Quality Navigator">
        <div className="quality-navigator__header">
          <h2 className="quality-navigator__title">Quality Navigator</h2>
          <span className="quality-navigator__subtitle">All QMS destinations</span>
        </div>
        <div className="quality-navigator__grid">
          {navigatorTiles.map((tile) => {
            const Icon = tile.icon;
            return (
              <button
                key={tile.id}
                type="button"
                className="quality-navigator__tile"
                onClick={() => nav(tile.to)}
                aria-label={`Open ${tile.label}`}
              >
                <div className="quality-navigator__tile-top">
                  <Icon size={16} />
                  {typeof tile.badge === "number" ? (
                    <span className="quality-navigator__badge">{tile.badge}</span>
                  ) : null}
                </div>
                <span>{tile.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {topPriority ? (
        <section className="priority-gate" aria-live="polite">
          <div className="priority-gate__eyebrow">Top priority</div>
          <h2 className="priority-gate__title">{topPriority.title}</h2>
          <p className="priority-gate__description">{topPriority.description}</p>
          <div className="priority-gate__actions">
            <span className="priority-gate__count">Count: {topPriority.count}</span>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => nav(topPriority.route)}
            >
              Resolve now
            </button>
          </div>
        </section>
      ) : (
        <DashboardScaffold
          title={`${department.toUpperCase()} cockpit`}
          subtitle="Operational QMS controls and deterministic drilldowns"
          kpis={kpis}
          drivers={drivers}
          actionItems={actionItems}
          activity={activityItems}
        />
      )}

      <ActionPanel
        isOpen={!!panelContext}
        context={panelContext}
        onClose={() => setPanelContext(null)}
      />
    </>
  );
};

export default DashboardCockpit;

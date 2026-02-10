import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { AlertTriangle, BookOpenCheck, ClipboardCheck, FileClock, GraduationCap, ShieldCheck, Truck, Wrench } from "lucide-react";

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

const DashboardCockpit: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const { activity } = useRealtime();

  const { data: activityHistory } = useInfiniteQuery({
    queryKey: ["activity-history", amoCode, department],
    queryFn: ({ pageParam }) => listEventHistory({ cursor: pageParam as string | undefined, limit: 50 }),
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

  const kpis = useMemo(() => {
    const auditsClosed = Math.max((snapshot?.audits_total ?? 0) - (snapshot?.audits_open ?? 0), 0);
    const carsOverdue = snapshot?.cars_overdue ?? 0;
    const carsOpen = snapshot?.cars_open_total ?? 0;
    const tiles: KpiTile[] = [
      { id: "findings-overdue", icon: AlertTriangle, status: "overdue", label: "Overdue findings", value: snapshot?.findings_overdue ?? 0, timeframe: "Now", updatedAt: "risk queue", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=in_progress&finding=overdue`) },
      { id: "findings-open", icon: FileClock, status: "awaiting-evidence", label: "Open findings", value: snapshot?.findings_open_total ?? 0, timeframe: "Now", updatedAt: "all levels", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=cap_open`) },
      { id: "acks", icon: ClipboardCheck, status: "awaiting-evidence", label: "Pending acknowledgements", value: snapshot?.pending_acknowledgements ?? 0, timeframe: "Now", updatedAt: "document control", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`) },
      { id: "doc-pending-approvals", icon: BookOpenCheck, status: "due-week", label: "Pending doc approvals", value: snapshot?.documents_draft ?? 0, timeframe: "Now", updatedAt: "draft/review", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/documents?status_=DRAFT`) },
      { id: "cars-overdue", icon: Wrench, status: carsOverdue > 0 ? "overdue" : "closed", label: "Overdue CARs", value: `${carsOverdue}/${carsOpen}`, timeframe: "Now", updatedAt: "corrective actions", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue`) },
      { id: "training-currency", icon: GraduationCap, status: (snapshot?.training_records_expired ?? 0) > 0 ? "overdue" : "due-week", label: "Training currency", value: `${snapshot?.training_records_expired ?? 0}/${snapshot?.training_records_expiring_30d ?? 0}`, timeframe: "expired / 30d", updatedAt: "records", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/training?currency=expiring_30d`) },
      { id: "training-pending", icon: GraduationCap, status: "awaiting-evidence", label: "Pending training controls", value: `${snapshot?.training_records_unverified ?? 0}/${snapshot?.training_deferrals_pending ?? 0}`, timeframe: "verify / deferrals", updatedAt: "quality review", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/training?verification=pending&deferral=pending`) },
      { id: "supplier-control", icon: Truck, status: (snapshot?.suppliers_inactive ?? 0) > 0 ? "noncompliance" : "closed", label: "Suppliers quality hold", value: `${snapshot?.suppliers_inactive ?? 0}/${snapshot?.suppliers_active ?? 0}`, timeframe: "hold / active", updatedAt: "subcontractors", onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/events?entity=supplier&status=hold`) },
      { id: "audit-closure", icon: ShieldCheck, status: "closed", label: "Audit closures", value: auditsClosed, timeframe: "last 90d", updatedAt: `${snapshot?.audits_open ?? 0} open`, onClick: () => nav(`/maintenance/${amoCode}/${department}/qms/audits?status=closed`) },
    ];
    return tiles;
  }, [snapshot, amoCode, department, navigate]);

  const drivers = useMemo(() => {
    const trend: AuditTrendPoint[] = snapshot?.audit_closure_trend ?? [];
    const xData = trend.map((point) => point.period_start.slice(5));
    const seriesData = trend.map((point) => ({ value: point.closed_count, ...point }));
    return [{
      id: "audit-closure",
      title: "Audit closure rate",
      subtitle: `${snapshot?.audits_open ?? 0} open audits · click any point for drilldown`,
      onChartClick: (event: { data?: unknown }) => {
        const datum = event.data as AuditTrendPoint | undefined;
        if (!datum?.period_start || !datum?.period_end) return;
        const ids = datum.audit_ids?.length ? `&auditIds=${encodeURIComponent(datum.audit_ids.join(","))}` : "";
        nav(`/maintenance/${amoCode}/${department}/qms/audits?status=closed&closed_from=${datum.period_start}&closed_to=${datum.period_end}${ids}`);
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
        series: [{
          data: seriesData,
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.14 },
          animationDuration: 420,
        }],
      },
    }];
  }, [snapshot, amoCode, department, navigate]);

  const actionItems = useMemo(() => (snapshot?.action_queue ?? []).map((item) => ({
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
  })), [snapshot?.action_queue, amoCode, department, navigate]);

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
          if (item.entityType === "user") return navigate(`/maintenance/${amoCode}/admin/users/${item.entityId}`);
          if (item.entityType === "task") return navigate(`/maintenance/${amoCode}/${department}/tasks/${item.entityId}`);
          if (item.entityType === "qms_document") return navigate(`/maintenance/${amoCode}/${department}/qms/documents?documentId=${item.entityId}`);
          if (item.entityType === "qms_audit") return navigate(`/maintenance/${amoCode}/${department}/qms/audits?auditId=${item.entityId}`);
          if (item.entityType === "qms_car") return navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${item.entityId}`);
          if (item.entityType.toLowerCase().includes("training")) return navigate(`/maintenance/${amoCode}/${department}/qms/training?userId=${item.entityId}`);
          return navigate(`/maintenance/${amoCode}/${department}/qms/events?entity=${item.entityType}&id=${item.entityId}`);
        },
      }));
  }, [activity, activityHistory?.pages, amoCode, department, navigate]);

  return (
    <>
      <DashboardScaffold title={`${department.toUpperCase()} cockpit`} subtitle="Operational QMS controls and deterministic drilldowns" kpis={kpis} drivers={drivers} actionItems={actionItems} activity={activityItems} />
      <ActionPanel isOpen={!!panelContext} context={panelContext} onClose={() => setPanelContext(null)} />
    </>
  );
};

export default DashboardCockpit;

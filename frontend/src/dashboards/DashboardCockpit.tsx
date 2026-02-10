import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { AlertTriangle, BookOpenCheck, ClipboardCheck, FileClock, ShieldCheck } from "lucide-react";

import DashboardScaffold, { type KpiTile } from "../components/dashboard/DashboardScaffold";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getContext } from "../services/auth";
import { qmsGetCockpitSnapshot, type CARStatus } from "../services/qms";
import { useRealtime } from "../components/realtime/RealtimeProvider";
import { listEventHistory } from "../services/events";

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

  const qmsEnabled = department === "quality" || department === "safety";

  const { data: snapshot } = useQuery({
    queryKey: ["qms-cockpit-snapshot", amoCode],
    queryFn: () => qmsGetCockpitSnapshot(),
    enabled: qmsEnabled,
    staleTime: 15_000,
  });

  const kpis = useMemo(() => {
    const auditsClosed = Math.max((snapshot?.audits_total ?? 0) - (snapshot?.audits_open ?? 0), 0);
    const tiles: KpiTile[] = [
      { id: "findings-overdue", icon: AlertTriangle, status: "overdue", label: "Overdue findings", value: snapshot?.findings_overdue ?? 0, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits?status=in_progress`) },
      { id: "findings-open", icon: FileClock, status: "awaiting-evidence", label: "Open findings", value: snapshot?.findings_open_total ?? 0, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits?status=cap_open`) },
      { id: "acks", icon: ClipboardCheck, status: "awaiting-evidence", label: "Pending acknowledgements", value: snapshot?.pending_acknowledgements ?? 0, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`) },
      { id: "doc-currency", icon: BookOpenCheck, status: "closed", label: "Document currency", value: snapshot?.documents_active ?? 0, timeframe: "Month", updatedAt: `${snapshot?.documents_obsolete ?? 0} obsolete`, onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/documents?currency=expiring_30d`) },
      { id: "audit-closure", icon: ShieldCheck, status: "closed", label: "Audit closures", value: auditsClosed, timeframe: "Month", updatedAt: `${snapshot?.audits_open ?? 0} open`, onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits?trend=monthly&status=closed`) },
    ];
    return tiles;
  }, [snapshot, amoCode, department, navigate]);

  const drivers = useMemo(() => {
    const auditOpen = snapshot?.audits_open ?? 0;
    return [{ id: "audit-closure", title: "Audit closure rate", subtitle: `${auditOpen} open audits`, option: { xAxis: { type: "category", data: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] }, yAxis: { type: "value" }, grid: { left: 24, right: 16, top: 24, bottom: 24 }, series: [{ data: [3, 4, 5, 4, 6, 5, 7], type: "line", smooth: true, animationDuration: 550 }] } }];
  }, [snapshot]);

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
      <DashboardScaffold title={`${department.toUpperCase()} cockpit`} subtitle="Realtime QMS management overview" kpis={kpis} drivers={drivers} actionItems={actionItems} activity={activityItems} />
      <ActionPanel isOpen={!!panelContext} context={panelContext} onClose={() => setPanelContext(null)} />
    </>
  );
};

export default DashboardCockpit;

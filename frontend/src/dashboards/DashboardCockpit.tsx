import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { addDays, endOfDay, isBefore, isWithinInterval, parseISO } from "date-fns";
import { AlertTriangle, BookOpenCheck, CalendarClock, ClipboardCheck, FileClock, ShieldCheck } from "lucide-react";

import DashboardScaffold, { type KpiTile } from "../components/dashboard/DashboardScaffold";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getCachedUser, getContext } from "../services/auth";
import { qmsGetDashboard, qmsListCars } from "../services/qms";
import { listMyTasks } from "../services/tasks";
import { useRealtime } from "../components/realtime/RealtimeProvider";
import { listEventHistory } from "../services/events";
import { getMyTrainingStatus } from "../services/training";

const isWithinDays = (dateStr: string | null | undefined, days: number) => {
  if (!dateStr) return false;
  const parsed = parseISO(dateStr);
  if (Number.isNaN(parsed.getTime())) return false;
  return isWithinInterval(parsed, { start: new Date(), end: addDays(new Date(), days) });
};

const isPastDue = (dateStr: string | null | undefined) => {
  if (!dateStr) return false;
  const parsed = parseISO(dateStr);
  if (Number.isNaN(parsed.getTime())) return false;
  return isBefore(parsed, endOfDay(new Date()));
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
    queryFn: ({ pageParam }) => listEventHistory({ cursor: pageParam as string | undefined, limit: 100 }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
  });
  const currentUser = getCachedUser();
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);

  const qmsEnabled = department === "quality" || department === "safety";

  const { data: cars = [] } = useQuery({ queryKey: ["qms-cars", amoCode], queryFn: () => qmsListCars(), enabled: qmsEnabled });
  const { data: dashboardSnapshot } = useQuery({ queryKey: ["qms-dashboard", amoCode], queryFn: () => qmsGetDashboard(), enabled: qmsEnabled });
  const { data: tasks = [] } = useQuery({ queryKey: ["my-tasks", amoCode], queryFn: () => listMyTasks() });
  const { data: trainingStatus = [] } = useQuery({ queryKey: ["training-status", amoCode], queryFn: () => getMyTrainingStatus() });

  const kpis = useMemo(() => {
    const overdueCars = cars.filter((car) => car.status !== "CLOSED" && isPastDue(car.due_date));
    const dueWeek = cars.filter((car) => car.status !== "CLOSED" && isWithinDays(car.due_date, 7));
    const dueMonth = cars.filter((car) => car.status !== "CLOSED" && isWithinDays(car.due_date, 30));
    const dueTasksToday = tasks.filter((task) => isWithinDays(task.due_at, 0));
    const overdueTraining = trainingStatus.filter((item) => item.status === "OVERDUE");
    const currentDocs = dashboardSnapshot?.documents_active ?? 0;
    const expiredDocs = dashboardSnapshot?.documents_obsolete ?? 0;
    const closedAudits = Math.max((dashboardSnapshot?.audits_total ?? 0) - (dashboardSnapshot?.audits_open ?? 0), 0);

    const tiles: KpiTile[] = [
      { id: "overdue", icon: AlertTriangle, status: "overdue", label: "Overdue CAR/CAPA", value: overdueCars.length, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue&dueWindow=now`) },
      { id: "due-today", icon: CalendarClock, status: "due-today", label: "Due today", value: dueTasksToday.length, timeframe: "Today", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/tasks?dueWindow=today&status=open`) },
      { id: "due-week", icon: CalendarClock, status: "due-week", label: "Due this week", value: dueWeek.length, timeframe: "Week", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=open&dueWindow=week`) },
      { id: "due-month", icon: FileClock, status: "awaiting-evidence", label: "Due this month", value: dueMonth.length, timeframe: "Month", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=open&dueWindow=month`) },
      { id: "training-overdue", icon: AlertTriangle, status: "noncompliance", label: "Overdue training", value: overdueTraining.length, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/training?status=overdue&dueWindow=now`) },
      { id: "acks", icon: ClipboardCheck, status: "awaiting-evidence", label: "Pending acknowledgements", value: dashboardSnapshot?.distributions_pending_ack ?? 0, timeframe: "Now", updatedAt: "just now", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`) },
      { id: "doc-currency", icon: BookOpenCheck, status: "closed", label: "Document currency", value: currentDocs, timeframe: "Month", updatedAt: `${expiredDocs} obsolete`, onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/documents?currency=expiring_30d`) },
      { id: "audit-closure", icon: ShieldCheck, status: "closed", label: "Audit closures", value: closedAudits, timeframe: "Month", updatedAt: `${dashboardSnapshot?.audits_open ?? 0} open`, onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits?trend=monthly&status=closed`) },
    ];
    return tiles;
  }, [cars, tasks, trainingStatus, dashboardSnapshot, amoCode, department, navigate]);

  const drivers = useMemo(() => {
    const auditOpen = dashboardSnapshot?.audits_open ?? 0;
    return [{ id: "audit-closure", title: "Audit closure rate", subtitle: `${auditOpen} open audits`, option: { xAxis: { type: "category", data: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] }, yAxis: { type: "value" }, grid: { left: 24, right: 16, top: 24, bottom: 24 }, series: [{ data: [3, 4, 5, 4, 6, 5, 7], type: "line", smooth: true, animationDuration: 550 }] } }];
  }, [dashboardSnapshot]);

  const actionItems = useMemo(() => {
    const taskItems = tasks.slice(0, 10).map((task) => ({
      id: task.id,
      type: "Task",
      title: task.title,
      owner: task.owner_user_id ?? "Assigned",
      ownerId: task.owner_user_id ?? null,
      onOwnerClick: task.owner_user_id ? () => navigate(`/maintenance/${amoCode}/admin/users/${task.owner_user_id}`) : undefined,
      due: task.due_at ? new Date(task.due_at).toLocaleDateString() : "—",
      status: task.status,
      priority: String(task.priority),
      onClick: () => navigate(`/maintenance/${amoCode}/${department}/tasks/${task.id}`),
      action: () => setPanelContext({ type: "user", userId: task.owner_user_id ?? currentUser?.id ?? "", name: task.owner_user_id ?? currentUser?.full_name ?? "User", role: currentUser?.role }),
    }));

    const carItems = cars.slice(0, 10).map((car) => ({
      id: car.id,
      type: "CAR",
      title: `${car.car_number} · ${car.title}`,
      owner: car.assigned_to_user_id ?? "Unassigned",
      ownerId: car.assigned_to_user_id ?? null,
      onOwnerClick: car.assigned_to_user_id ? () => navigate(`/maintenance/${amoCode}/admin/users/${car.assigned_to_user_id}`) : undefined,
      due: car.due_date ?? "—",
      status: car.status,
      priority: car.priority,
      onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${car.id}`),
      action: () => setPanelContext({ type: "car", id: car.id, title: car.title, status: car.status, ownerId: car.assigned_to_user_id }),
    }));

    return [...taskItems, ...carItems].slice(0, 20);
  }, [tasks, cars, currentUser, amoCode, department, navigate]);

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

import React, { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { addDays, endOfDay, isBefore, isWithinInterval, parseISO } from "date-fns";

import DashboardScaffold from "../components/dashboard/DashboardScaffold";
import { getContext } from "../services/auth";
import { qmsListAudits, qmsListCars, qmsListDistributions } from "../services/qms";
import { listMyTasks } from "../services/tasks";
import { useRealtime } from "../components/realtime/RealtimeProvider";

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

  const qmsEnabled = department === "quality" || department === "safety";

  const { data: cars = [] } = useQuery({
    queryKey: ["qms-cars", amoCode],
    queryFn: () => qmsListCars(),
    enabled: qmsEnabled,
  });

  const { data: audits = [] } = useQuery({
    queryKey: ["qms-audits", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    enabled: qmsEnabled,
  });

  const { data: distributions = [] } = useQuery({
    queryKey: ["qms-distributions", amoCode],
    queryFn: () => qmsListDistributions({ outstanding_only: true }),
    enabled: qmsEnabled,
  });

  const { data: tasks = [] } = useQuery({
    queryKey: ["my-tasks", amoCode],
    queryFn: () => listMyTasks(),
  });

  const kpis = useMemo(() => {
    const overdueCars = cars.filter((car) => car.status !== "CLOSED" && isPastDue(car.due_date));
    const dueWeek = cars.filter((car) => car.status !== "CLOSED" && isWithinDays(car.due_date, 7));
    const dueMonth = cars.filter((car) => car.status !== "CLOSED" && isWithinDays(car.due_date, 30));
    const dueTasksToday = tasks.filter((task) => isWithinDays(task.due_at, 0));

    return [
      {
        id: "overdue",
        label: "Overdue CAR/CAPA",
        value: overdueCars.length,
        timeframe: "Now",
        updatedAt: "just now",
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=overdue&dueWindow=now`),
      },
      {
        id: "due-today",
        label: "Due today",
        value: dueTasksToday.length,
        timeframe: "Today",
        updatedAt: "just now",
        onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/tasks?dueWindow=today`),
      },
      {
        id: "due-week",
        label: "Due this week",
        value: dueWeek.length,
        timeframe: "Week",
        updatedAt: "just now",
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=open&dueWindow=week`),
      },
      {
        id: "due-month",
        label: "Due this month",
        value: dueMonth.length,
        timeframe: "Month",
        updatedAt: "just now",
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/cars?status=open&dueWindow=month`),
      },
      {
        id: "acks",
        label: "Pending acknowledgements",
        value: distributions.length,
        timeframe: "Now",
        updatedAt: "just now",
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/documents?ack=pending`),
      },
      {
        id: "audits",
        label: "Open audits",
        value: audits.filter((audit) => audit.status !== "CLOSED").length,
        timeframe: "Now",
        updatedAt: "just now",
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/audits?status=open`),
      },
    ];
  }, [audits, cars, distributions.length, tasks, amoCode, department, navigate]);

  const drivers = useMemo(() => {
    const auditOpen = audits.filter((audit) => audit.status !== "CLOSED").length;
    return [
      {
        id: "audit-closure",
        title: "Audit closure rate",
        subtitle: `${auditOpen} open audits`,
        option: {
          xAxis: { type: "category", data: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] },
          yAxis: { type: "value" },
          grid: { left: 24, right: 16, top: 24, bottom: 24 },
          series: [{ data: [3, 4, 5, 4, 6, 5, 7], type: "line", smooth: true }],
        },
      },
    ];
  }, [audits]);

  const actionItems = useMemo(() => {
    const taskItems = tasks.slice(0, 10).map((task) => ({
      id: task.id,
      type: "Task",
      title: task.title,
      owner: task.owner_user_id ?? "Assigned",
      due: task.due_at ? new Date(task.due_at).toLocaleDateString() : "—",
      status: task.status,
      priority: String(task.priority),
      onClick: () => navigate(`/maintenance/${amoCode}/${department}/tasks/${task.id}`),
      action: () => navigate(`/maintenance/${amoCode}/${department}/tasks/${task.id}`),
    }));

    const carItems = cars.slice(0, 10).map((car) => ({
      id: car.id,
      type: "CAR",
      title: `${car.car_number} · ${car.title}`,
      owner: car.assigned_to_user_id ?? "Unassigned",
      due: car.due_date ?? "—",
      status: car.status,
      priority: car.priority,
      onClick: () =>
        navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${car.id}`),
      action: () =>
        navigate(`/maintenance/${amoCode}/${department}/qms/cars?carId=${car.id}`),
    }));

    return [...taskItems, ...carItems].slice(0, 20);
  }, [tasks, cars, amoCode, department, navigate]);

  const activityItems = useMemo(
    () =>
      activity.map((item) => ({
        id: item.id,
        summary: `${item.type.split(".").join(" · ")} ${item.action}`,
        timestamp: new Date(item.timestamp).toLocaleString(),
        onClick: () =>
          navigate(`/maintenance/${amoCode}/${department}/qms/events`),
      })),
    [activity, amoCode, department, navigate]
  );

  return (
    <DashboardScaffold
      title={`${department.toUpperCase()} cockpit`}
      subtitle="Realtime QMS management overview"
      kpis={kpis}
      drivers={drivers}
      actionItems={actionItems}
      activity={activityItems}
    />
  );
};

export default DashboardCockpit;

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import QMSLayout from "../components/QMS/QMSLayout";
import DataTableShell from "../components/shared/DataTableShell";
import SpreadsheetToolbar from "../components/shared/SpreadsheetToolbar";
import { getCachedUser } from "../services/auth";
import { listMyTasks, listTasks, updateTask, type TaskItem } from "../services/tasks";

type TasksTab = "mine" | "others";

function filterByRouteQuery(rows: TaskItem[], searchParams: URLSearchParams): TaskItem[] {
  const status = searchParams.get("status");
  const dueWindow = searchParams.get("dueWindow");
  const now = new Date();

  return rows.filter((task) => {
    if (status) {
      const normalized = task.status.toLowerCase();
      if (status === "overdue") {
        if (!task.due_at) return false;
        const due = new Date(task.due_at);
        if (Number.isNaN(due.getTime())) return false;
        if (["done", "cancelled"].includes(normalized)) return false;
        if (due >= now) return false;
      } else if (normalized !== status.toLowerCase()) {
        return false;
      }
    }

    if (dueWindow) {
      if (!task.due_at) return false;
      const due = new Date(task.due_at);
      if (Number.isNaN(due.getTime())) return false;
      if (dueWindow === "now") {
        return due <= now;
      }
      if (dueWindow === "week") {
        const diff = (due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
        return diff >= 0 && diff <= 7;
      }
    }

    return true;
  });
}

const MyTasksPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode = "UNKNOWN", department = "quality" } = useParams();
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<TasksTab>("mine");
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showAssignee, setShowAssignee] = useState(true);
  const [filters, setFilters] = useState({ status: "", task: "", context: "", assignee: "" });

  const currentUser = getCachedUser();

  const canViewOthers = Boolean(
    currentUser?.is_superuser ||
      currentUser?.is_amo_admin ||
      currentUser?.role === "QUALITY_MANAGER"
  );

  const myTasksQuery = useQuery({
    queryKey: ["my-tasks"],
    queryFn: listMyTasks,
    staleTime: 30_000,
  });

  const allTasksQuery = useQuery({
    queryKey: ["tasks"],
    queryFn: () => listTasks(),
    staleTime: 30_000,
    retry: false,
    enabled: canViewOthers && tab === "others",
  });

  const myTasks = useMemo(() => filterByRouteQuery(myTasksQuery.data ?? [], searchParams), [myTasksQuery.data, searchParams]);
  const assignedToOthers = useMemo(() => {
    if (!canViewOthers) return [];
    const raw = allTasksQuery.data ?? [];
    const mine = new Set((myTasksQuery.data ?? []).map((task) => task.id));
    const ownerId = currentUser?.id;
    return filterByRouteQuery(
      raw.filter((task) => !mine.has(task.id) && (!ownerId || task.owner_user_id !== ownerId)),
      searchParams
    );
  }, [allTasksQuery.data, canViewOthers, currentUser?.id, myTasksQuery.data, searchParams]);

  const activeRows = tab === "mine" ? myTasks : assignedToOthers;

  const filteredRows = useMemo(
    () =>
      activeRows
        .filter((task) => task.status.toLowerCase().includes(filters.status.toLowerCase()))
        .filter((task) => task.title.toLowerCase().includes(filters.task.toLowerCase()))
        .filter((task) => `${task.entity_type ?? ""} ${task.entity_id ?? ""}`.toLowerCase().includes(filters.context.toLowerCase()))
        .filter((task) => (task.owner_user_id ?? "").toLowerCase().includes(filters.assignee.toLowerCase()))
        .sort((a, b) => {
          const aDue = a.due_at ? Date.parse(a.due_at) : Number.POSITIVE_INFINITY;
          const bDue = b.due_at ? Date.parse(b.due_at) : Number.POSITIVE_INFINITY;
          return aDue - bDue;
        }),
    [activeRows, filters.assignee, filters.context, filters.status, filters.task]
  );

  const handleMarkDone = async (taskId: string) => {
    await updateTask(taskId, { status: "DONE" });
    await myTasksQuery.refetch();
    if (canViewOthers) await allTasksQuery.refetch();
  };

  const loading = myTasksQuery.isLoading || (tab === "others" && canViewOthers && allTasksQuery.isLoading);
  const error = myTasksQuery.error instanceof Error
    ? myTasksQuery.error.message
    : tab === "others" && canViewOthers && allTasksQuery.error instanceof Error
      ? allTasksQuery.error.message
      : null;

  return (
    <QMSLayout amoCode={amoCode} department={department} title="Tasks" subtitle="Assigned to me and team workload routed from existing Quality task services.">
      <DataTableShell
        title="QMS Task Register"
        actions={
          <div className="qms-segmented" role="tablist" aria-label="Task assignment tabs">
            <button type="button" className={tab === "mine" ? "is-active" : ""} onClick={() => setTab("mine")}>Assigned to me</button>
            <button type="button" className={tab === "others" ? "is-active" : ""} onClick={() => setTab("others")}>Assigned to others</button>
          </div>
        }
      >
        <SpreadsheetToolbar
          density={density}
          onDensityChange={setDensity}
          wrapText={wrapText}
          onWrapTextChange={setWrapText}
          showFilters={showFilters}
          onShowFiltersChange={setShowFilters}
          columnToggles={[{ id: "assignee", label: "Assignee", checked: showAssignee, onToggle: () => setShowAssignee((v) => !v) }]}
        />

        {loading ? <p>Loading tasks…</p> : null}
        {error ? <p className="error-text">{error}</p> : null}

        {!loading && tab === "others" && !canViewOthers ? <p className="text-muted">Assigned to others is available for Quality Manager, AMO Admin, and Superuser roles.</p> : null}
        {!loading && !filteredRows.length ? <p>No tasks for this tab/filter.</p> : null}

        {!!filteredRows.length && (
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Status</th>
                <th>Task</th>
                <th>Record / Context</th>
                <th>Assigned date</th>
                <th>Due date</th>
                {showAssignee ? <th>Assignee</th> : null}
                <th>Actions</th>
              </tr>
              {showFilters ? (
                <tr>
                  <th><input className="input" style={{ height: 30 }} placeholder="Status" value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} /></th>
                  <th><input className="input" style={{ height: 30 }} placeholder="Task" value={filters.task} onChange={(e) => setFilters((prev) => ({ ...prev, task: e.target.value }))} /></th>
                  <th><input className="input" style={{ height: 30 }} placeholder="Record/context" value={filters.context} onChange={(e) => setFilters((prev) => ({ ...prev, context: e.target.value }))} /></th>
                  <th></th>
                  <th></th>
                  {showAssignee ? <th><input className="input" style={{ height: 30 }} placeholder="Assignee" value={filters.assignee} onChange={(e) => setFilters((prev) => ({ ...prev, assignee: e.target.value }))} /></th> : null}
                  <th></th>
                </tr>
              ) : null}
            </thead>
            <tbody>
              {filteredRows.map((task) => (
                <tr key={task.id}>
                  <td>{task.status}</td>
                  <td>
                    <strong>{task.title}</strong>
                    {task.description ? <div className="table-subtext">{task.description}</div> : null}
                  </td>
                  <td>
                    <div className="table-subtext">{task.entity_type ?? "—"}</div>
                    <div className="table-subtext">{task.entity_id ?? "—"}</div>
                  </td>
                  <td>{new Date(task.created_at).toLocaleDateString()}</td>
                  <td>{task.due_at ? new Date(task.due_at).toLocaleString() : "—"}</td>
                  {showAssignee ? <td>{task.owner_user_id ?? "Unassigned"}</td> : null}
                  <td>
                    <button
                      type="button"
                      className="secondary-chip-btn"
                      onClick={() => navigate(`/maintenance/${amoCode}/${department}/tasks/${task.id}`)}
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      className="secondary-chip-btn"
                      onClick={() => void handleMarkDone(task.id)}
                      disabled={task.status === "DONE" || task.status === "CANCELLED"}
                    >
                      Mark done
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DataTableShell>
    </QMSLayout>
  );
};

export default MyTasksPage;

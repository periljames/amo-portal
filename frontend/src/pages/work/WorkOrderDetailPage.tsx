// src/pages/work/WorkOrderDetailPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import {
  createTask,
  getWorkOrder,
  listTasksForWorkOrder,
  type TaskCategory,
  type TaskCardRead,
  type TaskCreatePayload,
  type TaskPriority,
  type WorkOrderRead,
} from "../../services/workOrders";

type UrlParams = {
  amoCode?: string;
  department?: string;
  id?: string;
};

const WorkOrderDetailPage: React.FC = () => {
  const { amoCode, department, id } = useParams<UrlParams>();
  const context = getContext();
  const navigate = useNavigate();
  const [workOrder, setWorkOrder] = useState<WorkOrderRead | null>(null);
  const [tasks, setTasks] = useState<TaskCardRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [taskForm, setTaskForm] = useState({
    title: "",
    description: "",
    category: "UNSCHEDULED" as TaskCategory,
    priority: "MEDIUM" as TaskPriority,
    ataChapter: "",
    zone: "",
    accessPanel: "",
  });

  const workOrderId = Number(id);
  const resolvedAmoCode = amoCode || context.amoSlug || "system";
  const activeDepartment = (department || context.department || "planning").toLowerCase();
  const basePath = `/maintenance/${resolvedAmoCode}/${activeDepartment}`;
  const canCreateNonRoutine =
    activeDepartment === "engineering" || activeDepartment === "production";

  useEffect(() => {
    if (!workOrderId || Number.isNaN(workOrderId)) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [wo, taskList] = await Promise.all([
          getWorkOrder(workOrderId),
          listTasksForWorkOrder(workOrderId),
        ]);
        setWorkOrder(wo);
        setTasks(taskList);
      } catch (e: any) {
        console.error("Failed to load work order", e);
        setError(e?.message || "Could not load work order.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [workOrderId]);

  const openTask = (taskId?: number) => {
    if (!taskId) return;
    navigate(`${basePath}/tasks/${taskId}`);
  };

  const openTaskPrint = (taskId?: number) => {
    if (!taskId) return;
    navigate(`${basePath}/tasks/${taskId}/print`);
  };

  const goBackToWorkOrders = () => {
    navigate(`${basePath}/work-orders`);
  };

  const handleTaskChange =
    (key: keyof typeof taskForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setTaskForm((prev) => ({ ...prev, [key]: e.target.value }));
    };

  const handleTaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workOrder?.id) return;
    setCreatingTask(true);
    setError(null);
    setNotice(null);
    try {
      const payload: TaskCreatePayload = {
        title: taskForm.title.trim(),
        description: taskForm.description.trim() || null,
        category: taskForm.category || "UNSCHEDULED",
        origin_type: "NON_ROUTINE",
        priority: taskForm.priority || "MEDIUM",
        ata_chapter: taskForm.ataChapter.trim() || null,
        zone: taskForm.zone.trim() || null,
        access_panel: taskForm.accessPanel.trim() || null,
      };

      if (!payload.title) {
        setError("Task title is required.");
        return;
      }

      const created = await createTask(workOrder.id, payload);
      setTasks((prev) => [created, ...prev]);
      setTaskForm({
        title: "",
        description: "",
        category: "UNSCHEDULED",
        priority: "MEDIUM",
        ataChapter: "",
        zone: "",
        accessPanel: "",
      });
      setNotice(`Non-routine task "${created.title || payload.title}" created.`);
    } catch (e: any) {
      console.error("Failed to create task", e);
      setError(e?.message || "Could not create task.");
    } finally {
      setCreatingTask(false);
    }
  };

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment={activeDepartment}>
      <div className="page-layout">
        <div className="page-header">
          <h1 className="page-header__title">Work Order Detail</h1>
          <p className="page-header__subtitle">
            {workOrder?.wo_number || "Work order"} •{" "}
            {workOrder?.aircraft_serial_number || "—"}
          </p>
          <div className="page-section__actions">
            <button className="btn btn-secondary" type="button" onClick={goBackToWorkOrders}>
              Back to work orders
            </button>
          </div>
        </div>

        {error && <div className="card card--error">{error}</div>}
        {notice && <div className="card card--info">{notice}</div>}
        {loading && <div className="card">Loading work order…</div>}

        {workOrder && (
          <section className="page-section">
            <h2 className="page-section__title">Summary</h2>
            <div className="page-section__grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
              <div>
                <div className="table-secondary-text">Work Order</div>
                <div className="table-primary-text">{workOrder.wo_number || "—"}</div>
              </div>
              <div>
                <div className="table-secondary-text">Aircraft</div>
                <div className="table-primary-text">{workOrder.aircraft_serial_number || "—"}</div>
              </div>
              <div>
                <div className="table-secondary-text">Status</div>
                <div className="table-primary-text">{workOrder.status || "—"}</div>
              </div>
              <div>
                <div className="table-secondary-text">Check Type</div>
                <div className="table-primary-text">{workOrder.check_type || "—"}</div>
              </div>
              <div>
                <div className="table-secondary-text">Work Order Type</div>
                <div className="table-primary-text">{workOrder.wo_type || "—"}</div>
              </div>
              <div>
                <div className="table-secondary-text">Open Date</div>
                <div className="table-primary-text">
                  {workOrder.open_date ? new Date(workOrder.open_date).toLocaleDateString() : "—"}
                </div>
              </div>
              <div>
                <div className="table-secondary-text">Due Date</div>
                <div className="table-primary-text">
                  {workOrder.due_date ? new Date(workOrder.due_date).toLocaleDateString() : "—"}
                </div>
              </div>
            </div>
          </section>
        )}

        {canCreateNonRoutine && workOrder && (
          <section className="page-section">
            <h2 className="page-section__title">Add non-routine task</h2>
            <form className="work-orders-panel" onSubmit={handleTaskSubmit}>
              <div className="form-grid">
                <label>
                  Task Title
                  <input
                    type="text"
                    value={taskForm.title}
                    onChange={handleTaskChange("title")}
                    placeholder="Describe the non-routine task"
                  />
                </label>
                <label>
                  Description
                  <input
                    type="text"
                    value={taskForm.description}
                    onChange={handleTaskChange("description")}
                    placeholder="Optional details"
                  />
                </label>
                <label>
                  Category
                  <select value={taskForm.category} onChange={handleTaskChange("category")}>
                    <option value="UNSCHEDULED">Unscheduled</option>
                    <option value="DEFECT">Defect</option>
                  </select>
                </label>
                <label>
                  Priority
                  <select value={taskForm.priority} onChange={handleTaskChange("priority")}>
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="CRITICAL">Critical</option>
                  </select>
                </label>
                <label>
                  ATA Chapter
                  <input
                    type="text"
                    value={taskForm.ataChapter}
                    onChange={handleTaskChange("ataChapter")}
                    placeholder="e.g. 27"
                  />
                </label>
                <label>
                  Zone
                  <input
                    type="text"
                    value={taskForm.zone}
                    onChange={handleTaskChange("zone")}
                    placeholder="Optional"
                  />
                </label>
                <label>
                  Access Panel
                  <input
                    type="text"
                    value={taskForm.accessPanel}
                    onChange={handleTaskChange("accessPanel")}
                    placeholder="Optional"
                  />
                </label>
              </div>
              <div className="page-section__actions">
                <button className="btn btn-primary" type="submit" disabled={creatingTask}>
                  {creatingTask ? "Creating…" : "Add task"}
                </button>
              </div>
            </form>
          </section>
        )}

        <section className="page-section">
          <h2 className="page-section__title">Tasks</h2>
          <div className="table-responsive">
            <table className="table table-compact table-striped">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Task</th>
                  <th>Title</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Planned Start</th>
                  <th>Planned End</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!loading && tasks.length === 0 ? (
                  <tr>
                    <td colSpan={9}>No tasks for this work order.</td>
                  </tr>
                ) : (
                  tasks.map((task, index) => (
                    <tr
                      key={task.id}
                      onClick={() => openTask(task.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{index + 1}</td>
                      <td>{task.task_code || task.id}</td>
                      <td>{task.title || "—"}</td>
                      <td>{task.category || "—"}</td>
                      <td>{task.status || "—"}</td>
                      <td>{task.priority || "—"}</td>
                      <td>{task.planned_start ? new Date(task.planned_start).toLocaleString() : "—"}</td>
                      <td>{task.planned_end ? new Date(task.planned_end).toLocaleString() : "—"}</td>
                      <td>
                        <div className="table-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-small"
                            onClick={(event) => {
                              event.stopPropagation();
                              openTask(task.id);
                            }}
                          >
                            View
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-small"
                            onClick={(event) => {
                              event.stopPropagation();
                              openTaskPrint(task.id);
                            }}
                          >
                            Print
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </DepartmentLayout>
  );
};

export default WorkOrderDetailPage;

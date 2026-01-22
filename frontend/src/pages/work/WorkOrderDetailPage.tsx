// src/pages/work/WorkOrderDetailPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import {
  getWorkOrder,
  listTasksForWorkOrder,
  type TaskCardRead,
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
  const [error, setError] = useState<string | null>(null);

  const workOrderId = Number(id);
  const resolvedAmoCode = amoCode || context.amoSlug || "system";
  const activeDepartment = (department || context.department || "planning").toLowerCase();

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
    navigate(`/tasks/${taskId}`);
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
        </div>

        {error && <div className="card card--error">{error}</div>}
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

        <section className="page-section">
          <h2 className="page-section__title">Tasks</h2>
          <div className="table-responsive">
            <table className="table table-compact table-striped">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Planned Start</th>
                  <th>Planned End</th>
                </tr>
              </thead>
              <tbody>
                {!loading && tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No tasks for this work order.</td>
                  </tr>
                ) : (
                  tasks.map((task) => (
                    <tr
                      key={task.id}
                      onClick={() => openTask(task.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{task.task_code || task.id}</td>
                      <td>{task.title || "—"}</td>
                      <td>{task.status || "—"}</td>
                      <td>{task.priority || "—"}</td>
                      <td>{task.planned_start ? new Date(task.planned_start).toLocaleString() : "—"}</td>
                      <td>{task.planned_end ? new Date(task.planned_end).toLocaleString() : "—"}</td>
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

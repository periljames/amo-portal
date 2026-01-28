// src/pages/work/TaskPrintPage.tsx
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getTask, type TaskCardRead } from "../../services/workOrders";

type UrlParams = {
  amoCode?: string;
  department?: string;
  taskId?: string;
};

const TaskPrintPage: React.FC = () => {
  const { taskId } = useParams<UrlParams>();
  const id = Number(taskId);
  const [task, setTask] = useState<TaskCardRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || Number.isNaN(id)) return;
    const load = async () => {
      try {
        const data = await getTask(id);
        setTask(data);
      } catch (e: any) {
        console.error("Failed to load task for print", e);
        setError(e?.message || "Could not load task.");
      }
    };
    load();
  }, [id]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      window.print();
    }, 200);
    window.onafterprint = () => {
      try {
        window.close();
      } catch {
        // ignore if blocked
      }
    };
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "Inter, sans-serif", color: "#0f172a" }}>
      <h1 style={{ marginBottom: 6 }}>Task Summary</h1>
      {error && <p>{error}</p>}
      {!task && !error && <p>Loading task…</p>}
      {task && (
        <div style={{ display: "grid", gap: 12 }}>
          <div>
            <strong>Task</strong>: {task.task_code || task.id}
          </div>
          <div>
            <strong>Title</strong>: {task.title || "—"}
          </div>
          <div>
            <strong>Aircraft</strong>: {task.aircraft_serial_number || "—"}
          </div>
          <div>
            <strong>Status</strong>: {task.status || "—"}
          </div>
          <div>
            <strong>Description</strong>: {task.description || "—"}
          </div>
          <div>
            <strong>Planned</strong>:{" "}
            {task.planned_start ? new Date(task.planned_start).toLocaleString() : "—"} →{" "}
            {task.planned_end ? new Date(task.planned_end).toLocaleString() : "—"}
          </div>
        </div>
      )}
    </div>
  );
};

export default TaskPrintPage;

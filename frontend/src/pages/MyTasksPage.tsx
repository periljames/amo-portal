import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import QMSLayout from "../components/QMS/QMSLayout";
import { listMyTasks, updateTask, type TaskItem } from "../services/tasks";

const MyTasksPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode = "UNKNOWN", department = "quality" } = useParams();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    let active = true;
    setLoading(true);
    listMyTasks()
      .then((data) => {
        if (!active) return;
        setTasks(data);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err?.message || "Failed to load tasks.");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const rows = useMemo(() => {
    const dueWindow = searchParams.get("dueWindow");
    const now = new Date();
    return [...tasks]
      .filter((task) => {
        if (!dueWindow) return true;
        if (!task.due_at) return false;
        const due = new Date(task.due_at);
        if (dueWindow === "today") {
          return due.toDateString() === now.toDateString();
        }
        if (dueWindow === "week") {
          const diff = (due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
          return diff >= 0 && diff <= 7;
        }
        if (dueWindow === "month") {
          const diff = (due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
          return diff >= 0 && diff <= 30;
        }
        return true;
      })
      .sort((a, b) => {
        const aDue = a.due_at ? Date.parse(a.due_at) : Number.POSITIVE_INFINITY;
        const bDue = b.due_at ? Date.parse(b.due_at) : Number.POSITIVE_INFINITY;
        return aDue - bDue;
      });
  }, [tasks, searchParams]);

  const handleMarkDone = async (taskId: string) => {
    try {
      const updated = await updateTask(taskId, { status: "DONE" });
      setTasks((prev) => prev.map((task) => (task.id === updated.id ? updated : task)));
    } catch (err: any) {
      setError(err?.message || "Failed to update task.");
    }
  };

  const goToEntity = (task: TaskItem) => {
    if (!amoCode || !department) return;
    const base = `/maintenance/${amoCode}/${department}`;
    switch (task.entity_type) {
      case "qms_document":
      case "qms_document_distribution":
        navigate(`${base}/qms/documents`);
        return;
      case "qms_audit":
      case "qms_finding":
      case "qms_cap":
        navigate(`${base}/qms/audits`);
        return;
      case "qms_car":
        navigate(`${base}/qms/cars`);
        return;
      default:
        navigate(`${base}/qms`);
    }
  };

  return (
    <QMSLayout
      amoCode={amoCode}
      department={department}
      title="My Tasks"
      subtitle="Due-date driven tasks from QMS, training, and FRACAS workflows."
    >
      {loading && <p>Loading tasks…</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && !rows.length && <p>No tasks assigned right now.</p>}

      {!!rows.length && (
        <div className="qms-table-wrapper">
          <table className="qms-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Due</th>
                <th>Entity</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((task) => (
                <tr key={task.id}>
                  <td>
                    <strong>{task.title}</strong>
                    {task.description && <div className="table-subtext">{task.description}</div>}
                  </td>
                  <td>{task.status}</td>
                  <td>{task.due_at ? new Date(task.due_at).toLocaleString() : "—"}</td>
                  <td>
                    <div className="table-subtext">{task.entity_type || "—"}</div>
                    <div className="table-subtext">{task.entity_id || "—"}</div>
                  </td>
                  <td className="table-actions">
                    <button
                      type="button"
                      className="primary-btn"
                      onClick={() => handleMarkDone(task.id)}
                      disabled={task.status === "DONE" || task.status === "CANCELLED"}
                    >
                      Mark done
                    </button>
                    <button type="button" className="secondary-btn" onClick={() => goToEntity(task)}>
                      Open entity
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </QMSLayout>
  );
};

export default MyTasksPage;

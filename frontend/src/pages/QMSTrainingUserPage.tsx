import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import type { AdminUserRead } from "../services/adminUsers";
import { listAdminUsers } from "../services/adminUsers";
import { getContext } from "../services/auth";
import { getUserTrainingStatus } from "../services/training";
import type { TrainingStatusItem } from "../types/training";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_FILTERS = [
  { value: "ALL", label: "All statuses" },
  { value: "OVERDUE", label: "Overdue" },
  { value: "DUE_SOON", label: "Due soon" },
  { value: "OK", label: "Compliant" },
  { value: "NOT_DONE", label: "Not done" },
];

const QMSTrainingUserPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; userId?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const userId = params.userId;

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AdminUserRead | null>(null);
  const [items, setItems] = useState<TrainingStatusItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");

  const load = async () => {
    if (!userId) return;
    setState("loading");
    setError(null);
    try {
      const [users, status] = await Promise.all([
        listAdminUsers({ limit: 50 }),
        getUserTrainingStatus(userId),
      ]);
      setUser(users.find((u) => u.id === userId) || null);
      setItems(status);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load training profile.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const filteredItems = useMemo(() => {
    if (statusFilter === "ALL") return items;
    return items.filter((item) => item.status === statusFilter);
  }, [items, statusFilter]);

  const summary = useMemo(() => {
    return items.reduce(
      (acc, item) => {
        if (item.status === "OVERDUE") acc.overdue += 1;
        if (item.status === "DUE_SOON") acc.dueSoon += 1;
        if (item.status === "OK") acc.ok += 1;
        if (item.status === "NOT_DONE") acc.notDone += 1;
        return acc;
      },
      { overdue: 0, dueSoon: 0, ok: 0, notDone: 0 }
    );
  }, [items]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Training Profile"
      subtitle="Detailed training compliance for individual staff members."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh profile
        </button>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            {STATUS_FILTERS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back to matrix
        </button>
      </section>

      {state === "loading" && (
        <div className="card card--info">
          <p>Loading training profile…</p>
        </div>
      )}

      {state === "error" && (
        <div className="card card--error">
          <p>{error}</p>
          <button type="button" className="primary-chip-btn" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {state === "ready" && (
        <section className="qms-grid">
          <div className="qms-card">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">
                  {user?.full_name || "Training profile"}
                </h3>
                <p className="qms-card__subtitle">
                  {user?.position_title || "Quality staff"} · {user?.staff_code || "N/A"}
                </p>
              </div>
            </div>
            <div className="qms-split">
              <div>
                <span className="qms-pill qms-pill--danger">Overdue: {summary.overdue}</span>
                <p className="text-muted">Immediate remediation required.</p>
              </div>
              <div>
                <span className="qms-pill qms-pill--warning">Due soon: {summary.dueSoon}</span>
                <p className="text-muted">Schedule next available course.</p>
              </div>
              <div>
                <span className="qms-pill">Compliant: {summary.ok}</span>
                <p className="text-muted">In date and compliant.</p>
              </div>
              <div>
                <span className="qms-pill">Not done: {summary.notDone}</span>
                <p className="text-muted">Not yet completed by staff member.</p>
              </div>
            </div>
          </div>

          <div className="qms-card qms-card--wide">
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Status</th>
                    <th>Last completion</th>
                    <th>Due</th>
                    <th>Next event</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item) => (
                    <tr key={item.course_id}>
                      <td>
                        <strong>{item.course_name}</strong>
                        <div className="text-muted">{item.course_id}</div>
                      </td>
                      <td>
                        <span
                          className={
                            item.status === "OVERDUE"
                              ? "qms-pill qms-pill--danger"
                              : item.status === "DUE_SOON"
                              ? "qms-pill qms-pill--warning"
                              : "qms-pill"
                          }
                        >
                          {item.status.replace("_", " ")}
                        </span>
                      </td>
                      <td>{formatDate(item.last_completion_date)}</td>
                      <td>{formatDate(item.extended_due_date || item.valid_until)}</td>
                      <td>
                        {item.upcoming_event_date ? formatDate(item.upcoming_event_date) : "—"}
                      </td>
                    </tr>
                  ))}
                  {filteredItems.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-muted">
                        No training records match the selected status.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </QMSLayout>
  );
};

export default QMSTrainingUserPage;

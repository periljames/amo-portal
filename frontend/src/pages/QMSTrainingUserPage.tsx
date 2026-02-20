import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import type { AdminUserRead } from "../services/adminUsers";
import { listAdminUsers } from "../services/adminUsers";
import { getContext } from "../services/auth";
import { downloadTrainingUserEvidencePack, getUserTrainingStatus } from "../services/training";
import type { TrainingStatusItem } from "../types/training";
import "../styles/training.css";

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
  { value: "DEFERRED", label: "Deferred" },
  { value: "SCHEDULED_ONLY", label: "Scheduled" },
  { value: "OK", label: "Compliant" },
  { value: "NOT_DONE", label: "Not done" },
];

function statusLabel(status: string): string {
  switch (status) {
    case "OVERDUE":
      return "Overdue";
    case "DUE_SOON":
      return "Due soon";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled only";
    case "NOT_DONE":
      return "Not done";
    case "OK":
    default:
      return "OK";
  }
}

function statusPillClass(status: string): string {
  if (status === "OVERDUE") return "qms-pill qms-pill--danger";
  if (status === "DUE_SOON") return "qms-pill qms-pill--warning";
  if (status === "DEFERRED") return "qms-pill qms-pill--info";
  if (status === "SCHEDULED_ONLY") return "qms-pill qms-pill--info";
  return "qms-pill";
}

function dueLabel(item: TrainingStatusItem): string {
  const due = item.extended_due_date || item.valid_until;
  if (!due) return "—";
  if (item.extended_due_date && item.valid_until && item.extended_due_date !== item.valid_until) {
    return `Deferred to ${formatDate(item.extended_due_date)}`;
  }
  return formatDate(due);
}

function daysLabel(days: number | null): string {
  if (days == null) return "—";
  if (days < 0) return `${Math.abs(days)} days overdue`;
  if (days === 0) return "Due today";
  return `${days} days remaining`;
}

const QMSTrainingUserPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; userId?: string; staffId?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const userId = params.userId ?? params.staffId;

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AdminUserRead | null>(null);
  const [items, setItems] = useState<TrainingStatusItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [exporting, setExporting] = useState(false);

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

  const handleExport = async () => {
    if (!userId) return;
    setError(null);
    setExporting(true);
    try {
      const blob = await downloadTrainingUserEvidencePack(userId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `training_${userId}_evidence_pack.zip`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.message || "Failed to export training evidence pack.");
    } finally {
      setExporting(false);
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
        if (item.status === "DEFERRED") acc.deferred += 1;
        if (item.status === "SCHEDULED_ONLY") acc.scheduled += 1;
        if (item.status === "NOT_DONE") acc.notDone += 1;
        return acc;
      },
      { overdue: 0, dueSoon: 0, ok: 0, deferred: 0, scheduled: 0, notDone: 0 }
    );
  }, [items]);

  const compliance = useMemo(() => {
    const total = items.length;
    if (total === 0) return 0;
    return Math.round(((summary.ok || 0) / total) * 100);
  }, [items.length, summary.ok]);

  const nextDue = useMemo(() => {
    const withDays = items
      .filter((item) => typeof item.days_until_due === "number")
      .slice()
      .sort((a, b) => (a.days_until_due ?? 0) - (b.days_until_due ?? 0));
    return withDays[0] || null;
  }, [items]);

  const nextEvent = useMemo(() => {
    const upcoming = items
      .filter((item) => item.upcoming_event_date)
      .slice()
      .sort(
        (a, b) =>
          new Date(a.upcoming_event_date as string).getTime() -
          new Date(b.upcoming_event_date as string).getTime()
      );
    return upcoming[0] || null;
  }, [items]);

  const actionItems = useMemo(() => {
    return items
      .filter((item) => ["OVERDUE", "DUE_SOON", "NOT_DONE"].includes(item.status))
      .slice()
      .sort((a, b) => (a.days_until_due ?? 0) - (b.days_until_due ?? 0))
      .slice(0, 6);
  }, [items]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Training Profile"
      subtitle="Detailed training compliance for individual staff members."
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="primary-chip-btn" onClick={load}>
            Refresh profile
          </button>
          <button
            type="button"
            className="secondary-chip-btn"
            onClick={handleExport}
            disabled={exporting || !userId}
          >
            {exporting ? "Exporting…" : "Export evidence pack"}
          </button>
        </div>
      }
    >
      <div className="training-module training-module--qms">
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
          <div className="qms-card qms-card--hero">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">
                  {user?.full_name || "Training profile"}
                </h3>
                <p className="qms-card__subtitle">
                  {user?.position_title || "Quality staff"} · {user?.staff_code || "N/A"}
                </p>
              </div>
              <span className="qms-pill qms-pill--info">Compliance {compliance}%</span>
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
                <span className="qms-pill qms-pill--info">Deferred: {summary.deferred}</span>
                <p className="text-muted">Monitor approved extensions.</p>
              </div>
              <div>
                <span className="qms-pill qms-pill--info">Scheduled: {summary.scheduled}</span>
                <p className="text-muted">Upcoming course already planned.</p>
              </div>
              <div>
                <span className="qms-pill">Not done: {summary.notDone}</span>
                <p className="text-muted">Not yet completed by staff member.</p>
              </div>
            </div>
          </div>

          <div className="qms-card qms-card--attention">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Priority actions</h3>
                <p className="qms-card__subtitle">
                  Next due items and overdue courses for this staff member.
                </p>
              </div>
            </div>
            {actionItems.length > 0 ? (
              <div className="qms-list">
                {actionItems.map((item) => (
                  <div key={item.course_id} className="qms-list__item">
                    <div>
                      <strong>{item.course_name}</strong>
                      <span className="qms-list__meta">{daysLabel(item.days_until_due)}</span>
                    </div>
                    <span className={statusPillClass(item.status)}>{statusLabel(item.status)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted">No urgent training items for this staff member.</p>
            )}
          </div>

          <div className="qms-card">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Next milestones</h3>
                <p className="qms-card__subtitle">Upcoming due dates and scheduled sessions.</p>
              </div>
            </div>
            <div className="qms-list">
              <div className="qms-list__item">
                <div>
                  <strong>Next due</strong>
                  <span className="qms-list__meta">
                    {nextDue ? `${nextDue.course_name} · ${dueLabel(nextDue)}` : "No due dates available"}
                  </span>
                </div>
                <span className="qms-pill">
                  {nextDue ? daysLabel(nextDue.days_until_due) : "—"}
                </span>
              </div>
              <div className="qms-list__item">
                <div>
                  <strong>Next event</strong>
                  <span className="qms-list__meta">
                    {nextEvent
                      ? `${nextEvent.course_name} · ${formatDate(nextEvent.upcoming_event_date)}`
                      : "No upcoming events scheduled"}
                  </span>
                </div>
                <span className="qms-pill">Session</span>
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
                    <th>Time left</th>
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
                        <span className={statusPillClass(item.status)}>
                          {statusLabel(item.status)}
                        </span>
                      </td>
                      <td>{formatDate(item.last_completion_date)}</td>
                      <td>{dueLabel(item)}</td>
                      <td>{daysLabel(item.days_until_due)}</td>
                      <td>
                        {item.upcoming_event_date ? formatDate(item.upcoming_event_date) : "—"}
                      </td>
                    </tr>
                  ))}
                  {filteredItems.length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-muted">
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
      </div>
    </QMSLayout>
  );
};

export default QMSTrainingUserPage;

import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import {
  type CAROut,
  type CARPriority,
  type CARProgram,
  type CARStatus,
  qmsCreateCar,
  qmsListCars,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

const PROGRAM_OPTIONS: Array<{ value: CARProgram; label: string }> = [
  { value: "QUALITY", label: "Quality" },
  { value: "RELIABILITY", label: "Reliability" },
];

const PRIORITY_LABELS: Record<CARPriority, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
};

const STATUS_COLORS: Record<CARStatus, string> = {
  DRAFT: "badge--neutral",
  OPEN: "badge--info",
  IN_PROGRESS: "badge--warning",
  PENDING_VERIFICATION: "badge--warning",
  CLOSED: "badge--success",
  ESCALATED: "badge--danger",
  CANCELLED: "badge--neutral",
};

const QualityCarsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [programFilter, setProgramFilter] = useState<CARProgram>("QUALITY");

  const [form, setForm] = useState<{
    title: string;
    summary: string;
    program: CARProgram;
    priority: CARPriority;
  }>({
    title: "",
    summary: "",
    program: "QUALITY",
    priority: "MEDIUM",
  });

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const next = await qmsListCars({ program: programFilter });
      setCars(next);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load CAR register.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programFilter]);

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!form.title.trim() || !form.summary.trim()) return;
    try {
      await qmsCreateCar({
        program: form.program,
        title: form.title.trim(),
        summary: form.summary.trim(),
        priority: form.priority,
      });
      setForm({ ...form, title: "", summary: "" });
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to create CAR");
    }
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">
          Corrective Action Requests · {amoDisplay}
        </h1>
        <p className="page-header__subtitle">
          Register for Quality & Reliability programmes with escalation tracking.
        </p>
      </header>

      <section className="page-section" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button
          type="button"
          className="secondary-chip-btn"
          onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms`)}
        >
          Back to QMS overview
        </button>
        <select
          value={programFilter}
          onChange={(e) => setProgramFilter(e.target.value as CARProgram)}
          className="form-control"
          style={{ width: 220 }}
        >
          {PROGRAM_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} programme
            </option>
          ))}
        </select>
      </section>

      {state === "error" && (
        <div className="card card--error">
          <p>{error}</p>
          <button type="button" className="primary-chip-btn" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <section className="page-section">
        <div className="card">
          <div className="card-header">
            <h2>Log a new CAR</h2>
            <p className="text-muted">
              Assign programme, priority, and a concise summary. Numbers are auto-generated per programme and year.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="form-grid">
            <label className="form-control">
              <span>Programme</span>
              <select
                value={form.program}
                onChange={(e) =>
                  setForm((f) => ({ ...f, program: e.target.value as CARProgram }))
                }
              >
                {PROGRAM_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-control">
              <span>Priority</span>
              <select
                value={form.priority}
                onChange={(e) =>
                  setForm((f) => ({ ...f, priority: e.target.value as CARPriority }))
                }
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Title</span>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="Short, action-oriented title"
                required
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Summary</span>
              <textarea
                value={form.summary}
                onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
                placeholder="Detail the finding, containment, and requested corrective actions."
                rows={4}
                required
              />
            </label>

            <div>
              <button type="submit" className="primary-chip-btn">
                Create CAR
              </button>
            </div>
          </form>
        </div>
      </section>

      <section className="page-section">
        <div className="card">
          <div className="card-header">
            <h2>Register</h2>
            <p className="text-muted">Auto-numbered entries with status, priority, and ownership.</p>
          </div>

          {state === "loading" && <p>Loading register…</p>}

          {state === "ready" && (
            <div className="table-responsive">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>CAR #</th>
                    <th>Title</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Due</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {cars.map((car) => (
                    <tr key={car.id}>
                      <td>{car.car_number}</td>
                      <td>{car.title}</td>
                      <td>
                        <span className="badge badge--neutral">
                          {PRIORITY_LABELS[car.priority]}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${STATUS_COLORS[car.status] || "badge--neutral"}`}>
                          {car.status}
                        </span>
                      </td>
                      <td>{car.due_date || "—"}</td>
                      <td>{new Date(car.updated_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                  {cars.length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-muted">
                        No CARs logged for this programme yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default QualityCarsPage;

// src/pages/DashboardPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext, getCachedUser } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import {
  type AircraftDocument,
  type AircraftUsageSummary,
  getAircraftUsageSummary,
  listAircraft,
  listDocumentAlerts,
} from "../services/fleet";
import { DASHBOARD_WIDGETS, getWidgetStorageKey } from "../utils/dashboardWidgets";

type DepartmentId =
  | "planning"
  | "production"
  | "quality"
  | "safety"
  | "stores"
  | "engineering"
  | "workshops"
  | "admin";

const DEPT_LABEL: Record<string, string> = {
  planning: "Planning",
  production: "Production",
  quality: "Quality & Compliance",
  safety: "Safety Management",
  stores: "Procurement & Stores",
  engineering: "Engineering",
  workshops: "Workshops",
  admin: "System Admin",
};

const niceLabel = (dept: string) => DEPT_LABEL[dept] || dept;

type Holiday = {
  date: string;
  localName: string;
  name: string;
};

type LeaveEntry = {
  id: string;
  date: string;
  reason: string;
};

type ThrottleStore = {
  amo: Record<
    string,
    {
      limit: number;
      perUser: Record<string, number>;
    }
  >;
  cacheHolidays: boolean;
};

const DEFAULT_THROTTLE: ThrottleStore = {
  amo: {},
  cacheHolidays: true,
};

const THROTTLE_STORAGE_KEY = "amo_calendar_throttle_settings";

function isAdminUser(u: any): boolean {
  if (!u) return false;
  return (
    !!u.is_superuser ||
    !!u.is_amo_admin ||
    u.role === "SUPERUSER" ||
    u.role === "AMO_ADMIN"
  );
}

function isDepartmentId(v: string): v is DepartmentId {
  return Object.prototype.hasOwnProperty.call(DEPT_LABEL, v);
}

function getLocalStorageJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function setLocalStorageJson<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function getThrottleStore(): ThrottleStore {
  if (typeof window === "undefined") return DEFAULT_THROTTLE;
  try {
    const raw = window.localStorage.getItem(THROTTLE_STORAGE_KEY);
    if (!raw) return DEFAULT_THROTTLE;
    return { ...DEFAULT_THROTTLE, ...(JSON.parse(raw) as ThrottleStore) };
  } catch {
    return DEFAULT_THROTTLE;
  }
}

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function buildMonthDays(month: Date): Date[] {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const days: Date[] = [];
  const startWeekday = start.getDay();
  for (let i = 0; i < startWeekday; i += 1) {
    const filler = new Date(start);
    filler.setDate(start.getDate() - (startWeekday - i));
    days.push(filler);
  }
  for (let d = 1; d <= end.getDate(); d += 1) {
    days.push(new Date(month.getFullYear(), month.getMonth(), d));
  }
  const remaining = 42 - days.length;
  for (let i = 1; i <= remaining; i += 1) {
    days.push(new Date(month.getFullYear(), month.getMonth() + 1, i));
  }
  return days;
}

const DashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();

  const ctx = getContext();

  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";

  const currentUser = getCachedUser();
  const isAdmin = isAdminUser(currentUser);
  const [docAlerts, setDocAlerts] = useState<AircraftDocument[] | null>(null);
  const [docAlertsError, setDocAlertsError] = useState<string | null>(null);
  const [docAlertsLoading, setDocAlertsLoading] = useState(false);
  const [fleetCount, setFleetCount] = useState(0);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [dueSummaries, setDueSummaries] = useState<AircraftUsageSummary[]>([]);
  const [dueLoading, setDueLoading] = useState(false);
  const [dueError, setDueError] = useState<string | null>(null);
  const [holidayCountry, setHolidayCountry] = useState(() =>
    getLocalStorageJson<string>("amo_holiday_country", "KE")
  );
  const [holidayYear, setHolidayYear] = useState(() => new Date().getFullYear());
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holidayLoading, setHolidayLoading] = useState(false);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [calendarMonth, setCalendarMonth] = useState<Date>(() => new Date());
  const [leaveEntries, setLeaveEntries] = useState<LeaveEntry[]>(() =>
    getLocalStorageJson<LeaveEntry[]>("amo_leave_entries", [])
  );
  const [leaveForm, setLeaveForm] = useState({ date: "", reason: "" });
  const [calendarConnections, setCalendarConnections] = useState(() =>
    getLocalStorageJson<{ google: boolean; outlook: boolean }>(
      "amo_calendar_connections",
      { google: false, outlook: false }
    )
  );
  const [throttleStore, setThrottleStore] = useState<ThrottleStore>(() =>
    getThrottleStore()
  );

  // For normal users, this MUST be their assigned department (server-driven context).
  // We also fall back to cached user.department_id if you ever store codes there.
  const assignedDept = useMemo(() => {
    const ctxDept = (ctx.department || "").trim();
    if (ctxDept) return ctxDept;

    const userDept = (currentUser?.department_id || "").trim();
    if (userDept) return userDept;

    return null;
  }, [ctx.department, currentUser?.department_id]);

  const requestedDeptRaw = (params.department || "").trim();
  const requestedDept: string | null = requestedDeptRaw ? requestedDeptRaw : null;

  // ✅ Guard: normal users can ONLY access their assigned department.
  useEffect(() => {
    if (!currentUser) return;
    if (isAdmin) return;

    if (!assignedDept) {
      // Misconfigured account/session; bounce to AMO login
      navigate(`/maintenance/${amoSlug}/login`, { replace: true });
      return;
    }

    // Non-admins must never land in "admin"
    if (assignedDept === "admin") {
      navigate(`/maintenance/${amoSlug}/login`, { replace: true });
      return;
    }

    // If URL dept differs, hard-correct it (prevents cross-department browsing)
    if (requestedDept && requestedDept !== assignedDept) {
      navigate(`/maintenance/${amoSlug}/${assignedDept}`, { replace: true });
    }

    // If URL dept is missing, send them to assigned dept
    if (!requestedDept) {
      navigate(`/maintenance/${amoSlug}/${assignedDept}`, { replace: true });
    }
  }, [currentUser, isAdmin, assignedDept, requestedDept, amoSlug, navigate]);

  // While we are correcting routes for non-admins, render nothing to avoid flicker.
  if (
    currentUser &&
    !isAdmin &&
    assignedDept &&
    (requestedDept !== assignedDept || !requestedDept)
  ) {
    return null;
  }

  // Effective department for rendering
  const department: DepartmentId = useMemo(() => {
    if (isAdmin) {
      const d = requestedDept || ctx.department || "planning";
      return (isDepartmentId(d) ? d : "planning") as DepartmentId;
    }

    const d = assignedDept || "planning";
    return (isDepartmentId(d) ? d : "planning") as DepartmentId;
  }, [isAdmin, requestedDept, ctx.department, assignedDept]);

  const amoDisplay =
    amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const isCRSDept = department === "planning" || department === "production";
  const isSystemAdminDept = department === "admin";
  const isQualityDept = department === "quality";
  const shouldShowComplianceAlerts =
    department === "planning" ||
    department === "production" ||
    department === "quality";

  const canManageUsers =
    !!currentUser &&
    (currentUser.is_superuser ||
      currentUser.is_amo_admin ||
      currentUser.role === "SUPERUSER" ||
      currentUser.role === "AMO_ADMIN");

  const handleNewCrs = () => {
    navigate(`/maintenance/${amoSlug}/${department}/crs/new`);
  };

  const handleCreateUser = () => {
    navigate(`/maintenance/${amoSlug}/admin/users/new`);
  };

  const handleOpenQms = () => {
    navigate(`/maintenance/${amoSlug}/${department}/qms`);
  };

  const renderMetric = (label: string, value: number, max = 100) => {
    const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
    return (
      <div className="metric-card">
        <div className="metric-card__value">{value}</div>
        <div className="metric-card__label">{label}</div>
        <div className="metric-card__bar">
          <span style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  const renderDueStatus = (summary: AircraftUsageSummary) => {
    if (summary.next_due_date) return `Due ${summary.next_due_date}`;
    if (summary.next_due_hours !== null) return `Due ${summary.next_due_hours}h`;
    if (summary.next_due_cycles !== null)
      return `Due ${summary.next_due_cycles} cycles`;
    return "No due data";
  };

  const fetchHolidays = async (countryCode: string, year: number) => {
    if (!throttleStore.cacheHolidays) {
      setHolidays([]);
    }
    setHolidayLoading(true);
    setHolidayError(null);
    try {
      const res = await fetch(
        `https://date.nager.at/api/v3/PublicHolidays/${year}/${countryCode}`
      );
      if (!res.ok) {
        throw new Error(`Holiday feed error ${res.status}`);
      }
      const data = (await res.json()) as Holiday[];
      setHolidays(data);
      setLocalStorageJson("amo_holidays_cache", data);
    } catch (e: any) {
      setHolidayError(e?.message || "Failed to load public holidays.");
      if (throttleStore.cacheHolidays) {
        const cached = getLocalStorageJson<Holiday[]>("amo_holidays_cache", []);
        if (cached.length) setHolidays(cached);
      }
    } finally {
      setHolidayLoading(false);
    }
  };

  const handleConnectCalendar = (provider: "google" | "outlook") => {
    const envKey =
      provider === "google"
        ? (import.meta as any).env?.VITE_CALENDAR_GOOGLE_OAUTH_URL
        : (import.meta as any).env?.VITE_CALENDAR_OUTLOOK_OAUTH_URL;
    if (envKey) {
      window.open(envKey, "_blank", "width=720,height=720");
    }
    setCalendarConnections((prev) => {
      const next = { ...prev, [provider]: true };
      setLocalStorageJson("amo_calendar_connections", next);
      return next;
    });
  };

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === THROTTLE_STORAGE_KEY) {
        setThrottleStore(getThrottleStore());
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const handleDisconnectCalendar = (provider: "google" | "outlook") => {
    setCalendarConnections((prev) => {
      const next = { ...prev, [provider]: false };
      setLocalStorageJson("amo_calendar_connections", next);
      return next;
    });
  };

  const handleAddLeave = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!leaveForm.date) return;
    const entry: LeaveEntry = {
      id: `${leaveForm.date}-${Date.now()}`,
      date: leaveForm.date,
      reason: leaveForm.reason.trim() || "Leave",
    };
    const next = [entry, ...leaveEntries];
    setLeaveEntries(next);
    setLocalStorageJson("amo_leave_entries", next);
    setLeaveForm({ date: "", reason: "" });
  };

  const handleRemoveLeave = (id: string) => {
    const next = leaveEntries.filter((entry) => entry.id !== id);
    setLeaveEntries(next);
    setLocalStorageJson("amo_leave_entries", next);
  };

  useEffect(() => {
    setLocalStorageJson("amo_holiday_country", holidayCountry);
  }, [holidayCountry]);

  useEffect(() => {
    fetchHolidays(holidayCountry, holidayYear);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holidayCountry, holidayYear, throttleStore.cacheHolidays]);

  useEffect(() => {
    if (!shouldShowComplianceAlerts) {
      setDocAlerts(null);
      return;
    }

    setDocAlertsLoading(true);
    setDocAlertsError(null);
    listDocumentAlerts({ due_within_days: 45 })
      .then((alerts) => setDocAlerts(alerts))
      .catch((err) => {
        setDocAlertsError(err?.message || "Could not load document alerts.");
      })
      .finally(() => setDocAlertsLoading(false));
  }, [department, shouldShowComplianceAlerts]);

  useEffect(() => {
    setFleetLoading(true);
    setFleetError(null);
    listAircraft({ is_active: true })
      .then((data) => setFleetCount(data.length))
      .catch((err) => {
        setFleetError(err?.message || "Could not load fleet count.");
        setFleetCount(0);
      })
      .finally(() => setFleetLoading(false));
  }, []);

  useEffect(() => {
    if (department !== "planning") return;
    setDueLoading(true);
    setDueError(null);
    listAircraft({ is_active: true })
      .then((aircraft) =>
        Promise.all(
          aircraft.slice(0, 6).map((item) => getAircraftUsageSummary(item.serial_number))
        )
      )
      .then((summaries) => setDueSummaries(summaries))
      .catch((err) => {
        setDueError(err?.message || "Could not load due schedules.");
        setDueSummaries([]);
      })
      .finally(() => setDueLoading(false));
  }, [department]);

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">
          {niceLabel(department)} · {amoDisplay}
        </h1>
        <p className="page-header__subtitle">
          Welcome to the {niceLabel(department).toLowerCase()} dashboard for AMO{" "}
          <strong>{amoDisplay}</strong>.
        </p>
      </header>

      {isCRSDept && (
        <section className="page-section">
          <h2 className="page-section__title">Certificates of Release to Service</h2>
          <p className="page-section__body">
            Create, track, and download CRS forms for completed maintenance.
          </p>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={handleNewCrs}
          >
            + New CRS
          </button>
        </section>
      )}

      {!isSystemAdminDept && (
        <section className="page-section">
          <h2 className="page-section__title">Key metrics</h2>
          {fleetError && <p className="error-text">{fleetError}</p>}
          {fleetLoading && <p className="text-muted">Loading metrics…</p>}

          {!fleetLoading && (
            <div className="metric-grid">
              {department === "planning" && (
                <>
                  {renderMetric("Fleet size", fleetCount, Math.max(1, fleetCount))}
                  {renderMetric("Available slots", 0)}
                  {renderMetric("Upcoming checks", 0)}
                </>
              )}
              {department === "production" && (
                <>
                  {renderMetric("Active work orders", 0)}
                  {renderMetric("CRS issued", 0)}
                  {renderMetric("Delays", 0)}
                </>
              )}
              {department === "quality" && (
                <>
                  {renderMetric("Open findings", 0)}
                  {renderMetric("Open CARs", 0)}
                  {renderMetric("Audits scheduled", 0)}
                </>
              )}
              {department === "safety" && (
                <>
                  {renderMetric("Hazard reports", 0)}
                  {renderMetric("Mitigations", 0)}
                  {renderMetric("Safety actions", 0)}
                </>
              )}
              {department === "stores" && (
                <>
                  {renderMetric("Stockouts", 0)}
                  {renderMetric("Reorder lines", 0)}
                  {renderMetric("Inbound shipments", 0)}
                </>
              )}
              {department === "engineering" && (
                <>
                  {renderMetric("Work packages", 0)}
                  {renderMetric("Tech logs", 0)}
                  {renderMetric("Deferred items", 0)}
                </>
              )}
              {department === "workshops" && (
                <>
                  {renderMetric("Shop orders", 0)}
                  {renderMetric("Components in work", 0)}
                  {renderMetric("Turnaround delays", 0)}
                </>
              )}
            </div>
          )}
        </section>
      )}


      {department === "planning" && (
        <section className="page-section">
          <h2 className="page-section__title">Upcoming maintenance due</h2>
          {dueError && <p className="error-text">{dueError}</p>}
          {dueLoading && <p className="text-muted">Loading due schedules…</p>}
          {!dueLoading && (
            <div className="table-responsive">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>Aircraft</th>
                    <th>Next task</th>
                    <th>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {dueSummaries.map((summary) => (
                    <tr key={summary.aircraft_serial_number}>
                      <td>{summary.aircraft_serial_number}</td>
                      <td>{summary.next_due_task_code || "—"}</td>
                      <td>{renderDueStatus(summary)}</td>
                    </tr>
                  ))}
                  {dueSummaries.length === 0 && (
                    <tr>
                      <td colSpan={3} className="text-muted">
                        No due data yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {department === "planning" && (
        <section className="page-section">
          <h2 className="page-section__title">Planning calendar & leave management</h2>
          <p className="page-section__body">
            Sync personal calendars, review public holidays, and mark leave days
            before assigning maintenance slots.
          </p>

          <div className="page-section__grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Calendar connections</h3>
              <p className="text-muted">
                Connect personal calendars to surface planned time off and reduce
                scheduling conflicts.
              </p>
              <div className="page-section__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    calendarConnections.google
                      ? handleDisconnectCalendar("google")
                      : handleConnectCalendar("google")
                  }
                >
                  {calendarConnections.google ? "Disconnect Google" : "Connect Google"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    calendarConnections.outlook
                      ? handleDisconnectCalendar("outlook")
                      : handleConnectCalendar("outlook")
                  }
                >
                  {calendarConnections.outlook ? "Disconnect Outlook" : "Connect Outlook"}
                </button>
              </div>
              {currentUser?.amo_id && (
                <p className="text-muted" style={{ marginTop: 12 }}>
                  Throttle budget:{" "}
                  <strong>
                    {throttleStore.amo[currentUser.amo_id]?.perUser[currentUser.id] ??
                      throttleStore.amo[currentUser.amo_id]?.limit ??
                      70}
                    %
                  </strong>
                  . Adjust in Admin → Usage Throttling.
                </p>
              )}
              <p className="text-muted" style={{ marginTop: 12 }}>
                OAuth URLs are configured by
                <code style={{ marginLeft: 4 }}>VITE_CALENDAR_GOOGLE_OAUTH_URL</code>{" "}
                and <code>VITE_CALENDAR_OUTLOOK_OAUTH_URL</code>.
              </p>
            </div>

            <div className="card">
              <h3 style={{ marginTop: 0 }}>Public holidays</h3>
              <div className="form-row" style={{ gap: 8 }}>
                <label className="form-control">
                  <span>Country code</span>
                  <input
                    value={holidayCountry}
                    onChange={(e) => setHolidayCountry(e.target.value.toUpperCase())}
                    maxLength={2}
                    placeholder="KE"
                  />
                </label>
                <label className="form-control">
                  <span>Year</span>
                  <input
                    type="number"
                    value={holidayYear}
                    onChange={(e) => setHolidayYear(Number(e.target.value))}
                  />
                </label>
              </div>
              {holidayLoading && <p className="text-muted">Loading holidays…</p>}
              {holidayError && <p className="error-text">{holidayError}</p>}
              {!holidayLoading && holidays.length > 0 && (
                <ul style={{ margin: "8px 0 0", paddingLeft: 16 }}>
                  {holidays.slice(0, 6).map((holiday) => (
                    <li key={`${holiday.date}-${holiday.name}`}>
                      {formatDate(holiday.date)} · {holiday.localName}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginTop: 0 }}>Leave planner</h3>
              <form onSubmit={handleAddLeave} className="form-row" style={{ gap: 8 }}>
                <label className="form-control">
                  <span>Date</span>
                  <input
                    type="date"
                    value={leaveForm.date}
                    onChange={(e) =>
                      setLeaveForm((prev) => ({ ...prev, date: e.target.value }))
                    }
                    required
                  />
                </label>
                <label className="form-control">
                  <span>Reason</span>
                  <input
                    value={leaveForm.reason}
                    onChange={(e) =>
                      setLeaveForm((prev) => ({ ...prev, reason: e.target.value }))
                    }
                    placeholder="Annual leave"
                  />
                </label>
                <div style={{ alignSelf: "end" }}>
                  <button type="submit" className="btn btn-primary">
                    Add leave
                  </button>
                </div>
              </form>
              {leaveEntries.length === 0 ? (
                <p className="text-muted">No leave days scheduled yet.</p>
              ) : (
                <ul style={{ margin: "8px 0 0", paddingLeft: 16 }}>
                  {leaveEntries.slice(0, 6).map((entry) => (
                    <li key={entry.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <span>
                        {formatDate(entry.date)} · {entry.reason}
                      </span>
                      <button
                        type="button"
                        className="secondary-chip-btn"
                        onClick={() => handleRemoveLeave(entry.id)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-header">
              <h3>Month view</h3>
              <div className="page-section__actions">
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() =>
                    setCalendarMonth(
                      new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() - 1, 1)
                    )
                  }
                >
                  ‹ Prev
                </button>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() =>
                    setCalendarMonth(
                      new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 1)
                    )
                  }
                >
                  Next ›
                </button>
              </div>
            </div>

            <div
              className="calendar-grid"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
                gap: 6,
                fontSize: 12,
              }}
            >
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
                <div key={label} className="text-muted">
                  {label}
                </div>
              ))}
              {buildMonthDays(calendarMonth).map((day) => {
                const iso = day.toISOString().slice(0, 10);
                const isCurrentMonth = day.getMonth() === calendarMonth.getMonth();
                const leave = leaveEntries.find((entry) => entry.date === iso);
                const holiday = holidays.find((entry) => entry.date === iso);
                return (
                  <div
                    key={iso}
                    style={{
                      padding: 8,
                      borderRadius: 10,
                      border: "1px solid rgba(148, 163, 184, 0.2)",
                      background: isCurrentMonth ? "var(--surface)" : "var(--surface-soft)",
                      opacity: isCurrentMonth ? 1 : 0.5,
                      minHeight: 60,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{day.getDate()}</div>
                    {holiday && (
                      <div className="badge badge--warning" style={{ marginTop: 4 }}>
                        {holiday.localName}
                      </div>
                    )}
                    {leave && (
                      <div className="badge badge--info" style={{ marginTop: 4 }}>
                        {leave.reason}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {department === "planning" && (
        <section className="page-section">
          <h2 className="page-section__title">Fleet & inventory readiness</h2>
          <p className="page-section__body">
            Track fleet utilization, third-party aircraft intake, and inventory
            posture to support MRO planning.
          </p>
          <div
            className="page-section__grid"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}
          >
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Fleet utilisation</h3>
              <p className="text-muted">
                Monitor aircraft availability, utilization hours, and upcoming
                checks to protect slot planning.
              </p>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={() => navigate(`/maintenance/${amoSlug}/${department}/aircraft-import`)}
              >
                Configure fleet inputs
              </button>
              <button
                type="button"
                className="primary-chip-btn"
                style={{ marginLeft: 8 }}
                onClick={() => navigate(`/maintenance/${amoSlug}/${department}/component-import`)}
              >
                Import components
              </button>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Inventory health</h3>
              <p className="text-muted">
                Ensure rotable and consumable inventory lines are aligned to the
                upcoming maintenance plan.
              </p>
              <p className="text-muted" style={{ marginTop: 8 }}>
                Hook into procurement and stores data feeds to activate this panel.
              </p>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Third-party aircraft</h3>
              <p className="text-muted">
                Capture AOG or third-party maintenance arrivals and reserve bay
                capacity.
              </p>
              <p className="text-muted" style={{ marginTop: 8 }}>
                Add third-party aircraft details once intake workflows are enabled.
              </p>
            </div>
          </div>
        </section>
      )}

      {isSystemAdminDept && (
        <section className="page-section">
          <h2 className="page-section__title">System Administration</h2>
          <p className="page-section__body">
            User account management for this AMO. Access is restricted to AMO
            Administrators and platform Superusers in line with AMO and
            regulatory requirements.
          </p>

          {canManageUsers ? (
            <div className="page-section__actions">
              <button
                type="button"
                className="primary-chip-btn"
                onClick={handleCreateUser}
              >
                + Create new user
              </button>
            </div>
          ) : (
            <p className="page-section__body">
              You are signed in to the System Admin dashboard but do not have
              the required system privileges to manage user accounts. Please
              contact Quality or the AMO System Administrator.
            </p>
          )}
        </section>
      )}

      {shouldShowComplianceAlerts && (
        <section className="page-section">
          <h2 className="page-section__title">Airworthiness document alerts</h2>
          <p className="page-section__body">
            Planning, Production, and Quality are notified when documents like C
            of A, ARC, or radio licenses are due or missing. Work on an affected
            aircraft is blocked until updated evidence is uploaded (Quality can
            override with a recorded reason).
          </p>

          {docAlertsLoading && (
            <p className="page-section__body">Loading document alerts…</p>
          )}
          {docAlertsError && (
            <p className="page-section__body error-text">{docAlertsError}</p>
          )}
          {!docAlertsLoading && !docAlertsError && (
            <>
              {(docAlerts?.length || 0) === 0 ? (
                <p className="page-section__body">
                  No document alerts found in the next 45 days.
                </p>
              ) : (
                <ul className="card-list">
                  {docAlerts?.map((alert) => (
                    <li className="card card--border" key={alert.id}>
                      <h3 className="card__title">
                        {alert.document_type.replace(/_/g, " ")} ·{" "}
                        {alert.aircraft_serial_number}
                      </h3>
                      <p className="card__subtitle">
                        Authority: {alert.authority} · Status: {alert.status}
                      </p>
                      <p className="card__body">
                        {alert.expires_on
                          ? `Expires on ${alert.expires_on}${
                              alert.days_to_expiry !== null
                                ? ` (${alert.days_to_expiry} days)`
                                : ""
                            }`
                          : "Expiry not recorded"}
                        {alert.missing_evidence && " · Evidence missing"}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}

      {isQualityDept && (
        <section className="page-section">
          <h2 className="page-section__title">Quality Management System</h2>
          <p className="page-section__body">
            Review QMS documents, audits, change requests, and distribution
            activity for {niceLabel(department)}.
          </p>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={handleOpenQms}
          >
            Open QMS overview
          </button>
        </section>
      )}

      {!isSystemAdminDept && currentUser && (
        <section className="page-section">
          <h2 className="page-section__title">Your widgets</h2>
          {(() => {
            const storageKey = getWidgetStorageKey(amoSlug, currentUser.id, department);
            let selected: string[] = [];
            try {
              const raw = localStorage.getItem(storageKey);
              selected = raw ? (JSON.parse(raw) as string[]) : [];
            } catch {
              selected = [];
            }
            const widgets = DASHBOARD_WIDGETS.filter(
              (widget) =>
                selected.includes(widget.id) &&
                widget.departments.includes(department as any)
            );
            if (widgets.length === 0) {
              return (
                <p className="text-muted">
                  No widgets added yet. Use Dashboard widgets in your profile menu.
                </p>
              );
            }
            return (
              <div className="metric-grid">
                {widgets.map((widget) => (
                  <div key={widget.id} className="metric-card">
                    <div className="metric-card__value">0</div>
                    <div className="metric-card__label">{widget.label}</div>
                    <div className="text-muted">{widget.description}</div>
                    <div className="metric-card__bar">
                      <span style={{ width: "0%" }} />
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </section>
      )}

      {!isCRSDept && !isSystemAdminDept && (
        <section className="page-section">
          <p className="page-section__body">
            Department widgets for {niceLabel(department)} will appear here.
          </p>
        </section>
      )}
    </DepartmentLayout>
  );
};

export default DashboardPage;

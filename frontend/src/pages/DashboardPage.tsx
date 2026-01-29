// src/pages/DashboardPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext, getCachedUser } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import {
  listDocumentAlerts,
  type AircraftDocument,
} from "../services/fleet";
import {
  qmsGetAuditorStats,
  qmsListNotifications,
  qmsMarkNotificationRead,
  type AuditorStatsOut,
  type QMSNotificationOut,
} from "../services/qms";
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
  date: string; // YYYY-MM-DD
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
const DOC_ALERTS_BANNER_STORAGE_KEY = "amo_doc_alerts_banner_dismissed";

type CalendarProvider = "google" | "outlook";
type CalendarConnections = Record<CalendarProvider, boolean>;

type DueSummary = {
  aircraft_serial_number: string;
  next_due_task_code?: string | null;
  due_date?: string | null; // ISO date
  due_status?: string | null;
  days_to_due?: number | null;
};

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

function safeEnv(key: string): string {
  try {
    const v = (import.meta as any)?.env?.[key];
    return typeof v === "string" ? v : "";
  } catch {
    return "";
  }
}

function getLeaveStorageKey(amoSlug: string, userId: string): string {
  return `amo_leave_${amoSlug}_${userId}`;
}

function getConnectionsStorageKey(amoSlug: string, userId: string): string {
  return `amo_calendar_connections_${amoSlug}_${userId}`;
}

function renderDueStatus(summary: DueSummary): React.ReactElement {
  if (!summary.due_date) return <span className="text-muted">—</span>;
  const label = formatDate(summary.due_date);
  const days =
    typeof summary.days_to_due === "number" ? ` (${summary.days_to_due}d)` : "";
  const status = (summary.due_status || "").toUpperCase();
  const cls =
    status === "OVERDUE"
      ? "badge badge--danger"
      : status === "DUE_SOON"
      ? "badge badge--warning"
      : "badge badge--neutral";
  return <span className={cls}>{label + days}</span>;
}

function makeId(prefix = "ID"): string {
  // Not cryptographic; stable enough for local-only UI ids
  return `${prefix}-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
}

async function fetchPublicHolidays(year: number, country: string): Promise<Holiday[]> {
  // Uses a public holiday provider. If it ever changes, this remains isolated here.
  const url = `https://date.nager.at/api/v3/PublicHolidays/${year}/${country}`;
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) throw new Error(`Holiday lookup failed (HTTP ${res.status})`);
  const data = (await res.json()) as any[];
  return (data || []).map((h) => ({
    date: String(h.date),
    localName: String(h.localName || h.name || ""),
    name: String(h.name || h.localName || ""),
  }));
}

const DashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();

  const ctx = getContext();

  // IMPORTANT:
  // - URL param "amoCode" is actually the AMO login slug in your routes (e.g. "root").
  // - Auth context stores BOTH: amoCode (e.g. PLATFORM) and amoSlug (e.g. root).
  // Prefer slug, then fall back to code.
  const amoSlug = (params.amoCode ?? ctx.amoSlug ?? ctx.amoCode ?? "UNKNOWN").trim();

  const currentUser = getCachedUser();
  const isAdmin = isAdminUser(currentUser);
  const isSuperuser =
    !!currentUser &&
    (currentUser.is_superuser || currentUser.role === "SUPERUSER");

  const [notifications, setNotifications] = useState<QMSNotificationOut[]>([]);
  const [auditorStats, setAuditorStats] = useState<AuditorStatsOut | null>(null);

  const [docAlerts, setDocAlerts] = useState<AircraftDocument[]>([]);
  const [docAlertsLoading, setDocAlertsLoading] = useState(false);
  const [docAlertsError, setDocAlertsError] = useState<string | null>(null);
  const [docBannerDismissed, setDocBannerDismissed] = useState(false);

  // ---- FIX: define fleet state used by the metrics block (prevents fleetError undefined) ----
  const [fleetLoading, setFleetLoading] = useState(false);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const fleetCount = useMemo(() => {
    // For a first-time setup you likely have 0 aircraft; keep safe.
    // If doc alerts exist, approximate unique aircraft count from alerts.
    const serials = new Set(
      (docAlerts || [])
        .map((a) => (a as any)?.aircraft_serial_number)
        .filter((v) => typeof v === "string" && v.trim())
        .map((v) => v.trim())
    );
    return serials.size;
  }, [docAlerts]);

  // ---- Planning due schedules (safe defaults; wire backend later) ----
  const [dueSummaries, setDueSummaries] = useState<DueSummary[]>([]);
  const [dueLoading, setDueLoading] = useState(false);
  const [dueError, setDueError] = useState<string | null>(null);

  // ---- Calendar / leave / holidays (local-first, stable) ----
  const [throttleStore, setThrottleStore] = useState<ThrottleStore>(() => getThrottleStore());

  const [calendarConnections, setCalendarConnections] = useState<CalendarConnections>({
    google: false,
    outlook: false,
  });

  const today = new Date();
  const [holidayCountry, setHolidayCountry] = useState<string>("KE");
  const [holidayYear, setHolidayYear] = useState<number>(today.getFullYear());
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holidayLoading, setHolidayLoading] = useState(false);
  const [holidayError, setHolidayError] = useState<string | null>(null);

  const [leaveEntries, setLeaveEntries] = useState<LeaveEntry[]>([]);
  const [leaveForm, setLeaveForm] = useState<{ date: string; reason: string }>({
    date: "",
    reason: "",
  });

  const [calendarMonth, setCalendarMonth] = useState<Date>(
    new Date(today.getFullYear(), today.getMonth(), 1)
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

  const blockingDocAlerts = useMemo(() => {
    return docAlerts.filter(
      (alert) =>
        alert.is_blocking ||
        alert.status === "OVERDUE" ||
        (alert as any).missing_evidence
    );
  }, [docAlerts]);

  const blockingDocSignature = useMemo(() => {
    if (blockingDocAlerts.length === 0) return "";
    return blockingDocAlerts
      .map((alert) => String(alert.id))
      .sort()
      .join("|");
  }, [blockingDocAlerts]);

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

  const handleFixDocuments = () => {
    navigate(`/maintenance/${amoSlug}/${department}/aircraft-documents`);
  };

  const handleHideDocBanner = () => {
    if (!blockingDocSignature) return;
    const stored = getLocalStorageJson<Record<string, string>>(
      DOC_ALERTS_BANNER_STORAGE_KEY,
      {}
    );
    setLocalStorageJson(DOC_ALERTS_BANNER_STORAGE_KEY, {
      ...stored,
      [amoSlug]: blockingDocSignature,
    });
    setDocBannerDismissed(true);
  };

  const renderMetric = (
    label: string,
    value: number | string,
    target = 0
  ) => (
    <div className="metric-card" key={label}>
      <div className="metric-card__value">{value}</div>
      <div className="metric-card__label">{label}</div>
      <div className="metric-card__bar">
        <span style={{ width: target ? `${Math.min(100, (Number(value) / target) * 100)}%` : "0%" }} />
      </div>
    </div>
  );

  const loadNotifications = async () => {
    try {
      const data = await qmsListNotifications();
      setNotifications(data.filter((n) => !n.read_at));
    } catch {
      setNotifications([]);
    }
  };

  const loadAuditorStats = async () => {
    if (!currentUser?.id) return;
    try {
      const data = await qmsGetAuditorStats(currentUser.id);
      setAuditorStats(data);
    } catch {
      setAuditorStats(null);
    }
  };

  useEffect(() => {
    loadNotifications();
    loadAuditorStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fleet metrics are currently derived safely (no backend dependency).
  // Keep hooks here so future API wiring is contained and doesn't break the page.
  useEffect(() => {
    let mounted = true;
    const run = async () => {
      setFleetLoading(false);
      setFleetError(null);
      if (!mounted) return;
    };
    run();
    return () => {
      mounted = false;
    };
  }, [amoSlug]);

  // Planning "due schedules" placeholder (safe). Wire to backend later if needed.
  useEffect(() => {
    let mounted = true;
    const run = async () => {
      if (department !== "planning") return;
      setDueLoading(false);
      setDueError(null);
      if (!mounted) return;
      setDueSummaries([]);
    };
    run();
    return () => {
      mounted = false;
    };
  }, [department, amoSlug]);

  useEffect(() => {
    if (!shouldShowComplianceAlerts) {
      setDocAlerts([]);
      setDocAlertsLoading(false);
      setDocAlertsError(null);
      setDocBannerDismissed(false);
      return;
    }

    let isMounted = true;
    const loadAlerts = async () => {
      setDocAlertsLoading(true);
      setDocAlertsError(null);
      try {
        const data = await listDocumentAlerts({ due_within_days: 45 });
        if (!isMounted) return;
        setDocAlerts(data);
      } catch (err: any) {
        if (!isMounted) return;
        setDocAlertsError(
          err?.message || "Unable to load aircraft document alerts."
        );
      } finally {
        if (isMounted) setDocAlertsLoading(false);
      }
    };

    loadAlerts();
    return () => {
      isMounted = false;
    };
  }, [shouldShowComplianceAlerts]);

  useEffect(() => {
    if (!blockingDocSignature) {
      setDocBannerDismissed(false);
      return;
    }
    if (!isSuperuser) {
      setDocBannerDismissed(false);
      return;
    }
    const stored = getLocalStorageJson<Record<string, string>>(
      DOC_ALERTS_BANNER_STORAGE_KEY,
      {}
    );
    setDocBannerDismissed(stored[amoSlug] === blockingDocSignature);
  }, [amoSlug, blockingDocSignature, isSuperuser]);

  const handleMarkRead = async (id: string) => {
    try {
      await qmsMarkNotificationRead(id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    } catch {
      // noop
    }
  };

  // ---- Calendar helpers ----
  useEffect(() => {
    // Load throttle store once, then keep local state in sync with storage updates you may add later.
    setThrottleStore(getThrottleStore());
  }, []);

  useEffect(() => {
    if (!currentUser?.id) return;
    const key = getConnectionsStorageKey(amoSlug, currentUser.id);
    const stored = getLocalStorageJson<CalendarConnections>(key, {
      google: false,
      outlook: false,
    });
    setCalendarConnections(stored);
  }, [amoSlug, currentUser?.id]);

  const handleConnectCalendar = (provider: CalendarProvider) => {
    const url =
      provider === "google"
        ? safeEnv("VITE_CALENDAR_GOOGLE_OAUTH_URL")
        : safeEnv("VITE_CALENDAR_OUTLOOK_OAUTH_URL");

    if (!url) {
      alert(
        `Calendar OAuth URL not configured. Set ${
          provider === "google"
            ? "VITE_CALENDAR_GOOGLE_OAUTH_URL"
            : "VITE_CALENDAR_OUTLOOK_OAUTH_URL"
        } in your frontend environment.`
      );
      return;
    }

    // Open OAuth flow (best-effort; your backend should handle callback)
    window.open(url, "_blank", "noopener,noreferrer");

    if (!currentUser?.id) return;
    const next = { ...calendarConnections, [provider]: true };
    setCalendarConnections(next);
    setLocalStorageJson(getConnectionsStorageKey(amoSlug, currentUser.id), next);
  };

  const handleDisconnectCalendar = (provider: CalendarProvider) => {
    if (!currentUser?.id) return;
    const next = { ...calendarConnections, [provider]: false };
    setCalendarConnections(next);
    setLocalStorageJson(getConnectionsStorageKey(amoSlug, currentUser.id), next);
  };

  // Leave storage
  useEffect(() => {
    if (!currentUser?.id) return;
    const key = getLeaveStorageKey(amoSlug, currentUser.id);
    const stored = getLocalStorageJson<LeaveEntry[]>(key, []);
    setLeaveEntries(
      (stored || []).filter(
        (e) => typeof e?.date === "string" && e.date.length >= 10
      )
    );
  }, [amoSlug, currentUser?.id]);

  const persistLeave = (entries: LeaveEntry[]) => {
    if (!currentUser?.id) return;
    const key = getLeaveStorageKey(amoSlug, currentUser.id);
    setLocalStorageJson(key, entries);
    setLeaveEntries(entries);
  };

  const handleAddLeave = (e: React.FormEvent) => {
    e.preventDefault();
    const date = (leaveForm.date || "").trim();
    if (!date) return;

    const reason = (leaveForm.reason || "").trim() || "Leave";
    const exists = leaveEntries.some((x) => x.date === date);

    const next = exists
      ? leaveEntries.map((x) => (x.date === date ? { ...x, reason } : x))
      : [...leaveEntries, { id: makeId("LV"), date, reason }];

    // Keep ordered by date
    next.sort((a, b) => a.date.localeCompare(b.date));
    persistLeave(next);

    setLeaveForm({ date: "", reason: "" });
  };

  const handleRemoveLeave = (id: string) => {
    const next = leaveEntries.filter((x) => x.id !== id);
    persistLeave(next);
  };

  // Holidays (cached)
  useEffect(() => {
    let mounted = true;

    const run = async () => {
      const country = (holidayCountry || "").trim().toUpperCase();
      const year = Number(holidayYear);

      if (!country || country.length !== 2 || !Number.isFinite(year) || year < 1970) {
        setHolidayError("Enter a valid 2-letter country code and year.");
        setHolidays([]);
        return;
      }

      const cacheKey = `amo_public_holidays_${country}_${year}`;
      setHolidayLoading(true);
      setHolidayError(null);

      try {
        if (throttleStore.cacheHolidays) {
          const cached = getLocalStorageJson<Holiday[] | null>(cacheKey, null);
          if (cached && Array.isArray(cached) && cached.length > 0) {
            if (!mounted) return;
            setHolidays(cached);
            setHolidayLoading(false);
            return;
          }
        }

        const data = await fetchPublicHolidays(year, country);
        if (!mounted) return;
        setHolidays(data);

        if (throttleStore.cacheHolidays) {
          setLocalStorageJson(cacheKey, data);
        }
      } catch (err: any) {
        if (!mounted) return;
        setHolidays([]);
        setHolidayError(err?.message || "Unable to load public holidays.");
      } finally {
        if (mounted) setHolidayLoading(false);
      }
    };

    // Only auto-fetch on planning dashboard (keeps noise down)
    if (department === "planning") run();

    return () => {
      mounted = false;
    };
  }, [department, holidayCountry, holidayYear, throttleStore.cacheHolidays]);

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

      {shouldShowComplianceAlerts &&
        blockingDocAlerts.length > 0 &&
        !docBannerDismissed && (
          <section className="page-section">
            <div className="info-banner info-banner--warning">
              <div>
                <strong>Aircraft document blockers detected</strong>
                <p className="text-muted" style={{ margin: "4px 0 0" }}>
                  Work on affected aircraft is blocked until overdue or missing
                  evidence is resolved. Upload the latest compliance evidence to
                  restore planning and quality workflows.
                </p>
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {blockingDocAlerts.slice(0, 3).map((alert: any) => (
                    <li key={alert.id}>
                      {alert.aircraft_serial_number} ·{" "}
                      {String(alert.document_type || "").replace(/_/g, " ")} ·{" "}
                      {String(alert.status || "").replace(/_/g, " ")}
                      {alert.days_to_expiry !== null &&
                        alert.days_to_expiry !== undefined &&
                        ` (${alert.days_to_expiry} days)`}
                      {alert.missing_evidence && " · Evidence missing"}
                    </li>
                  ))}
                  {blockingDocAlerts.length > 3 && (
                    <li>
                      +{blockingDocAlerts.length - 3} more blocking documents
                    </li>
                  )}
                </ul>
              </div>
              <div className="page-section__actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleFixDocuments}
                >
                  Fix documents
                </button>
                {isSuperuser && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleHideDocBanner}
                  >
                    Hide
                  </button>
                )}
              </div>
            </div>
          </section>
        )}

      {notifications.length > 0 && (
        <section className="page-section">
          <div className="card">
            <div className="card-header">
              <h2>Notifications</h2>
              <p className="text-muted">
                Recent quality actions that need your attention.
              </p>
            </div>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {notifications.map((note) => (
                <li
                  key={note.id}
                  style={{
                    display: "flex",
                    gap: 12,
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 0",
                    borderBottom: "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        flexWrap: "wrap",
                        alignItems: "center",
                      }}
                    >
                      <span
                        className={
                          note.severity === "ACTION_REQUIRED"
                            ? "badge badge--warning"
                            : note.severity === "WARNING"
                            ? "badge badge--danger"
                            : "badge badge--info"
                        }
                      >
                        {note.severity}
                      </span>
                      <span>{note.message}</span>
                    </div>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {new Date(note.created_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={() => handleMarkRead(note.id)}
                  >
                    Mark read
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {auditorStats && (
        <section className="page-section">
          <div className="card">
            <div className="card-header">
              <h2>Auditor workload</h2>
              <p className="text-muted">
                Summary of audits assigned to you across lead/observer/assistant
                roles.
              </p>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <span className="badge badge--info">
                Total: {auditorStats.audits_total}
              </span>
              <span className="badge badge--warning">
                Open: {auditorStats.audits_open}
              </span>
              <span className="badge badge--success">
                Closed: {auditorStats.audits_closed}
              </span>
              <span className="badge badge--neutral">
                Lead: {auditorStats.lead_audits}
              </span>
              <span className="badge badge--neutral">
                Observer: {auditorStats.observer_audits}
              </span>
              <span className="badge badge--neutral">
                Assistant: {auditorStats.assistant_audits}
              </span>
            </div>
          </div>
        </section>
      )}

      {isCRSDept && (
        <section className="page-section">
          <h2 className="page-section__title">
            Certificates of Release to Service
          </h2>
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
          <h2 className="page-section__title">
            Planning calendar & leave management
          </h2>
          <p className="page-section__body">
            Sync personal calendars, review public holidays, and mark leave days
            before assigning maintenance slots.
          </p>

          <div
            className="page-section__grid"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}
          >
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
                  {calendarConnections.outlook
                    ? "Disconnect Outlook"
                    : "Connect Outlook"}
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
              {!holidayLoading && !holidayError && holidays.length === 0 && (
                <p className="text-muted">No holidays found for that selection.</p>
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
                    <li
                      key={entry.id}
                      style={{ display: "flex", gap: 8, alignItems: "center" }}
                    >
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
                onClick={() =>
                  navigate(`/maintenance/${amoSlug}/${department}/aircraft-import`)
                }
              >
                Configure fleet inputs
              </button>
              <button
                type="button"
                className="primary-chip-btn"
                style={{ marginLeft: 8 }}
                onClick={() =>
                  navigate(`/maintenance/${amoSlug}/${department}/component-import`)
                }
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
                  {docAlerts?.map((alert: any) => (
                    <li className="card card--border" key={alert.id}>
                      <h3 className="card__title">
                        {String(alert.document_type || "").replace(/_/g, " ")} ·{" "}
                        {alert.aircraft_serial_number}
                      </h3>
                      <p className="card__subtitle">
                        Authority: {alert.authority} · Status: {alert.status}
                      </p>
                      <p className="card__body">
                        {alert.expires_on
                          ? `Expires on ${alert.expires_on}${
                              alert.days_to_expiry !== null &&
                              alert.days_to_expiry !== undefined
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

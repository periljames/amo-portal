// src/pages/MyTrainingPage.tsx
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import "../styles/training.css";
import {
  getMyTrainingStatus,
  listTrainingCourses,
  listTrainingEvents,
  createTrainingDeferralRequest,
  listMyTrainingDeferrals,
  listTrainingFiles,
  downloadTrainingFile,
  uploadTrainingFile,
} from "../services/training";
import type {
  TrainingStatusItem,
  TrainingCourseRead,
  TrainingEventRead,
  TrainingDeferralRequestRead,
} from "../types/training";
import type { TrainingFileRead, TransferProgress } from "../services/training";

type SortField =
  | "course_name"
  | "status"
  | "due_date"
  | "days_until_due"
  | "upcoming_event_date"
  | "cycle_progress";
type SortDirection = "asc" | "desc";

interface SortState {
  field: SortField;
  direction: SortDirection;
}

type Status =
  | "OVERDUE"
  | "DUE_SOON"
  | "DEFERRED"
  | "SCHEDULED_ONLY"
  | "NOT_DONE"
  | "OK"
  | string;

type CalendarItemType = "DUE" | "EVENT";

type CalendarItem = {
  key: string;
  dateKey: string; // YYYY-MM-DD
  type: CalendarItemType;
  courseId: string;
  courseName: string;
  status?: Status;
  daysUntilDue?: number | null;
  eventId?: string | null;
};

const initialSort: SortState = { field: "status", direction: "asc" };

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return `${y}-${pad2(m)}-${pad2(day)}`;
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;

  // "YYYY-MM-DD" date-only from API
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-").map((v) => Number(v));
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function formatDate(value: string | null | undefined): string {
  const d = parseDate(value);
  if (!d) return "";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function formatIsoDate(value: string | null | undefined): string {
  const d = parseDate(value);
  if (!d) return "";
  return toDateKey(d);
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function daysBetween(a: Date, b: Date): number {
  const ms = startOfDay(b).getTime() - startOfDay(a).getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

function addDays(date: Date, delta: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + delta);
}

function statusLabelDisplay(status: Status): string {
  switch (String(status).toUpperCase()) {
    case "OVERDUE":
      return "Overdue";
    case "DUE_SOON":
      return "Due soon";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled";
    case "NOT_DONE":
      return "Not done";
    case "OK":
    default:
      return "OK";
  }
}

function statusSortRank(status: Status): number {
  switch (String(status).toUpperCase()) {
    case "OVERDUE":
      return 0;
    case "DUE_SOON":
      return 1;
    case "DEFERRED":
      return 2;
    case "SCHEDULED_ONLY":
      return 3;
    case "NOT_DONE":
      return 4;
    case "OK":
    default:
      return 5;
  }
}

function badgeClass(status: Status): string {
  switch (String(status).toUpperCase()) {
    case "OVERDUE":
      return "badge badge--danger";
    case "DUE_SOON":
      return "badge badge--warning";
    case "DEFERRED":
      return "badge badge--info";
    case "SCHEDULED_ONLY":
      return "badge badge--neutral";
    case "NOT_DONE":
      return "badge badge--neutral";
    case "OK":
    default:
      return "badge badge--success";
  }
}

function deferralStatusLabel(status: string): string {
  switch (status) {
    case "APPROVED":
      return "Approved";
    case "REJECTED":
      return "Rejected / revoked";
    case "PENDING":
    default:
      return "Pending";
  }
}

function deferralStatusBadge(status: string): string {
  switch (status) {
    case "APPROVED":
      return "badge badge--success";
    case "REJECTED":
      return "badge badge--danger";
    case "PENDING":
    default:
      return "badge badge--warning";
  }
}

type RevocationRiskLevel = "HIGH" | "MEDIUM";

function revocationRiskLabel(level: RevocationRiskLevel): string {
  return level === "HIGH" ? "High revocation risk" : "Revocation risk";
}

function revocationRiskClass(level: RevocationRiskLevel): string {
  return level === "HIGH" ? "badge badge--danger" : "badge badge--warning";
}

function getRevocationRisk(daysUntilDue: number | null | undefined): RevocationRiskLevel | null {
  if (daysUntilDue == null) return null;
  if (daysUntilDue <= -90) return "HIGH";
  if (daysUntilDue <= -30) return "MEDIUM";
  return null;
}

function getDueDate(item: TrainingStatusItem): string | null {
  // controlling date = deferral date if approved, otherwise valid_until
  return item.extended_due_date || item.valid_until || null;
}

function isActionRequired(status: Status): boolean {
  const s = String(status).toUpperCase();
  return s === "OVERDUE" || s === "DUE_SOON" || s === "NOT_DONE";
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

function computeCycleProgress(item: TrainingStatusItem): number | null {
  const last = parseDate(item.last_completion_date);
  const due = parseDate(getDueDate(item));
  if (!due) return null;

  const today = startOfDay(new Date());

  if (!last) {
    // If never completed, show urgency by moving towards 1 when due approaches/passes.
    const diff = daysBetween(today, due);
    // due in 180 days => ~0, due today => 1, overdue => 1
    const approxWindow = 180;
    const used = approxWindow - Math.max(0, diff);
    return clamp01(used / approxWindow);
  }

  const totalDays = Math.max(1, daysBetween(last, due));
  const usedDays = Math.max(0, daysBetween(last, today));
  return clamp01(usedDays / totalDays);
}

function ProgressBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(clamp01(value) * 100);
  return (
    <div style={{ display: "grid", gap: 6 }}>
      {label ? <div className="text-muted">{label}</div> : null}
      <div
        style={{
          height: 10,
          borderRadius: 999,
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
        }}
        aria-label={label ? `${label}: ${pct}%` : `Progress: ${pct}%`}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "rgba(255,255,255,0.55)",
          }}
        />
      </div>
      <div style={{ fontSize: 12 }} className="text-muted">
        {pct}%
      </div>
    </div>
  );
}

function StackedStatusBar({
  counts,
  total,
}: {
  counts: Record<string, number>;
  total: number;
}) {
  const segs: Array<{ key: string; label: string; value: number; bg: string }> = [
    { key: "OVERDUE", label: "Overdue", value: counts.OVERDUE || 0, bg: "#b83a3a" },
    { key: "DUE_SOON", label: "Due soon", value: counts.DUE_SOON || 0, bg: "#b97a2a" },
    { key: "DEFERRED", label: "Deferred", value: counts.DEFERRED || 0, bg: "#2f78b7" },
    { key: "SCHEDULED_ONLY", label: "Scheduled", value: counts.SCHEDULED_ONLY || 0, bg: "#6b6b6b" },
    { key: "NOT_DONE", label: "Not done", value: counts.NOT_DONE || 0, bg: "#7a7a7a" },
    { key: "OK", label: "OK", value: counts.OK || 0, bg: "#2f8f4e" },
  ];

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div
        style={{
          height: 12,
          borderRadius: 999,
          overflow: "hidden",
          display: "flex",
          background: "rgba(255,255,255,0.08)",
        }}
        aria-label="Training status distribution"
      >
        {segs.map((s) => {
          const w = total > 0 ? (s.value / total) * 100 : 0;
          if (w <= 0) return null;
          return (
            <div
              key={s.key}
              title={`${s.label}: ${s.value}`}
              style={{ width: `${w}%`, background: s.bg }}
            />
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {segs.map((s) => (
          <span key={s.key} className={badgeClass(s.key)}>
            {s.label}: {s.value}
          </span>
        ))}
      </div>
    </div>
  );
}

function MonthCalendar({
  monthDate,
  itemsByDate,
  selectedDateKey,
  onSelectDateKey,
}: {
  monthDate: Date;
  itemsByDate: Map<string, CalendarItem[]>;
  selectedDateKey: string | null;
  onSelectDateKey: (k: string | null) => void;
}) {
  const monthStart = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const monthEnd = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0);

  const startWeekday = monthStart.getDay(); // 0=Sun
  const daysInMonth = monthEnd.getDate();

  const cells: Array<{ date: Date | null; dateKey: string | null }> = [];

  for (let i = 0; i < startWeekday; i++) cells.push({ date: null, dateKey: null });
  for (let day = 1; day <= daysInMonth; day++) {
    const d = new Date(monthDate.getFullYear(), monthDate.getMonth(), day);
    cells.push({ date: d, dateKey: toDateKey(d) });
  }
  while (cells.length % 7 !== 0) cells.push({ date: null, dateKey: null });

  const weekRows: Array<typeof cells> = [];
  for (let i = 0; i < cells.length; i += 7) weekRows.push(cells.slice(i, i + 7));

  const todayKey = toDateKey(new Date());

  return (
    <div className="card">
      <div className="card-header">
        <h2>Calendar</h2>
        <p className="text-muted" style={{ margin: 0 }}>
          Due dates and scheduled training events.
        </p>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <table className="table table-compact" style={{ tableLayout: "fixed" }}>
          <thead>
            <tr>
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <th key={d} style={{ textAlign: "center", fontWeight: 600 }}>
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weekRows.map((row, idx) => (
              <tr key={idx}>
                {row.map((cell, j) => {
                  if (!cell.date || !cell.dateKey) {
                    return <td key={j} style={{ height: 56 }} />;
                  }

                  const hasItems = (itemsByDate.get(cell.dateKey) || []).length > 0;
                  const isSelected = selectedDateKey === cell.dateKey;
                  const isToday = cell.dateKey === todayKey;

                  return (
                    <td key={j} style={{ verticalAlign: "top", padding: 6 }}>
                      <button
                        type="button"
                        onClick={() => onSelectDateKey(isSelected ? null : cell.dateKey)}
                        style={{
                          width: "100%",
                          border: "none",
                          background: isSelected
                            ? "rgba(255,255,255,0.12)"
                            : "rgba(255,255,255,0.04)",
                          borderRadius: 10,
                          padding: 8,
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                        aria-label={`Select ${cell.dateKey}`}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                          <div style={{ fontWeight: 700 }}>
                            {cell.date.getDate()}
                            {isToday ? <span className="text-muted"> · Today</span> : null}
                          </div>
                          {hasItems ? (
                            <span className="badge badge--info" style={{ alignSelf: "start" }}>
                              {itemsByDate.get(cell.dateKey)!.length}
                            </span>
                          ) : null}
                        </div>

                        {hasItems ? (
                          <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                            {(itemsByDate.get(cell.dateKey) || []).slice(0, 3).map((it) => (
                              <span
                                key={it.key}
                                className={
                                  it.type === "DUE" ? "badge badge--warning" : "badge badge--neutral"
                                }
                                title={it.courseName}
                              >
                                {it.type === "DUE" ? "Due" : "Event"}
                              </span>
                            ))}
                            {(itemsByDate.get(cell.dateKey) || []).length > 3 ? (
                              <span className="badge badge--neutral">
                                +{(itemsByDate.get(cell.dateKey) || []).length - 3}
                              </span>
                            ) : null}
                          </div>
                        ) : (
                          <div className="text-muted" style={{ marginTop: 6, fontSize: 12 }}>
                            —
                          </div>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {selectedDateKey ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="table-primary-text">Selected: {selectedDateKey}</div>
            <div className="table-responsive">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Course</th>
                    <th>Info</th>
                  </tr>
                </thead>
                <tbody>
                  {(itemsByDate.get(selectedDateKey) || []).map((it) => (
                    <tr key={it.key}>
                      <td>{it.type === "DUE" ? "Due date" : "Training event"}</td>
                      <td>{it.courseName}</td>
                      <td>
                        {it.type === "DUE" ? (
                          <span className={badgeClass(it.status || "")}>
                            {statusLabelDisplay(it.status || "")}
                            {typeof it.daysUntilDue === "number"
                              ? it.daysUntilDue < 0
                                ? ` · overdue by ${Math.abs(it.daysUntilDue)}d`
                                : ` · ${it.daysUntilDue}d left`
                              : ""}
                          </span>
                        ) : (
                          <span className="badge badge--neutral">Scheduled</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(itemsByDate.get(selectedDateKey) || []).length === 0 ? (
                    <tr>
                      <td colSpan={3} className="text-muted">
                        Nothing on this date.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function tryGetUserIdFromStorage(): string | null {
  const direct =
    localStorage.getItem("user_id") ||
    localStorage.getItem("userId") ||
    localStorage.getItem("current_user_id");
  if (direct && direct.trim()) return direct.trim();

  const token =
    localStorage.getItem("access_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("jwt");
  if (!token) return null;

  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(payload));
    // Common JWT patterns: sub, user_id, uid
    return (json?.user_id || json?.uid || json?.sub || null) as string | null;
  } catch {
    return null;
  }
}

function MyTrainingPage() {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const amoCode = (params.amoCode || "AMO").trim();
  const department = (params.department || "planning").trim();

  const cachedUser = useMemo(() => getCachedUser(), []);

  const [items, setItems] = useState<TrainingStatusItem[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const [sort, setSort] = useState<SortState>(initialSort);
  const [query, setQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [actionOnly, setActionOnly] = useState<boolean>(false);

  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(null);

  const [calendarMonth, setCalendarMonth] = useState<Date>(() => new Date());
  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);

  // Map logical course code (HF-REF) -> backend course PK (uuid)
  const [coursePkByCode, setCoursePkByCode] = useState<Record<string, string>>({});
  const [coursesLoaded, setCoursesLoaded] = useState<boolean>(false);

  // Toast
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Event details modal
  const [eventOpen, setEventOpen] = useState<boolean>(false);
  const [eventLoading, setEventLoading] = useState<boolean>(false);
  const [eventError, setEventError] = useState<string | null>(null);
  const [eventDetails, setEventDetails] = useState<TrainingEventRead | null>(null);

  // Deferral modal
  const [deferralOpen, setDeferralOpen] = useState<boolean>(false);
  const [deferralSaving, setDeferralSaving] = useState<boolean>(false);
  const [deferralError, setDeferralError] = useState<string | null>(null);
  const [deferralRequestedNewDate, setDeferralRequestedNewDate] = useState<string>("");
  const [deferralReasonCategory, setDeferralReasonCategory] = useState<
    | "ILLNESS"
    | "OPERATIONAL_REQUIREMENTS"
    | "PERSONAL_EMERGENCY"
    | "PROVIDER_CANCELLATION"
    | "SYSTEM_FAILURE"
    | "OTHER"
  >("OPERATIONAL_REQUIREMENTS");
  const [deferralReasonText, setDeferralReasonText] = useState<string>("");

  const [deferrals, setDeferrals] = useState<TrainingDeferralRequestRead[]>([]);
  const [deferralsLoading, setDeferralsLoading] = useState<boolean>(false);
  const [deferralsError, setDeferralsError] = useState<string | null>(null);

  // Training evidence files
  const [trainingFiles, setTrainingFiles] = useState<TrainingFileRead[]>([]);
  const [trainingFilesLoading, setTrainingFilesLoading] = useState<boolean>(false);
  const [trainingFilesError, setTrainingFilesError] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{
    fileId: string;
    progress: TransferProgress;
  } | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadKind, setUploadKind] = useState<string>("EVIDENCE");
  const [uploadCourseId, setUploadCourseId] = useState<string>("");
  const [uploadDeferralId, setUploadDeferralId] = useState<string>("");
  const [uploadSaving, setUploadSaving] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const selectedItem = useMemo(() => {
    if (!selectedCourseId) return null;
    return items.find((x) => x.course_id === selectedCourseId) || null;
  }, [items, selectedCourseId]);

  const buildCoursePkMap = (courses: TrainingCourseRead[]) => {
    const map: Record<string, string> = {};
    for (const c of courses) {
      map[c.course_id] = c.id;
    }
    setCoursePkByCode(map);
    setCourses(courses);
    setCoursesLoaded(true);
  };

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const [status, courses] = await Promise.all([
        getMyTrainingStatus(),
        listTrainingCourses({ include_inactive: true }),
      ]);
      setItems(status);
      buildCoursePkMap(courses);
      setLastRefreshedAt(new Date());
    } catch (err: any) {
      setError(err?.message || "Failed to load training status.");
    } finally {
      setLoading(false);
    }
  };

  const loadTrainingFiles = async () => {
    setTrainingFilesLoading(true);
    setTrainingFilesError(null);
    try {
      const data = await listTrainingFiles();
      setTrainingFiles(data);
    } catch (err: any) {
      setTrainingFilesError(err?.message || "Failed to load training files.");
    } finally {
      setTrainingFilesLoading(false);
    }
  };

  const loadDeferrals = async () => {
    setDeferralsLoading(true);
    setDeferralsError(null);
    try {
      const data = await listMyTrainingDeferrals();
      setDeferrals(data);
    } catch (err: any) {
      setDeferralsError(err?.message || "Failed to load deferrals.");
    } finally {
      setDeferralsLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [status, courses] = await Promise.all([
          getMyTrainingStatus(),
          listTrainingCourses({ include_inactive: true }),
        ]);

        if (!cancelled) {
          setItems(status);
          buildCoursePkMap(courses);
          setLastRefreshedAt(new Date());
        }
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Failed to load training status.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    loadTrainingFiles();
  }, []);

  useEffect(() => {
    loadDeferrals();
  }, []);

  const handleSortChange = (field: SortField) => {
    setSort((current) => {
      if (current.field === field) {
        return { field, direction: current.direction === "asc" ? "desc" : "asc" };
      }
      return { field, direction: "asc" };
    });
  };

  const metrics = useMemo(() => {
    const counts: Record<string, number> = {
      OVERDUE: 0,
      DUE_SOON: 0,
      DEFERRED: 0,
      SCHEDULED_ONLY: 0,
      NOT_DONE: 0,
      OK: 0,
    };

    for (const it of items) {
      const s = String(it.status).toUpperCase();
      if (counts[s] == null) counts[s] = 0;
      counts[s] += 1;
    }

    const total = items.length;
    const ok = counts.OK || 0;
    const complianceOkOnly = total > 0 ? ok / total : 0;

    const coveredCount = (counts.OK || 0) + (counts.DEFERRED || 0) + (counts.DUE_SOON || 0);
    const complianceCovered = total > 0 ? coveredCount / total : 0;

    const actionRequired = items.filter((i) => isActionRequired(i.status));

    const nextDue = [...items]
      .map((i) => {
        const due = getDueDate(i);
        const dd = parseDate(due);
        if (!dd) return null;
        return { item: i, due: dd };
      })
      .filter(Boolean) as Array<{ item: TrainingStatusItem; due: Date }>;

    nextDue.sort((a, b) => a.due.getTime() - b.due.getTime());

    const today = startOfDay(new Date());
    const upcoming30 = nextDue.filter((x) => {
      const diff = daysBetween(today, x.due);
      return diff >= 0 && diff <= 30;
    });

    return {
      counts,
      total,
      complianceOkOnly,
      complianceCovered,
      coveredCount,
      actionRequiredCount: actionRequired.length,
      nextDue: nextDue[0]?.item || null,
      upcoming30Count: upcoming30.length,
      actionRequiredItems: actionRequired,
    };
  }, [items]);

  const revocationAlerts = useMemo(() => {
    return items
      .map((item) => {
        const risk = getRevocationRisk(item.days_until_due);
        if (!risk) return null;
        return { item, risk };
      })
      .filter(Boolean) as Array<{ item: TrainingStatusItem; risk: RevocationRiskLevel }>;
  }, [items]);

  const navigationItems = [
    { id: "training-overview", label: "Overview" },
    { id: "training-workflow", label: "Workflow" },
    { id: "training-deferrals", label: "Deferrals" },
    { id: "training-calendar", label: "Calendar" },
    { id: "training-courses", label: "All courses" },
    { id: "training-evidence", label: "Evidence files" },
  ];

  const courseNameById = useMemo(() => {
    const map = new Map<string, string>();
    courses.forEach((course) => map.set(course.id, course.course_name));
    return map;
  }, [courses]);

  const itemsByDate = useMemo(() => {
    const map = new Map<string, CalendarItem[]>();

    const push = (k: string, it: CalendarItem) => {
      const arr = map.get(k) || [];
      arr.push(it);
      map.set(k, arr);
    };

    for (const it of items) {
      const due = parseDate(getDueDate(it));
      if (due) {
        const dk = toDateKey(due);
        push(dk, {
          key: `due:${it.course_id}:${dk}`,
          dateKey: dk,
          type: "DUE",
          courseId: it.course_id,
          courseName: it.course_name,
          status: it.status,
          daysUntilDue: it.days_until_due ?? null,
        });
      }

      const ev = parseDate(it.upcoming_event_date || null);
      if (ev) {
        const ek = toDateKey(ev);
        push(ek, {
          key: `event:${it.course_id}:${ek}:${it.upcoming_event_id || "x"}`,
          dateKey: ek,
          type: "EVENT",
          courseId: it.course_id,
          courseName: it.course_name,
          eventId: it.upcoming_event_id ?? null,
        });
      }
    }

    for (const [k, arr] of map.entries()) {
      arr.sort((a, b) => {
        if (a.type !== b.type) return a.type === "DUE" ? -1 : 1;
        const ra = statusSortRank(a.status || "");
        const rb = statusSortRank(b.status || "");
        return ra - rb;
      });
      map.set(k, arr);
    }

    return map;
  }, [items]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();

    return items.filter((it) => {
      if (actionOnly && !isActionRequired(it.status)) return false;

      if (statusFilter !== "ALL") {
        if (String(it.status).toUpperCase() !== statusFilter) return false;
      }

      if (selectedDateKey) {
        const dueKey = (() => {
          const d = parseDate(getDueDate(it));
          return d ? toDateKey(d) : null;
        })();
        const eventKey = (() => {
          const d = parseDate(it.upcoming_event_date || null);
          return d ? toDateKey(d) : null;
        })();

        if (dueKey !== selectedDateKey && eventKey !== selectedDateKey) return false;
      }

      if (!q) return true;
      return (
        it.course_name.toLowerCase().includes(q) ||
        it.course_id.toLowerCase().includes(q) ||
        String(it.status).toLowerCase().includes(q)
      );
    });
  }, [items, query, statusFilter, actionOnly, selectedDateKey]);

  const sortedItems = useMemo(() => {
    const copy = [...filteredItems];

    copy.sort((a, b) => {
      let result = 0;

      if (sort.field === "course_name") {
        result = a.course_name.localeCompare(b.course_name);
      } else if (sort.field === "status") {
        result = statusSortRank(a.status) - statusSortRank(b.status);
      } else if (sort.field === "due_date") {
        const da = parseDate(getDueDate(a))?.getTime() ?? Infinity;
        const db = parseDate(getDueDate(b))?.getTime() ?? Infinity;
        result = da - db;
      } else if (sort.field === "days_until_due") {
        const da = a.days_until_due ?? Infinity;
        const db = b.days_until_due ?? Infinity;
        result = da - db;
      } else if (sort.field === "upcoming_event_date") {
        const da = parseDate(a.upcoming_event_date || null)?.getTime() ?? Infinity;
        const db = parseDate(b.upcoming_event_date || null)?.getTime() ?? Infinity;
        result = da - db;
      } else if (sort.field === "cycle_progress") {
        const pa = computeCycleProgress(a);
        const pb = computeCycleProgress(b);
        const da = pa == null ? Infinity : pa;
        const db = pb == null ? Infinity : pb;
        result = da - db;
      }

      return sort.direction === "asc" ? result : -result;
    });

    return copy;
  }, [filteredItems, sort]);

  const exportCsv = () => {
    const rows = sortedItems.map((it) => ({
      course_id: it.course_id,
      course_name: it.course_name,
      status: it.status,
      frequency_months: it.frequency_months ?? "",
      last_completion_date: it.last_completion_date ?? "",
      due_date: getDueDate(it) ?? "",
      days_until_due: it.days_until_due ?? "",
      upcoming_event_date: it.upcoming_event_date ?? "",
    }));

    const header = rows.length
      ? Object.keys(rows[0]).join(",")
      : "course_id,course_name,status,frequency_months,last_completion_date,due_date,days_until_due,upcoming_event_date";
    const body = rows
      .map((r) =>
        Object.values(r)
          .map((v) => {
            const s = String(v ?? "");
            const escaped =
              s.includes(",") || s.includes('"') || s.includes("\n")
                ? `"${s.replace(/"/g, '""')}"`
                : s;
            return escaped;
          })
          .join(","),
      )
      .join("\n");

    const csv = rows.length ? `${header}\n${body}\n` : `${header}\n`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "my_training_status.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportPdf = () => {
    if (typeof window === "undefined") return;
    const rows = sortedItems.map((it) => ({
      course_id: it.course_id,
      course_name: it.course_name,
      status: it.status,
      frequency_months: it.frequency_months ?? "",
      last_completion_date: it.last_completion_date ?? "",
      due_date: getDueDate(it) ?? "",
      days_until_due: it.days_until_due ?? "",
      upcoming_event_date: it.upcoming_event_date ?? "",
    }));

    const win = window.open("", "_blank", "width=980,height=720");
    if (!win) return;

    const tableRows = rows
      .map(
        (row) => `
          <tr>
            <td>${row.course_id}</td>
            <td>${row.course_name}</td>
            <td>${row.status}</td>
            <td>${row.frequency_months}</td>
            <td>${row.last_completion_date}</td>
            <td>${row.due_date}</td>
            <td>${row.days_until_due}</td>
            <td>${row.upcoming_event_date}</td>
          </tr>
        `,
      )
      .join("");

    win.document.write(`
      <html>
        <head>
          <title>AMO Training Status</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; }
            h1 { font-size: 18px; margin-bottom: 12px; }
            table { width: 100%; border-collapse: collapse; font-size: 12px; }
            th, td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; }
            th { background: #f3f4f6; text-transform: uppercase; letter-spacing: 0.04em; font-size: 11px; }
          </style>
        </head>
        <body>
          <h1>AMO Training Status</h1>
          <table>
            <thead>
              <tr>
                <th>Course ID</th>
                <th>Course</th>
                <th>Status</th>
                <th>Frequency (Months)</th>
                <th>Last Completion</th>
                <th>Due Date</th>
                <th>Days Until Due</th>
                <th>Next Event</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows || `<tr><td colspan="8">No rows available.</td></tr>`}
            </tbody>
          </table>
        </body>
      </html>
    `);
    win.document.close();
    win.focus();
    win.print();
  };

  const exportTrainingRecordPdf = () => {
    if (typeof window === "undefined") return;
    const rows = sortedItems.map((it) => ({
      course_id: it.course_id,
      course_name: it.course_name,
      last_completion_date: formatIsoDate(it.last_completion_date),
      next_due_date: formatIsoDate(getDueDate(it)),
      status: statusLabelDisplay(it.status),
    }));

    const tableRows = rows
      .map(
        (row) => `
          <tr>
            <td>${row.course_id}</td>
            <td>${row.course_name}</td>
            <td>${row.last_completion_date || "—"}</td>
            <td>${row.next_due_date || "—"}</td>
            <td>${row.status}</td>
          </tr>
        `,
      )
      .join("");

    const win = window.open("", "_blank", "width=1000,height=800");
    if (!win) return;

    const name = cachedUser?.full_name || "Staff member";

    win.document.write(`
      <html>
        <head>
          <title>Individual Training Record</title>
          <style>
            @page { size: A4; margin: 18mm; }
            body {
              font-family: "Times New Roman", "Georgia", serif;
              margin: 0;
              color: #111827;
            }
            h1 {
              text-align: center;
              font-size: 20px;
              letter-spacing: 0.08em;
              margin: 12px 0 18px;
            }
            .meta {
              font-size: 14px;
              margin-bottom: 12px;
            }
            table {
              width: 100%;
              border-collapse: collapse;
              font-size: 12px;
            }
            th, td {
              border: 1px solid #d1d5db;
              padding: 6px 8px;
              vertical-align: top;
            }
            th {
              background: #b18f2c;
              color: #fff;
              font-weight: 700;
            }
            tbody tr:nth-child(even) {
              background: #f8f5e9;
            }
          </style>
        </head>
        <body>
          <h1>INDIVIDUAL TRAINING RECORD</h1>
          <div class="meta"><strong>Name:</strong> ${name}</div>
          <table>
            <thead>
              <tr>
                <th>CourseID</th>
                <th>CourseName</th>
                <th>LastTrainingDate</th>
                <th>NextDueDate</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows || `<tr><td colspan="5">No training records available.</td></tr>`}
            </tbody>
          </table>
        </body>
      </html>
    `);
    win.document.close();
    win.focus();
    win.print();
  };

  const handleDownloadTrainingFile = async (file: TrainingFileRead) => {
    setTrainingFilesError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadTrainingFile(file.id, (progress) =>
        setDownloadProgress({ fileId: file.id, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.original_filename || `training_file_${file.id}`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setTrainingFilesError(err?.message || "Could not download training file.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const handleUploadTrainingFile = async () => {
    if (!uploadFile) {
      setUploadError("Please choose a file to upload.");
      return;
    }
    setUploadSaving(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const payload = new FormData();
      payload.append("file", uploadFile);
      if (uploadKind) payload.append("kind", uploadKind);
      if (uploadCourseId) payload.append("course_id", uploadCourseId);
      if (uploadDeferralId) payload.append("deferral_request_id", uploadDeferralId);
      await uploadTrainingFile(payload);
      setUploadFile(null);
      setUploadCourseId("");
      setUploadDeferralId("");
      setUploadSuccess("Evidence uploaded successfully.");
      await loadTrainingFiles();
    } catch (err: any) {
      setUploadError(err?.message || "Failed to upload evidence.");
    } finally {
      setUploadSaving(false);
    }
  };

  const formatSpeed = (progress: TransferProgress) => {
    const mbps = progress.megaBytesPerSecond;
    const mbits = progress.megaBitsPerSecond;
    const mbpsLabel = Number.isFinite(mbps) ? mbps.toFixed(2) : "0.00";
    const mbitsLabel = Number.isFinite(mbits) ? mbits.toFixed(2) : "0.00";
    return `${mbpsLabel} MB/s • ${mbitsLabel} Mb/s`;
  };

  const shiftMonth = (delta: number) => {
    setCalendarMonth((d) => new Date(d.getFullYear(), d.getMonth() + delta, 1));
  };

  const openEventDetails = async (statusItem: TrainingStatusItem) => {
    setEventError(null);
    setEventDetails(null);

    if (!statusItem.upcoming_event_id) {
      setEventError("No upcoming event for this course.");
      setEventOpen(true);
      return;
    }

    const coursePk = coursePkByCode[statusItem.course_id];
    if (!coursePk) {
      setEventError("Unable to resolve this course in the Courses list. Refresh and try again.");
      setEventOpen(true);
      return;
    }

    setEventOpen(true);
    setEventLoading(true);
    try {
      // Use list endpoint + id match (works even if backend doesn't have GET /events/:id)
      const events = await listTrainingEvents({ course_pk: coursePk });
      const found = events.find((e) => e.id === statusItem.upcoming_event_id) || null;

      if (!found) {
        // Try narrowing around the date if we have it
        const evDate = parseDate(statusItem.upcoming_event_date || null);
        if (evDate) {
          const from = toDateKey(addDays(evDate, -7));
          const to = toDateKey(addDays(evDate, 7));
          const events2 = await listTrainingEvents({ course_pk: coursePk, from_date: from, to_date: to });
          const found2 = events2.find((e) => e.id === statusItem.upcoming_event_id) || null;
          setEventDetails(found2);
          if (!found2) setEventError("Event not found. It may have been updated or removed.");
        } else {
          setEventError("Event not found. It may have been updated or removed.");
        }
      } else {
        setEventDetails(found);
      }
    } catch (err: any) {
      setEventError(err?.message || "Failed to load event details.");
    } finally {
      setEventLoading(false);
    }
  };

  const openDeferral = (statusItem: TrainingStatusItem) => {
    setDeferralError(null);
    const due = getDueDate(statusItem);
    if (!due) {
      setDeferralError("No due date found for this course. Deferral requires a due date.");
      setDeferralOpen(true);
      return;
    }

    // default requested date: +30 days from controlling due date, else +30 days from today
    const dueDateObj = parseDate(due) || new Date();
    const suggested = addDays(dueDateObj, 30);
    setDeferralRequestedNewDate(toDateKey(suggested));
    setDeferralReasonCategory("OPERATIONAL_REQUIREMENTS");
    setDeferralReasonText("");
    setDeferralOpen(true);
  };

  const submitDeferral = async (statusItem: TrainingStatusItem) => {
    setDeferralSaving(true);
    setDeferralError(null);

    try {
      const due = getDueDate(statusItem);
      if (!due) throw new Error("No due date found for this course.");

      const coursePk = coursePkByCode[statusItem.course_id];
      if (!coursePk) throw new Error("Unable to resolve course PK. Refresh and try again.");

      if (!deferralRequestedNewDate || !/^\d{4}-\d{2}-\d{2}$/.test(deferralRequestedNewDate)) {
        throw new Error("Please enter a valid requested due date.");
      }

      const maybeUserId = tryGetUserIdFromStorage();

      // If backend accepts user_id omitted for self-requests, this still works.
      const payload: any = {
        course_pk: coursePk,
        original_due_date: due,
        requested_new_due_date: deferralRequestedNewDate,
        reason_category: deferralReasonCategory,
        reason_text: deferralReasonText?.trim() ? deferralReasonText.trim() : null,
      };
      if (maybeUserId) payload.user_id = maybeUserId;

      await createTrainingDeferralRequest(payload);

      setDeferralOpen(false);
      setToast({ type: "success", text: "Deferral request submitted." });
      await reload();
      await loadDeferrals();
      // keep the details drawer open after reload
      setSelectedCourseId(statusItem.course_id);
    } catch (err: any) {
      setDeferralError(err?.message || "Failed to submit deferral request.");
      setToast({ type: "error", text: err?.message || "Failed to submit deferral request." });
    } finally {
      setDeferralSaving(false);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <div className="page training-module">
        <header className="page-header">
          <h1 className="page-title">My Training</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>
            Your compliance snapshot, due dates, and upcoming training events.
          </p>
        </header>

        {loading ? (
          <div className="card card--info">
            <p>Loading your training status…</p>
          </div>
        ) : null}

        {error ? (
          <div className="card card--error">
            <p>{error}</p>
            <button type="button" className="primary-chip-btn" onClick={reload}>
              Retry
            </button>
          </div>
        ) : null}

        {!loading && !error ? (
          <>
            <section className="page-section">
              <div className="card card--info">
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <strong>Quick navigation</strong>
                  {navigationItems.map((item) => (
                    <a key={item.id} href={`#${item.id}`} className="secondary-chip-btn">
                      {item.label}
                    </a>
                  ))}
                </div>
              </div>
            </section>

            {/* Summary row */}
            <section className="page-section" id="training-overview">
              <div
                className="page-section__grid"
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                  gap: 12,
                }}
              >
                <div className="card">
                  <div className="card-header">
                    <h2>Your profile</h2>
                    <p className="text-muted">Quick context for auditors and managers.</p>
                  </div>
                  <div style={{ display: "grid", gap: 10 }}>
                    <div>
                      <div className="text-muted" style={{ fontSize: 12 }}>
                        Staff member
                      </div>
                      <div style={{ fontWeight: 700 }}>
                        {cachedUser?.full_name || "Current user"}
                      </div>
                      <div className="text-muted" style={{ fontSize: 12 }}>
                        {cachedUser?.position_title || "Role not set"} ·{" "}
                        {cachedUser?.staff_code || "Staff code not set"}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="badge badge--neutral">
                        AMO: {amoCode.toUpperCase()}
                      </span>
                      <span className="badge badge--neutral">
                        Department: {department}
                      </span>
                      <span className="badge badge--neutral">
                        Courses tracked: {metrics.total}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Compliance</h2>
                    <p className="text-muted">Overall status across your active courses.</p>
                  </div>

                  <ProgressBar value={metrics.complianceOkOnly} label="Courses in OK status" />
                  <div style={{ height: 10 }} />
                  <ProgressBar
                    value={metrics.complianceCovered}
                    label="Covered (OK + Deferred + Due soon)"
                  />

                  <div style={{ marginTop: 12 }}>
                    <StackedStatusBar counts={metrics.counts} total={metrics.total} />
                  </div>

                  <p className="text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
                    Last refreshed:{" "}
                    <strong>{lastRefreshedAt ? lastRefreshedAt.toLocaleString() : "—"}</strong>
                  </p>
                  {!coursesLoaded ? (
                    <p className="text-muted" style={{ marginTop: 6, marginBottom: 0 }}>
                      Loading course catalogue…
                    </p>
                  ) : null}
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Next actions</h2>
                    <p className="text-muted">What needs attention soon.</p>
                  </div>

                  <div style={{ display: "grid", gap: 10 }}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span
                        className={
                          metrics.actionRequiredCount > 0
                            ? "badge badge--warning"
                            : "badge badge--success"
                        }
                      >
                        Action required: {metrics.actionRequiredCount}
                      </span>
                      <span className="badge badge--neutral">
                        Due in next 30 days: {metrics.upcoming30Count}
                      </span>
                      <span className="badge badge--neutral">
                        Covered: {metrics.coveredCount}/{metrics.total}
                      </span>
                    </div>

                    {metrics.nextDue ? (
                      <div
                        style={{
                          padding: 10,
                          borderRadius: 12,
                          background: "rgba(255,255,255,0.04)",
                        }}
                      >
                        <div className="table-primary-text" style={{ marginBottom: 4 }}>
                          Next due
                        </div>
                        <div style={{ fontWeight: 700 }}>{metrics.nextDue.course_name}</div>
                        <div className="text-muted" style={{ fontSize: 13 }}>
                          Due: <strong>{formatDate(getDueDate(metrics.nextDue))}</strong>{" "}
                          {typeof metrics.nextDue.days_until_due === "number" ? (
                            metrics.nextDue.days_until_due < 0 ? (
                              <span>
                                {" "}
                                · overdue by {Math.abs(metrics.nextDue.days_until_due)} days
                              </span>
                            ) : (
                              <span> · {metrics.nextDue.days_until_due} days left</span>
                            )
                          ) : null}
                        </div>
                        <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => setSelectedCourseId(metrics.nextDue!.course_id)}
                          >
                            View details
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => {
                              setSelectedCourseId(metrics.nextDue!.course_id);
                              openDeferral(metrics.nextDue!);
                            }}
                            disabled={!getDueDate(metrics.nextDue!) || !coursesLoaded}
                            title={
                              !coursesLoaded
                                ? "Courses catalogue still loading"
                                : !getDueDate(metrics.nextDue!)
                                ? "No due date available"
                                : "Request a deferral"
                            }
                          >
                            Request deferral
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-muted" style={{ margin: 0 }}>
                        No due dates found.
                      </p>
                    )}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Quick tools</h2>
                    <p className="text-muted">Search, filter, export.</p>
                  </div>

                  <div style={{ display: "grid", gap: 10 }}>
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search course, code, status…"
                      className="input"
                      style={{ width: "100%" }}
                    />

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="input"
                        style={{ minWidth: 180 }}
                        aria-label="Filter by status"
                      >
                        <option value="ALL">All statuses</option>
                        <option value="OVERDUE">Overdue</option>
                        <option value="DUE_SOON">Due soon</option>
                        <option value="DEFERRED">Deferred</option>
                        <option value="SCHEDULED_ONLY">Scheduled</option>
                        <option value="NOT_DONE">Not done</option>
                        <option value="OK">OK</option>
                      </select>

                      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={actionOnly}
                          onChange={(e) => setActionOnly(e.target.checked)}
                        />
                        <span className="text-muted">Action required only</span>
                      </label>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="secondary-chip-btn"
                        onClick={() => setSelectedDateKey(null)}
                      >
                        Clear calendar filter
                      </button>
                      <button type="button" className="secondary-chip-btn" onClick={exportCsv}>
                        Export CSV
                      </button>
                      <button type="button" className="secondary-chip-btn" onClick={exportPdf}>
                        Export PDF
                      </button>
                      <button
                        type="button"
                        className="secondary-chip-btn"
                        onClick={exportTrainingRecordPdf}
                      >
                        Download training record
                      </button>
                      <button type="button" className="primary-chip-btn" onClick={reload}>
                        Refresh
                      </button>
                    </div>

                    {selectedDateKey ? (
                      <div className="card card--info" style={{ marginTop: 4 }}>
                        <p style={{ margin: 0 }}>
                          Calendar filter active: <strong>{selectedDateKey}</strong>
                        </p>
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Revocation watch</h2>
                    <p className="text-muted">
                      Overdue courses can trigger certification reviews.
                    </p>
                  </div>
                  {revocationAlerts.length > 0 ? (
                    <div style={{ display: "grid", gap: 10 }}>
                      {revocationAlerts.slice(0, 4).map(({ item, risk }) => (
                        <div
                          key={item.course_id}
                          style={{
                            padding: 12,
                            borderRadius: 12,
                            background: "rgba(255,255,255,0.04)",
                          }}
                        >
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <span className={revocationRiskClass(risk)}>
                              {revocationRiskLabel(risk)}
                            </span>
                            <span className="badge badge--neutral">
                              {item.course_id}
                            </span>
                          </div>
                          <div style={{ fontWeight: 700, marginTop: 6 }}>{item.course_name}</div>
                          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                            Overdue by{" "}
                            {typeof item.days_until_due === "number"
                              ? Math.abs(item.days_until_due)
                              : "—"}{" "}
                            day(s). Upload evidence or request a deferral if applicable.
                          </div>
                        </div>
                      ))}
                      {revocationAlerts.length > 4 ? (
                        <p className="text-muted" style={{ margin: 0 }}>
                          {revocationAlerts.length - 4} additional items are overdue.
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-muted" style={{ margin: 0 }}>
                      No courses are at revocation risk right now.
                    </p>
                  )}
                </div>
              </div>
            </section>

            <section className="page-section" id="training-workflow">
              <div className="card">
                <div className="card-header">
                  <h2>Your training workflow</h2>
                  <p className="text-muted">
                    Simple steps for staying compliant and documenting delays.
                  </p>
                </div>
                <div style={{ display: "grid", gap: 12 }}>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                      gap: 12,
                    }}
                  >
                    <div style={{ padding: 12, borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                      <div className="table-primary-text">1. Review due dates</div>
                      <p className="text-muted" style={{ marginTop: 6 }}>
                        Use the calendar and “All courses” list to check what is due soon or
                        overdue.
                      </p>
                    </div>
                    <div style={{ padding: 12, borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                      <div className="table-primary-text">2. Book or attend training</div>
                      <p className="text-muted" style={{ marginTop: 6 }}>
                        Confirm your scheduled sessions and mark attendance once completed.
                      </p>
                    </div>
                    <div style={{ padding: 12, borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                      <div className="table-primary-text">3. Request deferrals when needed</div>
                      <p className="text-muted" style={{ marginTop: 6 }}>
                        Provide a clear reason and supporting evidence to help Quality approve
                        faster.
                      </p>
                    </div>
                    <div style={{ padding: 12, borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
                      <div className="table-primary-text">4. Upload evidence</div>
                      <p className="text-muted" style={{ marginTop: 6 }}>
                        Certificates, medical notes, passport copies, and other documents should
                        be stored in the evidence section for audits.
                      </p>
                    </div>
                  </div>
                  <div className="card card--info">
                    <p style={{ margin: 0 }}>
                      Tip: if a course is overdue, submit a deferral and attach evidence immediately
                      to reduce the risk of certification review or revocation.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section className="page-section" id="training-deferrals">
              <div className="card">
                <div className="card-header">
                  <h2>Deferral requests</h2>
                  <p className="text-muted">
                    Track approvals, rejections, and new scheduled due dates.
                  </p>
                </div>

                {deferralsLoading && (
                  <div className="card card--info">
                    <p style={{ margin: 0 }}>Loading deferral requests…</p>
                  </div>
                )}

                {deferralsError && (
                  <div className="card card--error">
                    <p style={{ margin: 0 }}>{deferralsError}</p>
                    <button type="button" className="secondary-chip-btn" onClick={loadDeferrals}>
                      Retry
                    </button>
                  </div>
                )}

                {!deferralsLoading && !deferralsError && (
                  <div className="table-responsive">
                    <table className="table table-striped table-compact">
                      <thead>
                        <tr>
                          <th>Course</th>
                          <th>Requested</th>
                          <th>New due date</th>
                          <th>Status</th>
                          <th>Decision</th>
                          <th>Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {deferrals.map((deferral) => (
                          <tr key={deferral.id}>
                            <td>
                              <div className="table-primary-text">
                                {courseNameById.get(deferral.course_id) || "Training course"}
                              </div>
                              <div className="table-secondary-text">{deferral.course_id}</div>
                            </td>
                            <td>{formatDate(deferral.original_due_date)}</td>
                            <td>
                              <strong>{formatDate(deferral.requested_new_due_date)}</strong>
                            </td>
                            <td>
                              <span className={deferralStatusBadge(deferral.status)}>
                                {deferralStatusLabel(deferral.status)}
                              </span>
                            </td>
                            <td>{deferral.decision_comment || "—"}</td>
                            <td>
                              {deferral.decided_at
                                ? new Date(deferral.decided_at).toLocaleString()
                                : "Pending"}
                            </td>
                          </tr>
                        ))}
                        {deferrals.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="text-center text-muted">
                              No deferral requests yet.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>

            {/* Calendar + list */}
            <section className="page-section" id="training-calendar">
              <div
                className="page-section__grid"
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(320px, 1.1fr) minmax(320px, 0.9fr)",
                  gap: 12,
                  alignItems: "start",
                }}
              >
                <div style={{ display: "grid", gap: 10 }}>
                  <div className="card">
                    <div className="card-header">
                      <h2
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 10,
                        }}
                      >
                        <span>
                          {calendarMonth.toLocaleDateString(undefined, {
                            month: "long",
                            year: "numeric",
                          })}
                        </span>
                        <span style={{ display: "flex", gap: 8 }}>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => shiftMonth(-1)}
                          >
                            Prev
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => shiftMonth(1)}
                          >
                            Next
                          </button>
                        </span>
                      </h2>
                      <p className="text-muted" style={{ margin: 0 }}>
                        Click a day to filter the table.
                      </p>
                    </div>
                  </div>

                  <MonthCalendar
                    monthDate={calendarMonth}
                    itemsByDate={itemsByDate}
                    selectedDateKey={selectedDateKey}
                    onSelectDateKey={setSelectedDateKey}
                  />
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Upcoming (next 30 days)</h2>
                    <p className="text-muted">Due dates and scheduled events.</p>
                  </div>

                  <div className="table-responsive">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Type</th>
                          <th>Course</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(() => {
                          const today = startOfDay(new Date());
                          const upcoming: Array<{ date: Date; type: CalendarItemType; item: CalendarItem }> = [];

                          for (const [dk, arr] of itemsByDate.entries()) {
                            const d = parseDate(dk);
                            if (!d) continue;
                            const diff = daysBetween(today, d);
                            if (diff < 0 || diff > 30) continue;

                            for (const it of arr) {
                              upcoming.push({ date: d, type: it.type, item: it });
                            }
                          }

                          upcoming.sort((a, b) => a.date.getTime() - b.date.getTime());

                          const view = upcoming.slice(0, 20);

                          if (view.length === 0) {
                            return (
                              <tr>
                                <td colSpan={3} className="text-muted">
                                  Nothing scheduled / due in the next 30 days.
                                </td>
                              </tr>
                            );
                          }

                          return view.map((u) => (
                            <tr
                              key={`${u.item.key}`}
                              style={{ cursor: "pointer" }}
                              onClick={() => {
                                setSelectedDateKey(u.item.dateKey);
                                setSelectedCourseId(u.item.courseId);
                              }}
                            >
                              <td>{formatDate(u.item.dateKey)}</td>
                              <td>
                                <span
                                  className={
                                    u.type === "DUE" ? "badge badge--warning" : "badge badge--neutral"
                                  }
                                >
                                  {u.type === "DUE" ? "Due" : "Event"}
                                </span>
                              </td>
                              <td>{u.item.courseName}</td>
                            </tr>
                          ));
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </section>

            {/* Table */}
            <section className="page-section" id="training-courses">
              <div className="card">
                <div className="card-header">
                  <h2>All courses</h2>
                  <p className="text-muted">Click a row for details. Sort by clicking headers.</p>
                </div>

                <div className="table-responsive">
                  <table className="table table-striped table-compact">
                    <thead>
                      <tr>
                        <th onClick={() => handleSortChange("course_name")} style={{ cursor: "pointer" }}>
                          Course
                          {sort.field === "course_name" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                        <th>Frequency</th>
                        <th onClick={() => handleSortChange("status")} style={{ cursor: "pointer" }}>
                          Status
                          {sort.field === "status" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                        <th>Last completion</th>
                        <th onClick={() => handleSortChange("due_date")} style={{ cursor: "pointer" }}>
                          Due date
                          {sort.field === "due_date" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                        <th onClick={() => handleSortChange("days_until_due")} style={{ cursor: "pointer" }}>
                          Days left
                          {sort.field === "days_until_due" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                        <th onClick={() => handleSortChange("cycle_progress")} style={{ cursor: "pointer" }}>
                          Cycle
                          {sort.field === "cycle_progress" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                        <th onClick={() => handleSortChange("upcoming_event_date")} style={{ cursor: "pointer" }}>
                          Upcoming event
                          {sort.field === "upcoming_event_date" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedItems.map((item) => {
                        const due = getDueDate(item);
                        const progress = computeCycleProgress(item);
                        const days = item.days_until_due;

                        return (
                          <tr
                            key={item.course_id}
                            style={{ cursor: "pointer" }}
                            onClick={() => setSelectedCourseId(item.course_id)}
                          >
                            <td>
                              <div className="table-primary-text">{item.course_name}</div>
                              <div className="table-secondary-text">{item.course_id}</div>
                            </td>
                            <td>{item.frequency_months ?? "-"}</td>
                            <td>
                              <span className={badgeClass(item.status)}>{statusLabelDisplay(item.status)}</span>
                            </td>
                            <td>{formatDate(item.last_completion_date)}</td>
                            <td>{formatDate(due)}</td>
                            <td>
                              {typeof days === "number" ? (
                                days >= 0 ? (
                                  <span>{days}</span>
                                ) : (
                                  <span className="badge badge--danger">-{Math.abs(days)}</span>
                                )
                              ) : (
                                ""
                              )}
                            </td>
                            <td style={{ minWidth: 140 }}>
                              {progress == null ? (
                                <span className="text-muted">—</span>
                              ) : (
                                <div
                                  style={{
                                    height: 10,
                                    borderRadius: 999,
                                    background: "rgba(255,255,255,0.08)",
                                    overflow: "hidden",
                                  }}
                                  title={`${Math.round(progress * 100)}%`}
                                >
                                  <div
                                    style={{
                                      width: `${Math.round(progress * 100)}%`,
                                      height: "100%",
                                      background: "rgba(255,255,255,0.55)",
                                    }}
                                  />
                                </div>
                              )}
                            </td>
                            <td>
                              {item.upcoming_event_date ? (
                                <span>{formatDate(item.upcoming_event_date)}</span>
                              ) : (
                                <span className="text-muted">None</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}

                      {sortedItems.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="text-center text-muted">
                            No courses match the current filters.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            {/* Training evidence files */}
            <section className="page-section" id="training-evidence">
              <div className="card">
                <div className="card-header">
                  <h2>Training evidence files</h2>
                  <p className="text-muted">
                    Store certificates, medical notes, passport copies, and other supporting
                    evidence for audit trails.
                  </p>
                </div>
                <div className="card card--info" style={{ marginBottom: 12 }}>
                  <p style={{ margin: 0 }}>
                    Evidence should clearly explain why you could not attend. If you need to upload
                    new evidence, upload it below and link it to the relevant course or deferral.
                  </p>
                </div>

                <div
                  style={{
                    display: "grid",
                    gap: 12,
                    padding: 12,
                    borderRadius: 12,
                    border: "1px solid rgba(148, 163, 184, 0.3)",
                    marginBottom: 12,
                  }}
                >
                  <div className="table-primary-text">Upload evidence</div>
                  <div style={{ display: "grid", gap: 10 }}>
                    <input
                      type="file"
                      className="input"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    />
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <select
                        className="input"
                        value={uploadKind}
                        onChange={(e) => setUploadKind(e.target.value)}
                      >
                        <option value="CERTIFICATE">Certificate</option>
                        <option value="AMEL">AMEL</option>
                        <option value="LICENSE">License</option>
                        <option value="EVIDENCE">Evidence</option>
                        <option value="OTHER">Other</option>
                      </select>
                      <select
                        className="input"
                        value={uploadCourseId}
                        onChange={(e) => setUploadCourseId(e.target.value)}
                      >
                        <option value="">Attach to course (optional)</option>
                        {courses.map((course) => (
                          <option key={course.id} value={course.id}>
                            {course.course_name} ({course.course_id})
                          </option>
                        ))}
                      </select>
                      <select
                        className="input"
                        value={uploadDeferralId}
                        onChange={(e) => setUploadDeferralId(e.target.value)}
                      >
                        <option value="">Attach to deferral (optional)</option>
                        {deferrals.map((deferral) => (
                          <option key={deferral.id} value={deferral.id}>
                            {courseNameById.get(deferral.course_id) || "Course"} ·{" "}
                            {deferralStatusLabel(deferral.status)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="primary-chip-btn"
                        onClick={handleUploadTrainingFile}
                        disabled={uploadSaving}
                      >
                        {uploadSaving ? "Uploading…" : "Upload evidence"}
                      </button>
                    </div>
                  </div>
                  {uploadError && (
                    <div className="card card--error">
                      <p style={{ margin: 0 }}>{uploadError}</p>
                    </div>
                  )}
                  {uploadSuccess && (
                    <div className="card card--success">
                      <p style={{ margin: 0 }}>{uploadSuccess}</p>
                    </div>
                  )}
                </div>

                {trainingFilesLoading && (
                  <div className="card card--info">
                    <p style={{ margin: 0 }}>Loading training files…</p>
                  </div>
                )}

                {trainingFilesError && (
                  <div className="card card--error">
                    <p style={{ margin: 0 }}>{trainingFilesError}</p>
                    <button type="button" className="secondary-chip-btn" onClick={loadTrainingFiles}>
                      Retry
                    </button>
                  </div>
                )}

                {!trainingFilesLoading && !trainingFilesError && (
                  <div className="table-responsive">
                    <table className="table table-striped table-compact">
                      <thead>
                        <tr>
                          <th>Filename</th>
                          <th>Type</th>
                          <th>Status</th>
                          <th>Uploaded</th>
                          <th>Size</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {trainingFiles.map((file) => {
                          const isDownloading = downloadProgress?.fileId === file.id;
                          const sizeMb =
                            typeof file.size_bytes === "number"
                              ? `${(file.size_bytes / (1024 * 1024)).toFixed(2)} MB`
                              : "—";
                          return (
                            <tr key={file.id}>
                              <td>{file.original_filename || "—"}</td>
                              <td>{file.kind || "OTHER"}</td>
                              <td>{file.review_status || "PENDING"}</td>
                              <td>{new Date(file.uploaded_at).toLocaleString()}</td>
                              <td>{sizeMb}</td>
                              <td>
                                <button
                                  type="button"
                                  className="secondary-chip-btn"
                                  onClick={() => handleDownloadTrainingFile(file)}
                                >
                                  Download
                                </button>
                                {isDownloading && (
                                  <div style={{ marginTop: 8 }}>
                                    {downloadProgress?.progress.percent !== undefined && (
                                      <progress
                                        value={downloadProgress.progress.percent}
                                        max={100}
                                        style={{ width: "100%", height: 8 }}
                                      />
                                    )}
                                    <p style={{ marginTop: 6, opacity: 0.8 }}>
                                      {formatSpeed(downloadProgress.progress)}
                                    </p>
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                        {trainingFiles.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="text-center text-muted">
                              No training files uploaded yet.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>

            {/* Details drawer */}
            {selectedItem ? (
              <div
                role="dialog"
                aria-modal="true"
                onClick={() => setSelectedCourseId(null)}
                style={{
                  position: "fixed",
                  inset: 0,
                  background: "rgba(0,0,0,0.55)",
                  display: "grid",
                  placeItems: "center",
                  padding: 16,
                  zIndex: 9999,
                }}
              >
                <div
                  className="card"
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    width: "min(860px, 96vw)",
                    maxHeight: "86vh",
                    overflow: "auto",
                  }}
                >
                  <div className="card-header">
                    <h2 style={{ marginBottom: 4 }}>{selectedItem.course_name}</h2>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {selectedItem.course_id}
                    </p>
                  </div>

                  <div style={{ padding: 16, display: "grid", gap: 12 }}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className={badgeClass(selectedItem.status)}>
                        {statusLabelDisplay(selectedItem.status)}
                      </span>
                      {getRevocationRisk(selectedItem.days_until_due) ? (
                        <span className={revocationRiskClass(getRevocationRisk(selectedItem.days_until_due)!)}>
                          {revocationRiskLabel(getRevocationRisk(selectedItem.days_until_due)!)}
                        </span>
                      ) : null}
                      {selectedItem.frequency_months != null ? (
                        <span className="badge badge--neutral">
                          Frequency: {selectedItem.frequency_months} months
                        </span>
                      ) : null}
                      {selectedItem.upcoming_event_date ? (
                        <span className="badge badge--info">
                          Upcoming: {formatDate(selectedItem.upcoming_event_date)}
                        </span>
                      ) : null}
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                        gap: 12,
                      }}
                    >
                      <div
                        style={{
                          padding: 12,
                          borderRadius: 12,
                          background: "rgba(255,255,255,0.04)",
                        }}
                      >
                        <div className="text-muted" style={{ fontSize: 12 }}>
                          Last completion
                        </div>
                        <div style={{ fontWeight: 700 }}>
                          {formatDate(selectedItem.last_completion_date) || "—"}
                        </div>
                      </div>

                      <div
                        style={{
                          padding: 12,
                          borderRadius: 12,
                          background: "rgba(255,255,255,0.04)",
                        }}
                      >
                        <div className="text-muted" style={{ fontSize: 12 }}>
                          Due date (controlling)
                        </div>
                        <div style={{ fontWeight: 700 }}>
                          {formatDate(getDueDate(selectedItem)) || "—"}
                        </div>
                        {typeof selectedItem.days_until_due === "number" ? (
                          <div className="text-muted" style={{ fontSize: 12, marginTop: 6 }}>
                            {selectedItem.days_until_due < 0
                              ? `Overdue by ${Math.abs(selectedItem.days_until_due)} day(s)`
                              : `${selectedItem.days_until_due} day(s) remaining`}
                          </div>
                        ) : null}
                      </div>

                      <div
                        style={{
                          padding: 12,
                          borderRadius: 12,
                          background: "rgba(255,255,255,0.04)",
                        }}
                      >
                        <div className="text-muted" style={{ fontSize: 12 }}>
                          Cycle progress
                        </div>
                        {computeCycleProgress(selectedItem) == null ? (
                          <div style={{ fontWeight: 700 }}>—</div>
                        ) : (
                          <ProgressBar value={computeCycleProgress(selectedItem)!} />
                        )}
                      </div>
                    </div>

                    {(() => {
                      const selectedCoursePk = coursePkByCode[selectedItem.course_id];
                      const relatedDeferrals = selectedCoursePk
                        ? deferrals.filter((d) => d.course_id === selectedCoursePk)
                        : [];
                      if (relatedDeferrals.length === 0) return null;
                      return (
                        <div>
                          <div className="table-primary-text" style={{ marginBottom: 8 }}>
                            Deferral history
                          </div>
                          <div style={{ display: "grid", gap: 8 }}>
                            {relatedDeferrals.map((deferral) => (
                              <div
                                key={deferral.id}
                                style={{
                                  padding: 12,
                                  borderRadius: 12,
                                  background: "rgba(255,255,255,0.04)",
                                  display: "grid",
                                  gap: 6,
                                }}
                              >
                                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                  <span className={deferralStatusBadge(deferral.status)}>
                                    {deferralStatusLabel(deferral.status)}
                                  </span>
                                  <span className="badge badge--neutral">
                                    Requested: {formatDate(deferral.original_due_date)}
                                  </span>
                                  <span className="badge badge--neutral">
                                    New due: {formatDate(deferral.requested_new_due_date)}
                                  </span>
                                </div>
                                <div className="text-muted" style={{ fontSize: 12 }}>
                                  {deferral.decision_comment || "No decision comment yet."}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    <div className="card card--info">
                      <p style={{ margin: 0 }}>
                        Use the actions below to request a deferral (if needed) or view scheduled event details.
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => openDeferral(selectedItem)}
                          disabled={!getDueDate(selectedItem) || !coursesLoaded}
                          title={
                            !coursesLoaded
                              ? "Courses catalogue still loading"
                              : !getDueDate(selectedItem)
                              ? "No due date available"
                              : "Request a deferral"
                          }
                        >
                          Request deferral
                        </button>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => openEventDetails(selectedItem)}
                          disabled={!selectedItem.upcoming_event_id || !coursesLoaded}
                          title={
                            !selectedItem.upcoming_event_id
                              ? "No upcoming event on this course"
                              : !coursesLoaded
                              ? "Courses catalogue still loading"
                              : "View event details"
                          }
                        >
                          Event details
                        </button>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                      <button type="button" className="secondary-chip-btn" onClick={() => setSelectedCourseId(null)}>
                        Close
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Event modal */}
            {eventOpen ? (
              <div
                role="dialog"
                aria-modal="true"
                onClick={() => setEventOpen(false)}
                style={{
                  position: "fixed",
                  inset: 0,
                  background: "rgba(0,0,0,0.55)",
                  display: "grid",
                  placeItems: "center",
                  padding: 16,
                  zIndex: 10000,
                }}
              >
                <div
                  className="card"
                  onClick={(e) => e.stopPropagation()}
                  style={{ width: "min(720px, 96vw)", maxHeight: "86vh", overflow: "auto" }}
                >
                  <div className="card-header">
                    <h2 style={{ marginBottom: 4 }}>Event details</h2>
                    <p className="text-muted" style={{ margin: 0 }}>
                      Upcoming training session information.
                    </p>
                  </div>

                  <div style={{ padding: 16, display: "grid", gap: 10 }}>
                    {eventLoading ? (
                      <div className="card card--info">
                        <p style={{ margin: 0 }}>Loading event…</p>
                      </div>
                    ) : null}

                    {eventError ? (
                      <div className="card card--error">
                        <p style={{ margin: 0 }}>{eventError}</p>
                      </div>
                    ) : null}

                    {eventDetails ? (
                      <div style={{ display: "grid", gap: 10 }}>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <span className="badge badge--neutral">
                            Status: {String(eventDetails.status || "").replace(/_/g, " ")}
                          </span>
                          <span className="badge badge--neutral">
                            Start: {formatDate(eventDetails.starts_on)}
                          </span>
                          {eventDetails.ends_on ? (
                            <span className="badge badge--neutral">
                              End: {formatDate(eventDetails.ends_on)}
                            </span>
                          ) : null}
                        </div>

                        <div
                          style={{
                            padding: 12,
                            borderRadius: 12,
                            background: "rgba(255,255,255,0.04)",
                            display: "grid",
                            gap: 8,
                          }}
                        >
                          <div>
                            <div className="text-muted" style={{ fontSize: 12 }}>
                              Title
                            </div>
                            <div style={{ fontWeight: 700 }}>{eventDetails.title || "—"}</div>
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                            <div>
                              <div className="text-muted" style={{ fontSize: 12 }}>
                                Location
                              </div>
                              <div style={{ fontWeight: 600 }}>{eventDetails.location || "—"}</div>
                            </div>
                            <div>
                              <div className="text-muted" style={{ fontSize: 12 }}>
                                Provider
                              </div>
                              <div style={{ fontWeight: 600 }}>{eventDetails.provider || "—"}</div>
                            </div>
                          </div>

                          <div>
                            <div className="text-muted" style={{ fontSize: 12 }}>
                              Notes
                            </div>
                            <div style={{ whiteSpace: "pre-wrap" }}>{eventDetails.notes || "—"}</div>
                          </div>
                        </div>
                      </div>
                    ) : null}

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                      <button type="button" className="secondary-chip-btn" onClick={() => setEventOpen(false)}>
                        Close
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Deferral modal */}
            {deferralOpen && selectedItem ? (
              <div
                role="dialog"
                aria-modal="true"
                onClick={() => setDeferralOpen(false)}
                style={{
                  position: "fixed",
                  inset: 0,
                  background: "rgba(0,0,0,0.55)",
                  display: "grid",
                  placeItems: "center",
                  padding: 16,
                  zIndex: 10000,
                }}
              >
                <div
                  className="card"
                  onClick={(e) => e.stopPropagation()}
                  style={{ width: "min(720px, 96vw)", maxHeight: "86vh", overflow: "auto" }}
                >
                  <div className="card-header">
                    <h2 style={{ marginBottom: 4 }}>Request deferral</h2>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {selectedItem.course_name} · {selectedItem.course_id}
                    </p>
                  </div>

                  <div style={{ padding: 16, display: "grid", gap: 12 }}>
                    {deferralError ? (
                      <div className="card card--error">
                        <p style={{ margin: 0 }}>{deferralError}</p>
                      </div>
                    ) : null}

                    <div className="card card--info">
                      <p style={{ margin: 0 }}>
                        Provide evidence that supports the deferral (e.g., sick leave note, passport/visa
                        document, provider cancellation notice). Quality uses this during review and audits.
                      </p>
                      <ul style={{ marginTop: 8 }}>
                        <li>Document must include dates and issuing authority</li>
                        <li>Ensure the document matches the requested deferral window</li>
                        <li>Upload evidence in the Training evidence files section</li>
                      </ul>
                    </div>

                    <div
                      style={{
                        padding: 12,
                        borderRadius: 12,
                        background: "rgba(255,255,255,0.04)",
                        display: "grid",
                        gap: 10,
                      }}
                    >
                      <div style={{ display: "grid", gap: 6 }}>
                        <div className="text-muted" style={{ fontSize: 12 }}>
                          Original due date (controlling)
                        </div>
                        <div style={{ fontWeight: 700 }}>{formatDate(getDueDate(selectedItem)) || "—"}</div>
                      </div>

                      <div style={{ display: "grid", gap: 6 }}>
                        <label className="text-muted" style={{ fontSize: 12 }}>
                          Requested new due date
                        </label>
                        <input
                          className="input"
                          type="date"
                          value={deferralRequestedNewDate}
                          onChange={(e) => setDeferralRequestedNewDate(e.target.value)}
                          min={toDateKey(new Date())}
                        />
                      </div>

                      <div style={{ display: "grid", gap: 6 }}>
                        <label className="text-muted" style={{ fontSize: 12 }}>
                          Reason category
                        </label>
                        <select
                          className="input"
                          value={deferralReasonCategory}
                          onChange={(e) => setDeferralReasonCategory(e.target.value as any)}
                        >
                          <option value="ILLNESS">Illness</option>
                          <option value="OPERATIONAL_REQUIREMENTS">Operational requirements</option>
                          <option value="PERSONAL_EMERGENCY">Personal emergency</option>
                          <option value="PROVIDER_CANCELLATION">Provider cancellation</option>
                          <option value="SYSTEM_FAILURE">System failure</option>
                          <option value="OTHER">Other</option>
                        </select>
                      </div>

                      <div style={{ display: "grid", gap: 6 }}>
                        <label className="text-muted" style={{ fontSize: 12 }}>
                          Reason (optional)
                        </label>
                        <textarea
                          className="input"
                          value={deferralReasonText}
                          onChange={(e) => setDeferralReasonText(e.target.value)}
                          placeholder="Brief context to support the request…"
                          rows={4}
                        />
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
                      <button type="button" className="secondary-chip-btn" onClick={() => setDeferralOpen(false)}>
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="primary-chip-btn"
                        onClick={() => submitDeferral(selectedItem)}
                        disabled={deferralSaving || !coursesLoaded || !getDueDate(selectedItem)}
                      >
                        {deferralSaving ? "Submitting…" : "Submit request"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Toast */}
            {toast ? (
              <div
                style={{
                  position: "fixed",
                  right: 16,
                  bottom: 16,
                  zIndex: 11000,
                  maxWidth: 420,
                }}
              >
                <div className={toast.type === "success" ? "card card--success" : "card card--error"}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                    <p style={{ margin: 0 }}>{toast.text}</p>
                    <button
                      type="button"
                      className="secondary-chip-btn"
                      onClick={() => setToast(null)}
                      style={{ whiteSpace: "nowrap" }}
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
}

export default MyTrainingPage;

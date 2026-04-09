import React, { useEffect, useMemo, useState } from "react";
import {
  Award,
  BookOpenCheck,
  CalendarClock,
  Download,
  ExternalLink,
  FileDown,
  Plus,
  Printer,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  UploadCloud,
  Users,
} from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import Drawer from "../components/shared/Drawer";
import { useToast } from "../components/feedback/ToastProvider";
import { getCachedUser } from "../services/auth";
import {
  createTrainingCourse,
  createTrainingRequirement,
  downloadTrainingUserEvidencePack,
  getBulkTrainingStatusForUsers,
  getTrainingDashboardSummary,
  getUserTrainingAccessState,
  getUserTrainingStatus,
  importTrainingCoursesWorkbook,
  importTrainingRecordsWorkbook,
  issueTrainingCertificate,
  listTrainingCertificates,
  listTrainingCourses,
  listTrainingDeferrals,
  listTrainingEvents,
  listTrainingRecords,
  listTrainingRequirements,
  updateTrainingCourse,
  type TransferProgress,
} from "../services/training";
import {
  getAdminUserDirectory,
  type AdminUserDirectoryItem,
  type AdminUserDirectoryMetrics,
} from "../services/adminUsers";
import type {
  CourseImportSummary,
  TrainingRecordImportSummary,
  TrainingAccessState,
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventRead,
  TrainingRecordRead,
  TrainingRequirementCreate,
  TrainingRequirementRead,
  TrainingStatusItem,
  TrainingDashboardSummary,
  TrainingRequirementScope,
} from "../types/training";
import { shouldUseMockData } from "../services/runtimeMode";
import "../styles/training-competence.css";

type SectionKey =
  | "overview"
  | "matrix"
  | "schedule"
  | "sessions"
  | "attendance"
  | "assessments"
  | "certificates"
  | "personnel"
  | "templates"
  | "settings";

const sectionItems: Array<{ key: SectionKey; title: string; desc: string; icon: React.ReactNode }> = [
  { key: "overview", title: "Overview", desc: "Compliance posture and hot items", icon: <ShieldAlert size={16} /> },
  { key: "matrix", title: "Matrix", desc: "Courses and applicability rules", icon: <BookOpenCheck size={16} /> },
  { key: "schedule", title: "Schedule", desc: "Sessions and upcoming delivery", icon: <CalendarClock size={16} /> },
  { key: "personnel", title: "Personnel", desc: "Per-person records and PDF export", icon: <Users size={16} /> },
  { key: "certificates", title: "Certificates", desc: "Issued certificates and verification", icon: <Award size={16} /> },
  { key: "settings", title: "Policy", desc: "Training rules and reminder controls", icon: <Settings2 size={16} /> },
  { key: "templates", title: "Evidence", desc: "Audit pack exports and templates", icon: <FileDown size={16} /> },
];

const sampleCourses: TrainingCourseRead[] = [
  {
    id: "sample-course-1",
    amo_id: "sample",
    course_id: "HF-REF",
    course_name: "Sample Human Factors Refresher",
    frequency_months: 24,
    is_mandatory: true,
    mandatory_for_all: true,
    is_active: true,
    created_by_user_id: null,
    updated_by_user_id: null,
    category: null,
    category_raw: "Human Factors",
    status: "Recurrent",
    scope: "All Staff",
    kind: null,
    delivery_method: null,
    regulatory_reference: "MTM 2.13",
    default_provider: "Internal",
    default_duration_days: 1,
    prerequisite_course_id: null,
  },
];

const sampleEvents: TrainingEventRead[] = [
  {
    id: "sample-event-1",
    amo_id: "sample",
    course_id: "sample-course-1",
    title: "Sample HF Session",
    location: "Training Room",
    provider: "Internal",
    starts_on: "2026-03-20",
    ends_on: null,
    status: "PLANNED",
    notes: "Sample",
    created_by_user_id: null,
  },
];

const sampleRecords: TrainingRecordRead[] = [
  {
    id: "sample-record-1",
    amo_id: "sample",
    user_id: "sample-user",
    course_id: "sample-course-1",
    event_id: "sample-event-1",
    completion_date: "2026-03-01",
    valid_until: "2028-03-01",
    hours_completed: 8,
    exam_score: 87,
    certificate_reference: "SAMPLE-CERT-0001",
    remarks: "Sample",
    is_manual_entry: false,
    created_by_user_id: null,
    verification_status: "VERIFIED",
    verified_at: null,
    verified_by_user_id: null,
    verification_comment: null,
  },
];

const sampleRequirements: TrainingRequirementRead[] = [
  {
    id: "sample-req-1",
    amo_id: "sample",
    course_pk: "sample-course-1",
    scope: "ALL",
    department_code: null,
    job_role: null,
    user_id: null,
    is_mandatory: true,
    is_active: true,
    effective_from: null,
    effective_to: null,
    created_by_user_id: null,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
];

const sampleDirectory: AdminUserDirectoryItem[] = [
  {
    id: "sample-user",
    amo_id: "sample",
    department_id: null,
    department_name: "Quality & Compliance",
    staff_code: "SAM01",
    email: "sample@safarilink.test",
    first_name: "Sample",
    last_name: "Engineer",
    full_name: "Sample Engineer",
    role: "AMO_ADMIN",
    position_title: "Quality Support",
    is_active: true,
    is_superuser: false,
    is_amo_admin: true,
    display_title: "Quality Support",
    last_login_at: "2026-03-10T08:00:00Z",
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-10T08:00:00Z",
    presence: {
      state: "online",
      is_online: true,
      last_seen_at: "2026-03-10T08:30:00Z",
      source: "sample",
    },
    presence_display: {
      status_label: "Online",
      last_seen_label: "Active now",
      last_seen_at: "2026-03-10T08:30:00Z",
      last_seen_at_display: "10 Mar 2026, 08:30",
    },
  },
];

const sampleMetrics: AdminUserDirectoryMetrics = {
  total_users: 1,
  active_users: 1,
  inactive_users: 0,
  online_users: 1,
  away_users: 0,
  recently_active_users: 1,
  departmentless_users: 0,
  managers: 1,
};

const sampleDashboard: TrainingDashboardSummary = {
  total_mandatory_records: 1,
  ok_count: 1,
  due_soon_count: 0,
  overdue_count: 0,
  deferred_count: 0,
  scheduled_count: 1,
  not_done_count: 0,
};

const EMPTY_METRICS: AdminUserDirectoryMetrics = {
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  online_users: 0,
  away_users: 0,
  recently_active_users: 0,
  departmentless_users: 0,
  managers: 0,
};

const EMPTY_ACCESS_STATE: TrainingAccessState = {
  user_id: "",
  portal_locked: false,
  portal_lock_reason: null,
  crs_blocked: false,
  overdue_mandatory_count: 0,
  due_soon_mandatory_count: 0,
  deferred_mandatory_count: 0,
  not_done_mandatory_count: 0,
  ok_mandatory_count: 0,
  upcoming_scheduled_count: 0,
};

const TRAINING_WORKSPACE_CACHE_MAX_AGE_MS = 5 * 60_000;
const TRAINING_WORKSPACE_SKIP_REFRESH_MS = 45_000;

type CacheEnvelope<T> = {
  savedAt: number;
  data: T;
};

function readSessionCache<T>(key: string, maxAgeMs: number): CacheEnvelope<T> | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope<T>;
    if (!parsed || typeof parsed.savedAt !== "number") return null;
    if (Date.now() - parsed.savedAt > maxAgeMs) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeSessionCache<T>(key: string, data: T): void {
  try {
    const payload: CacheEnvelope<T> = { savedAt: Date.now(), data };
    sessionStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // ignore cache write failures
  }
}

function formatIsoDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(date);
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatRelativeFromNow(value?: string | null): string {
  if (!value) return "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(Math.floor(diffMs / 60000), 0);
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function humanizeEnum(value?: string | null): string {
  if (!value) return "—";
  return String(value)
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getDueDate(item: TrainingStatusItem): string | null {
  return item.extended_due_date || item.valid_until || null;
}

function statusClass(status: string): string {
  switch (status) {
    case "OK":
      return "ok";
    case "DUE_SOON":
      return "due-soon";
    case "OVERDUE":
      return "overdue";
    case "DEFERRED":
      return "deferred";
    case "SCHEDULED_ONLY":
      return "scheduled";
    case "NOT_DONE":
      return "not-done";
    default:
      return "not-done";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "DUE_SOON":
      return "Due soon";
    case "OVERDUE":
      return "Overdue";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled";
    case "NOT_DONE":
      return "Not done";
    default:
      return humanizeEnum(status);
  }
}

function saveBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function requirementScopeBadge(
  requirement: TrainingRequirementRead,
  userDirectory: Map<string, AdminUserDirectoryItem>,
): { label: string; value: string } {
  switch (requirement.scope) {
    case "ALL":
      return { label: "All staff", value: "Mandatory" };
    case "DEPARTMENT":
      return { label: "Department", value: requirement.department_code || "—" };
    case "JOB_ROLE":
      return { label: "Role", value: requirement.job_role || "—" };
    case "USER": {
      const user = requirement.user_id ? userDirectory.get(requirement.user_id) : null;
      return { label: "User", value: user ? `${user.full_name} (${user.staff_code})` : requirement.user_id || "—" };
    }
    default:
      return { label: humanizeEnum(requirement.scope), value: "—" };
  }
}

function buildApplicabilitySummary(
  course: TrainingCourseRead,
  requirements: TrainingRequirementRead[],
  userDirectory: Map<string, AdminUserDirectoryItem>,
): Array<{ label: string; value: string }> {
  const explicit = requirements
    .filter((item) => item.course_pk === course.id && item.is_active)
    .map((item) => requirementScopeBadge(item, userDirectory));
  if (explicit.length > 0) return explicit;

  if (course.mandatory_for_all) return [{ label: "All staff", value: "Mandatory" }];
  if (course.scope && course.scope.trim()) return [{ label: "Imported scope", value: course.scope.trim() }];
  if (course.is_mandatory) return [{ label: "Mandatory", value: "Manual assignment pending" }];
  return [{ label: "Applicability", value: "Not assigned" }];
}

function buildTrainingRecordPdf(params: {
  user: AdminUserDirectoryItem;
  amoCode: string;
  statuses: TrainingStatusItem[];
  records: TrainingRecordRead[];
  coursesById: Map<string, TrainingCourseRead>;
}): void {
  if (typeof window === "undefined") return;
  const { user, amoCode, statuses, records, coursesById } = params;

  const rows = statuses
    .slice()
    .sort((a, b) => a.course_id.localeCompare(b.course_id))
    .map((item) => ({
      courseId: escapeHtml(item.course_id),
      courseName: escapeHtml(item.course_name),
      lastCompletion: escapeHtml(formatIsoDate(item.last_completion_date) || "—"),
      nextDue: escapeHtml(formatIsoDate(getDueDate(item)) || "—"),
      status: escapeHtml(statusLabel(item.status)),
      nextEvent: escapeHtml(formatIsoDate(item.upcoming_event_date) || "—"),
    }));

  const historyRows = records
    .slice()
    .sort((a, b) => String(b.completion_date || "").localeCompare(String(a.completion_date || "")))
    .map((record) => {
      const course = coursesById.get(record.course_id);
      return `
        <tr>
          <td>${escapeHtml(course?.course_id || record.course_id)}</td>
          <td>${escapeHtml(course?.course_name || record.course_id)}</td>
          <td>${escapeHtml(formatIsoDate(record.completion_date))}</td>
          <td>${escapeHtml(formatIsoDate(record.valid_until))}</td>
          <td>${escapeHtml(record.exam_score == null ? "—" : String(record.exam_score))}</td>
          <td>${escapeHtml(record.certificate_reference || "—")}</td>
        </tr>
      `;
    })
    .join("");

  const win = window.open("", "_blank", "width=1100,height=820");
  if (!win) return;

  const tableRows = rows
    .map(
      (row) => `
        <tr>
          <td>${row.courseId}</td>
          <td>${row.courseName}</td>
          <td>${row.lastCompletion}</td>
          <td>${row.nextDue}</td>
          <td>${row.status}</td>
          <td>${row.nextEvent}</td>
        </tr>
      `,
    )
    .join("");

  win.document.write(`
    <html>
      <head>
        <title>Individual Training Record</title>
        <style>
          @page { size: A4; margin: 15mm; }
          body { font-family: "Segoe UI", Arial, sans-serif; color: #0f172a; margin: 0; }
          .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
          .brand { font-size: 28px; font-weight: 800; color: #b18f2c; letter-spacing: 0.02em; }
          .title { font-size: 22px; font-weight: 800; margin: 0; }
          .meta-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 18px; }
          .meta { border: 1px solid #d7dde7; border-radius: 12px; padding: 10px 12px; background: #f8fbff; }
          .meta span { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #667085; }
          .meta strong { display: block; margin-top: 4px; font-size: 14px; }
          h2 { margin: 20px 0 8px; font-size: 15px; letter-spacing: 0.04em; text-transform: uppercase; }
          table { width: 100%; border-collapse: collapse; font-size: 12px; }
          th, td { border: 1px solid #d1d5db; padding: 7px 8px; vertical-align: top; text-align: left; }
          th { background: #b18f2c; color: #fff; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
          tbody tr:nth-child(even) { background: #f8f5e9; }
          .footer { margin-top: 18px; font-size: 11px; color: #667085; text-align: right; }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <div class="brand">Safarilink</div>
            <p style="margin:4px 0 0;color:#667085;">${escapeHtml(amoCode.toUpperCase())} · Training & Competence</p>
          </div>
          <div>
            <h1 class="title">Individual Training Record</h1>
            <p style="margin:4px 0 0;color:#667085; text-align:right;">Printed ${escapeHtml(formatDateTime(new Date().toISOString()))}</p>
          </div>
        </div>

        <div class="meta-grid">
          <div class="meta"><span>Name</span><strong>${escapeHtml(user.full_name)}</strong></div>
          <div class="meta"><span>Staff Code</span><strong>${escapeHtml(user.staff_code || "—")}</strong></div>
          <div class="meta"><span>Title</span><strong>${escapeHtml(user.display_title || humanizeEnum(user.role))}</strong></div>
          <div class="meta"><span>Department</span><strong>${escapeHtml(user.department_name || "—")}</strong></div>
        </div>

        <h2>Current compliance matrix</h2>
        <table>
          <thead>
            <tr>
              <th>CourseID</th>
              <th>Course Name</th>
              <th>Last Training</th>
              <th>Next Due</th>
              <th>Status</th>
              <th>Next Session</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows || `<tr><td colspan="6">No training rows available.</td></tr>`}
          </tbody>
        </table>

        <h2>Historical record</h2>
        <table>
          <thead>
            <tr>
              <th>CourseID</th>
              <th>Course Name</th>
              <th>Completed</th>
              <th>Valid Until</th>
              <th>Score</th>
              <th>Certificate</th>
            </tr>
          </thead>
          <tbody>
            ${historyRows || `<tr><td colspan="6">No historical training records available.</td></tr>`}
          </tbody>
        </table>
        <div class="footer">Generated from AMO Portal Training & Competence workspace.</div>
      </body>
    </html>
  `);
  win.document.close();
  win.focus();
  win.print();
}

const TrainingCompetencePage: React.FC = () => {
  const { amoCode, department } = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentUser = getCachedUser();
  const sectionParam = (searchParams.get("section") || "overview") as SectionKey;
  const [section, setSection] = useState<SectionKey>(sectionParam);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSampleMode, setIsSampleMode] = useState(false);

  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [requirements, setRequirements] = useState<TrainingRequirementRead[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [records, setRecords] = useState<TrainingRecordRead[]>([]);
  const [certificates, setCertificates] = useState<TrainingRecordRead[]>([]);
  const [deferrals, setDeferrals] = useState<TrainingDeferralRequestRead[]>([]);
  const [directory, setDirectory] = useState<AdminUserDirectoryItem[]>([]);
  const [directoryMetrics, setDirectoryMetrics] = useState<AdminUserDirectoryMetrics>(EMPTY_METRICS);
  const [dashboardSummary, setDashboardSummary] = useState<TrainingDashboardSummary | null>(null);
  const [statusByUser, setStatusByUser] = useState<Record<string, TrainingStatusItem[]>>({});

  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedUserStatuses, setSelectedUserStatuses] = useState<TrainingStatusItem[]>([]);
  const [selectedUserRecords, setSelectedUserRecords] = useState<TrainingRecordRead[]>([]);
  const [selectedUserCertificates, setSelectedUserCertificates] = useState<TrainingRecordRead[]>([]);
  const [selectedAccessState, setSelectedAccessState] = useState<TrainingAccessState>(EMPTY_ACCESS_STATE);
  const [selectedUserLoading, setSelectedUserLoading] = useState(false);
  const [selectedUserError, setSelectedUserError] = useState<string | null>(null);

  const [courseSearch, setCourseSearch] = useState("");
  const [peopleSearch, setPeopleSearch] = useState("");
  const [drawer, setDrawer] = useState<{ title: string; body: React.ReactNode } | null>(null);
  const { pushToast } = useToast();

  const canManageCourses = Boolean(
    currentUser?.is_superuser || currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER",
  );

  const [courseFormOpen, setCourseFormOpen] = useState(false);
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [savingCourse, setSavingCourse] = useState(false);
  const [courseForm, setCourseForm] = useState({
    course_id: "",
    course_name: "",
    frequency_months: "",
    status: "One_Off",
    category_raw: "",
    is_mandatory: false,
    scope: "",
    regulatory_reference: "",
  });

  const [requirementFormOpen, setRequirementFormOpen] = useState(false);
  const [requirementSaving, setRequirementSaving] = useState(false);
  const [requirementUserQuery, setRequirementUserQuery] = useState("");
  const [requirementForm, setRequirementForm] = useState<TrainingRequirementCreate>({
    course_pk: "",
    scope: "ALL",
    department_code: null,
    job_role: null,
    user_id: null,
    is_mandatory: true,
    is_active: true,
    effective_from: null,
    effective_to: null,
  });

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importingMode, setImportingMode] = useState<"preview" | "apply" | null>(null);
  const [importProgress, setImportProgress] = useState<TransferProgress | null>(null);
  const [importSummary, setImportSummary] = useState<CourseImportSummary | null>(null);

  const [recordsImportOpen, setRecordsImportOpen] = useState(false);
  const [recordsImportFile, setRecordsImportFile] = useState<File | null>(null);
  const [recordsImportingMode, setRecordsImportingMode] = useState<"preview" | "apply" | null>(null);
  const [recordsImportProgress, setRecordsImportProgress] = useState<TransferProgress | null>(null);
  const [recordsImportSummary, setRecordsImportSummary] = useState<TrainingRecordImportSummary | null>(null);

  useEffect(() => {
    if (section !== sectionParam) setSection(sectionParam);
  }, [section, sectionParam]);

  const openSection = (next: SectionKey) => {
    setSection(next);
    const sp = new URLSearchParams(searchParams);
    sp.set("section", next);
    setSearchParams(sp, { replace: true });
  };

  const directoryById = useMemo(
    () => new Map(directory.map((item) => [item.id, item])),
    [directory],
  );

  const coursesByPk = useMemo(
    () => new Map(courses.map((course) => [course.id, course])),
    [courses],
  );

  const workspaceCacheKey = useMemo(
    () => `training-workspace:${amoCode || "amo"}:${department || "dept"}:${canManageCourses ? "editor" : "viewer"}`,
    [amoCode, canManageCourses, department],
  );

  const selectedUserCacheKey = useMemo(
    () => (selectedUserId ? `training-user:${amoCode || "amo"}:${selectedUserId}` : null),
    [amoCode, selectedUserId],
  );

  const load = async (force = false) => {
    const cached = !force ? readSessionCache<{
      isSampleMode: boolean;
      error: string | null;
      directory: AdminUserDirectoryItem[];
      directoryMetrics: AdminUserDirectoryMetrics;
      courses: TrainingCourseRead[];
      requirements: TrainingRequirementRead[];
      events: TrainingEventRead[];
      records: TrainingRecordRead[];
      deferrals: TrainingDeferralRequestRead[];
      certificates: TrainingRecordRead[];
      dashboardSummary: TrainingDashboardSummary | null;
      statusByUser: Record<string, TrainingStatusItem[]>;
    }>(workspaceCacheKey, TRAINING_WORKSPACE_CACHE_MAX_AGE_MS) : null;

    if (cached) {
      setIsSampleMode(cached.data.isSampleMode);
      setError(cached.data.error);
      setDirectory(cached.data.directory);
      setDirectoryMetrics(cached.data.directoryMetrics);
      setCourses(cached.data.courses);
      setRequirements(cached.data.requirements);
      setEvents(cached.data.events);
      setRecords(cached.data.records);
      setDeferrals(cached.data.deferrals);
      setCertificates(cached.data.certificates);
      setDashboardSummary(cached.data.dashboardSummary);
      setStatusByUser(cached.data.statusByUser);
      setLoading(false);
      if (Date.now() - cached.savedAt < TRAINING_WORKSPACE_SKIP_REFRESH_MS) {
        return;
      }
    } else {
      setLoading(true);
    }
    setError(null);

    const directoryPromise = getAdminUserDirectory({ limit: 250 });
    const baseRequests = await Promise.allSettled([
      directoryPromise,
      listTrainingCourses({ include_inactive: true }),
      canManageCourses ? listTrainingRequirements() : Promise.resolve<TrainingRequirementRead[]>([]),
      listTrainingEvents(),
      listTrainingRecords({ limit: 1000 }),
      listTrainingDeferrals({ limit: 200 }),
      listTrainingCertificates(),
      canManageCourses ? getTrainingDashboardSummary(true) : Promise.resolve<TrainingDashboardSummary | null>(null),
    ]);

    const [directoryRes, coursesRes, requirementsRes, eventsRes, recordsRes, deferralsRes, certsRes, summaryRes] = baseRequests;

    const nextDirectory = directoryRes.status === "fulfilled" ? directoryRes.value.items : [];
    const nextMetrics = directoryRes.status === "fulfilled" ? directoryRes.value.metrics : EMPTY_METRICS;
    const nextCourses = coursesRes.status === "fulfilled" ? coursesRes.value : [];
    const nextRequirements = requirementsRes.status === "fulfilled" ? requirementsRes.value : [];
    const nextEvents = eventsRes.status === "fulfilled" ? eventsRes.value : [];
    const nextRecords = recordsRes.status === "fulfilled" ? recordsRes.value : [];
    const nextDeferrals = deferralsRes.status === "fulfilled" ? deferralsRes.value : [];
    const nextCertificates = certsRes.status === "fulfilled" ? certsRes.value : [];
    const nextSummary = summaryRes.status === "fulfilled" ? summaryRes.value : null;

    let nextStatusMap: Record<string, TrainingStatusItem[]> = {};
    const activeDirectoryIds = nextDirectory.filter((item) => item.is_active).map((item) => item.id);
    if (activeDirectoryIds.length > 0) {
      try {
        const bulk = await getBulkTrainingStatusForUsers(activeDirectoryIds);
        nextStatusMap = bulk.users || {};
      } catch (bulkError) {
        console.error("bulk training status failed", bulkError);
      }
    }

    const anySuccess = [directoryRes, coursesRes, eventsRes, recordsRes, certsRes].some((result) => result.status === "fulfilled");

    if (!anySuccess && shouldUseMockData()) {
      const samplePayload = {
        isSampleMode: true,
        error: "Training service unavailable. Sample data loaded.",
        directory: sampleDirectory,
        directoryMetrics: sampleMetrics,
        courses: sampleCourses,
        requirements: sampleRequirements,
        events: sampleEvents,
        records: sampleRecords,
        deferrals: [] as TrainingDeferralRequestRead[],
        certificates: sampleRecords.filter((record) => Boolean(record.certificate_reference)),
        dashboardSummary: sampleDashboard,
        statusByUser: {
          [sampleDirectory[0].id]: [
            {
              course_id: sampleCourses[0].course_id,
              course_name: sampleCourses[0].course_name,
              frequency_months: sampleCourses[0].frequency_months,
              last_completion_date: sampleRecords[0].completion_date,
              valid_until: sampleRecords[0].valid_until,
              extended_due_date: null,
              days_until_due: 720,
              status: "OK",
              upcoming_event_id: sampleEvents[0].id,
              upcoming_event_date: sampleEvents[0].starts_on,
            },
          ],
        },
      };
      setIsSampleMode(samplePayload.isSampleMode);
      setError(samplePayload.error);
      setDirectory(samplePayload.directory);
      setDirectoryMetrics(samplePayload.directoryMetrics);
      setCourses(samplePayload.courses);
      setRequirements(samplePayload.requirements);
      setEvents(samplePayload.events);
      setRecords(samplePayload.records);
      setDeferrals(samplePayload.deferrals);
      setCertificates(samplePayload.certificates);
      setDashboardSummary(samplePayload.dashboardSummary);
      setStatusByUser(samplePayload.statusByUser);
      writeSessionCache(workspaceCacheKey, samplePayload);
    } else {
      const livePayload = {
        isSampleMode: false,
        error: anySuccess ? null : "Training service unavailable.",
        directory: nextDirectory,
        directoryMetrics: nextMetrics,
        courses: nextCourses,
        requirements: nextRequirements,
        events: nextEvents,
        records: nextRecords,
        deferrals: nextDeferrals,
        certificates: nextCertificates.filter((record) => !String(record.certificate_reference || "").startsWith("TC-DEMO")),
        dashboardSummary: nextSummary,
        statusByUser: nextStatusMap,
      };
      setIsSampleMode(livePayload.isSampleMode);
      setError(livePayload.error);
      setDirectory(livePayload.directory);
      setDirectoryMetrics(livePayload.directoryMetrics);
      setCourses(livePayload.courses);
      setRequirements(livePayload.requirements);
      setEvents(livePayload.events);
      setRecords(livePayload.records);
      setDeferrals(livePayload.deferrals);
      setCertificates(livePayload.certificates);
      setDashboardSummary(livePayload.dashboardSummary);
      setStatusByUser(livePayload.statusByUser);
      writeSessionCache(workspaceCacheKey, livePayload);
    }

    setLoading(false);
  };

  useEffect(() => {
    void load(false);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!directory.length) {
      setSelectedUserId(null);
      return;
    }
    if (selectedUserId && directory.some((item) => item.id === selectedUserId)) return;
    const preferred = currentUser?.id && directory.some((item) => item.id === currentUser.id)
      ? currentUser.id
      : directory[0].id;
    setSelectedUserId(preferred);
  }, [currentUser?.id, directory, selectedUserId]);

  useEffect(() => {
    const loadSelectedUser = async () => {
      if (!selectedUserId) {
        setSelectedUserStatuses([]);
        setSelectedUserRecords([]);
        setSelectedUserCertificates([]);
        setSelectedAccessState(EMPTY_ACCESS_STATE);
        return;
      }

      const cached = selectedUserCacheKey
        ? readSessionCache<{
            records: TrainingRecordRead[];
            certificates: TrainingRecordRead[];
            statuses: TrainingStatusItem[];
            accessState: TrainingAccessState;
            error: string | null;
          }>(selectedUserCacheKey, TRAINING_WORKSPACE_CACHE_MAX_AGE_MS)
        : null;

      if (cached) {
        setSelectedUserRecords(cached.data.records);
        setSelectedUserCertificates(cached.data.certificates);
        setSelectedUserStatuses(cached.data.statuses);
        setSelectedAccessState(cached.data.accessState);
        setSelectedUserError(cached.data.error);
        setSelectedUserLoading(false);
        if (Date.now() - cached.savedAt < TRAINING_WORKSPACE_SKIP_REFRESH_MS) {
          return;
        }
      }

      setSelectedUserLoading(true);
      setSelectedUserError(null);
      try {
        const [recordsRes, certsRes, statusRes, accessRes] = await Promise.allSettled([
          listTrainingRecords({ user_id: selectedUserId, limit: 1000 }),
          listTrainingCertificates(selectedUserId),
          getUserTrainingStatus(selectedUserId),
          getUserTrainingAccessState(selectedUserId),
        ]);

        const payload = {
          records: recordsRes.status === "fulfilled" ? recordsRes.value : [],
          certificates: certsRes.status === "fulfilled" ? certsRes.value : [],
          statuses: statusRes.status === "fulfilled" ? statusRes.value : statusByUser[selectedUserId] || [],
          accessState: accessRes.status === "fulfilled" ? accessRes.value : { ...EMPTY_ACCESS_STATE, user_id: selectedUserId },
          error: [recordsRes, certsRes, statusRes, accessRes].every((result) => result.status === "rejected")
            ? "Could not load the selected user record."
            : null,
        };

        setSelectedUserRecords(payload.records);
        setSelectedUserCertificates(payload.certificates);
        setSelectedUserStatuses(payload.statuses);
        setSelectedAccessState(payload.accessState);
        setSelectedUserError(payload.error);
        if (selectedUserCacheKey) {
          writeSessionCache(selectedUserCacheKey, payload);
        }
      } catch (selectedError: unknown) {
        setSelectedUserError(selectedError instanceof Error ? selectedError.message : "Could not load the selected user record.");
      } finally {
        setSelectedUserLoading(false);
      }
    };

    void loadSelectedUser();
  }, [selectedUserCacheKey, selectedUserId, statusByUser]);

  const activeFlattenedStatuses = useMemo(
    () => directory.filter((user) => user.is_active).flatMap((user) => statusByUser[user.id] || []),
    [directory, statusByUser],
  );

  const selectedUser = selectedUserId ? directoryById.get(selectedUserId) || null : null;

  const selectedUserCounts = useMemo(() => {
    const rows = selectedUserStatuses;
    return {
      overdue: rows.filter((item) => item.status === "OVERDUE").length,
      dueSoon: rows.filter((item) => item.status === "DUE_SOON").length,
      deferred: rows.filter((item) => item.status === "DEFERRED").length,
      notDone: rows.filter((item) => item.status === "NOT_DONE").length,
      ok: rows.filter((item) => item.status === "OK").length,
    };
  }, [selectedUserStatuses]);

  const recordsCountByCoursePk = useMemo(() => {
    const map = new Map<string, number>();
    records.forEach((record) => {
      map.set(record.course_id, (map.get(record.course_id) || 0) + 1);
    });
    return map;
  }, [records]);

  const requirementCountByCoursePk = useMemo(() => {
    const map = new Map<string, number>();
    requirements.forEach((item) => {
      map.set(item.course_pk, (map.get(item.course_pk) || 0) + 1);
    });
    return map;
  }, [requirements]);

  const nextEventByCoursePk = useMemo(() => {
    const today = new Date();
    const map = new Map<string, TrainingEventRead>();
    events
      .filter((event) => event.status === "PLANNED" || event.status === "IN_PROGRESS")
      .filter((event) => {
        const starts = new Date(event.starts_on);
        return !Number.isNaN(starts.getTime()) && starts >= new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
      })
      .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)))
      .forEach((event) => {
        if (!map.has(event.course_id)) map.set(event.course_id, event);
      });
    return map;
  }, [events]);

  const statusCountsByCourseCode = useMemo(() => {
    const map = new Map<string, { overdue: number; dueSoon: number; notDone: number }>();
    activeFlattenedStatuses.forEach((item) => {
      const current = map.get(item.course_id) || { overdue: 0, dueSoon: 0, notDone: 0 };
      if (item.status === "OVERDUE") current.overdue += 1;
      if (item.status === "DUE_SOON") current.dueSoon += 1;
      if (item.status === "NOT_DONE") current.notDone += 1;
      map.set(item.course_id, current);
    });
    return map;
  }, [activeFlattenedStatuses]);

  const filteredCourses = useMemo(() => {
    const needle = courseSearch.trim().toLowerCase();
    if (!needle) return courses;
    return courses.filter((course) => {
      const haystack = [
        course.course_id,
        course.course_name,
        course.category_raw,
        course.scope,
        course.regulatory_reference,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [courseSearch, courses]);

  const filteredPeople = useMemo(() => {
    const needle = peopleSearch.trim().toLowerCase();
    if (!needle) return directory;
    return directory.filter((person) =>
      [
        person.full_name,
        person.staff_code,
        person.email,
        person.department_name,
        person.display_title,
        person.role,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [directory, peopleSearch]);

  const filteredRequirementUserChoices = useMemo(() => {
    const needle = requirementUserQuery.trim().toLowerCase();
    if (!needle) return directory.slice(0, 20);
    return directory
      .filter((person) =>
        [person.full_name, person.staff_code, person.email, person.id]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(needle),
      )
      .slice(0, 20);
  }, [directory, requirementUserQuery]);

  const overviewMetrics = useMemo(() => ({
    totalCourses: courses.length,
    mandatoryCourses: courses.filter((course) => course.is_mandatory).length,
    requirementRules: requirements.filter((item) => item.is_active).length,
    overdueItems: activeFlattenedStatuses.filter((item) => item.status === "OVERDUE").length,
    dueSoonItems: activeFlattenedStatuses.filter((item) => item.status === "DUE_SOON").length,
    plannedSessions: events.filter((event) => event.status === "PLANNED").length,
    certificates: certificates.length,
    trackedPeople: directory.length,
  }), [activeFlattenedStatuses, certificates.length, courses, directory.length, events, requirements]);

  const topAttentionUsers = useMemo(() => {
    return directory
      .filter((user) => user.is_active)
      .map((user) => {
        const items = statusByUser[user.id] || [];
        return {
          user,
          overdue: items.filter((item) => item.status === "OVERDUE").length,
          dueSoon: items.filter((item) => item.status === "DUE_SOON").length,
          notDone: items.filter((item) => item.status === "NOT_DONE").length,
        };
      })
      .filter((row) => row.overdue > 0 || row.dueSoon > 0 || row.notDone > 0)
      .sort((a, b) => (b.overdue - a.overdue) || (b.notDone - a.notDone) || (b.dueSoon - a.dueSoon))
      .slice(0, 12);
  }, [directory, statusByUser]);

  const activeSectionCount = (key: SectionKey): number | null => {
    if (key === "overview") return overviewMetrics.overdueItems;
    if (key === "matrix") return requirements.filter((item) => item.is_active).length || courses.length;
    if (key === "schedule" || key === "sessions" || key === "attendance") return events.length;
    if (key === "assessments") return records.filter((record) => record.exam_score == null).length;
    if (key === "certificates") return certificates.length;
    if (key === "personnel") return directory.length;
    if (key === "templates") return selectedUser ? selectedUserCertificates.length : certificates.length;
    if (key === "settings") return deferrals.filter((item) => item.status === "PENDING").length;
    return null;
  };

  const openCreateCourse = () => {
    setEditingCourseId(null);
    setCourseForm({
      course_id: "",
      course_name: "",
      frequency_months: "",
      status: "One_Off",
      category_raw: "",
      is_mandatory: false,
      scope: "",
      regulatory_reference: "",
    });
    setCourseFormOpen(true);
  };

  const openEditCourse = (course: TrainingCourseRead) => {
    setEditingCourseId(course.id);
    setCourseForm({
      course_id: course.course_id || "",
      course_name: course.course_name || "",
      frequency_months: course.frequency_months == null ? "" : String(course.frequency_months),
      status: course.status || "One_Off",
      category_raw: course.category_raw || "",
      is_mandatory: Boolean(course.is_mandatory),
      scope: course.scope || "",
      regulatory_reference: course.regulatory_reference || "",
    });
    setCourseFormOpen(true);
  };

  const submitCourse = async () => {
    if (!courseForm.course_id.trim() || !courseForm.course_name.trim()) {
      pushToast({ title: "Missing fields", message: "Course ID and Course Name are required.", variant: "error" });
      return;
    }
    setSavingCourse(true);
    try {
      const payload = {
        course_id: courseForm.course_id.trim(),
        course_name: courseForm.course_name.trim(),
        frequency_months: courseForm.frequency_months.trim() ? Number(courseForm.frequency_months.trim()) : null,
        status: courseForm.status,
        category_raw: courseForm.category_raw.trim() || null,
        scope: courseForm.scope.trim() || null,
        regulatory_reference: courseForm.regulatory_reference.trim() || null,
        is_mandatory: courseForm.is_mandatory,
        mandatory_for_all: false,
      };
      if (editingCourseId) {
        await updateTrainingCourse(editingCourseId, payload);
        pushToast({ title: "Course updated", message: `${payload.course_id} updated successfully.`, variant: "info" });
      } else {
        await createTrainingCourse(payload);
        pushToast({ title: "Course created", message: `${payload.course_id} created successfully.`, variant: "info" });
      }
      setCourseFormOpen(false);
      await load(true);
      openSection("matrix");
    } catch (err: unknown) {
      pushToast({
        title: "Save failed",
        message: err instanceof Error ? err.message : "Unable to save course.",
        variant: "error",
      });
    } finally {
      setSavingCourse(false);
    }
  };

  const openCreateRequirement = (coursePk?: string) => {
    setRequirementUserQuery("");
    setRequirementForm({
      course_pk: coursePk || (courses[0]?.id || ""),
      scope: "ALL",
      department_code: null,
      job_role: null,
      user_id: null,
      is_mandatory: true,
      is_active: true,
      effective_from: null,
      effective_to: null,
    });
    setRequirementFormOpen(true);
  };

  const submitRequirement = async () => {
    if (!requirementForm.course_pk) {
      pushToast({ title: "Missing course", message: "Select a course first.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "DEPARTMENT" && !requirementForm.department_code?.trim()) {
      pushToast({ title: "Missing department", message: "Department code is required for a department rule.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "JOB_ROLE" && !requirementForm.job_role?.trim()) {
      pushToast({ title: "Missing role", message: "Role title is required for a role rule.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "USER" && !requirementForm.user_id) {
      pushToast({ title: "Missing user", message: "Choose a user for this rule.", variant: "error" });
      return;
    }

    setRequirementSaving(true);
    try {
      const payload: TrainingRequirementCreate = {
        course_pk: requirementForm.course_pk,
        scope: requirementForm.scope,
        department_code: requirementForm.scope === "DEPARTMENT" ? requirementForm.department_code?.trim() || null : null,
        job_role: requirementForm.scope === "JOB_ROLE" ? requirementForm.job_role?.trim() || null : null,
        user_id: requirementForm.scope === "USER" ? requirementForm.user_id || null : null,
        is_mandatory: requirementForm.is_mandatory,
        is_active: requirementForm.is_active,
        effective_from: requirementForm.effective_from || null,
        effective_to: requirementForm.effective_to || null,
      };
      await createTrainingRequirement(payload);
      setRequirementFormOpen(false);
      pushToast({ title: "Requirement saved", message: "Training requirement created successfully.", variant: "info" });
      await load(true);
      openSection("matrix");
    } catch (err: unknown) {
      pushToast({
        title: "Requirement failed",
        message: err instanceof Error ? err.message : "Could not save the requirement rule.",
        variant: "error",
      });
    } finally {
      setRequirementSaving(false);
    }
  };

  const runImport = async (mode: "preview" | "apply") => {
    if (!importFile) {
      pushToast({ title: "No file selected", message: "Choose a COURSES.xlsx file first.", variant: "error" });
      return;
    }
    setImportingMode(mode);
    setImportProgress(null);
    try {
      const summary = await importTrainingCoursesWorkbook(importFile, {
        dryRun: mode === "preview",
        sheetName: "Courses",
        onProgress: setImportProgress,
      });
      setImportSummary(summary);
      if (summary.dry_run) {
        pushToast({
          title: "Preview complete",
          message: `${summary.created_courses} new and ${summary.updated_courses} existing courses were detected. No changes have been saved yet.`,
          variant: "info",
        });
      } else {
        pushToast({
          title: "Import applied",
          message: `${summary.created_courses} created, ${summary.updated_courses} updated, ${summary.skipped_rows} skipped.`,
          variant: "info",
        });
        await load(true);
        openSection("matrix");
      }
    } catch (err: unknown) {
      pushToast({
        title: "Import failed",
        message: err instanceof Error ? err.message : "Could not import courses workbook.",
        variant: "error",
      });
    } finally {
      setImportingMode(null);
    }
  };

  const runRecordsImport = async (mode: "preview" | "apply") => {
    if (!recordsImportFile) {
      pushToast({ title: "No file selected", message: "Choose a TRAINING.xlsx file first.", variant: "error" });
      return;
    }
    setRecordsImportingMode(mode);
    setRecordsImportProgress(null);
    try {
      const summary = await importTrainingRecordsWorkbook(recordsImportFile, {
        dryRun: mode === "preview",
        sheetName: "Training",
        onProgress: setRecordsImportProgress,
      });
      setRecordsImportSummary(summary);
      if (summary.dry_run) {
        pushToast({
          title: "Preview complete",
          message: `${summary.created_records} new, ${summary.updated_records} updates, ${summary.unchanged_rows} unchanged, ${summary.skipped_rows} skipped.`,
          variant: "info",
        });
      } else {
        pushToast({
          title: "Training history imported",
          message: `${summary.created_records} created, ${summary.updated_records} updated, ${summary.unchanged_rows} unchanged, ${summary.skipped_rows} skipped.`,
          variant: "info",
        });
        await load(true);
        openSection("personnel");
      }
    } catch (err: unknown) {
      pushToast({
        title: "Training history import failed",
        message: err instanceof Error ? err.message : "Could not import TRAINING.xlsx.",
        variant: "error",
      });
    } finally {
      setRecordsImportingMode(null);
    }
  };


  const handlePrintSelectedRecord = () => {
    if (!selectedUser) {
      pushToast({ title: "Select a user", message: "Choose a user first.", variant: "error" });
      return;
    }
    buildTrainingRecordPdf({
      user: selectedUser,
      amoCode: amoCode || "AMO",
      statuses: selectedUserStatuses,
      records: selectedUserRecords,
      coursesById: coursesByPk,
    });
  };

  const handleDownloadEvidencePack = async () => {
    if (!selectedUser) {
      pushToast({ title: "Select a user", message: "Choose a user first.", variant: "error" });
      return;
    }
    try {
      const blob = await downloadTrainingUserEvidencePack(selectedUser.id);
      saveBlob(blob, `${selectedUser.staff_code || selectedUser.id}_training_evidence_pack.zip`);
    } catch (err: unknown) {
      pushToast({
        title: "Download failed",
        message: err instanceof Error ? err.message : "Could not export the evidence pack.",
        variant: "error",
      });
    }
  };

  const heroActions = (
    <div className="tc-inline-actions">
      <button type="button" className="secondary-chip-btn" onClick={() => void load(true)} title="Refresh training workspace">
        <RefreshCw size={14} /> Refresh
      </button>
      {canManageCourses ? (
        <>
          <button type="button" className="secondary-chip-btn" onClick={() => setImportOpen(true)}>
            <UploadCloud size={14} /> Import courses
          </button>
          <button type="button" className="secondary-chip-btn" onClick={() => setRecordsImportOpen(true)}>
            <UploadCloud size={14} /> Import training records
          </button>
        </>
      ) : null}
      <button type="button" className="secondary-chip-btn" onClick={handlePrintSelectedRecord} disabled={!selectedUser}>
        <Printer size={14} /> Print record
      </button>
    </div>
  );

  return (
    <QMSLayout
      amoCode={amoCode || "UNKNOWN"}
      department={department || "quality"}
      title="Training & Competence"
      subtitle="Maintenance training control, progression, records, and compliance evidence"
      actions={heroActions}
    >
      <div className="tc-page">
        <section className="tc-hero">
          <div className="tc-hero__row">
            <div>
              <p className="tc-eyebrow">Training control workspace</p>
              <h1 className="tc-title">Training & Competence Matrix</h1>
              <p className="tc-muted">
                One place for course catalog control, role applicability, scheduled sessions, personnel history,
                certificate issuance, and printable records.
              </p>
            </div>
            <div className="tc-stateline">
              {isSampleMode ? <span className="tc-chip">Sample mode</span> : null}
              {error ? <span className="tc-chip">{error}</span> : null}
              <span className="tc-chip">Users tracked: {directoryMetrics.total_users}</span>
              <span className="tc-chip">Overdue items: {overviewMetrics.overdueItems}</span>
            </div>
          </div>
        </section>

        <section className="tc-summary-grid">
          <MetricCard label="Courses" value={overviewMetrics.totalCourses} />
          <MetricCard label="Mandatory" value={overviewMetrics.mandatoryCourses} />
          <MetricCard label="Requirement rules" value={overviewMetrics.requirementRules} />
          <MetricCard label="Tracked people" value={overviewMetrics.trackedPeople} />
          <MetricCard label="Planned sessions" value={overviewMetrics.plannedSessions} />
          <MetricCard label="Issued certificates" value={overviewMetrics.certificates} />
        </section>

        <div className="tc-shell">
          <aside className="tc-rail">
            <div>
              <h2 className="tc-rail__title">Training sections</h2>
              <p className="tc-rail__subtitle">Use the rail to jump between control, delivery, and per-person records.</p>
            </div>
            <div className="tc-nav">
              {sectionItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`tc-nav__button${item.key === section ? " is-active" : ""}`}
                  onClick={() => openSection(item.key)}
                >
                  <div className="tc-nav__text">
                    <span className="tc-nav__title">{item.title}</span>
                    <span className="tc-nav__desc">{item.desc}</span>
                  </div>
                  <div className="tc-stateline">
                    {activeSectionCount(item.key) != null ? (
                      <span className="tc-nav__count">{activeSectionCount(item.key)}</span>
                    ) : null}
                    {item.icon}
                  </div>
                </button>
              ))}
            </div>
            <div className="tc-import-note">
              <strong>Import note</strong>
              <p className="tc-muted">
                Workbook previews do not save changes. Use <strong>Apply import</strong> after reviewing the preview to persist courses or training history.
              </p>
            </div>
          </aside>

          <div className="tc-content">
            {loading ? (
              <section className="tc-panel">
                <div className="tc-empty">Loading training workspace…</div>
              </section>
            ) : (
              <TrainingSectionContent
                section={section}
                amoCode={amoCode || "UNKNOWN"}
                department={department || "quality"}
                directory={directory}
                directoryById={directoryById}
                directoryMetrics={directoryMetrics}
                selectedUser={selectedUser}
                selectedUserCounts={selectedUserCounts}
                selectedUserStatuses={selectedUserStatuses}
                selectedUserRecords={selectedUserRecords}
                selectedUserCertificates={selectedUserCertificates}
                selectedAccessState={selectedAccessState}
                selectedUserLoading={selectedUserLoading}
                selectedUserError={selectedUserError}
                setSelectedUserId={setSelectedUserId}
                courses={courses}
                filteredCourses={filteredCourses}
                requirements={requirements}
                events={events}
                records={records}
                certificates={certificates}
                deferrals={deferrals}
                overviewMetrics={overviewMetrics}
                dashboardSummary={dashboardSummary}
                topAttentionUsers={topAttentionUsers}
                courseSearch={courseSearch}
                setCourseSearch={setCourseSearch}
                peopleSearch={peopleSearch}
                setPeopleSearch={setPeopleSearch}
                filteredPeople={filteredPeople}
                recordsCountByCoursePk={recordsCountByCoursePk}
                requirementCountByCoursePk={requirementCountByCoursePk}
                nextEventByCoursePk={nextEventByCoursePk}
                statusCountsByCourseCode={statusCountsByCourseCode}
                statusByUser={statusByUser}
                onOpenCreateCourse={openCreateCourse}
                onOpenEditCourse={openEditCourse}
                onOpenImport={() => setImportOpen(true)}
                onOpenRecordsImport={() => setRecordsImportOpen(true)}
                onOpenRequirement={openCreateRequirement}
                onRefresh={load}
                onPrintSelectedRecord={handlePrintSelectedRecord}
                onDownloadEvidencePack={handleDownloadEvidencePack}
                canManageCourses={canManageCourses}
                navigate={navigate}
              />
            )}
          </div>
        </div>

        <Drawer title={drawer?.title || "Details"} isOpen={Boolean(drawer)} onClose={() => setDrawer(null)}>
          <div className="tc-drawer-grid">{drawer?.body}</div>
        </Drawer>

        <Drawer title={editingCourseId ? "Modify course" : "Create course"} isOpen={courseFormOpen} onClose={() => setCourseFormOpen(false)}>
          <div className="tc-drawer-grid">
            <input className="tc-input" placeholder="Course ID" value={courseForm.course_id} onChange={(e) => setCourseForm((p) => ({ ...p, course_id: e.target.value }))} />
            <input className="tc-input" placeholder="Course name" value={courseForm.course_name} onChange={(e) => setCourseForm((p) => ({ ...p, course_name: e.target.value }))} />
            <div className="tc-grid">
              <input className="tc-input" placeholder="Frequency months" value={courseForm.frequency_months} onChange={(e) => setCourseForm((p) => ({ ...p, frequency_months: e.target.value }))} />
              <select className="tc-select" value={courseForm.status} onChange={(e) => setCourseForm((p) => ({ ...p, status: e.target.value }))}>
                <option value="Initial">Initial</option>
                <option value="Recurrent">Recurrent</option>
                <option value="One_Off">One_Off</option>
              </select>
            </div>
            <input className="tc-input" placeholder="Category (raw)" value={courseForm.category_raw} onChange={(e) => setCourseForm((p) => ({ ...p, category_raw: e.target.value }))} />
            <input className="tc-input" placeholder="Applicability scope (free text)" value={courseForm.scope} onChange={(e) => setCourseForm((p) => ({ ...p, scope: e.target.value }))} />
            <input className="tc-input" placeholder="Regulatory reference" value={courseForm.regulatory_reference} onChange={(e) => setCourseForm((p) => ({ ...p, regulatory_reference: e.target.value }))} />
            <label className="tc-stateline">
              <input type="checkbox" checked={courseForm.is_mandatory} onChange={(e) => setCourseForm((p) => ({ ...p, is_mandatory: e.target.checked }))} />
              Mandatory course
            </label>
            <div className="tc-inline-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => setCourseFormOpen(false)} disabled={savingCourse}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={submitCourse} disabled={savingCourse}>
                {savingCourse ? "Saving…" : editingCourseId ? "Update course" : "Create course"}
              </button>
            </div>
          </div>
        </Drawer>

        <Drawer title="Create requirement rule" isOpen={requirementFormOpen} onClose={() => setRequirementFormOpen(false)}>
          <div className="tc-drawer-grid">
            <select
              className="tc-select"
              value={requirementForm.course_pk}
              onChange={(e) => setRequirementForm((p) => ({ ...p, course_pk: e.target.value }))}
            >
              <option value="">Select course</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>
              ))}
            </select>
            <select
              className="tc-select"
              value={requirementForm.scope}
              onChange={(e) => setRequirementForm((p) => ({
                ...p,
                scope: e.target.value as TrainingRequirementScope,
                department_code: null,
                job_role: null,
                user_id: null,
              }))}
            >
              <option value="ALL">All staff</option>
              <option value="DEPARTMENT">Department</option>
              <option value="JOB_ROLE">Role / title</option>
              <option value="USER">Specific user</option>
            </select>
            {requirementForm.scope === "DEPARTMENT" ? (
              <input
                className="tc-input"
                placeholder="Department code (e.g. QUALITY)"
                value={requirementForm.department_code || ""}
                onChange={(e) => setRequirementForm((p) => ({ ...p, department_code: e.target.value }))}
              />
            ) : null}
            {requirementForm.scope === "JOB_ROLE" ? (
              <input
                className="tc-input"
                placeholder="Role / title (e.g. Certifying Engineer)"
                value={requirementForm.job_role || ""}
                onChange={(e) => setRequirementForm((p) => ({ ...p, job_role: e.target.value }))}
              />
            ) : null}
            {requirementForm.scope === "USER" ? (
              <>
                <input
                  className="tc-input"
                  placeholder="Search by name, staff code, email, or user ID"
                  value={requirementUserQuery}
                  onChange={(e) => setRequirementUserQuery(e.target.value)}
                />
                <div className="tc-choice-list">
                  {filteredRequirementUserChoices.map((person) => (
                    <button
                      type="button"
                      key={person.id}
                      className={`tc-choice-item${requirementForm.user_id === person.id ? " is-active" : ""}`}
                      onClick={() => {
                        setRequirementForm((p) => ({ ...p, user_id: person.id }));
                        setRequirementUserQuery(`${person.full_name} · ${person.staff_code}`);
                      }}
                    >
                      <strong>{person.full_name}</strong>
                      <span className="tc-table__secondary">{person.staff_code} · {person.display_title}</span>
                    </button>
                  ))}
                </div>
              </>
            ) : null}
            <div className="tc-grid">
              <input
                className="tc-input"
                type="date"
                value={requirementForm.effective_from || ""}
                onChange={(e) => setRequirementForm((p) => ({ ...p, effective_from: e.target.value || null }))}
              />
              <input
                className="tc-input"
                type="date"
                value={requirementForm.effective_to || ""}
                onChange={(e) => setRequirementForm((p) => ({ ...p, effective_to: e.target.value || null }))}
              />
            </div>
            <label className="tc-stateline">
              <input
                type="checkbox"
                checked={requirementForm.is_mandatory}
                onChange={(e) => setRequirementForm((p) => ({ ...p, is_mandatory: e.target.checked }))}
              />
              Mandatory requirement
            </label>
            <div className="tc-inline-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => setRequirementFormOpen(false)} disabled={requirementSaving}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={submitRequirement} disabled={requirementSaving}>
                {requirementSaving ? "Saving…" : "Create rule"}
              </button>
            </div>
          </div>
        </Drawer>

        <Drawer title="Import courses workbook" isOpen={importOpen} onClose={() => setImportOpen(false)}>
          <div className="tc-drawer-grid">
            <p className="tc-muted" style={{ marginTop: 0 }}>
              Upload the official <strong>Courses</strong> worksheet. Preview first if you want to verify what will be created or updated,
              then apply the import to refresh the live matrix.
            </p>
            <input type="file" accept=".xlsx,.xlsm,.xltx,.xltm" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
            {importProgress?.percent != null ? (
              <p className="tc-muted">Uploading… {importProgress.percent.toFixed(1)}%</p>
            ) : null}
            {importSummary ? (
              <div className={`tc-import-note${importSummary.dry_run ? " is-warning" : ""}`}>
                <strong>{importSummary.dry_run ? "Preview only" : "Live import applied"}</strong>
                <p className="tc-muted" style={{ marginTop: 6 }}>
                  Rows: {importSummary.total_rows} · Courses created: {importSummary.created_courses} · Courses updated: {importSummary.updated_courses}
                  · Requirements created: {importSummary.created_requirements || 0} · Requirements updated: {importSummary.updated_requirements || 0}
                  · Skipped: {importSummary.skipped_rows}
                </p>
                {importSummary.dry_run ? (
                  <p className="tc-muted" style={{ marginTop: 6 }}>
                    No changes have been saved yet. Use <strong>Apply import</strong> to write these results to the course catalog.
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="tc-inline-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => void runImport("preview")} disabled={Boolean(importingMode)}>
                {importingMode === "preview" ? "Previewing…" : "Preview workbook"}
              </button>
              <button type="button" className="primary-chip-btn" onClick={() => void runImport("apply")} disabled={Boolean(importingMode)}>
                {importingMode === "apply" ? "Applying…" : "Apply import"}
              </button>
            </div>
            {importSummary?.issues?.length ? (
              <div className="tc-issues">
                {importSummary.issues.map((issue, index) => (
                  <div key={`${issue.row_number}-${index}`} className="tc-issue">
                    <strong>Row {issue.row_number}</strong>
                    {issue.course_id ? <span className="tc-table__secondary">{issue.course_id}</span> : null}
                    <p className="tc-muted" style={{ marginTop: 4 }}>{issue.reason}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Drawer>

        <Drawer title="Import training history workbook" isOpen={recordsImportOpen} onClose={() => setRecordsImportOpen(false)}>
          <div className="tc-drawer-grid">
            <input
              className="tc-input"
              type="file"
              accept=".xlsx,.xlsm,.xltx,.xltm"
              onChange={(e) => {
                const picked = e.target.files?.[0] || null;
                setRecordsImportFile(picked);
                setRecordsImportSummary(null);
                setRecordsImportProgress(null);
              }}
            />
            <p className="tc-muted">Upload <strong>TRAINING.xlsx</strong> from the <strong>Training</strong> worksheet. Preview first, then apply after confirming the create/update plan.</p>
            {recordsImportProgress ? (
              <div className="tc-progress">
                Uploading… {recordsImportProgress.percent != null ? `${recordsImportProgress.percent.toFixed(1)}%` : `${(recordsImportProgress.loadedBytes / (1024 * 1024)).toFixed(2)} MB`}
              </div>
            ) : null}
            {recordsImportSummary ? (
              <div className="tc-import-result">
                <strong>{recordsImportSummary.dry_run ? "Preview ready" : "Import applied"}</strong>
                <p className="tc-muted" style={{ marginTop: 6 }}>
                  Rows: {recordsImportSummary.total_rows} · Create: {recordsImportSummary.created_records} · Update: {recordsImportSummary.updated_records}
                  · Unchanged: {recordsImportSummary.unchanged_rows} · Skipped: {recordsImportSummary.skipped_rows}
                  · Inactive matches: {recordsImportSummary.matched_inactive_rows || 0}
                </p>
                {recordsImportSummary.dry_run ? (
                  <p className="tc-muted" style={{ marginTop: 6 }}>
                    Nothing has been saved yet. Review the preview table below, then use <strong>Apply import</strong> to commit the changes.
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="tc-inline-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => void runRecordsImport("preview")} disabled={Boolean(recordsImportingMode)}>
                {recordsImportingMode === "preview" ? "Previewing…" : "Preview workbook"}
              </button>
              <button type="button" className="primary-chip-btn" onClick={() => void runRecordsImport("apply")} disabled={Boolean(recordsImportingMode)}>
                {recordsImportingMode === "apply" ? "Applying…" : "Apply import"}
              </button>
            </div>
            {recordsImportSummary?.preview_rows?.length ? (
              <div className="tc-table-wrap tc-import-preview">
                <table className="tc-table">
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Person</th>
                      <th>Course</th>
                      <th>Completed</th>
                      <th>Next due</th>
                      <th>Action</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recordsImportSummary.preview_rows.map((row) => (
                      <tr key={`records-import-${row.row_number}`}>
                        <td>{row.row_number}</td>
                        <td>
                          <span className="tc-table__primary">{row.matched_user_name || row.person_name || row.person_id}</span>
                          <span className="tc-table__secondary">{row.person_id}{row.matched_user_active === false ? " · inactive" : ""}</span>
                        </td>
                        <td>
                          <span className="tc-table__primary">{row.course_id}</span>
                          <span className="tc-table__secondary">{row.matched_course_name || row.course_name}</span>
                        </td>
                        <td>{formatIsoDate(row.completion_date)}</td>
                        <td>{formatIsoDate(row.next_due_date)}</td>
                        <td><span className={`tc-status-pill ${row.action === "CREATE" ? "ok" : row.action === "UPDATE" ? "due-soon" : row.action === "SKIP" ? "overdue" : "not-done"}`}>{row.action}</span></td>
                        <td>
                          {row.reason ? <div className="tc-table__secondary">{row.reason}</div> : null}
                          {row.source_status ? <div className="tc-table__secondary">Source status: {row.source_status}{row.days_to_due != null ? ` · ${row.days_to_due} days` : ""}</div> : null}
                          {row.changes?.length ? (
                            <ul className="tc-import-changes">
                              {row.changes.map((change) => (
                                <li key={`${row.row_number}-${change.field}`}>{change.label}: {change.old_value || "—"} → {change.new_value || "—"}</li>
                              ))}
                            </ul>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {recordsImportSummary?.issues?.length ? (
              <div className="tc-issues">
                {recordsImportSummary.issues.map((issue, index) => (
                  <div key={`records-issue-${issue.row_number}-${index}`} className="tc-issue">
                    <strong>Row {issue.row_number}</strong>
                    <span className="tc-table__secondary">{issue.person_id || "Unknown person"}{issue.course_id ? ` · ${issue.course_id}` : ""}</span>
                    <p className="tc-muted" style={{ marginTop: 4 }}>{issue.reason}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Drawer>
      </div>
    </QMSLayout>
  );
};

type TrainingSectionContentProps = {
  section: SectionKey;
  amoCode: string;
  department: string;
  directory: AdminUserDirectoryItem[];
  directoryById: Map<string, AdminUserDirectoryItem>;
  directoryMetrics: AdminUserDirectoryMetrics;
  selectedUser: AdminUserDirectoryItem | null;
  selectedUserCounts: { overdue: number; dueSoon: number; deferred: number; notDone: number; ok: number };
  selectedUserStatuses: TrainingStatusItem[];
  selectedUserRecords: TrainingRecordRead[];
  selectedUserCertificates: TrainingRecordRead[];
  selectedAccessState: TrainingAccessState;
  selectedUserLoading: boolean;
  selectedUserError: string | null;
  setSelectedUserId: (userId: string) => void;
  courses: TrainingCourseRead[];
  filteredCourses: TrainingCourseRead[];
  requirements: TrainingRequirementRead[];
  events: TrainingEventRead[];
  records: TrainingRecordRead[];
  certificates: TrainingRecordRead[];
  deferrals: TrainingDeferralRequestRead[];
  overviewMetrics: {
    totalCourses: number;
    mandatoryCourses: number;
    requirementRules: number;
    overdueItems: number;
    dueSoonItems: number;
    plannedSessions: number;
    certificates: number;
    trackedPeople: number;
  };
  dashboardSummary: TrainingDashboardSummary | null;
  topAttentionUsers: Array<{ user: AdminUserDirectoryItem; overdue: number; dueSoon: number; notDone: number }>;
  courseSearch: string;
  setCourseSearch: (value: string) => void;
  peopleSearch: string;
  setPeopleSearch: (value: string) => void;
  filteredPeople: AdminUserDirectoryItem[];
  recordsCountByCoursePk: Map<string, number>;
  requirementCountByCoursePk: Map<string, number>;
  nextEventByCoursePk: Map<string, TrainingEventRead>;
  statusCountsByCourseCode: Map<string, { overdue: number; dueSoon: number; notDone: number }>;
  statusByUser: Record<string, TrainingStatusItem[]>;
  onOpenCreateCourse: () => void;
  onOpenEditCourse: (course: TrainingCourseRead) => void;
  onOpenImport: () => void;
  onOpenRecordsImport: () => void;
  onOpenRequirement: (coursePk?: string) => void;
  onRefresh: () => Promise<void>;
  onPrintSelectedRecord: () => void;
  onDownloadEvidencePack: () => Promise<void>;
  canManageCourses: boolean;
  navigate: ReturnType<typeof useNavigate>;
};

const TrainingSectionContent: React.FC<TrainingSectionContentProps> = (props) => {
  const {
    section,
    amoCode,
    department,
    directoryById,
    selectedUser,
    selectedUserCounts,
    selectedUserStatuses,
    selectedUserRecords,
    selectedUserCertificates,
    selectedAccessState,
    selectedUserLoading,
    selectedUserError,
    setSelectedUserId,
    filteredCourses,
    requirements,
    events,
    certificates,
    deferrals,
    overviewMetrics,
    dashboardSummary,
    topAttentionUsers,
    courseSearch,
    setCourseSearch,
    peopleSearch,
    setPeopleSearch,
    filteredPeople,
    recordsCountByCoursePk,
    requirementCountByCoursePk,
    nextEventByCoursePk,
    statusCountsByCourseCode,
    statusByUser,
    onOpenCreateCourse,
    onOpenEditCourse,
    onOpenImport,
    onOpenRecordsImport,
    onOpenRequirement,
    onRefresh,
    onPrintSelectedRecord,
    onDownloadEvidencePack,
    canManageCourses,
    navigate,
  } = props;

  if (section === "overview") {
    return (
      <>
        <section className="tc-panel">
          <div className="tc-panel__header">
            <div>
              <h2 className="tc-panel__title">Compliance overview</h2>
              <p className="tc-muted">Quick visibility on overdue mandatory training, due-soon items, and delivery load.</p>
            </div>
            <div className="tc-inline-actions">
              <span className={`tc-status-pill ${overviewMetrics.overdueItems > 0 ? "overdue" : "ok"}`}>
                {overviewMetrics.overdueItems > 0 ? `${overviewMetrics.overdueItems} overdue` : "No overdue items"}
              </span>
            </div>
          </div>
          <div className="tc-summary-grid">
            <MetricCard label="Mandatory records" value={dashboardSummary?.total_mandatory_records ?? overviewMetrics.mandatoryCourses} compact />
            <MetricCard label="OK" value={dashboardSummary?.ok_count ?? 0} compact />
            <MetricCard label="Due soon" value={dashboardSummary?.due_soon_count ?? overviewMetrics.dueSoonItems} compact />
            <MetricCard label="Overdue" value={dashboardSummary?.overdue_count ?? overviewMetrics.overdueItems} compact />
            <MetricCard label="Deferred" value={dashboardSummary?.deferred_count ?? deferrals.filter((item) => item.status === "APPROVED").length} compact />
            <MetricCard label="Not done" value={dashboardSummary?.not_done_count ?? 0} compact />
          </div>
        </section>

        <section className="tc-panel">
          <div className="tc-panel__header">
            <div>
              <h2 className="tc-panel__title">Attention queue</h2>
              <p className="tc-muted">People with the most urgent training exposure based on current records.</p>
            </div>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/events`)}>
              <ExternalLink size={14} /> Open schedule
            </button>
          </div>
          {topAttentionUsers.length === 0 ? (
            <div className="tc-empty">No urgent user records are currently flagged.</div>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Overdue</th>
                    <th>Due soon</th>
                    <th>Not done</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {topAttentionUsers.map((row) => (
                    <tr key={row.user.id}>
                      <td>
                        <span className="tc-table__primary">{row.user.full_name}</span>
                        <span className="tc-table__secondary">{row.user.staff_code} · {row.user.email}</span>
                      </td>
                      <td>{row.user.display_title}</td>
                      <td>{row.user.department_name || "—"}</td>
                      <td>{row.overdue}</td>
                      <td>{row.dueSoon}</td>
                      <td>{row.notDone}</td>
                      <td>
                        <button type="button" className="secondary-chip-btn" onClick={() => setSelectedUserId(row.user.id)}>
                          Review user
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </>
    );
  }

  if (section === "matrix") {
    return (
      <>
        <section className="tc-panel">
          <div className="tc-panel__header">
            <div>
              <h2 className="tc-panel__title">Course catalog and applicability matrix</h2>
              <p className="tc-muted">Every imported course is visible here together with rule coverage, upcoming sessions, and exposure counts.</p>
            </div>
            <div className="tc-inline-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => void onRefresh()}>
                <RefreshCw size={14} /> Refresh
              </button>
              {canManageCourses ? (
                <>
                  <button type="button" className="secondary-chip-btn" onClick={onOpenCreateCourse}>
                    <Plus size={14} /> New course
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => onOpenRequirement()}>
                    <Plus size={14} /> Add requirement
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={onOpenRecordsImport}>
                    <UploadCloud size={14} /> Import training history
                  </button>
                  <button type="button" className="primary-chip-btn" onClick={onOpenImport}>
                    <UploadCloud size={14} /> Import workbook
                  </button>
                </>
              ) : null}
            </div>
          </div>
          <div className="tc-filterbar">
            <label style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: 12, top: 13, color: "#667085" }} />
              <input
                className="tc-input"
                style={{ paddingLeft: 34 }}
                placeholder="Search by CourseID, name, scope, or reference"
                value={courseSearch}
                onChange={(e) => setCourseSearch(e.target.value)}
              />
            </label>
          </div>

          {filteredCourses.length === 0 ? (
            <div className="tc-empty">
              No courses are visible yet. If you just ran a preview import, the workbook has not been applied. Open the import drawer and use <strong>Apply import</strong>.
            </div>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Cycle</th>
                    <th>Applicability</th>
                    <th>Matrix rules</th>
                    <th>Records</th>
                    <th>Next session</th>
                    <th>Exposure</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCourses.map((course) => {
                    const applicability = buildApplicabilitySummary(course, requirements, directoryById);
                    const exposure = statusCountsByCourseCode.get(course.course_id) || { overdue: 0, dueSoon: 0, notDone: 0 };
                    const nextEvent = nextEventByCoursePk.get(course.id);
                    return (
                      <tr key={course.id}>
                        <td>
                          <span className="tc-table__primary">{course.course_id}</span>
                          <span className="tc-table__secondary">{course.course_name}</span>
                          <span className="tc-table__secondary">{course.regulatory_reference || course.category_raw || "No reference yet"}</span>
                        </td>
                        <td>
                          <span>{course.frequency_months ? `${course.frequency_months} months` : "One-off"}</span>
                          <span className="tc-table__secondary">{humanizeEnum(course.status)}</span>
                        </td>
                        <td>
                          <div className="tc-stateline">
                            {applicability.map((item, index) => (
                              <span key={`${course.id}-${index}`} className="tc-mini-chip">{item.label}: {item.value}</span>
                            ))}
                          </div>
                        </td>
                        <td>{requirementCountByCoursePk.get(course.id) || 0}</td>
                        <td>{recordsCountByCoursePk.get(course.id) || 0}</td>
                        <td>
                          {nextEvent ? (
                            <>
                              <span>{formatIsoDate(nextEvent.starts_on)}</span>
                              <span className="tc-table__secondary">{nextEvent.title}</span>
                            </>
                          ) : (
                            <span className="tc-muted">No planned session</span>
                          )}
                        </td>
                        <td>
                          <div className="tc-stateline">
                            {exposure.overdue > 0 ? <span className="tc-status-pill overdue">{exposure.overdue} overdue</span> : null}
                            {exposure.dueSoon > 0 ? <span className="tc-status-pill due-soon">{exposure.dueSoon} due soon</span> : null}
                            {exposure.notDone > 0 ? <span className="tc-status-pill not-done">{exposure.notDone} not done</span> : null}
                            {exposure.overdue === 0 && exposure.dueSoon === 0 && exposure.notDone === 0 ? (
                              <span className="tc-status-pill ok">In tolerance</span>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <div className="tc-inline-actions">
                            {canManageCourses ? (
                              <button type="button" className="secondary-chip-btn" onClick={() => onOpenEditCourse(course)}>Modify</button>
                            ) : null}
                            {canManageCourses ? (
                              <button type="button" className="secondary-chip-btn" onClick={() => onOpenRequirement(course.id)}>Assign</button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="tc-panel">
          <div className="tc-panel__header">
            <div>
              <h2 className="tc-panel__title">Requirement rules</h2>
              <p className="tc-muted">Explicit rule rows drive the real training matrix by all staff, department, job role, or named user.</p>
            </div>
            {canManageCourses ? (
              <button type="button" className="secondary-chip-btn" onClick={() => onOpenRequirement()}>
                <Plus size={14} /> New rule
              </button>
            ) : null}
          </div>
          {requirements.length === 0 ? (
            <div className="tc-empty">
              No explicit requirement rows exist yet. Imported courses will still show their raw scope, but the operational matrix becomes much more useful once you assign formal rules.
            </div>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Scope</th>
                    <th>Applies to</th>
                    <th>Mandatory</th>
                    <th>Effective window</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {requirements.map((requirement) => {
                    const course = filteredCourses.find((item) => item.id === requirement.course_pk) || null;
                    const scopeBadge = requirementScopeBadge(requirement, directoryById);
                    return (
                      <tr key={requirement.id}>
                        <td>
                          <span className="tc-table__primary">{course?.course_id || requirement.course_pk}</span>
                          <span className="tc-table__secondary">{course?.course_name || "Course not currently visible"}</span>
                        </td>
                        <td>{humanizeEnum(requirement.scope)}</td>
                        <td>{scopeBadge.value}</td>
                        <td>{requirement.is_mandatory ? "Yes" : "No"}</td>
                        <td>{formatIsoDate(requirement.effective_from)} → {formatIsoDate(requirement.effective_to)}</td>
                        <td>{requirement.is_active ? "Active" : "Retired"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </>
    );
  }

  if (section === "schedule" || section === "sessions" || section === "attendance") {
    return (
      <section className="tc-panel">
        <div className="tc-panel__header">
          <div>
            <h2 className="tc-panel__title">Training schedule</h2>
            <p className="tc-muted">Upcoming and in-progress sessions with a direct route into the event scheduler.</p>
          </div>
          <button type="button" className="primary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/events`)}>
            <ExternalLink size={14} /> Open event scheduler
          </button>
        </div>
        {events.length === 0 ? (
          <div className="tc-empty">No training sessions are currently scheduled.</div>
        ) : (
          <div className="tc-table-wrap">
            <table className="tc-table">
              <thead>
                <tr>
                  <th>Course / Session</th>
                  <th>Starts</th>
                  <th>Ends</th>
                  <th>Provider</th>
                  <th>Location</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {events
                  .slice()
                  .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)))
                  .map((event) => (
                    <tr key={event.id}>
                      <td>
                        <span className="tc-table__primary">{event.title}</span>
                        <span className="tc-table__secondary">{event.id}</span>
                      </td>
                      <td>{formatIsoDate(event.starts_on)}</td>
                      <td>{formatIsoDate(event.ends_on)}</td>
                      <td>{event.provider || "—"}</td>
                      <td>{event.location || "—"}</td>
                      <td><span className={`tc-status-pill ${event.status === "COMPLETED" ? "ok" : event.status === "CANCELLED" ? "overdue" : "scheduled"}`}>{humanizeEnum(event.status)}</span></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  if (section === "assessments") {
    const pendingAssessments = props.records.filter((record) => record.exam_score == null);
    return (
      <section className="tc-panel">
        <div className="tc-panel__header">
          <div>
            <h2 className="tc-panel__title">Assessments and outcomes</h2>
            <p className="tc-muted">Records missing exam scores or final outcome evidence.</p>
          </div>
        </div>
        {pendingAssessments.length === 0 ? (
          <div className="tc-empty">No incomplete assessment rows are currently open.</div>
        ) : (
          <div className="tc-table-wrap">
            <table className="tc-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Course</th>
                  <th>Completed</th>
                  <th>Certificate</th>
                </tr>
              </thead>
              <tbody>
                {pendingAssessments.map((record) => {
                  const person = directoryById.get(record.user_id);
                  const course = props.courses.find((item) => item.id === record.course_id);
                  return (
                    <tr key={record.id}>
                      <td>{person?.full_name || record.user_id}</td>
                      <td>{course ? `${course.course_id} · ${course.course_name}` : record.course_id}</td>
                      <td>{formatIsoDate(record.completion_date)}</td>
                      <td>{record.certificate_reference || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  if (section === "certificates" || section === "templates") {
    return (
      <section className="tc-panel">
        <div className="tc-panel__header">
          <div>
            <h2 className="tc-panel__title">Certificates and audit evidence</h2>
            <p className="tc-muted">Issue missing certificate numbers, inspect issued records, and export user evidence packs.</p>
          </div>
          <div className="tc-inline-actions">
            <button type="button" className="secondary-chip-btn" onClick={onPrintSelectedRecord} disabled={!selectedUser}>
              <Printer size={14} /> Print selected record
            </button>
            <button type="button" className="secondary-chip-btn" onClick={() => void onDownloadEvidencePack()} disabled={!selectedUser}>
              <Download size={14} /> Evidence pack
            </button>
          </div>
        </div>
        {certificates.length === 0 ? (
          <div className="tc-empty">No certificates have been issued yet.</div>
        ) : (
          <div className="tc-table-wrap">
            <table className="tc-table tc-record-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Course</th>
                  <th>Completed</th>
                  <th>Valid until</th>
                  <th>Certificate</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {certificates.map((record) => {
                  const person = directoryById.get(record.user_id);
                  const course = props.courses.find((item) => item.id === record.course_id);
                  return (
                    <tr key={record.id}>
                      <td>{person?.full_name || record.user_id}</td>
                      <td>{course ? `${course.course_id} · ${course.course_name}` : record.course_id}</td>
                      <td>{formatIsoDate(record.completion_date)}</td>
                      <td>{formatIsoDate(record.valid_until)}</td>
                      <td>{record.certificate_reference || "—"}</td>
                      <td>
                        {!record.certificate_reference && canManageCourses ? (
                          <button type="button" className="secondary-chip-btn" onClick={async () => {
                            await issueTrainingCertificate(record.id);
                            await onRefresh();
                          }}>
                            Issue
                          </button>
                        ) : (
                          <button type="button" className="secondary-chip-btn" onClick={() => window.open(`/verify/certificate/${record.certificate_reference}`, "_blank")} disabled={!record.certificate_reference}>
                            Verify
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  if (section === "personnel") {
    return (
      <div className="tc-personnel-grid">
        <section className="tc-panel tc-personnel-grid__list">
          <div className="tc-panel__header">
            <div>
              <h2 className="tc-panel__title">Personnel training records</h2>
              <p className="tc-muted">Search staff, inspect their live training posture, import historical records, and print clean records.</p>
            </div>
            {canManageCourses ? (
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={onOpenRecordsImport}>
                  <UploadCloud size={14} /> Import TRAINING.xlsx
                </button>
              </div>
            ) : null}
          </div>
          <div className="tc-filterbar">
            <label style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: 12, top: 13, color: "#667085" }} />
              <input
                className="tc-input"
                style={{ paddingLeft: 34 }}
                placeholder="Search by name, staff code, email, or title"
                value={peopleSearch}
                onChange={(e) => setPeopleSearch(e.target.value)}
              />
            </label>
          </div>
          {filteredPeople.length === 0 ? (
            <div className="tc-empty">No personnel match the current filter.</div>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Status</th>
                    <th>Last seen</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPeople.map((person) => {
                    const userStatuses = statusByUser[person.id] || [];
                    const showTrainingAlerts = person.is_active;
                    const overdue = showTrainingAlerts ? userStatuses.filter((item) => item.status === "OVERDUE").length : 0;
                    const dueSoon = showTrainingAlerts ? userStatuses.filter((item) => item.status === "DUE_SOON").length : 0;
                    return (
                      <tr key={person.id}>
                        <td>
                          <span className="tc-table__primary">{person.full_name}</span>
                          <span className="tc-table__secondary">{person.staff_code} · {person.email}</span>
                        </td>
                        <td>{person.display_title}</td>
                        <td>{person.department_name || "—"}</td>
                        <td>
                          <div className="tc-stateline">
                            <span className={`tc-status-pill ${!person.is_active ? "not-done" : person.presence.is_online ? "ok" : "not-done"}`}>{!person.is_active ? "Inactive" : person.presence_display.status_label || (person.presence.is_online ? "Online" : "Offline")}</span>
                            {overdue > 0 ? <span className="tc-status-pill overdue">{overdue} overdue</span> : null}
                            {dueSoon > 0 ? <span className="tc-status-pill due-soon">{dueSoon} due soon</span> : null}
                          </div>
                        </td>
                        <td>{!person.is_active ? "Inactive user" : person.presence.is_online ? "Active now" : formatRelativeFromNow(person.presence.last_seen_at || person.last_login_at)}</td>
                        <td>
                          <div className="tc-inline-actions">
                            <button type="button" className="secondary-chip-btn" onClick={() => setSelectedUserId(person.id)}>Open</button>
                            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${person.id}`)}>
                              Profile
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="tc-user-card tc-personnel-grid__detail">
          {selectedUser ? (
            <>
              <div className="tc-panel__header">
                <div>
                  <h2 className="tc-panel__title">{selectedUser.full_name}</h2>
                  <p className="tc-muted">{selectedUser.staff_code} · {selectedUser.display_title} · {selectedUser.department_name || "No department"}</p>
                </div>
                <div className="tc-inline-actions">
                  <span className={`tc-status-pill ${!selectedUser.is_active ? "not-done" : selectedUser.presence.is_online ? "ok" : "not-done"}`}>{!selectedUser.is_active ? "Inactive" : selectedUser.presence.is_online ? "Online" : "Offline"}</span>
                  {selectedUser.is_active && selectedAccessState.crs_blocked ? <span className="tc-status-pill overdue">CRS blocked</span> : null}
                  {selectedUser.is_active && selectedAccessState.portal_locked ? <span className="tc-status-pill overdue">Portal locked</span> : null}
                </div>
              </div>
              {selectedUser.is_active ? (
                <div className="tc-user-card__metrics">
                  <MetricCard label="Overdue" value={selectedUserCounts.overdue} compact />
                  <MetricCard label="Due soon" value={selectedUserCounts.dueSoon} compact />
                  <MetricCard label="Deferred" value={selectedUserCounts.deferred} compact />
                  <MetricCard label="Not done" value={selectedUserCounts.notDone} compact />
                  <MetricCard label="OK" value={selectedUserCounts.ok} compact />
                </div>
              ) : (
                <div className="tc-import-note is-warning">This user is inactive/disabled. Historical records remain visible, but alert badges and gate indicators are suppressed.</div>
              )}
              <div className="tc-user-summary">
                <span className="tc-chip">Email: {selectedUser.email}</span>
                <span className="tc-chip">Last seen: {!selectedUser.is_active ? "Inactive user" : selectedUser.presence.is_online ? "Active now" : formatRelativeFromNow(selectedUser.presence.last_seen_at || selectedUser.last_login_at)}</span>
                <span className="tc-chip">Exact: {formatDateTime(selectedUser.presence.last_seen_at || selectedUser.last_login_at)}</span>
              </div>
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${selectedUser.id}`)}>
                  <ExternalLink size={14} /> Open full profile
                </button>
                <button type="button" className="secondary-chip-btn" onClick={onPrintSelectedRecord}>
                  <Printer size={14} /> Print PDF
                </button>
                <button type="button" className="secondary-chip-btn" onClick={() => void onDownloadEvidencePack()}>
                  <Download size={14} /> Evidence pack
                </button>
              </div>

              {selectedUserLoading ? <div className="tc-empty">Loading selected user data…</div> : null}
              {selectedUserError ? <div className="tc-empty">{selectedUserError}</div> : null}

              <div className="tc-table-wrap">
                <table className="tc-table tc-record-table">
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Status</th>
                      <th>Last completion</th>
                      <th>Next due</th>
                      <th>Next session</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedUserStatuses.map((item) => (
                      <tr key={`${selectedUser.id}-${item.course_id}`}>
                        <td>
                          <span className="tc-table__primary">{item.course_id}</span>
                          <span className="tc-table__secondary">{item.course_name}</span>
                        </td>
                        <td><span className={`tc-status-pill ${statusClass(item.status)}`}>{statusLabel(item.status)}</span></td>
                        <td>{formatIsoDate(item.last_completion_date)}</td>
                        <td>{formatIsoDate(getDueDate(item))}</td>
                        <td>{formatIsoDate(item.upcoming_event_date)}</td>
                      </tr>
                    ))}
                    {selectedUserStatuses.length === 0 ? (
                      <tr><td colSpan={5} className="tc-muted">No live compliance rows found for this user.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              <div className="tc-table-wrap">
                <table className="tc-table tc-record-table">
                  <thead>
                    <tr>
                      <th>Historical course record</th>
                      <th>Completed</th>
                      <th>Valid until</th>
                      <th>Hours</th>
                      <th>Score</th>
                      <th>Certificate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedUserRecords
                      .slice()
                      .sort((a, b) => String(b.completion_date || "").localeCompare(String(a.completion_date || "")))
                      .map((record) => {
                        const course = props.courses.find((item) => item.id === record.course_id);
                        return (
                          <tr key={record.id}>
                            <td>{course ? `${course.course_id} · ${course.course_name}` : record.course_id}</td>
                            <td>{formatIsoDate(record.completion_date)}</td>
                            <td>{formatIsoDate(record.valid_until)}</td>
                            <td>{record.hours_completed ?? "—"}</td>
                            <td>{record.exam_score ?? "—"}</td>
                            <td>{record.certificate_reference || "—"}</td>
                          </tr>
                        );
                      })}
                    {selectedUserRecords.length === 0 ? (
                      <tr><td colSpan={6} className="tc-muted">No historical training records found.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              {selectedUserCertificates.length > 0 ? (
                <p className="tc-muted">Issued certificates for selected user: {selectedUserCertificates.length}</p>
              ) : null}
            </>
          ) : (
            <div className="tc-empty">Select a user to inspect their live compliance matrix and printable training history.</div>
          )}
        </section>
      </div>
    );
  }

  return (
    <section className="tc-panel">
      <div className="tc-panel__header">
        <div>
          <h2 className="tc-panel__title">Policy and controls</h2>
          <p className="tc-muted">Operational reminders for lockout, deferrals, and role-based authorization.</p>
        </div>
      </div>
      <div className="tc-summary-grid">
        <MetricCard label="Pending deferrals" value={deferrals.filter((item) => item.status === "PENDING").length} compact />
        <MetricCard label="Approved deferrals" value={deferrals.filter((item) => item.status === "APPROVED").length} compact />
        <MetricCard label="Certificates" value={certificates.length} compact />
        <MetricCard label="Scheduled sessions" value={events.filter((event) => event.status === "PLANNED").length} compact />
      </div>
      <div className="tc-import-note">
        <strong>Portal behaviour</strong>
        <p className="tc-muted" style={{ marginTop: 6 }}>
          Keep the course catalog current, assign explicit requirement rules, schedule users before due dates, and review overdue mandatory training before authorizations remain in force.
        </p>
      </div>
      <div className="tc-empty">
        Use the <strong>Matrix</strong> section to assign rules, the <strong>Schedule</strong> section to plan delivery, and the <strong>Personnel</strong> section to print individual records or inspect CRS-block posture.
      </div>
    </section>
  );
};

const MetricCard: React.FC<{ label: string; value: number; compact?: boolean }> = ({ label, value, compact = false }) => (
  <div className={`tc-kpi-card${compact ? " compact" : ""}`}>
    <span>{label}</span>
    <strong>{value}</strong>
  </div>
);

export default TrainingCompetencePage;

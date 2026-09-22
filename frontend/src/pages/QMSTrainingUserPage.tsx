import type { ColDef, FirstDataRenderedEvent, GridReadyEvent, GridSizeChangedEvent, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { ArrowLeft, CalendarDays, Clock3, FolderOpen, GraduationCap, Package, ShieldCheck, Download, FileImage, FileText, Plus, X } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import Drawer from "../components/shared/Drawer";
import PersonnelLicencePanel from "../components/training/PersonnelLicencePanel";
import { getTrainingAccess } from "../services/trainingOperating";
import TrainingRequirementList from "../components/training/TrainingRequirementList";
import type { AdminUserRead } from "../services/adminUsers";
import { getCachedUser, getContext, type PortalUser } from "../services/auth";
import {
  createTrainingDeferralRequest,
  createTrainingRecord,
  deleteTrainingRecord,
  downloadTrainingFile,
  downloadTrainingUserEvidencePack,
  previewTrainingUserRecordPdf,
  getTrainingUserDetailBundle,
  listTrainingCourses,
  updateTrainingDeferralRequest,
  updateTrainingRecord,
  uploadTrainingFile,
  waitForTrainingUserRecordPdfReady,
  type TransferProgress,
  type TrainingFileRead,
} from "../services/training";
import type {
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventRead,
  TrainingRecordRead,
  TrainingRecordUpdate,
  TrainingStatusItem,
} from "../types/training";
import "../styles/training.css";
import { saveDownloadedFile } from "../utils/downloads";
import { canonicalTrainingType, complianceStatusLabel, completedEventStatusWithoutRequirement, explicitTrainingRequirementKey } from "../utils/trainingPresentation";

type LoadState = "idle" | "loading" | "ready" | "error";
type SortKey = "course" | "completion_date" | "valid_until" | "hours" | "score" | "certificate";
type SortDirection = "asc" | "desc";
type ProfileSection = "courses" | "schedule" | "deferrals" | "licences" | "evidence";
type RecordConflictKind = "duplicate" | "renewal";

type ScheduleGridRow = {
  id: string;
  course: string;
  session: string;
  starts: string;
  status: string;
  location: string;
};

type DeferralGridRow = {
  id: string;
  course: string;
  originalDue: string;
  newDue: string;
  status: string;
  reason: string;
  requested: string;
};

type EvidenceGridRow = {
  id: string;
  filename: string;
  kind: string;
  review: string;
  uploaded: string;
  isPdf: boolean;
  file: TrainingFileRead;
};

const PROFILE_GRID_DEFAULT_COL_DEF: ColDef = {
  resizable: true,
  sortable: true,
  suppressMovable: true,
  wrapHeaderText: false,
  autoHeaderHeight: false,
  flex: 1,
  minWidth: 96,
};

const PROFILE_GRID_HEADER_HEIGHT = 36;
const PROFILE_GRID_ROW_HEIGHT = 46;
const PROFILE_GRID_AUTO_SIZE = { type: "fitGridWidth" as const, defaultMinWidth: 96 };

function profileGridHostHeight(rowCount: number): number {
  return Math.max(160, Math.min(420, PROFILE_GRID_HEADER_HEIGHT + Math.max(rowCount, 1) * PROFILE_GRID_ROW_HEIGHT + 8));
}

function fitProfileGridColumns(api: { sizeColumnsToFit: () => void } | undefined | null): void {
  if (!api) return;
  requestAnimationFrame(() => {
    try {
      api.sizeColumnsToFit();
    } catch {
      /* grid may already be destroyed during tab switch */
    }
  });
}

function onProfileGridReady(event: GridReadyEvent): void {
  fitProfileGridColumns(event.api);
}

function onProfileGridFirstData(event: FirstDataRenderedEvent): void {
  fitProfileGridColumns(event.api);
}

function onProfileGridSizeChanged(event: GridSizeChangedEvent): void {
  if (event.clientWidth > 0) fitProfileGridColumns(event.api);
}

type RecordConflictState = {
  kind: RecordConflictKind;
  title: string;
  message: string;
  records: TrainingRecordRead[];
};

type DeferralReasonCategory =
  | "ILLNESS"
  | "OPERATIONAL_REQUIREMENTS"
  | "PERSONAL_EMERGENCY"
  | "PROVIDER_CANCELLATION"
  | "SYSTEM_FAILURE"
  | "OTHER";

const DEFERRAL_REASON_OPTIONS: Array<{ value: DeferralReasonCategory; label: string }> = [
  { value: "ILLNESS", label: "Illness" },
  { value: "OPERATIONAL_REQUIREMENTS", label: "Operational requirements" },
  { value: "PERSONAL_EMERGENCY", label: "Personal emergency" },
  { value: "PROVIDER_CANCELLATION", label: "Provider cancellation" },
  { value: "SYSTEM_FAILURE", label: "System failure" },
  { value: "OTHER", label: "Other" },
];

function portalUserToAdminUser(user: PortalUser): AdminUserRead {
  return {
    id: user.id,
    amo_id: user.amo_id || "",
    department_id: user.department_id,
    staff_code: user.staff_code,
    email: user.email,
    first_name: user.first_name,
    last_name: user.last_name,
    full_name: user.full_name,
    role: user.role,
    position_title: user.position_title,
    phone: user.phone,
    secondary_phone: null,
    regulatory_authority: user.regulatory_authority,
    licence_number: user.licence_number,
    licence_state_or_country: user.licence_state_or_country,
    licence_expires_on: user.licence_expires_on,
    is_active: user.is_active,
    is_superuser: user.is_superuser,
    is_amo_admin: user.is_amo_admin,
    must_change_password: user.must_change_password,
    token_revoked_at: null,
    last_login_at: user.last_login_at,
    last_login_ip: user.last_login_ip,
    created_at: user.created_at,
    updated_at: user.updated_at,
  };
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function addMonthsIso(dateValue: string, months: number | null | undefined): string {
  if (!dateValue || !months) return "-";
  const base = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(base.getTime())) return "-";
  const result = new Date(base);
  const originalDay = result.getDate();
  result.setMonth(result.getMonth() + months);
  if (result.getDate() < originalDay) {
    result.setDate(0);
  }
  return result.toISOString().slice(0, 10);
}


function coursePhase(course: TrainingCourseRead | null | undefined): "INITIAL" | "RECURRENT" | "ONE_OFF" | "UNKNOWN" {
  if (!course) return "UNKNOWN";
  const canonical = canonicalTrainingType(course);
  if (canonical) return canonical;
  const status = String(course.status || "").trim().toUpperCase();
  if (status === "ONE_OFF" || status === "ONE-OFF" || status === "ONE OFF") return "ONE_OFF";
  return "UNKNOWN";
}

function courseFamilyKey(course: TrainingCourseRead | null | undefined, courses: TrainingCourseRead[] = []): string {
  return explicitTrainingRequirementKey(course, courses);
}

function buildCourseLookup(courses: TrainingCourseRead[]): Map<string, TrainingCourseRead> {
  const lookup = new Map<string, TrainingCourseRead>();
  courses.forEach((course) => {
    if (course.id) lookup.set(String(course.id), course);
    if (course.course_id) lookup.set(String(course.course_id), course);
  });
  return lookup;
}

function resolveCourse(lookup: Map<string, TrainingCourseRead>, key: string | null | undefined): TrainingCourseRead | null {
  if (!key) return null;
  return lookup.get(String(key)) || null;
}

function cleanRoleTitle(user: AdminUserRead | null): string {
  const preferred = user?.position_title?.trim() || user?.role?.trim() || "";
  if (!preferred) return "-";
  return preferred.replace(/^TECHNICIAN\s*[-·]\s*/i, "").replace(/\s+/g, " ").trim();
}


function profileAvatarUrl(user: AdminUserRead | null): string | null {
  if (!user || typeof window === "undefined") return null;
  const candidates = [
    (user as any).avatar_url,
    (user as any).profile_photo_url,
    (user as any).photo_url,
    (user as any).portrait_url,
  ].filter(Boolean) as string[];
  if (candidates[0]) return candidates[0];
  const keys = [
    user.id ? `amo_portal_profile_avatar:${user.id}` : "",
    user.staff_code ? `amo_portal_profile_avatar:${user.staff_code}` : "",
    user.email ? `amo_portal_profile_avatar:${user.email}` : "",
    user.id ? `profile_avatar:${user.id}` : "",
  ].filter(Boolean);
  for (const key of keys) {
    const stored = window.localStorage.getItem(key);
    if (stored) return stored;
  }
  return null;
}

function profileAvatarVariant(user: AdminUserRead | null): "male" | "female" | "neutral" {
  const raw = String((user as any)?.gender || (user as any)?.sex || "").trim().toLowerCase();
  if (["f", "female", "woman", "lady"].includes(raw)) return "female";
  if (["m", "male", "man", "gentleman"].includes(raw)) return "male";
  return "neutral";
}

function initialsForUser(user: AdminUserRead | null): string {
  const name = user?.full_name || `${user?.first_name || ""} ${user?.last_name || ""}`.trim() || user?.email || "User";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "U";
}

function dueDateForItem(item: TrainingStatusItem | null | undefined): string | null {
  if (!item) return null;
  return item.extended_due_date || item.valid_until || null;
}

function daysUntilDueFromItem(item: TrainingStatusItem | null | undefined): number | null {
  if (!item) return null;
  if (typeof item.days_until_due === "number" && Number.isFinite(item.days_until_due)) return item.days_until_due;
  const due = dueDateForItem(item);
  if (!due) return null;
  const dueEnd = new Date(`${due}T23:59:59`);
  if (Number.isNaN(dueEnd.getTime())) return null;
  const diffMs = dueEnd.getTime() - Date.now();
  return Math.floor(diffMs / (24 * 60 * 60 * 1000));
}

function effectiveTrainingStatus(item: TrainingStatusItem | null | undefined): string {
  return item?.status || "NOT_DONE";
}

function effectiveTrainingStatusForRecord(record: TrainingRecordRead | null | undefined, item: TrainingStatusItem | null | undefined): string {
  if (item) return effectiveTrainingStatus(item);
  return completedEventStatusWithoutRequirement(Boolean(record?.completion_date));
}

function normaliseRecordLifecycleStatus(record: TrainingRecordRead | null | undefined): string {
  return String(record?.record_status || record?.source_status || "ACTIVE").trim().toUpperCase().replace(/\s+/g, "_");
}

function isHistoricalTrainingRecord(record: TrainingRecordRead | null | undefined): boolean {
  const status = normaliseRecordLifecycleStatus(record);
  return status === "RENEWED" || status === "SUPERSEDED" || status === "INACTIVE";
}

function recordDateTime(value: string | null | undefined, fallback = 0): number {
  if (!value) return fallback;
  const parsed = new Date(value.includes("T") ? value : `${value}T12:00:00`).getTime();
  return Number.isFinite(parsed) ? parsed : fallback;
}

function compareRecordRecency(a: TrainingRecordRead, b: TrainingRecordRead): number {
  const completedDiff = recordDateTime(a.completion_date) - recordDateTime(b.completion_date);
  if (completedDiff !== 0) return completedDiff;
  const createdDiff = recordDateTime(a.created_at) - recordDateTime(b.created_at);
  if (createdDiff !== 0) return createdDiff;
  return String(a.id || "").localeCompare(String(b.id || ""));
}

function dedupeTrainingRecords(input: TrainingRecordRead[]): TrainingRecordRead[] {
  const latestByCourse = new Map<string, TrainingRecordRead>();
  input.forEach((record) => {
    if (isHistoricalTrainingRecord(record)) return;
    const key = String(record.course_id || record.course_pk || "").trim();
    if (!key) return;
    const previous = latestByCourse.get(key);
    if (!previous || compareRecordRecency(record, previous) > 0) {
      latestByCourse.set(key, record);
    }
  });
  return [...latestByCourse.values()].sort((a, b) => compareRecordRecency(b, a));
}

function trainingApiConflictFromError(error: any): { code: string; message: string; records: TrainingRecordRead[] } | null {
  const detail = error?.detail || error?.responseBody?.detail;
  if (detail && typeof detail === "object" && typeof detail.code === "string") {
    const records = Array.isArray(detail.records) ? detail.records : detail.record ? [detail.record] : [];
    return {
      code: detail.code,
      message: String(detail.message || error?.message || "Training record conflict."),
      records: records as TrainingRecordRead[],
    };
  }
  const message = String(error?.message || "");
  if (message.includes("TRAINING_RECORD_RENEWAL_CONFIRMATION_REQUIRED")) {
    return { code: "TRAINING_RECORD_RENEWAL_CONFIRMATION_REQUIRED", message, records: [] };
  }
  if (message.includes("DUPLICATE_TRAINING_RECORD")) {
    return { code: "DUPLICATE_TRAINING_RECORD", message, records: [] };
  }
  return null;
}

function statusLabel(status: string): string {
  return complianceStatusLabel(status);
}

function statusPillClass(status: string): string {
  if (status === "OVERDUE") return "qms-pill qms-pill--danger";
  if (status === "DUE_SOON") return "qms-pill qms-pill--warning";
  if (status === "DEFERRED") return "qms-pill qms-pill--info";
  if (status === "SCHEDULED_ONLY") return "qms-pill qms-pill--info";
  if (status === "NOT_DONE") return "qms-pill qms-pill--danger";
  return "qms-pill qms-pill--success";
}

function deferralStatusPill(status: string): string {
  if (status === "APPROVED") return "qms-pill qms-pill--success";
  if (status === "REJECTED") return "qms-pill qms-pill--danger";
  if (status === "CANCELLED") return "qms-pill";
  return "qms-pill qms-pill--warning";
}

function dueLabel(item: TrainingStatusItem | null | undefined): string {
  const due = dueDateForItem(item);
  if (!due) return "-";
  if (item?.extended_due_date && item?.valid_until && item.extended_due_date !== item.valid_until) {
    return `Deferred to ${formatDate(item.extended_due_date)}`;
  }
  return formatDate(due);
}

function timeLeftFromDueDate(due: string | null | undefined): string {
  if (!due) return "-";
  const dueEnd = new Date(`${due}T23:59:59`);
  if (Number.isNaN(dueEnd.getTime())) return "-";
  const diffMs = dueEnd.getTime() - Date.now();
  const absMs = Math.abs(diffMs);
  const dayMs = 24 * 60 * 60 * 1000;
  const hourMs = 60 * 60 * 1000;
  if (diffMs < 0) {
    const overdueDays = Math.floor(absMs / dayMs);
    if (overdueDays >= 1) return `Overdue by ${overdueDays} D`;
    const overdueHours = Math.max(1, Math.ceil(absMs / hourMs));
    return `Overdue by ${overdueHours} H`;
  }
  const days = Math.floor(diffMs / dayMs);
  if (days >= 1) return `${days} D`;
  const hours = Math.max(0, Math.ceil(diffMs / hourMs));
  return `${hours} H`;
}

function dueCountdownLabel(item: TrainingStatusItem | null | undefined): string {
  if (!item) return "-";
  const effectiveStatus = effectiveTrainingStatus(item);
  if (effectiveStatus === "OVERDUE") return "Overdue";
  if (effectiveStatus === "OK") return "Current";
  if (effectiveStatus === "NOT_DONE") return "Not completed";
  if (effectiveStatus === "DEFERRED") {
    const due = dueDateForItem(item);
    return due ? `Deferred to ${formatDate(due)}` : "Deferred";
  }
  const due = dueDateForItem(item);
  if (!due) return "-";
  const timeLeft = timeLeftFromDueDate(due);
  if (timeLeft === "-") return formatDate(due);
  return `Due in (${timeLeft})`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatTransferPercent(progress: number): string {
  return `${Math.max(0, Math.min(100, Math.round(progress)))}%`;
}

type TransferButtonState = {
  active: boolean;
  progress: number;
  label: string;
};

function TransferProgressButton({
  variant,
  idleLabel,
  busyState,
  disabled,
  onClick,
}: {
  variant: "primary-chip-btn" | "secondary-chip-btn";
  idleLabel: string;
  busyState: TransferButtonState;
  disabled?: boolean;
  onClick: () => void;
}) {
  const showBusy = busyState.active;
  return (
    <button
      type="button"
      className={`${variant} training-progress-button ${showBusy ? "is-busy" : ""}`.trim()}
      disabled={disabled}
      onClick={onClick}
      aria-busy={showBusy}
    >
      <span
        className="training-progress-button__fill"
        style={{ width: showBusy ? `${Math.max(6, Math.min(100, busyState.progress))}%` : "0%" }}
        aria-hidden="true"
      />
      <span className="training-progress-button__content">
        <span className="training-progress-button__label">{showBusy ? busyState.label : idleLabel}</span>
        {showBusy && <span className="training-progress-button__value">{formatTransferPercent(busyState.progress)}</span>}
      </span>
    </button>
  );
}

const QMSTrainingUserPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; userId?: string; staffId?: string }>();
  const [searchParams] = useSearchParams();
  const ctx = getContext();
  const navigate = useNavigate();
  const cachedUser = getCachedUser();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const userId = params.userId ?? params.staffId ?? cachedUser?.id ?? "";
  const isOwnProfile = Boolean(cachedUser && userId === cachedUser.id);
  const [canEdit, setCanEdit] = useState(false);

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AdminUserRead | null>(null);
  const [hireDate, setHireDate] = useState<string | null>(null);
  const [items, setItems] = useState<TrainingStatusItem[]>([]);
  const [records, setRecords] = useState<TrainingRecordRead[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [deferrals, setDeferrals] = useState<TrainingDeferralRequestRead[]>([]);
  const [files, setFiles] = useState<TrainingFileRead[]>([]);
  const [statusFilter, setStatusFilter] = useState(searchParams.get("filter") || "ALL");
  const [activeSection, setActiveSection] = useState<ProfileSection>(() => {
    const tab = searchParams.get("tab");
    return tab === "schedule" || tab === "deferrals" || tab === "licences" || tab === "evidence" ? tab : "courses";
  });
  const sectionStartRef = useRef<HTMLDivElement>(null);
  const selectSection = (section: ProfileSection) => {
    setActiveSection(section);
    sectionStartRef.current?.scrollIntoView({ block: "nearest" });
  };
  const [sortKey, setSortKey] = useState<SortKey>("completion_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [exportingEvidence, setExportingEvidence] = useState(false);
  const [exportingRecord, setExportingRecord] = useState(false);
  const [pdfReady, setPdfReady] = useState(false);
  const [recordTransfer, setRecordTransfer] = useState<TransferButtonState>({ active: false, progress: 0, label: "Staging PDF" });
  const [evidenceTransfer, setEvidenceTransfer] = useState<TransferButtonState>({ active: false, progress: 0, label: "Preparing pack" });

  const [recordForm, setRecordForm] = useState({
    coursePk: "",
    completionDate: new Date().toISOString().slice(0, 10),
    examScore: "",
    certificateReference: "",
    remarks: "",
  });
  const [recordAttachment, setRecordAttachment] = useState<File | null>(null);
  const [recordAttachmentKind, setRecordAttachmentKind] = useState("EVIDENCE");
  const [savingRecord, setSavingRecord] = useState(false);
  const [recordConflict, setRecordConflict] = useState<RecordConflictState | null>(null);
  const [editingRecordId, setEditingRecordId] = useState<string | null>(null);
  const [recordDrawerOpen, setRecordDrawerOpen] = useState(false);
  const [actionsDrawerOpen, setActionsDrawerOpen] = useState(false);
  const [deferralDrawerOpen, setDeferralDrawerOpen] = useState(false);
  const [inlineAttachmentTargetRecordId, setInlineAttachmentTargetRecordId] = useState<string | null>(null);
  const [uploadingInlineAttachment, setUploadingInlineAttachment] = useState(false);
  const [viewerFile, setViewerFile] = useState<TrainingFileRead | null>(null);
  const [viewerBlobUrl, setViewerBlobUrl] = useState<string | null>(null);
  const [viewerLoading, setViewerLoading] = useState(false);
  const inlineAttachmentInputRef = useRef<HTMLInputElement | null>(null);

  const [deferralForm, setDeferralForm] = useState({
    coursePk: "",
    requestedNewDueDate: "",
    reasonCategory: "OTHER" as DeferralReasonCategory,
    reasonText: "",
  });
  const [savingDeferral, setSavingDeferral] = useState(false);

  const load = async () => {
    if (!userId) {
      setError("Training profile could not be resolved.");
      setState("error");
      return;
    }
    setState("loading");
    setError(null);

    const result = await Promise.allSettled([
      listTrainingCourses({ include_inactive: true, limit: 200 }),
      getTrainingUserDetailBundle(userId, { recordsLimit: 200, deferralsLimit: 50, filesLimit: 200, eventsLimit: 20 }),
      getTrainingAccess(),
    ]);

    const [courseResult, bundleResult, accessResult] = result;
    setCanEdit(accessResult.status === "fulfilled" && accessResult.value.capabilities.includes("training.people.manage"));
    const bundle = bundleResult.status === "fulfilled" ? bundleResult.value : null;
    const resolvedUser = bundle?.user || (isOwnProfile && cachedUser ? portalUserToAdminUser(cachedUser) : null);

    if (!resolvedUser || !bundle) {
      const userError = bundleResult.status === "rejected" ? bundleResult.reason?.message || "Failed to load user profile." : "Failed to load user profile.";
      setError(userError);
      setState("error");
      return;
    }

    setUser(resolvedUser);
    setHireDate(bundle.hire_date || null);
    const listedCourses = courseResult.status === "fulfilled" ? courseResult.value : [];
    const bundleCourses = Array.isArray(bundle.courses) ? bundle.courses : [];
    const mergedCourses = new Map<string, TrainingCourseRead>();
    [...listedCourses, ...bundleCourses].forEach((course) => {
      const key = String(course.id || course.course_pk || course.course_id || "");
      if (key) mergedCourses.set(key, course);
    });
    setCourses(Array.from(mergedCourses.values()));
    setItems(bundle.status_items || []);
    setRecords(dedupeTrainingRecords(bundle.records || []));
    setDeferrals(bundle.deferrals || []);
    setEvents(bundle.upcoming_events || []);
    setFiles(bundle.files || []);

    const errors: string[] = [];
    [courseResult, bundleResult, accessResult].forEach((entry) => {
      if (entry.status === "rejected") {
        const message = String(entry.reason?.message || "").trim();
        if (message) errors.push(message);
      }
    });
    setError(errors.length > 0 ? errors[0] : null);
    setState("ready");
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    if (canEdit && searchParams.get("tab") === "new-record") {
      setRecordDrawerOpen(true);
    }
  }, [canEdit, searchParams]);

  const startProgressSimulation = (
    setState: React.Dispatch<React.SetStateAction<TransferButtonState>>,
    label: string,
    start = 8,
    ceiling = 84,
  ) => {
    setState({ active: true, progress: start, label });
    const timer = window.setInterval(() => {
      setState((prev) => {
        if (!prev.active) return prev;
        const next = Math.min(ceiling, prev.progress + Math.max(1, (ceiling - prev.progress) * 0.12));
        return { ...prev, progress: next, label };
      });
    }, 140);
    return () => window.clearInterval(timer);
  };

  const finalizeProgress = (setState: React.Dispatch<React.SetStateAction<TransferButtonState>>, label: string) => {
    setState({ active: true, progress: 100, label });
    window.setTimeout(() => setState({ active: false, progress: 0, label }), 520);
  };


  const handleExportEvidence = async () => {
    if (!userId) return;
    setExportingEvidence(true);
    const stopSim = startProgressSimulation(setEvidenceTransfer, "Preparing evidence pack", 10, 86);
    try {
      let file = null as Awaited<ReturnType<typeof downloadTrainingUserEvidencePack>> | null;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          file = await downloadTrainingUserEvidencePack(userId, (progress: TransferProgress) => {
            setEvidenceTransfer({
              active: true,
              progress: progress.percent ?? 92,
              label: progress.percent != null ? "Downloading evidence pack" : "Generating evidence pack",
            });
          });
          break;
        } catch (error) {
          if (attempt === 1) throw error;
          setEvidenceTransfer((prev) => ({ ...prev, active: true, progress: Math.max(prev.progress, 42), label: "Retrying evidence pack" }));
          await delay(350);
        }
      }
      saveDownloadedFile(file as Awaited<ReturnType<typeof downloadTrainingUserEvidencePack>>);
      finalizeProgress(setEvidenceTransfer, "Evidence pack ready");
    } catch (e: any) {
      setEvidenceTransfer({ active: false, progress: 0, label: "Preparing evidence pack" });
      setError(e?.message || "Failed to export training evidence pack.");
    } finally {
      stopSim();
      setExportingEvidence(false);
    }
  };

  const openTrainingRecordPreview = async (blob: Blob) => {
    const url = URL.createObjectURL(blob);
    const opened = window.open(url, "_blank", "noopener,noreferrer");
    if (!opened) {
      saveDownloadedFile(blob, `${(user?.full_name || "training-record").replace(/\s+/g, "_")}.pdf`);
      window.setTimeout(() => URL.revokeObjectURL(url), 1_500);
      return;
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
  };

  const handleExportRecord = async () => {
    if (!userId) return;
    setExportingRecord(true);
    const stopSim = startProgressSimulation(setRecordTransfer, "Preparing PDF", 8, 76);
    try {
      setRecordTransfer((prev) => ({ active: true, progress: Math.max(prev.progress, 18), label: "Preparing PDF" }));
      const ready = await waitForTrainingUserRecordPdfReady(userId, { attempts: 10, intervalMs: 350 });
      setPdfReady(ready);
      setRecordTransfer((prev) => ({ active: true, progress: Math.max(prev.progress, ready ? 66 : 52), label: ready ? "Opening PDF" : "Building PDF" }));
      const blob = await previewTrainingUserRecordPdf(userId);
      await openTrainingRecordPreview(blob);
      setPdfReady(true);
      finalizeProgress(setRecordTransfer, "PDF opened");
    } catch (e: any) {
      setRecordTransfer({ active: false, progress: 0, label: "Preparing PDF" });
      setError(e?.message || "Failed to open the individual training record PDF.");
    } finally {
      stopSim();
      setExportingRecord(false);
    }
  };

  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses]);
  const courseLookup = useMemo(() => buildCourseLookup(courses), [courses]);

  const itemByCoursePk = useMemo(() => {
    const map = new Map<string, TrainingStatusItem>();
    items.forEach((item) => {
      const match = resolveCourse(courseLookup, item.course_id) || courses.find((course) => course.course_name === item.course_name);
      if (match) map.set(match.id, item);
    });
    return map;
  }, [courseLookup, courses, items]);

  const completedInitialFamilyKeys = useMemo(() => {
    const keys = new Set<string>();
    records.forEach((record) => {
      if (!record.completion_date) return;
      const course = resolveCourse(courseLookup, record.course_id);
      if (coursePhase(course) === "INITIAL") {
        const key = courseFamilyKey(course, courses);
        if (key) keys.add(key);
      }
    });
    return keys;
  }, [courseLookup, courses, records]);

  const recordableCourses = useMemo(() => {
    return courses.filter((course) => {
      if (coursePhase(course) !== "RECURRENT") return true;
      const family = courseFamilyKey(course, courses);
      if (!family) return true;
      const hasInitialCourse = courses.some((entry) => coursePhase(entry) === "INITIAL" && courseFamilyKey(entry, courses) === family);
      if (!hasInitialCourse) return true;
      return completedInitialFamilyKeys.has(family);
    });
  }, [completedInitialFamilyKeys, courses]);

  useEffect(() => {
    if (!deferralForm.coursePk && items.length > 0) {
      const target = items.find((item) => {
        const status = effectiveTrainingStatus(item);
        return status === "OVERDUE" || status === "DUE_SOON" || status === "NOT_DONE";
      }) || items[0];
      const match = resolveCourse(courseLookup, target.course_id) || courses.find((course) => course.course_name === target.course_name);
      if (match) {
        setDeferralForm((prev) => ({ ...prev, coursePk: match.id }));
      }
    }
    if ((!recordForm.coursePk || !recordableCourses.some((course) => course.id === recordForm.coursePk)) && recordableCourses.length > 0) {
      setRecordForm((prev) => ({ ...prev, coursePk: recordableCourses[0].id }));
    }
  }, [courseLookup, courses, deferralForm.coursePk, items, recordForm.coursePk, recordableCourses]);

  const selectedCourse = useMemo(() => courseById.get(recordForm.coursePk) || null, [courseById, recordForm.coursePk]);
  const selectedCourseStatus = useMemo(() => itemByCoursePk.get(recordForm.coursePk) || null, [itemByCoursePk, recordForm.coursePk]);
  const activeRecordsForSelectedCourse = useMemo(() => {
    if (!recordForm.coursePk) return [] as TrainingRecordRead[];
    return records
      .filter((record) => !isHistoricalTrainingRecord(record))
      .filter((record) => String(record.course_id || record.course_pk || "") === String(recordForm.coursePk))
      .filter((record) => !editingRecordId || record.id !== editingRecordId)
      .sort((a, b) => compareRecordRecency(b, a));
  }, [editingRecordId, recordForm.coursePk, records]);
  const exactDuplicateRecord = useMemo(() => {
    if (!recordForm.coursePk || !recordForm.completionDate) return null;
    return activeRecordsForSelectedCourse.find((record) => record.completion_date === recordForm.completionDate) || null;
  }, [activeRecordsForSelectedCourse, recordForm.completionDate, recordForm.coursePk]);
  const linkedRefresherCourse = useMemo(() => {
    if (coursePhase(selectedCourse) !== "INITIAL") return null;
    const family = courseFamilyKey(selectedCourse, courses);
    if (!family) return null;
    return courses.find((course) => coursePhase(course) === "RECURRENT" && courseFamilyKey(course, courses) === family) || null;
  }, [courses, selectedCourse]);
  const selectedCoursePhase = coursePhase(selectedCourse);
  const derivedValidUntil = useMemo(() => {
    if (selectedCoursePhase === "INITIAL" && linkedRefresherCourse?.frequency_months) {
      return addMonthsIso(recordForm.completionDate, linkedRefresherCourse.frequency_months);
    }
    return addMonthsIso(recordForm.completionDate, selectedCourse?.frequency_months);
  }, [linkedRefresherCourse, recordForm.completionDate, selectedCourse?.frequency_months, selectedCoursePhase]);
  const derivedHours = selectedCourse?.nominal_hours ?? null;
  const derivedDueLabel = selectedCoursePhase === "INITIAL" && linkedRefresherCourse ? "Linked refresher due" : "Next due";

  const sortedRecords = useMemo(() => {
    const rows = records.slice().sort((a, b) => {
      const leftCourse = resolveCourse(courseLookup, a.course_id);
      const rightCourse = resolveCourse(courseLookup, b.course_id);
      const leftCourseName = `${leftCourse?.course_id || a.course_id} ${leftCourse?.course_name || ""}`.trim().toLowerCase();
      const rightCourseName = `${rightCourse?.course_id || b.course_id} ${rightCourse?.course_name || ""}`.trim().toLowerCase();
      let result = 0;
      switch (sortKey) {
        case "course":
          result = leftCourseName.localeCompare(rightCourseName);
          break;
        case "valid_until":
          result = String(a.valid_until || "").localeCompare(String(b.valid_until || ""));
          break;
        case "hours":
          result = (a.hours_completed || 0) - (b.hours_completed || 0);
          break;
        case "score":
          result = (a.exam_score || 0) - (b.exam_score || 0);
          break;
        case "certificate":
          result = String(a.certificate_reference || "").localeCompare(String(b.certificate_reference || ""));
          break;
        case "completion_date":
        default:
          result = String(a.completion_date || "").localeCompare(String(b.completion_date || ""));
          break;
      }
      return sortDirection === "asc" ? result : -result;
    });
    return rows;
  }, [courseLookup, records, sortDirection, sortKey]);

  const nextDue = useMemo(() => {
    const withDue = items
      .filter((item) => Boolean(dueDateForItem(item)))
      .slice()
      .sort((a, b) => String(dueDateForItem(a) || "").localeCompare(String(dueDateForItem(b) || "")));
    return withDue[0] || null;
  }, [items]);

  const relevantCourseIds = useMemo(() => {
    const ids = new Set<string>();
    sortedRecords.forEach((record) => ids.add(resolveCourse(courseLookup, record.course_id)?.id || record.course_id));
    itemByCoursePk.forEach((_item, coursePk) => ids.add(coursePk));
    return ids;
  }, [courseLookup, itemByCoursePk, sortedRecords]);

  const relevantEvents = useMemo(() => {
    return events
      .filter((event) => relevantCourseIds.has(event.course_id || event.course_pk || ""))
      .slice()
      .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)));
  }, [events, relevantCourseIds]);

  const scheduleRows = useMemo<ScheduleGridRow[]>(() => {
    return relevantEvents.map((event) => {
      const course = resolveCourse(courseLookup, event.course_id);
      return {
        id: event.id,
        course: course?.course_name || event.course_id,
        session: event.title || "-",
        starts: formatDate(event.starts_on),
        status: event.status,
        location: event.location || "-",
      };
    });
  }, [courseLookup, relevantEvents]);

  const deferralRows = useMemo<DeferralGridRow[]>(() => {
    return deferrals.map((deferral) => {
      const course = resolveCourse(courseLookup, deferral.course_id);
      return {
        id: deferral.id,
        course: course?.course_name || deferral.course_id,
        originalDue: formatDate(deferral.original_due_date),
        newDue: formatDate(deferral.requested_new_due_date),
        status: deferral.status,
        reason: deferral.reason_text || deferral.reason_category || "-",
        requested: formatDateTime(deferral.created_at),
      };
    });
  }, [courseLookup, deferrals]);

  const evidenceRows = useMemo<EvidenceGridRow[]>(() => {
    return files.map((file) => {
      const isPdf = (file.content_type || "").toLowerCase().includes("pdf") || file.original_filename.toLowerCase().endsWith(".pdf");
      return {
        id: file.id,
        filename: file.original_filename,
        kind: file.kind,
        review: file.review_status,
        uploaded: formatDateTime(file.uploaded_at),
        isPdf,
        file,
      };
    });
  }, [files]);

  const visibleCompletedRows = useMemo(() => {
    return sortedRecords.filter((record) => !isHistoricalTrainingRecord(record));
  }, [sortedRecords]);

  const filteredCompletedRows = useMemo(() => {
    return visibleCompletedRows.filter((record) => {
      const item = itemByCoursePk.get(record.course_id);
      const status = effectiveTrainingStatusForRecord(record, item);
      if (statusFilter === "ALL") return true;
      return status === statusFilter;
    });
  }, [itemByCoursePk, statusFilter, visibleCompletedRows]);

  const filteredMissingRows = useMemo(() => {
    const base = items.filter((item) => effectiveTrainingStatus(item) === "NOT_DONE").filter((item) => {
      const course = resolveCourse(courseLookup, item.course_id) || courses.find((entry) => entry.course_name === item.course_name) || null;
      if (coursePhase(course) !== "RECURRENT") return true;
      const family = courseFamilyKey(course, courses);
      if (!family) return true;
      const hasInitialCourse = courses.some((entry) => coursePhase(entry) === "INITIAL" && courseFamilyKey(entry, courses) === family);
      if (!hasInitialCourse) return true;
      return completedInitialFamilyKeys.has(family);
    });
    if (statusFilter === "ALL" || statusFilter === "NOT_DONE") return base;
    return base.filter((item) => effectiveTrainingStatus(item) === statusFilter);
  }, [completedInitialFamilyKeys, courseLookup, courses, items, statusFilter]);

  const recentFiles = useMemo(
    () => files.slice().sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || ""))).slice(0, 12),
    [files],
  );

  const latestFileByRecordId = useMemo(() => {
    const map = new Map<string, TrainingFileRead>();
    files
      .slice()
      .sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || "")))
      .forEach((file) => {
        if (file.record_id && !map.has(file.record_id)) map.set(file.record_id, file);
      });
    return map;
  }, [files]);

  useEffect(() => {
    return () => {
      if (viewerBlobUrl) window.URL.revokeObjectURL(viewerBlobUrl);
    };
  }, [viewerBlobUrl]);

  const resetRecordForm = () => {
    setEditingRecordId(null);
    setRecordForm({
      coursePk: "",
      completionDate: new Date().toISOString().slice(0, 10),
      examScore: "",
      certificateReference: "",
      remarks: "",
    });
    setRecordAttachment(null);
    setRecordAttachmentKind("EVIDENCE");
  };

  const closeRecordDrawer = () => {
    if (savingRecord) return;
    setRecordDrawerOpen(false);
    setRecordConflict(null);
    resetRecordForm();
  };

  const openRecordDrawer = () => {
    setRecordDrawerOpen(true);
  };

  const openDeferralDrawer = () => {
    setDeferralDrawerOpen(true);
  };

  const closeDeferralDrawer = () => {
    if (savingDeferral) return;
    setDeferralDrawerOpen(false);
  };

  const beginNewRecord = (coursePk?: string) => {
    resetRecordForm();
    if (coursePk) {
      setRecordForm((prev) => ({ ...prev, coursePk }));
      setRecordAttachmentKind("CERTIFICATE");
    }
    openRecordDrawer();
  };

  const openRecordEditor = (record: TrainingRecordRead) => {
    setEditingRecordId(record.id);
    setRecordForm({
      coursePk: resolveCourse(courseLookup, record.course_pk || record.course_id)?.id || record.course_id,
      completionDate: record.completion_date,
      examScore: record.exam_score == null ? "" : String(record.exam_score),
      certificateReference: record.certificate_reference || "",
      remarks: record.remarks || "",
    });
    setRecordAttachment(null);
    setRecordAttachmentKind("CERTIFICATE");
    openRecordDrawer();
  };

  const deleteRecord = async (record: TrainingRecordRead) => {
    if (!window.confirm(`Delete the training record for ${record.course_name || record.course_code || record.course_id}?`)) return;
    try {
      await deleteTrainingRecord(record.id);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to delete training record.");
    }
  };

  const openFileViewer = async (file: TrainingFileRead) => {
    try {
      setViewerLoading(true);
      if (viewerBlobUrl) window.URL.revokeObjectURL(viewerBlobUrl);
      const downloaded = await downloadTrainingFile(file.id);
      const url = window.URL.createObjectURL(downloaded.blob);
      setViewerFile(file);
      setViewerBlobUrl(url);
    } catch (e: any) {
      setError(e?.message || "Failed to open attachment.");
    } finally {
      setViewerLoading(false);
    }
  };

  const closeViewer = () => {
    if (viewerBlobUrl) window.URL.revokeObjectURL(viewerBlobUrl);
    setViewerBlobUrl(null);
    setViewerFile(null);
    setViewerLoading(false);
  };

  const handleDownloadCertificate = async (file: TrainingFileRead) => {
    try { saveDownloadedFile(await downloadTrainingFile(file.id)); }
    catch (e: any) { setError(e?.message || "Failed to download certificate."); }
  };

  const triggerInlineAttachmentUpload = (recordId: string) => {
    if (!canEdit || uploadingInlineAttachment) return;
    setInlineAttachmentTargetRecordId(recordId);
    inlineAttachmentInputRef.current?.click();
  };

  const handleInlineAttachmentChosen = async (file: File | null) => {
    if (!canEdit || !file || !inlineAttachmentTargetRecordId || !userId) return;
    const targetRecord = records.find((entry) => entry.id === inlineAttachmentTargetRecordId);
    if (!targetRecord) return;
    try {
      setUploadingInlineAttachment(true);
      const payload = new FormData();
      payload.append("file", file);
      payload.append("kind", "CERTIFICATE");
      payload.append("owner_user_id", userId);
      payload.append("course_id", targetRecord.course_id);
      payload.append("record_id", targetRecord.id);
      const uploaded = await uploadTrainingFile(payload);
      await updateTrainingRecord(targetRecord.id, { attachment_file_id: uploaded.id });
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to attach certificate to this record.");
    } finally {
      setUploadingInlineAttachment(false);
      setInlineAttachmentTargetRecordId(null);
      if (inlineAttachmentInputRef.current) inlineAttachmentInputRef.current.value = "";
    }
  };

  const submitRecord = async (confirmRenewal = false) => {
    if (!canEdit) return;
    if (!recordForm.coursePk || !userId) {
      setError("Select a course before saving a training record.");
      return;
    }
    const currentRecordFile = editingRecordId ? latestFileByRecordId.get(editingRecordId) : null;
    if (recordForm.certificateReference.trim() && !recordAttachment && !currentRecordFile) {
      setError("Attach the certificate file before saving a certificate reference.");
      return;
    }

    if (exactDuplicateRecord) {
      setError(null);
      setRecordConflict({
        kind: "duplicate",
        title: "Duplicate training record detected",
        message: "A current record already exists for the selected course and completion date. Review the existing details instead of saving a second copy.",
        records: [exactDuplicateRecord],
      });
      return;
    }

    if (!editingRecordId && !confirmRenewal && activeRecordsForSelectedCourse.length > 0) {
      setError(null);
      setRecordConflict({
        kind: "renewal",
        title: "Confirm training renewal",
        message: "This person already has a current record for the selected course. Saving this entry will mark the previous record as RENEWED in the database and hide it from the visible training record list.",
        records: activeRecordsForSelectedCourse,
      });
      return;
    }

    setSavingRecord(true);
    setError(null);
    try {
      let attachmentFileId: string | null = null;
      if (recordAttachment) {
        const payload = new FormData();
        payload.append("file", recordAttachment);
        payload.append("kind", recordForm.certificateReference.trim() ? "CERTIFICATE" : recordAttachmentKind);
        payload.append("owner_user_id", userId);
        payload.append("course_id", recordForm.coursePk);
        if (editingRecordId) payload.append("record_id", editingRecordId);
        const uploaded = await uploadTrainingFile(payload);
        attachmentFileId = uploaded.id;
      }

      if (editingRecordId) {
        const payload: TrainingRecordUpdate = {
          completion_date: recordForm.completionDate,
          valid_until: derivedValidUntil !== "-" ? derivedValidUntil : null,
          exam_score: recordForm.examScore ? Number(recordForm.examScore) : null,
          certificate_reference: recordForm.certificateReference.trim() || null,
          remarks: recordForm.remarks.trim() || null,
        };
        if (attachmentFileId) payload.attachment_file_id = attachmentFileId;
        await updateTrainingRecord(editingRecordId, payload);
      } else {
        await createTrainingRecord({
          user_id: userId,
          course_pk: recordForm.coursePk,
          completion_date: recordForm.completionDate,
          hours_completed: derivedHours,
          valid_until: derivedValidUntil !== "-" ? derivedValidUntil : null,
          exam_score: recordForm.examScore ? Number(recordForm.examScore) : null,
          certificate_reference: recordForm.certificateReference.trim() || null,
          attachment_file_id: attachmentFileId,
          remarks: recordForm.remarks.trim() || null,
          is_manual_entry: true,
          confirm_renewal: confirmRenewal,
        });
      }
      setRecordConflict(null);
      await load();
      resetRecordForm();
      setRecordDrawerOpen(false);
      setActiveSection("courses");
      setStatusFilter("ALL");
    } catch (e: any) {
      const conflict = trainingApiConflictFromError(e);
      if (conflict?.code === "TRAINING_RECORD_RENEWAL_CONFIRMATION_REQUIRED") {
        setError(null);
        setRecordConflict({
          kind: "renewal",
          title: "Confirm training renewal",
          message: conflict.message || "Confirm that this new record renews the existing active record.",
          records: conflict.records.length ? conflict.records : activeRecordsForSelectedCourse,
        });
        return;
      }
      if (conflict?.code === "DUPLICATE_TRAINING_RECORD") {
        setError(null);
        setRecordConflict({
          kind: "duplicate",
          title: "Duplicate training record detected",
          message: conflict.message || "A matching training record already exists.",
          records: conflict.records.length ? conflict.records : exactDuplicateRecord ? [exactDuplicateRecord] : [],
        });
        return;
      }
      setError(e?.message || "Failed to save training record.");
    } finally {
      setSavingRecord(false);
    }
  };


  const submitDeferral = async () => {
    if (!userId || !deferralForm.coursePk) {
      setError("Select a course before submitting a deferral request.");
      return;
    }
    const selectedItem = itemByCoursePk.get(deferralForm.coursePk);
    const originalDueDate = selectedItem?.extended_due_date || selectedItem?.valid_until;
    if (!originalDueDate) {
      setError("The selected course does not have a due date to defer.");
      return;
    }
    if (!deferralForm.requestedNewDueDate) {
      setError("Pick the requested new due date.");
      return;
    }
    setSavingDeferral(true);
    setError(null);
    try {
      await createTrainingDeferralRequest({
        user_id: userId,
        course_pk: deferralForm.coursePk,
        original_due_date: originalDueDate,
        requested_new_due_date: deferralForm.requestedNewDueDate,
        reason_category: deferralForm.reasonCategory,
        reason_text: deferralForm.reasonText.trim() || null,
      });
      await load();
      setDeferralForm((prev) => ({ ...prev, requestedNewDueDate: "", reasonText: "" }));
      setDeferralDrawerOpen(false);
    } catch (e: any) {
      setError(e?.message || "Failed to submit deferral request.");
    } finally {
      setSavingDeferral(false);
    }
  };

  const handleDeferralDecision = async (deferralId: string, status: "APPROVED" | "REJECTED") => {
    try {
      await updateTrainingDeferralRequest(deferralId, {
        status,
        decision_comment: status === "APPROVED" ? "Approved from the training profile." : "Rejected from the training profile.",
      });
      await load();
    } catch (e: any) {
      setError(e?.message || `Failed to ${status.toLowerCase()} deferral request.`);
    }
  };

  const scheduleColumnDefs: ColDef<ScheduleGridRow>[] = [
    { headerName: "Course", field: "course", flex: 1.6, minWidth: 160 },
    { headerName: "Session", field: "session", flex: 1.4, minWidth: 140 },
    { headerName: "Starts", field: "starts", flex: 0.7, minWidth: 100 },
    {
      headerName: "Status",
      field: "status",
      flex: 0.8,
      minWidth: 110,
      cellRenderer: ({ value }: ICellRendererParams<ScheduleGridRow, string>) => (
        <span className={statusPillClass(String(value || ""))}>{String(value || "").replaceAll("_", " ")}</span>
      ),
    },
    { headerName: "Location", field: "location", flex: 1, minWidth: 120 },
  ];

  const deferralColumnDefs: ColDef<DeferralGridRow>[] = (() => {
    const cols: ColDef<DeferralGridRow>[] = [
      { headerName: "Course", field: "course", flex: 1.5, minWidth: 150 },
      { headerName: "Original", field: "originalDue", flex: 0.7, minWidth: 100 },
      { headerName: "New due", field: "newDue", flex: 0.7, minWidth: 100 },
      {
        headerName: "Status",
        field: "status",
        flex: 0.7,
        minWidth: 100,
        cellRenderer: ({ value }: ICellRendererParams<DeferralGridRow, string>) => (
          <span className={deferralStatusPill(String(value || ""))}>{String(value || "")}</span>
        ),
      },
      { headerName: "Reason", field: "reason", flex: 1.3, minWidth: 140 },
      { headerName: "Requested", field: "requested", flex: 0.9, minWidth: 130 },
    ];
    if (canEdit) {
      cols.push({
        headerName: "Decision",
        colId: "decision",
        flex: 1,
        minWidth: 160,
        sortable: false,
        cellRenderer: ({ data }: ICellRendererParams<DeferralGridRow>) => {
          if (!data || data.status !== "PENDING") return <span className="text-muted">-</span>;
          return (
            <div className="training-row-actions">
              <button type="button" className="secondary-chip-btn" onClick={() => void handleDeferralDecision(data.id, "APPROVED")}>Approve</button>
              <button type="button" className="secondary-chip-btn" onClick={() => void handleDeferralDecision(data.id, "REJECTED")}>Reject</button>
            </div>
          );
        },
      });
    }
    return cols;
  })();

  const evidenceColumnDefs: ColDef<EvidenceGridRow>[] = [
    {
      headerName: "Filename",
      field: "filename",
      flex: 2,
      minWidth: 180,
      cellRenderer: ({ data }: ICellRendererParams<EvidenceGridRow>) => {
        if (!data) return null;
        return (
          <button type="button" className="tc-link-button" onClick={() => void openFileViewer(data.file)}>
            {data.filename}
          </button>
        );
      },
    },
    { headerName: "Type", field: "kind", flex: 0.7, minWidth: 100 },
    {
      headerName: "Review",
      field: "review",
      flex: 0.7,
      minWidth: 100,
      cellRenderer: ({ value }: ICellRendererParams<EvidenceGridRow, string>) => (
        <span className={deferralStatusPill(String(value || ""))}>{String(value || "")}</span>
      ),
    },
    { headerName: "Uploaded", field: "uploaded", flex: 1, minWidth: 140 },
    {
      headerName: "Actions",
      colId: "actions",
      flex: 0.5,
      minWidth: 80,
      maxWidth: 110,
      sortable: false,
      cellRenderer: ({ data }: ICellRendererParams<EvidenceGridRow>) => {
        if (!data) return null;
        return (
          <div className="training-row-actions">
            <button type="button" className="training-file-icon-btn" aria-label={`Open ${data.filename}`} onClick={() => void openFileViewer(data.file)}>
              {data.isPdf ? <FileText size={16} /> : <FileImage size={16} />}
            </button>
          </div>
        );
      },
    },
  ];

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection(key === "completion_date" ? "desc" : "asc");
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="training">
      <div className="qms-shell">
      <div className="qms-content">
      <div className="training-module training-module--qms training-profile-page">
        {state === "loading" && (
          <div className="card card--info">
            <p>Loading training profile...</p>
          </div>
        )}

        {state === "error" && (
          <div className="card card--error">
            <p>{error}</p>
            <button type="button" className="primary-chip-btn" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}

        {state === "ready" && user && (
          <section className="training-profile-shell">
            {error && <div className="card card--error" role="alert"><p>{error}</p></div>}

            <div className="training-profile-hero-card">
              <div className="training-profile-cover" aria-hidden="true" />
              <div className="training-profile-identity-block">
                <div className={`training-profile-avatar training-profile-avatar--${profileAvatarVariant(user)}`} aria-hidden="true">
                  {profileAvatarUrl(user) ? <img src={profileAvatarUrl(user) || ""} alt="" /> : <span>{initialsForUser(user)}</span>}
                </div>
                <div className="training-profile-identity-block__main">
                  <div className="training-profile-identity-block__headline">
                    <div>
                      <h2 className="training-profile-identity-block__name">{user.full_name || "Training profile"}</h2>
                      <p className="training-profile-identity-block__role">{cleanRoleTitle(user)}</p>
                    </div>
                  </div>
                  <dl className="training-profile-identity-meta">
                    <div>
                      <dt>Staff code</dt>
                      <dd>{user.staff_code || "—"}</dd>
                    </div>
                    <div>
                      <dt>Date hired</dt>
                      <dd>{formatDate(hireDate)}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>{user.is_active ? "Active" : "Inactive"}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>

            <div ref={sectionStartRef} className="training-profile-nav">
              <button type="button" className="training-profile-back" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoSlug)}/training/competence/people`)}>
                <ArrowLeft size={16} /> People
              </button>
              <nav aria-label="Training profile sections">
                {([
                  { key: "courses", label: "Courses", icon: GraduationCap },
                  { key: "schedule", label: "Schedule", icon: CalendarDays, count: relevantEvents.length },
                  { key: "deferrals", label: "Deferrals", icon: Clock3, count: deferrals.length },
                  { key: "licences", label: "Licences", icon: ShieldCheck },
                  { key: "evidence", label: "Evidence", icon: FolderOpen, count: files.length },
                ] as const).map((section) => (
                  <button
                    key={section.key}
                    type="button"
                    aria-current={activeSection === section.key ? "page" : undefined}
                    onClick={() => selectSection(section.key)}
                  >
                    <section.icon size={16} />
                    {section.label}
                    {"count" in section ? <span>{section.count}</span> : null}
                  </button>
                ))}
              </nav>
              <button
                type="button"
                className="training-profile-actions-btn"
                aria-label="Profile actions"
                onClick={() => setActionsDrawerOpen(true)}
              >
                <Plus size={18} />
              </button>
            </div>

            <div className="training-profile-layout">
              <section
                hidden={activeSection !== "courses" || !nextDue}
                className="training-profile-overview"
                aria-label="Next due training"
              >
                {nextDue ? (
                  <div className="training-profile-next-due">
                    <span className="training-profile-next-due__label">Next due</span>
                    <strong className="training-profile-next-due__course">{nextDue.course_name || nextDue.course_id}</strong>
                    <time className="training-profile-next-due__date" dateTime={dueDateForItem(nextDue) || undefined}>
                      {formatDate(dueDateForItem(nextDue))}
                    </time>
                  </div>
                ) : null}
              </section>

              <div className="training-profile-main">
                <div hidden={activeSection !== "courses"} className="qms-card training-profile-logcard training-profile-section-card">
                  <div className="training-profile-course-list">
                    <TrainingRequirementList
                      items={items}
                      initialFilter={searchParams.get("filter") === "NOT_DONE" ? "incomplete" : "all"}
                      courses={courses}
                      records={records}
                      files={files}
                      canEdit={canEdit}
                      busy={uploadingInlineAttachment}
                      onEditRecord={openRecordEditor}
                      onDeleteRecord={(record) => void deleteRecord(record)}
                      onOpenEvidence={(file) => void openFileViewer(file)}
                      onDownloadEvidence={(file) => void handleDownloadCertificate(file)}
                      onUploadEvidence={triggerInlineAttachmentUpload}
                      onRecordCompletion={(coursePk) => beginNewRecord(coursePk)}
                    />
                  </div>
                </div>

                <section hidden={activeSection !== "schedule"} className="qms-card training-profile-section-card">
                  <div className="training-collapse-panel">
                    {activeSection === "schedule" ? (
                      <div
                        className="ag-theme-alpine training-profile-grid"
                        style={{ height: profileGridHostHeight(scheduleRows.length) }}
                      >
                        <AgGridReact<ScheduleGridRow>
                          rowData={scheduleRows}
                          columnDefs={scheduleColumnDefs}
                          defaultColDef={PROFILE_GRID_DEFAULT_COL_DEF}
                          autoSizeStrategy={PROFILE_GRID_AUTO_SIZE}
                          getRowId={({ data }) => data.id}
                          headerHeight={PROFILE_GRID_HEADER_HEIGHT}
                          rowHeight={PROFILE_GRID_ROW_HEIGHT}
                          animateRows={false}
                          suppressCellFocus
                          onGridReady={onProfileGridReady}
                          onFirstDataRendered={onProfileGridFirstData}
                          onGridSizeChanged={onProfileGridSizeChanged}
                          overlayNoRowsTemplate='<span class="text-muted">No relevant training sessions are scheduled for this profile.</span>'
                        />
                      </div>
                    ) : null}
                  </div>
                </section>

                <section hidden={activeSection !== "deferrals"} className="qms-card training-profile-section-card">
                  <div className="training-collapse-panel training-profile-stack">
                    <div className="training-profile-section-toolbar">
                      <h3 className="training-profile-section-title">Deferral requests</h3>
                      {canEdit ? (
                        <button type="button" className="primary-chip-btn" onClick={openDeferralDrawer}>
                          <Plus size={15} /> Request a deferral
                        </button>
                      ) : null}
                    </div>
                    {activeSection === "deferrals" ? (
                      <div
                        className="ag-theme-alpine training-profile-grid"
                        style={{ height: profileGridHostHeight(deferralRows.length) }}
                      >
                        <AgGridReact<DeferralGridRow>
                          rowData={deferralRows}
                          columnDefs={deferralColumnDefs}
                          defaultColDef={PROFILE_GRID_DEFAULT_COL_DEF}
                          autoSizeStrategy={PROFILE_GRID_AUTO_SIZE}
                          getRowId={({ data }) => data.id}
                          headerHeight={PROFILE_GRID_HEADER_HEIGHT}
                          rowHeight={PROFILE_GRID_ROW_HEIGHT}
                          animateRows={false}
                          suppressCellFocus
                          onGridReady={onProfileGridReady}
                          onFirstDataRendered={onProfileGridFirstData}
                          onGridSizeChanged={onProfileGridSizeChanged}
                          overlayNoRowsTemplate='<span class="text-muted">No deferral requests have been captured for this user.</span>'
                        />
                      </div>
                    ) : null}
                  </div>
                </section>

                <section hidden={activeSection !== "licences"} className="qms-card training-profile-section-card">
                  <PersonnelLicencePanel
                    userId={user.id}
                    fallback={{
                      authority: user.regulatory_authority,
                      licenceNumber: user.licence_number,
                      country: user.licence_state_or_country,
                      expiresOn: user.licence_expires_on,
                    }}
                  />
                </section>

                <section hidden={activeSection !== "evidence"} className="qms-card training-profile-section-card">
                  <div className="qms-card training-profile-inner-card">
                    <div className="qms-card__header">
                      <div>
                        <h3 className="qms-card__title">Evidence</h3>
                      </div>
                    </div>
                    {activeSection === "evidence" ? (
                      <div
                        className="ag-theme-alpine training-profile-grid"
                        style={{ height: profileGridHostHeight(evidenceRows.length) }}
                      >
                        <AgGridReact<EvidenceGridRow>
                          rowData={evidenceRows}
                          columnDefs={evidenceColumnDefs}
                          defaultColDef={PROFILE_GRID_DEFAULT_COL_DEF}
                          autoSizeStrategy={PROFILE_GRID_AUTO_SIZE}
                          getRowId={({ data }) => data.id}
                          headerHeight={PROFILE_GRID_HEADER_HEIGHT}
                          rowHeight={PROFILE_GRID_ROW_HEIGHT}
                          animateRows={false}
                          suppressCellFocus
                          onGridReady={onProfileGridReady}
                          onFirstDataRendered={onProfileGridFirstData}
                          onGridSizeChanged={onProfileGridSizeChanged}
                          overlayNoRowsTemplate='<span class="text-muted">No attachments have been uploaded for this profile yet.</span>'
                        />
                      </div>
                    ) : null}
                  </div>
                </section>

                <input
                  ref={inlineAttachmentInputRef}
                  type="file"
                  accept="application/pdf,image/*,.pdf,.png,.jpg,.jpeg,.webp"
                  style={{ display: "none" }}
                  onChange={(e) => void handleInlineAttachmentChosen(e.target.files?.[0] || null)}
                />

                <Drawer
                  title="Profile actions"
                  isOpen={actionsDrawerOpen}
                  onClose={() => setActionsDrawerOpen(false)}
                  panelClassName="training-profile-actions-drawer"
                >
                  <ul className="training-profile-actions-list">
                    {canEdit ? (
                      <li>
                        <button
                          type="button"
                          className="training-profile-action-row training-profile-action-row--primary"
                          onClick={() => {
                            setActionsDrawerOpen(false);
                            beginNewRecord();
                          }}
                        >
                          <span className="training-profile-action-row__icon" aria-hidden="true">
                            <Plus size={18} />
                          </span>
                          <span className="training-profile-action-row__copy">
                            <strong>Add training record</strong>
                            <span>Log a course completion and attach supporting evidence.</span>
                          </span>
                        </button>
                      </li>
                    ) : null}
                    <li>
                      <div className="training-profile-action-row">
                        <span className="training-profile-action-row__icon" aria-hidden="true">
                          <FileText size={18} />
                        </span>
                        <span className="training-profile-action-row__copy">
                          <strong>Training profile PDF</strong>
                          <span>Printable summary of this person's courses, status and history.</span>
                        </span>
                        <TransferProgressButton
                          variant="secondary-chip-btn"
                          idleLabel="Open PDF"
                          busyState={recordTransfer}
                          disabled={exportingRecord || !userId}
                          onClick={() => void handleExportRecord()}
                        />
                      </div>
                    </li>
                    <li>
                      <div className="training-profile-action-row">
                        <span className="training-profile-action-row__icon" aria-hidden="true">
                          <Package size={18} />
                        </span>
                        <span className="training-profile-action-row__copy">
                          <strong>Evidence pack</strong>
                          <span>ZIP download of uploaded certificates and attachments.</span>
                        </span>
                        <TransferProgressButton
                          variant="secondary-chip-btn"
                          idleLabel="Download"
                          busyState={evidenceTransfer}
                          disabled={exportingEvidence || !userId}
                          onClick={() => void handleExportEvidence()}
                        />
                      </div>
                    </li>
                  </ul>
                </Drawer>

                {canEdit ? (
                  <Drawer
                    title={editingRecordId ? "Edit training record" : "Completion and evidence"}
                    isOpen={recordDrawerOpen}
                    onClose={closeRecordDrawer}
                    panelClassName="training-profile-form-drawer"
                    closeDisabled={savingRecord}
                  >
                    <div className="training-profile-drawer__body">
                      <fieldset className="training-profile-drawer__group">
                        <legend>Course &amp; dates</legend>
                        <div className="training-profile-form-grid">
                          <label className="qms-field">
                            <span>Course</span>
                            <select value={recordForm.coursePk} onChange={(e) => setRecordForm((prev) => ({ ...prev, coursePk: e.target.value }))}>
                              <option value="">Select course</option>
                              {recordableCourses.map((course) => (
                                <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>
                              ))}
                            </select>
                          </label>
                          <label className="qms-field">
                            <span>Completion date</span>
                            <input type="date" value={recordForm.completionDate} onChange={(e) => setRecordForm((prev) => ({ ...prev, completionDate: e.target.value }))} />
                          </label>
                          <label className="qms-field">
                            <span>Hours</span>
                            <input value={derivedHours ?? "-"} disabled />
                          </label>
                          {derivedValidUntil !== "-" ? (
                            <label className="qms-field">
                              <span>{derivedDueLabel}</span>
                              <input value={formatDate(derivedValidUntil)} disabled />
                            </label>
                          ) : null}
                          <label className="qms-field">
                            <span>Current course status</span>
                            <input value={selectedCourseStatus ? statusLabel(effectiveTrainingStatus(selectedCourseStatus)) : "-"} disabled />
                          </label>
                        </div>
                      </fieldset>

                      <fieldset className="training-profile-drawer__group">
                        <legend>Assessment</legend>
                        <div className="training-profile-form-grid">
                          <label className="qms-field">
                            <span>Exam score</span>
                            <input value={recordForm.examScore} onChange={(e) => setRecordForm((prev) => ({ ...prev, examScore: e.target.value }))} placeholder="Optional" />
                          </label>
                        </div>
                      </fieldset>

                      <fieldset className="training-profile-drawer__group">
                        <legend>Certificate &amp; attachment</legend>
                        <div className="training-profile-form-grid">
                          <label className="qms-field">
                            <span>Certificate reference</span>
                            <input value={recordForm.certificateReference} onChange={(e) => setRecordForm((prev) => ({ ...prev, certificateReference: e.target.value }))} placeholder="Requires a certificate attachment" />
                          </label>
                          <label className="qms-field">
                            <span>Attachment type</span>
                            <select value={recordAttachmentKind} onChange={(e) => setRecordAttachmentKind(e.target.value)}>
                              <option value="EVIDENCE">Evidence</option>
                              <option value="CERTIFICATE">Certificate</option>
                              <option value="AMEL">AMEL</option>
                              <option value="LICENSE">Licence</option>
                              <option value="OTHER">Other</option>
                            </select>
                          </label>
                          <label className="qms-field" style={{ gridColumn: "1 / -1" }}>
                            <span>Attachment</span>
                            <input type="file" onChange={(e) => setRecordAttachment(e.target.files?.[0] || null)} />
                          </label>
                        </div>
                      </fieldset>

                      <fieldset className="training-profile-drawer__group">
                        <legend>Notes</legend>
                        <div className="training-profile-form-grid">
                          <label className="qms-field" style={{ gridColumn: "1 / -1" }}>
                            <span>Remarks</span>
                            <textarea value={recordForm.remarks} onChange={(e) => setRecordForm((prev) => ({ ...prev, remarks: e.target.value }))} rows={3} />
                          </label>
                        </div>
                        <div className="training-profile-form-note">
                          {selectedCoursePhase === "INITIAL" && linkedRefresherCourse ? (
                            <p>Recording this initial course will seed the linked refresher entry automatically using the same completion date and the refresher recurrence.</p>
                          ) : null}
                        </div>
                      </fieldset>
                    </div>
                    <div className="training-profile-drawer__footer">
                      <button type="button" className="secondary-chip-btn" onClick={closeRecordDrawer} disabled={savingRecord}>
                        Cancel
                      </button>
                      <button type="button" className="primary-chip-btn" onClick={() => void submitRecord()} disabled={savingRecord}>
                        {savingRecord ? "Saving..." : editingRecordId ? "Update training record" : "Save training record"}
                      </button>
                    </div>
                  </Drawer>
                ) : null}

                <Drawer
                  title="Request a deferral"
                  isOpen={deferralDrawerOpen}
                  onClose={closeDeferralDrawer}
                  panelClassName="training-profile-form-drawer training-profile-form-drawer--compact"
                  closeDisabled={savingDeferral}
                >
                  <div className="training-profile-drawer__body">
                    <fieldset className="training-profile-drawer__group">
                      <legend>Course &amp; dates</legend>
                      <div className="training-profile-form-grid">
                        <label className="qms-field">
                          <span>Course</span>
                          <select value={deferralForm.coursePk} onChange={(e) => setDeferralForm((prev) => ({ ...prev, coursePk: e.target.value }))}>
                            <option value="">Select course</option>
                            {courses.map((course) => {
                              const item = itemByCoursePk.get(course.id);
                              const due = dueDateForItem(item);
                              return (
                                <option key={course.id} value={course.id}>
                                  {course.course_id} · {course.course_name}{due ? ` · due ${formatDate(due)}` : ""}
                                </option>
                              );
                            })}
                          </select>
                        </label>
                        <label className="qms-field">
                          <span>Current due</span>
                          <input value={deferralForm.coursePk ? dueLabel(itemByCoursePk.get(deferralForm.coursePk)) : "-"} disabled />
                        </label>
                        <label className="qms-field">
                          <span>Requested new due date</span>
                          <input type="date" value={deferralForm.requestedNewDueDate} onChange={(e) => setDeferralForm((prev) => ({ ...prev, requestedNewDueDate: e.target.value }))} />
                        </label>
                      </div>
                    </fieldset>
                    <fieldset className="training-profile-drawer__group">
                      <legend>Reason</legend>
                      <div className="training-profile-form-grid">
                        <label className="qms-field">
                          <span>Category</span>
                          <select value={deferralForm.reasonCategory} onChange={(e) => setDeferralForm((prev) => ({ ...prev, reasonCategory: e.target.value as DeferralReasonCategory }))}>
                            {DEFERRAL_REASON_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </label>
                        <label className="qms-field" style={{ gridColumn: "1 / -1" }}>
                          <span>Reason detail</span>
                          <textarea value={deferralForm.reasonText} onChange={(e) => setDeferralForm((prev) => ({ ...prev, reasonText: e.target.value }))} rows={3} />
                        </label>
                      </div>
                    </fieldset>
                  </div>
                  <div className="training-profile-drawer__footer">
                    <button type="button" className="secondary-chip-btn" onClick={closeDeferralDrawer} disabled={savingDeferral}>
                      Cancel
                    </button>
                    <button type="button" className="primary-chip-btn" onClick={() => void submitDeferral()} disabled={savingDeferral}>
                      {savingDeferral ? "Submitting..." : "Submit deferral request"}
                    </button>
                  </div>
                </Drawer>

                {recordConflict ? (
                  <div className="training-record-conflict-backdrop" role="dialog" aria-modal="true" aria-labelledby="training-record-conflict-title">
                    <div className="training-record-conflict-modal">
                      <div className="training-record-conflict-modal__header">
                        <div>
                          <span className={`qms-pill ${recordConflict.kind === "duplicate" ? "qms-pill--danger" : "qms-pill--warning"}`}>
                            {recordConflict.kind === "duplicate" ? "Duplicate" : "Renewal"}
                          </span>
                          <h3 id="training-record-conflict-title">{recordConflict.title}</h3>
                        </div>
                        <button type="button" className="training-icon-btn" onClick={() => setRecordConflict(null)} aria-label="Close record confirmation">
                          <X size={16} />
                        </button>
                      </div>
                      <p className="training-record-conflict-modal__message">{recordConflict.message}</p>
                      <div className="training-record-conflict-list">
                        {(recordConflict.records.length ? recordConflict.records : activeRecordsForSelectedCourse).map((record) => (
                          <div key={record.id || `${record.course_id}-${record.completion_date}`} className="training-record-conflict-item">
                            <div>
                              <strong>{record.course_code || selectedCourse?.course_id || record.course_id}</strong>
                              <span>{record.course_name || selectedCourse?.course_name || "Training course"}</span>
                            </div>
                            <dl>
                              <div><dt>Completed</dt><dd>{formatDate(record.completion_date)}</dd></div>
                              <div><dt>Valid until</dt><dd>{formatDate(record.valid_until)}</dd></div>
                              <div><dt>Certificate</dt><dd>{record.certificate_reference || "-"}</dd></div>
                              <div><dt>Status</dt><dd>{normaliseRecordLifecycleStatus(record)}</dd></div>
                            </dl>
                          </div>
                        ))}
                      </div>
                      <div className="training-record-conflict-modal__actions">
                        <button type="button" className="secondary-chip-btn" onClick={() => setRecordConflict(null)}>
                          Review form
                        </button>
                        {recordConflict.kind === "renewal" ? (
                          <button type="button" className="primary-chip-btn" disabled={savingRecord} onClick={() => void submitRecord(true)}>
                            {savingRecord ? "Saving..." : "Confirm renewal and save"}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : null}

                {viewerFile ? (
                  <div className="training-file-viewer-backdrop" onClick={closeViewer}>
                    <div className="training-file-viewer" onClick={(e) => e.stopPropagation()}>
                      <div className="training-file-viewer__toolbar">
                        <div className="training-file-viewer__title">
                          <strong>{viewerFile.original_filename}</strong>
                          <span>{viewerFile.kind}</span>
                        </div>
                        <div className="training-row-actions">
                          <button type="button" className="training-icon-btn" onClick={async () => { if (!viewerFile) return; const downloaded = await downloadTrainingFile(viewerFile.id); saveDownloadedFile(downloaded); }}><Download size={15} /></button>
                          <button type="button" className="training-icon-btn" onClick={closeViewer}><X size={15} /></button>
                        </div>
                      </div>
                      <div className="training-file-viewer__body">
                        {viewerLoading ? <p className="text-muted">Loading attachment...</p> : null}
                        {viewerBlobUrl && ((viewerFile.content_type || "").includes("pdf") || viewerFile.original_filename.toLowerCase().endsWith(".pdf")) ? (
                          <iframe title={viewerFile.original_filename} src={viewerBlobUrl} style={{ width: "100%", height: "78vh", border: "none" }} />
                        ) : viewerBlobUrl ? (
                          <img src={viewerBlobUrl} alt={viewerFile.original_filename} style={{ maxWidth: "100%", maxHeight: "78vh" }} />
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        )}
      </div>
      </div>
      </div>
    </DepartmentLayout>
  );
};

export default QMSTrainingUserPage;

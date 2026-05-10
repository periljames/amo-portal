import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CalendarClock, CheckSquare, ClipboardSignature, Download, ExternalLink, FileSpreadsheet, GraduationCap, RefreshCw, ScanLine, Search, ShieldCheck, Upload, Users } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import Drawer from "../components/shared/Drawer";
import { useToast } from "../components/feedback/ToastProvider";
import { saveDownloadedFile } from "../utils/downloads";
import { getCachedUser } from "../services/auth";
import { listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";
import {
  autoGroupTrainingEvents,
  createTrainingCourse,
  createTrainingDeferralRequest,
  createTrainingEventBatch,
  createTrainingRequirement,
  deleteTrainingRequirement,
  downloadTrainingCertificateArtifact,
  getBulkTrainingStatusForUsers,
  importTrainingCoursesWorkbook,
  importTrainingRecordsWorkbook,
  issueTrainingCertificate,
  listTrainingCertificates,
  listTrainingCourses,
  listTrainingDeferrals,
  listTrainingEventParticipants,
  listTrainingEvents,
  listTrainingRecordsByUsers,
  listTrainingRequirements,
  type TransferProgress,
  updateTrainingCourse,
  updateTrainingEventParticipant,
  updateTrainingRequirement,
  prefetchTrainingUserDetailBundle,
} from "../services/training";
import type {
  TrainingAutoGroupScheduleCreate,
  TrainingCertificateArtifactOptions,
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventBatchScheduleCreate,
  TrainingEventParticipantRead,
  TrainingEventRead,
  TrainingRecordRead,
  TrainingRequirementCreate,
  TrainingRequirementRead,
  TrainingRequirementScope,
  TrainingRequirementUpdate,
  TrainingStatusItem,
} from "../types/training";
import "../styles/training-competence.css";

type TabKey = "overview" | "people" | "matrix" | "schedule" | "certificates";

type PersonRow = {
  user: AdminUserSummaryRead;
  items: TrainingStatusItem[];
  records: TrainingRecordRead[];
  certificates: TrainingRecordRead[];
  overdue: number;
  dueSoon: number;
  notDone: number;
  deferred: number;
  outstanding: number;
  nextDueLabel: string;
  nextDueDate: string | null;
  anomalyCount: number;
};

type RefresherAnomaly = {
  key: string;
  userId: string;
  userName: string;
  coursePk: string;
  courseCode: string;
  courseName: string;
  prerequisiteNames: string[];
  completionDate: string | null;
};

type CourseFamilyIndex = Record<string, string[]>;

type SectionDrawer = {
  title: string;
  body: React.ReactNode;
} | null;

type TrainingDashboardSnapshot = {
  users: AdminUserSummaryRead[];
  courses: TrainingCourseRead[];
  requirements: TrainingRequirementRead[];
  events: TrainingEventRead[];
  records: TrainingRecordRead[];
  certificates: TrainingRecordRead[];
  deferrals: TrainingDeferralRequestRead[];
  statusByUser: Record<string, TrainingStatusItem[]>;
  savedAt: number;
};

function trainingDashboardSnapshotKey(amoCode?: string): string {
  return `training-dashboard-snapshot:${amoCode || "amo"}`;
}



const tabs: Array<{ key: TabKey; label: string; hint: string }> = [
  { key: "overview", label: "Overview", hint: "Health, alerts and priorities" },
  { key: "people", label: "Personnel", hint: "Search and open individual records" },
  { key: "matrix", label: "Course Requirements", hint: "Catalogue and requirement rules" },
  { key: "schedule", label: "Schedule", hint: "Sessions, roster and attendance" },
  { key: "certificates", label: "Certificates", hint: "Issued evidence and verification" },
];

function compactDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function coursePhase(course: TrainingCourseRead): "INITIAL" | "REFRESHER" | "ONE_OFF" | "UNKNOWN" {
  const blob = `${course.status || ""} ${course.kind || ""} ${course.course_id || ""} ${course.course_name || ""}`.toLowerCase();
  if (/one[_ -]?off/.test(blob)) return "ONE_OFF";
  if (/\b(init|initial|induction)\b/.test(blob)) return "INITIAL";
  if (/\b(refresh|refresher|recurrent|continuation|ref)\b/.test(blob)) return "REFRESHER";
  return "UNKNOWN";
}

function familyKey(course: TrainingCourseRead): string {
  return `${course.course_id || ""} ${course.course_name || ""}`
    .toLowerCase()
    .replace(/\b(init|initial|induction|refresh|refresher|recurrent|continuation|ref|rec|one[_ -]?off)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
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



function eventCoursePk(event: TrainingEventRead): string {
  return event.course_id || event.course_pk || "";
}

function timeLeftLabel(daysUntilDue?: number | null): string {
  if (daysUntilDue == null) return "—";
  if (daysUntilDue < 0) return `${Math.abs(daysUntilDue)} day(s) overdue`;
  if (daysUntilDue === 0) return "Due today";
  return `${daysUntilDue} day(s) left`;
}

function parseEventMeta(notes?: string | null): { meta: Record<string, string>; plainNotes: string } {
  const prefix = "[AMO-EVENT-META]";
  const raw = (notes || "").trim();
  if (!raw.startsWith(prefix)) return { meta: {}, plainNotes: raw };
  const firstNewLine = raw.indexOf("\n");
  const head = firstNewLine >= 0 ? raw.slice(prefix.length, firstNewLine).trim() : raw.slice(prefix.length).trim();
  const plain = firstNewLine >= 0 ? raw.slice(firstNewLine).trim() : "";
  try {
    const meta = JSON.parse(head);
    return { meta: typeof meta === "object" && meta ? meta as Record<string, string> : {}, plainNotes: plain };
  } catch {
    return { meta: {}, plainNotes: raw };
  }
}

function formatSessionMode(event: TrainingEventRead): string {
  const { meta } = parseEventMeta(event.notes);
  const providerKind = (meta.provider_kind || "").toUpperCase();
  const venueMode = (meta.venue_mode || "").toUpperCase();
  const parts = [providerKind, venueMode].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

function certificateSetupStorageKey(amoCode?: string): string {
  return `training-cert-setup:${amoCode || "amo"}`;
}

function downloadTextFile(content: string, filename: string, contentType = "text/csv;charset=utf-8") : void {
  const blob = new Blob([content], { type: contentType });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(url);
}

function csvEscape(value: unknown): string {
  const raw = value == null ? "" : String(value);
  if (/[",\n]/.test(raw)) return `"${raw.replace(/"/g, '""')}"`;
  return raw;
}

function buildCsv(rows: Array<Record<string, unknown>>, headers: string[]): string {
  const lines = [headers.join(",")];
  rows.forEach((row) => {
    lines.push(headers.map((header) => csvEscape(row[header])).join(","));
  });
  return lines.join("\n");
}

function useCountUp(target: number, key: string, durationMs = 700): number {
  const [value, setValue] = React.useState(0);
  React.useEffect(() => {
    const safeTarget = Number.isFinite(target) ? Math.max(0, target) : 0;
    if (safeTarget === 0) {
      setValue(0);
      return;
    }
    let frame = 0;
    const startedAt = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.max(1, Math.round(safeTarget * eased)));
      if (progress < 1) frame = window.requestAnimationFrame(tick);
    };
    setValue(1);
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [durationMs, key, target]);
  return value;
}

function nextDueLabel(items: TrainingStatusItem[]): { label: string; date: string | null } {
  const sorted = items
    .filter((item) => item.extended_due_date || item.valid_until)
    .slice()
    .sort((a, b) => String(a.extended_due_date || a.valid_until || "").localeCompare(String(b.extended_due_date || b.valid_until || "")));
  const item = sorted[0];
  if (!item) return { label: "—", date: null };
  const due = item.extended_due_date || item.valid_until;
  return { label: `${item.course_name} · ${compactDate(due)}`, date: due || null };
}

function buildRefresherAnomalies(
  users: AdminUserSummaryRead[],
  courses: TrainingCourseRead[],
  records: TrainingRecordRead[],
): RefresherAnomaly[] {
  const courseLookup = buildCourseLookup(courses);
  const initialsByFamily: CourseFamilyIndex = {};
  courses.forEach((course) => {
    if (coursePhase(course) === "INITIAL") {
      const key = familyKey(course);
      if (!key) return;
      initialsByFamily[key] = [...(initialsByFamily[key] || []), course.id];
    }
  });

  const completedByUser = new Map<string, Set<string>>();
  records.forEach((record) => {
    if (!completedByUser.has(record.user_id)) completedByUser.set(record.user_id, new Set());
    const completed = completedByUser.get(record.user_id)!;
    completed.add(record.course_id);
    const resolved = resolveCourse(courseLookup, record.course_id);
    if (resolved?.id) completed.add(resolved.id);
    if (resolved?.course_id) completed.add(resolved.course_id);
  });

  const userById = new Map(users.map((user) => [user.id, user]));
  const anomalies: RefresherAnomaly[] = [];
  const seen = new Set<string>();

  records.forEach((record) => {
    const course = resolveCourse(courseLookup, record.course_id);
    if (!course || coursePhase(course) !== "REFRESHER") return;
    const prerequisites = new Set<string>();
    if (course.prerequisite_course_id) prerequisites.add(course.prerequisite_course_id);
    const fk = familyKey(course);
    (initialsByFamily[fk] || []).forEach((courseId) => {
      if (courseId !== course.id) prerequisites.add(courseId);
    });
    if (prerequisites.size === 0) return;
    const completed = completedByUser.get(record.user_id) || new Set<string>();
    const hasInitial = [...prerequisites].some((courseId) => completed.has(courseId));
    if (hasInitial) return;
    const key = `${record.user_id}:${record.course_id}`;
    if (seen.has(key)) return;
    seen.add(key);
    anomalies.push({
      key,
      userId: record.user_id,
      userName: userById.get(record.user_id)?.full_name || userById.get(record.user_id)?.email || record.user_id,
      coursePk: record.course_id,
      courseCode: course.course_id,
      courseName: course.course_name,
      prerequisiteNames: [...prerequisites].map((id) => resolveCourse(courseLookup, id)?.course_name || resolveCourse(courseLookup, id)?.course_id || id),
      completionDate: record.completion_date,
    });
  });

  return anomalies.sort((a, b) => a.userName.localeCompare(b.userName) || a.courseName.localeCompare(b.courseName));
}

const TrainingCompetencePage: React.FC = () => {
  const { amoCode, department } = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const legacySection = searchParams.get("section");
  const tabParam = (searchParams.get("tab") || (legacySection === "personnel" ? "people" : legacySection) || "people") as TabKey;
  const filterCourseParam = searchParams.get("course") || "ALL";
  const dueWindowParam = searchParams.get("window") || "ALL";

  const [tab, setTab] = useState<TabKey>(tabParam);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<SectionDrawer>(null);
  const [users, setUsers] = useState<AdminUserSummaryRead[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [requirements, setRequirements] = useState<TrainingRequirementRead[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [records, setRecords] = useState<TrainingRecordRead[]>([]);
  const [certificates, setCertificates] = useState<TrainingRecordRead[]>([]);
  const [statusByUser, setStatusByUser] = useState<Record<string, TrainingStatusItem[]>>({});
  const [personQuery, setPersonQuery] = useState("");
  const [personStatusFilter, setPersonStatusFilter] = useState<string>("ALL");
  const [personCourseFilter, setPersonCourseFilter] = useState<string>(filterCourseParam);
  const [personAnomalyOnly, setPersonAnomalyOnly] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string>("");
  const [participants, setParticipants] = useState<TrainingEventParticipantRead[]>([]);
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
  const [editingRequirementId, setEditingRequirementId] = useState<string | null>(null);
  const [savingRequirement, setSavingRequirement] = useState(false);
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
  const [importMode, setImportMode] = useState<"courses" | "trainings">("courses");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDryRun, setImportDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<TransferProgress | null>(null);
  const [importSummary, setImportSummary] = useState<any | null>(null);
  const PEOPLE_PAGE_SIZE = 50;
  const [peoplePage, setPeoplePage] = useState(0);
  const [hasMorePeople, setHasMorePeople] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [autoGroupOpen, setAutoGroupOpen] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [autoGrouping, setAutoGrouping] = useState(false);
  const [scheduleForm, setScheduleForm] = useState<TrainingEventBatchScheduleCreate>({
    course_pk: "",
    user_ids: [],
    title: "",
    provider: "",
    provider_kind: "INTERNAL",
    delivery_mode: "CLASSROOM",
    venue_mode: "OFFLINE",
    instructor_name: "",
    location: "",
    meeting_link: "",
    starts_on: new Date().toISOString().slice(0, 10),
    ends_on: "",
    notes: "",
    participant_status: "SCHEDULED",
    auto_issue_certificates: true,
    allow_self_attendance: true,
  });
  const [autoGroupForm, setAutoGroupForm] = useState<TrainingAutoGroupScheduleCreate>({
    user_ids: [],
    include_due_soon: true,
    include_overdue: true,
    base_start_on: new Date().toISOString().slice(0, 10),
    provider: "",
    provider_kind: "INTERNAL",
    delivery_mode: "CLASSROOM",
    venue_mode: "OFFLINE",
    instructor_name: "",
    location: "",
    meeting_link: "",
    notes: "",
    participant_status: "SCHEDULED",
    auto_issue_certificates: true,
    allow_self_attendance: true,
  });
  const [deferralOpen, setDeferralOpen] = useState(false);
  const [deferralTarget, setDeferralTarget] = useState<{ participantId: string; userId: string; userName: string; coursePk: string; originalDueDate: string | null; } | null>(null);
  const [deferralForm, setDeferralForm] = useState({ requested_new_due_date: "", reason_category: "OPERATIONAL_REQUIREMENTS", reason_text: "" });
  const [certSetupOpen, setCertSetupOpen] = useState(false);
  const [certificateSetup, setCertificateSetup] = useState<TrainingCertificateArtifactOptions>({});
  const loadSeq = useRef(0);
  const anomalyToastKey = useRef<string>("");
  const hydratedSnapshotRef = useRef(false);
  const { pushToast } = useToast();
  const currentUser = getCachedUser();
  const canManageCourses = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER");

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(certificateSetupStorageKey(amoCode));
      if (raw) setCertificateSetup(JSON.parse(raw));
    } catch {
      // ignore broken local storage payloads
    }
  }, [amoCode]);

  useEffect(() => {
    try {
      window.localStorage.setItem(certificateSetupStorageKey(amoCode), JSON.stringify(certificateSetup));
    } catch {
      // ignore storage failures
    }
  }, [amoCode, certificateSetup]);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(trainingDashboardSnapshotKey(amoCode));
      if (!raw) return;
      const snapshot = JSON.parse(raw) as TrainingDashboardSnapshot;
      if (!snapshot || !snapshot.savedAt) return;
      if (Date.now() - snapshot.savedAt > 3 * 60_000) return;
      setUsers(snapshot.users || []);
      setCourses(snapshot.courses || []);
      setRequirements(snapshot.requirements || []);
      setEvents(snapshot.events || []);
      setRecords(snapshot.records || []);
      setCertificates(snapshot.certificates || []);
      setStatusByUser(snapshot.statusByUser || {});
      hydratedSnapshotRef.current = true;
      setLoading(false);
    } catch {
      // ignore broken snapshots
    }
  }, [amoCode]);

  useEffect(() => {
    setTab(tabParam);
  }, [tabParam]);

  useEffect(() => {
    if (!selectedEventId) {
      setParticipants([]);
      return;
    }
    listTrainingEventParticipants(selectedEventId)
      .then(setParticipants)
      .catch(() => setParticipants([]));
  }, [selectedEventId]);

  const load = async () => {
    const requestId = ++loadSeq.current;
    if (!hydratedSnapshotRef.current) setLoading(true);
    setError(null);

    const settled = await Promise.allSettled([
      listAdminUserSummaries({ limit: PEOPLE_PAGE_SIZE, skip: peoplePage * PEOPLE_PAGE_SIZE }),
      listTrainingCourses({ include_inactive: true, limit: 200 }),
      listTrainingRequirements({ include_inactive: true, limit: 200 }),
      listTrainingEvents({ limit: 50 }),
      listTrainingCertificates(undefined, { limit: 50 }),
      listTrainingDeferrals({ limit: 50 }),
    ]);

    if (requestId !== loadSeq.current) return;

    const [usersRes, coursesRes, requirementsRes, eventsRes, certificatesRes, deferralsRes] = settled;
    const failures: string[] = [];

    const nextUsers = usersRes.status === "fulfilled" ? usersRes.value : [];
    if (usersRes.status !== "fulfilled") failures.push("users");
    const nextCourses = coursesRes.status === "fulfilled" ? coursesRes.value : [];
    if (coursesRes.status !== "fulfilled") failures.push("courses");
    const nextRequirements = requirementsRes.status === "fulfilled" ? requirementsRes.value : [];
    if (requirementsRes.status !== "fulfilled") failures.push("requirements");
    const nextEvents = eventsRes.status === "fulfilled" ? eventsRes.value : [];
    if (eventsRes.status !== "fulfilled") failures.push("events");
    const nextCertificates = certificatesRes.status === "fulfilled" ? certificatesRes.value : [];
    if (certificatesRes.status !== "fulfilled") failures.push("certificates");
    const nextDeferrals = deferralsRes.status === "fulfilled" ? deferralsRes.value : [];
    setHasMorePeople(nextUsers.length === PEOPLE_PAGE_SIZE);
    if (deferralsRes.status !== "fulfilled") failures.push("deferrals");

    let nextStatusByUser: Record<string, TrainingStatusItem[]> = {};
    let nextRecords: TrainingRecordRead[] = [];
    if (nextUsers.length > 0) {
      try {
        const [statusResponse, recordsResponse] = await Promise.all([
          getBulkTrainingStatusForUsers(nextUsers.map((user) => user.id)),
          listTrainingRecordsByUsers(nextUsers.map((user) => user.id), { limit: 2000 }),
        ]);
        if (requestId !== loadSeq.current) return;
        nextStatusByUser = statusResponse.users || {};
        nextRecords = recordsResponse || [];
      } catch {
        failures.push("status");
      }
    }

    setUsers(nextUsers);
    setCourses(nextCourses);
    setRequirements(nextRequirements);
    setEvents(nextEvents);
    setRecords(nextRecords);
    setCertificates(nextCertificates);
    setStatusByUser(nextStatusByUser);
    try {
      window.sessionStorage.setItem(
        trainingDashboardSnapshotKey(amoCode),
        JSON.stringify({
          users: nextUsers,
          courses: nextCourses,
          requirements: nextRequirements,
          events: nextEvents,
          records: nextRecords,
          certificates: nextCertificates,
          deferrals: nextDeferrals,
          statusByUser: nextStatusByUser,
          savedAt: Date.now(),
        } satisfies TrainingDashboardSnapshot),
      );
    } catch {
      // ignore storage failures
    }
    setError(failures.length ? `Some datasets could not be loaded: ${failures.join(", ")}.` : null);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, [peoplePage]);

  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses]);
  const courseLookup = useMemo(() => buildCourseLookup(courses), [courses]);
  const anomalies = useMemo(() => buildRefresherAnomalies(users, courses, records), [users, courses, records]);
  const anomalyKeysByUser = useMemo(() => {
    const map = new Map<string, number>();
    anomalies.forEach((entry) => map.set(entry.userId, (map.get(entry.userId) || 0) + 1));
    return map;
  }, [anomalies]);

  useEffect(() => {
    const toastKey = `${anomalies.length}:${records.length}`;
    if (!loading && anomalies.length > 0 && anomalyToastKey.current !== toastKey) {
      anomalyToastKey.current = toastKey;
      pushToast({
        title: "Training data inconsistency detected",
        message: `${anomalies.length} refresher completion(s) were found without a matching initial course. Review the flagged personnel rows and rectify the records.`,
        variant: "warning",
      });
    }
  }, [anomalies.length, loading, pushToast, records.length]);

  const peopleRows = useMemo<PersonRow[]>(() => {
    return users.map((user) => {
      const items = (statusByUser[user.id] || []).slice().sort((a, b) => String(a.extended_due_date || a.valid_until || "").localeCompare(String(b.extended_due_date || b.valid_until || "")));
      const userRecords = records.filter((record) => record.user_id === user.id);
      const userCertificates = certificates.filter((record) => record.user_id === user.id && !!record.certificate_reference);
      const counts = {
        overdue: items.filter((item) => item.status === "OVERDUE").length,
        dueSoon: items.filter((item) => item.status === "DUE_SOON").length,
        notDone: items.filter((item) => item.status === "NOT_DONE").length,
        deferred: items.filter((item) => item.status === "DEFERRED").length,
      };
      const nextDue = nextDueLabel(items);
      return {
        user,
        items,
        records: userRecords,
        certificates: userCertificates,
        overdue: counts.overdue,
        dueSoon: counts.dueSoon,
        notDone: counts.notDone,
        deferred: counts.deferred,
        outstanding: counts.overdue + counts.dueSoon + counts.notDone,
        nextDueLabel: nextDue.label,
        nextDueDate: nextDue.date,
        anomalyCount: anomalyKeysByUser.get(user.id) || 0,
      };
    }).sort((a, b) => {
      if (b.anomalyCount !== a.anomalyCount) return b.anomalyCount - a.anomalyCount;
      if (b.overdue !== a.overdue) return b.overdue - a.overdue;
      if (b.dueSoon !== a.dueSoon) return b.dueSoon - a.dueSoon;
      return (a.user.full_name || "").localeCompare(b.user.full_name || "");
    });
  }, [anomalyKeysByUser, certificates, records, statusByUser, users]);

  const filteredPeople = useMemo(() => {
    const query = personQuery.trim().toLowerCase();
    return peopleRows.filter((row) => {
      if (personAnomalyOnly && row.anomalyCount === 0) return false;
      if (personCourseFilter !== "ALL" && !row.items.some((item) => item.course_id === personCourseFilter || item.course_name === personCourseFilter)) return false;
      if (personStatusFilter !== "ALL") {
        if (personStatusFilter === "ANOMALY") return row.anomalyCount > 0;
        if (!row.items.some((item) => item.status === personStatusFilter)) return false;
      }
      if (dueWindowParam !== "ALL") {
        const maxDays = dueWindowParam === "30d" ? 30 : dueWindowParam === "7d" ? 7 : null;
        if (maxDays != null && !row.items.some((item) => typeof item.days_until_due === "number" && item.days_until_due >= 0 && item.days_until_due <= maxDays)) {
          return false;
        }
      }
      if (!query) return true;
      return [row.user.full_name, row.user.email, row.user.staff_code, row.user.position_title, row.user.role]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [dueWindowParam, peopleRows, personAnomalyOnly, personCourseFilter, personQuery, personStatusFilter]);

  const selectedUserIdSet = useMemo(() => new Set(selectedUserIds), [selectedUserIds]);

  useEffect(() => {
    const visibleIds = new Set(filteredPeople.map((row) => row.user.id));
    setSelectedUserIds((prev) => prev.filter((id) => visibleIds.has(id)));
  }, [filteredPeople]);

  const kpis = useMemo(() => {
    const allItems = Object.values(statusByUser).flat() as TrainingStatusItem[];
    return {
      users: users.length,
      courses: courses.length,
      requirements: requirements.filter((item) => item.is_active).length,
      overdue: allItems.filter((item) => item.status === "OVERDUE").length,
      dueSoon: allItems.filter((item) => item.status === "DUE_SOON").length,
      anomalies: anomalies.length,
      events: events.filter((event) => event.status === "PLANNED" || event.status === "IN_PROGRESS").length,
      certificates: certificates.filter((item) => !!item.certificate_reference).length,
    };
  }, [anomalies.length, certificates, courses.length, events, requirements, statusByUser, users.length]);

  const animatedUsers = useCountUp(kpis.users, `users:${kpis.users}`);
  const animatedOverdue = useCountUp(kpis.overdue, `overdue:${kpis.overdue}`);
  const animatedDueSoon = useCountUp(kpis.dueSoon, `dueSoon:${kpis.dueSoon}`);
  const animatedRequirements = useCountUp(kpis.requirements, `requirements:${kpis.requirements}`);
  const animatedCourses = useCountUp(kpis.courses, `courses:${kpis.courses}`);
  const animatedCertificates = useCountUp(kpis.certificates, `certificates:${kpis.certificates}`);
  const animatedAnomalies = useCountUp(kpis.anomalies, `anomalies:${kpis.anomalies}`);
  const animatedEvents = useCountUp(kpis.events, `events:${kpis.events}`);

  const upcomingEvents = useMemo(() => {
    return events
      .slice()
      .filter((event) => event.status === "PLANNED" || event.status === "IN_PROGRESS")
      .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)))
      .slice(0, 8);
  }, [events]);

  const requirementRows = useMemo(() => {
    return requirements
      .slice()
      .map((req) => ({
        ...req,
        course: courseById.get(req.course_pk),
      }))
      .sort((a, b) => (a.course?.course_name || a.course?.course_id || a.course_pk).localeCompare(b.course?.course_name || b.course?.course_id || b.course_pk));
  }, [courseById, requirements]);

  const knownDepartments = useMemo(() => Array.from(new Set(users.map((user) => String((user as any).department_code || "").trim()).filter(Boolean))).sort(), [users]);
  const knownRoles = useMemo(() => Array.from(new Set(users.map((user) => String(user.position_title || user.role || "").trim()).filter(Boolean))).sort(), [users]);

  const courseRows = useMemo(() => {
    const requiredCourseIds = new Set(requirements.filter((item) => item.is_active).map((item) => item.course_pk));
    return courses
      .slice()
      .sort((a, b) => a.course_id.localeCompare(b.course_id))
      .map((course) => ({
        course,
        phase: coursePhase(course),
        requiredCount: requirements.filter((req) => req.course_pk === course.id && req.is_active).length,
        isRequired: requiredCourseIds.has(course.id),
      }));
  }, [courses, requirements]);

  const certificateRows = useMemo(() => {
    return certificates
      .slice()
      .sort((a, b) => String(b.completion_date || "").localeCompare(String(a.completion_date || "")));
  }, [certificates]);

  const openTab = (next: TabKey) => {
    setTab(next);
    const sp = new URLSearchParams(searchParams);
    sp.set("tab", next);
    sp.delete("section");
    setSearchParams(sp, { replace: true });
  };

  const updatePersonCourseFilter = (value: string) => {
    setPersonCourseFilter(value);
    const sp = new URLSearchParams(searchParams);
    if (value === "ALL") sp.delete("course");
    else sp.set("course", value);
    setSearchParams(sp, { replace: true });
  };

  const openPeopleFilter = (status: string, options?: { anomalyOnly?: boolean; course?: string; window?: string }) => {
    openTab("people");
    setPersonStatusFilter(status);
    setPersonAnomalyOnly(Boolean(options?.anomalyOnly));
    if (options?.course) setPersonCourseFilter(options.course);
    const sp = new URLSearchParams(searchParams);
    sp.set("tab", "people");
    if (status === "ALL") sp.delete("status");
    if (options?.course) sp.set("course", options.course); else if (!options?.course && personCourseFilter === "ALL") sp.delete("course");
    if (options?.window) sp.set("window", options.window); else sp.delete("window");
    setSearchParams(sp, { replace: true });
  };

  const togglePersonSelection = (userId: string) => {
    setSelectedUserIds((prev) => prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]);
  };

  const toggleAllFiltered = () => {
    const filteredIds = filteredPeople.map((row) => row.user.id);
    const allSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedUserIdSet.has(id));
    setSelectedUserIds(allSelected ? [] : filteredIds);
  };

  const openBatchScheduleDrawer = (presetCoursePk?: string) => {
    if (selectedUserIds.length === 0) {
      pushToast({ title: "No personnel selected", message: "Select one or more personnel rows before creating a class roster.", variant: "error" });
      return;
    }
    const coursePk = presetCoursePk || (personCourseFilter !== "ALL" ? courses.find((course) => course.course_id === personCourseFilter)?.id || "" : "");
    setScheduleForm((prev) => ({ ...prev, course_pk: coursePk || prev.course_pk, user_ids: selectedUserIds }));
    setScheduleOpen(true);
  };

  const openAutoGroupDrawer = () => {
    if (selectedUserIds.length === 0) {
      pushToast({ title: "No personnel selected", message: "Select one or more personnel rows before running the grouped scheduler.", variant: "error" });
      return;
    }
    setAutoGroupForm((prev) => ({
      ...prev,
      user_ids: selectedUserIds,
      base_start_on: prev.base_start_on || new Date().toISOString().slice(0, 10),
    }));
    setAutoGroupOpen(true);
  };

  const submitAutoGroupSchedule = async () => {
    if (selectedUserIds.length === 0) {
      pushToast({ title: "No personnel selected", message: "Select personnel first.", variant: "error" });
      return;
    }
    if (!autoGroupForm.include_due_soon && !autoGroupForm.include_overdue) {
      pushToast({ title: "Select a due bucket", message: "Choose overdue, due soon, or both before running the grouped scheduler.", variant: "error" });
      return;
    }
    setAutoGrouping(true);
    try {
      const result = await autoGroupTrainingEvents({
        ...autoGroupForm,
        user_ids: selectedUserIds,
        base_start_on: autoGroupForm.base_start_on || null,
        provider: autoGroupForm.provider || null,
        instructor_name: autoGroupForm.instructor_name || null,
        location: autoGroupForm.location || null,
        meeting_link: autoGroupForm.meeting_link || null,
        notes: autoGroupForm.notes || null,
      });
      setAutoGroupOpen(false);
      setSelectedUserIds([]);
      if (result.sessions[0]?.event?.id) setSelectedEventId(result.sessions[0].event.id);
      await load();
      openTab("schedule");
      pushToast({
        title: "Grouped schedule created",
        message: `${result.total_enrolled} enrolments were placed into ${result.total_sessions} course session(s).${result.skipped.length ? ` ${result.skipped.length} item(s) were skipped.` : ""}`,
        variant: result.skipped.length ? "warning" : "info",
      });
    } catch (error: any) {
      pushToast({ title: "Grouped scheduling failed", message: error?.message || "Could not auto-group the selected personnel.", variant: "error" });
    } finally {
      setAutoGrouping(false);
    }
  };

  const submitBatchSchedule = async () => {
    if (!scheduleForm.course_pk) {
      pushToast({ title: "Course required", message: "Choose the course/class to be delivered before scheduling personnel.", variant: "error" });
      return;
    }
    if (selectedUserIds.length === 0) {
      pushToast({ title: "No personnel selected", message: "Select personnel first.", variant: "error" });
      return;
    }
    setScheduling(true);
    try {
      const payload: TrainingEventBatchScheduleCreate = {
        ...scheduleForm,
        user_ids: selectedUserIds,
        ends_on: scheduleForm.ends_on || null,
        title: scheduleForm.title || null,
        provider: scheduleForm.provider || null,
        instructor_name: scheduleForm.instructor_name || null,
        location: scheduleForm.location || null,
        meeting_link: scheduleForm.meeting_link || null,
        notes: scheduleForm.notes || null,
      };
      const result = await createTrainingEventBatch(payload);
      setScheduleOpen(false);
      setSelectedEventId(result.event.id);
      setSelectedUserIds([]);
      await load();
      openTab("schedule");
      pushToast({ title: "Session scheduled", message: `${result.created_count} personnel were enrolled into ${result.event.title}.`, variant: "info" });
    } catch (error: any) {
      pushToast({ title: "Scheduling failed", message: error?.message || "Could not create the training session.", variant: "error" });
    } finally {
      setScheduling(false);
    }
  };

  const openDeferralRequestForParticipant = (participant: TrainingEventParticipantRead) => {
    const row = peopleRows.find((entry) => entry.user.id === participant.user_id);
    const event = events.find((entry) => entry.id === participant.event_id);
    const coursePk = event ? eventCoursePk(event) : "";
    const statusItem = row?.items.find((item) => item.course_id === (courses.find((course) => course.id === coursePk)?.course_id || ""));
    setDeferralTarget({
      participantId: participant.id,
      userId: participant.user_id,
      userName: row?.user.full_name || row?.user.email || participant.user_id,
      coursePk,
      originalDueDate: statusItem?.extended_due_date || statusItem?.valid_until || null,
    });
    setDeferralForm({
      requested_new_due_date: "",
      reason_category: "OPERATIONAL_REQUIREMENTS",
      reason_text: "",
    });
    setDeferralOpen(true);
  };

  const submitDeferralRequest = async () => {
    if (!deferralTarget?.coursePk || !deferralTarget.originalDueDate) {
      pushToast({ title: "Deferral unavailable", message: "A due date could not be determined for this participant/course pair.", variant: "error" });
      return;
    }
    if (!deferralForm.requested_new_due_date) {
      pushToast({ title: "New due date required", message: "Choose the proposed deferred due date.", variant: "error" });
      return;
    }
    try {
      await createTrainingDeferralRequest({
        user_id: deferralTarget.userId,
        course_pk: deferralTarget.coursePk,
        original_due_date: deferralTarget.originalDueDate,
        requested_new_due_date: deferralForm.requested_new_due_date,
        reason_category: deferralForm.reason_category as any,
        reason_text: deferralForm.reason_text || null,
      });
      await updateTrainingEventParticipant(deferralTarget.participantId, { status: "DEFERRED" });
      setDeferralOpen(false);
      await load();
      if (selectedEventId) {
        const refreshed = await listTrainingEventParticipants(selectedEventId);
        setParticipants(refreshed);
      }
      pushToast({ title: "Deferral submitted", message: `${deferralTarget.userName} has been marked deferred pending decision.`, variant: "info" });
    } catch (error: any) {
      pushToast({ title: "Deferral failed", message: error?.message || "Could not submit the deferral request.", variant: "error" });
    }
  };

  const downloadCertificatePdf = async (record: TrainingRecordRead) => {
    try {
      const downloaded = await downloadTrainingCertificateArtifact(record.id, certificateSetup);
      saveDownloadedFile(downloaded);
      await load();
    } catch (error: any) {
      pushToast({ title: "Certificate download failed", message: error?.message || "Could not generate the certificate PDF.", variant: "error" });
    }
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
      course_id: course.course_id,
      course_name: course.course_name,
      frequency_months: course.frequency_months == null ? "" : String(course.frequency_months),
      status: course.status || "One_Off",
      category_raw: course.category_raw || "",
      is_mandatory: !!course.is_mandatory,
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
      if (editingCourseId) await updateTrainingCourse(editingCourseId, payload);
      else await createTrainingCourse(payload);
      setCourseFormOpen(false);
      await load();
      pushToast({ title: editingCourseId ? "Course updated" : "Course created", message: `${payload.course_id} saved successfully.`, variant: "info" });
    } catch (error: any) {
      pushToast({ title: "Save failed", message: error?.message || "Unable to save course.", variant: "error" });
    } finally {
      setSavingCourse(false);
    }
  };

  const openCreateRequirement = () => {
    setEditingRequirementId(null);
    setRequirementForm({
      course_pk: personCourseFilter !== "ALL" ? (courses.find((course) => course.course_id === personCourseFilter)?.id || "") : "",
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

  const openEditRequirement = (requirement: TrainingRequirementRead) => {
    setEditingRequirementId(requirement.id);
    setRequirementForm({
      course_pk: requirement.course_pk,
      scope: requirement.scope,
      department_code: requirement.department_code || null,
      job_role: requirement.job_role || null,
      user_id: requirement.user_id || null,
      is_mandatory: requirement.is_mandatory,
      is_active: requirement.is_active,
      effective_from: requirement.effective_from || null,
      effective_to: requirement.effective_to || null,
    });
    setRequirementFormOpen(true);
  };

  const submitRequirement = async () => {
    if (!requirementForm.course_pk) {
      pushToast({ title: "Course required", message: "Select the course for this rule.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "DEPARTMENT" && !String(requirementForm.department_code || "").trim()) {
      pushToast({ title: "Department required", message: "Choose or enter a department code.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "JOB_ROLE" && !String(requirementForm.job_role || "").trim()) {
      pushToast({ title: "Job role required", message: "Choose or enter the role this rule applies to.", variant: "error" });
      return;
    }
    if (requirementForm.scope === "USER" && !String(requirementForm.user_id || "").trim()) {
      pushToast({ title: "User required", message: "Pick the user for this targeted requirement.", variant: "error" });
      return;
    }
    setSavingRequirement(true);
    try {
      const payload: TrainingRequirementCreate | TrainingRequirementUpdate = {
        course_pk: requirementForm.course_pk,
        scope: requirementForm.scope as TrainingRequirementScope,
        department_code: requirementForm.scope === "DEPARTMENT" ? String(requirementForm.department_code || "").trim().toUpperCase() || null : null,
        job_role: requirementForm.scope === "JOB_ROLE" ? String(requirementForm.job_role || "").trim() || null : null,
        user_id: requirementForm.scope === "USER" ? String(requirementForm.user_id || "").trim() || null : null,
        is_mandatory: requirementForm.is_mandatory,
        is_active: requirementForm.is_active,
        effective_from: requirementForm.effective_from || null,
        effective_to: requirementForm.effective_to || null,
      };
      if (editingRequirementId) await updateTrainingRequirement(editingRequirementId, payload as TrainingRequirementUpdate);
      else await createTrainingRequirement(payload as TrainingRequirementCreate);
      setRequirementFormOpen(false);
      await load();
      openTab("matrix");
      pushToast({ title: editingRequirementId ? "Requirement updated" : "Requirement created", message: "The course requirement matrix has been updated.", variant: "info" });
    } catch (error: any) {
      pushToast({ title: "Save failed", message: error?.message || "Unable to save the requirement rule.", variant: "error" });
    } finally {
      setSavingRequirement(false);
    }
  };

  const removeRequirement = async (requirement: TrainingRequirementRead) => {
    const course = courseById.get(requirement.course_pk);
    const okay = window.confirm(`Delete requirement rule for ${course?.course_id || requirement.course_pk}?`);
    if (!okay) return;
    try {
      await deleteTrainingRequirement(requirement.id);
      await load();
      pushToast({ title: "Requirement deleted", message: "The requirement rule has been removed.", variant: "info" });
    } catch (error: any) {
      pushToast({ title: "Delete failed", message: error?.message || "Could not delete the requirement rule.", variant: "error" });
    }
  };

  const runImport = async () => {
    if (!importFile) {
      pushToast({ title: "No file selected", message: `Choose a ${importMode === "courses" ? "COURSES" : "TRAINING"} workbook first.`, variant: "error" });
      return;
    }
    setImporting(true);
    setImportProgress(null);
    setImportSummary(null);
    try {
      const summary = importMode === "courses"
        ? await importTrainingCoursesWorkbook(importFile, { dryRun: importDryRun, sheetName: "Courses", onProgress: setImportProgress })
        : await importTrainingRecordsWorkbook(importFile, { dryRun: importDryRun, sheetName: "Training", onProgress: setImportProgress });
      setImportSummary(summary);
      const createdCount = Number((summary as any).created_courses ?? (summary as any).created_records ?? 0);
      const updatedCount = Number((summary as any).updated_courses ?? (summary as any).updated_records ?? 0);
      const skippedCount = Number((summary as any).skipped_rows ?? 0);
      pushToast({
        title: importDryRun ? "Dry-run completed" : "Import completed",
        message: `${createdCount} created, ${updatedCount} updated, ${skippedCount} skipped.`,
        variant: "info",
      });
      if (!importDryRun) await load();
    } catch (error: any) {
      pushToast({ title: "Import failed", message: error?.message || "Could not import the workbook.", variant: "error" });
    } finally {
      setImporting(false);
    }
  };

  const exportCourses = () => {
    const rows = courses.slice().sort((a, b) => a.course_id.localeCompare(b.course_id)).map((course) => ({
      course_id: course.course_id,
      course_name: course.course_name,
      status: course.status,
      category: course.category_raw || course.category || "",
      scope: course.scope || "",
      mandatory: course.is_mandatory ? "YES" : "NO",
      frequency_months: course.frequency_months ?? "",
      regulatory_reference: course.regulatory_reference || "",
      active: course.is_active ? "YES" : "NO",
    }));
    downloadTextFile(buildCsv(rows, ["course_id", "course_name", "status", "category", "scope", "mandatory", "frequency_months", "regulatory_reference", "active"]), `training-courses-${amoCode || "amo"}.csv`);
  };

  const exportTrainings = () => {
    const rows = records.slice().sort((a, b) => String(b.completion_date || "").localeCompare(String(a.completion_date || ""))).map((record) => {
      const course = resolveCourse(courseLookup, record.course_id);
      const user = users.find((entry) => entry.id === record.user_id);
      return {
        person_name: user?.full_name || user?.email || record.user_id,
        staff_code: user?.staff_code || "",
        role: user?.position_title || user?.role || "",
        course_id: course?.course_id || record.course_id,
        course_name: course?.course_name || "",
        completion_date: record.completion_date || "",
        valid_until: record.valid_until || "",
        hours_completed: record.hours_completed ?? "",
        exam_score: record.exam_score ?? "",
        certificate_reference: record.certificate_reference || "",
        remarks: record.remarks || "",
      };
    });
    downloadTextFile(buildCsv(rows, ["person_name", "staff_code", "role", "course_id", "course_name", "completion_date", "valid_until", "hours_completed", "exam_score", "certificate_reference", "remarks"]), `training-records-${amoCode || "amo"}.csv`);
  };

  const prefetchPerson = (userId: string) => {
    void prefetchTrainingUserDetailBundle(userId);
  };


  const openPerson = (userId: string, options?: { filter?: string; tab?: string }) => {
    prefetchPerson(userId);
    const qs = new URLSearchParams();
    if (options?.filter) qs.set("filter", options.filter);
    if (options?.tab) qs.set("tab", options.tab);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    navigate(`/maintenance/${amoCode || "UNKNOWN"}/qms/training-competence/people/${userId}/course-history${suffix}`);
  };

  const currentEventParticipants = useMemo(() => participants, [participants]);

  return (
    <QMSLayout
      amoCode={amoCode || "UNKNOWN"}
      department={department || "quality"}
      title="Training & Competence"
      subtitle="Unified QMS training control, requirements, scheduling and personnel records"
      actions={
        <div className="tc-toolbar__actions">
          {canManageCourses ? (
            <>
              <button type="button" className="secondary-chip-btn" onClick={openCreateCourse}><Users size={14} /> New course</button>
              <button type="button" className="secondary-chip-btn" onClick={() => { setImportMode("courses"); setImportOpen(true); }}><Upload size={14} /> Import courses</button>
              <button type="button" className="secondary-chip-btn" onClick={() => { setImportMode("trainings"); setImportOpen(true); }}><Upload size={14} /> Import trainings</button>
            </>
          ) : null}
          <button type="button" className="secondary-chip-btn" onClick={exportCourses}><FileSpreadsheet size={14} /> Courses</button>
          <button type="button" className="secondary-chip-btn" onClick={exportTrainings}><Download size={14} /> Trainings</button>
          <button type="button" className="secondary-chip-btn" onClick={() => void load()} aria-label="Refresh training dashboard" title="Refresh">
            <RefreshCw size={14} />
          </button>
        </div>
      }
    >
      <div className="tc-page">
        <section className="tc-hero">
          <div className="tc-hero__row">
            <div>
              <p className="tc-eyebrow">QMS · Training Control</p>
              <h2 className="tc-title">One training handler</h2>
              <p className="tc-muted">Course requirements, personnel compliance, scheduling, attendance and certificates now sit under the same QMS route.</p>
            </div>
            <div className="tc-inline-actions">
              <span className="tc-chip"><Users size={14} /> {animatedUsers} personnel</span>
              <span className="tc-chip"><CalendarClock size={14} /> {animatedEvents} active sessions</span>
            </div>
          </div>
          <div className="tc-summary-grid">
            <button type="button" className="tc-kpi-card tc-kpi-card--button" onClick={() => openPeopleFilter("OVERDUE")}><span>Overdue</span><strong>{animatedOverdue}</strong><small>Open overdue personnel</small></button>
            <button type="button" className="tc-kpi-card tc-kpi-card--button" onClick={() => openPeopleFilter("DUE_SOON")}><span>Due soon</span><strong>{animatedDueSoon}</strong><small>Open due-soon roster</small></button>
            <button type="button" className="tc-kpi-card tc-kpi-card--button" onClick={() => openTab("matrix")}><span>Requirement rules</span><strong>{animatedRequirements}</strong><small>Review rule coverage</small></button>
            <button type="button" className="tc-kpi-card tc-kpi-card--button" onClick={() => openTab("matrix")}><span>Course catalogue</span><strong>{animatedCourses}</strong><small>Manage courses</small></button>
            <button type="button" className="tc-kpi-card tc-kpi-card--button" onClick={() => openTab("certificates")}><span>Certificates</span><strong>{animatedCertificates}</strong><small>Issue and download</small></button>
            <button type="button" className="tc-kpi-card tc-kpi-card--warning tc-kpi-card--button" onClick={() => openPeopleFilter("ANOMALY", { anomalyOnly: true })}><span>Rectify data</span><strong>{animatedAnomalies}</strong><small>Open flagged records</small></button>
          </div>
        </section>

        {error ? (
          <section className="tc-alert tc-alert--soft">
            <AlertTriangle size={16} />
            <div>
              <strong>Partial training load</strong>
              <p>{error}</p>
            </div>
          </section>
        ) : null}

        {anomalies.length > 0 ? (
          <section className="tc-alert tc-alert--warning">
            <AlertTriangle size={16} />
            <div>
              <strong>Refresher without initial detected</strong>
              <p>{anomalies.length} record(s) show a refresher-style course completion without the matching initial course. These rows are flagged below for rectification.</p>
            </div>
            <button type="button" className="secondary-chip-btn" onClick={() => { openTab("people"); setPersonAnomalyOnly(true); setPersonStatusFilter("ANOMALY"); }}>
              Review flagged personnel
            </button>
          </section>
        ) : null}

        <section className="tc-tabs-wrap">
          <div className="tc-tabs" role="tablist" aria-label="Training dashboard tabs">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`tc-tab ${tab === item.key ? "is-active" : ""}`}
                onClick={() => openTab(item.key)}
              >
                <span>{item.label}</span>
                <small>{item.hint}</small>
              </button>
            ))}
          </div>
        </section>

        {loading ? <section className="tc-panel"><p className="tc-empty">Loading training data…</p></section> : null}

        {!loading && tab === "overview" ? (
          <div className="tc-content-grid">
            <section className="tc-panel">
              <div className="tc-panel__header">
                <div>
                  <h3 className="tc-panel__title">Urgent personnel</h3>
                  <p className="tc-muted">People with the highest compliance risk now.</p>
                </div>
              </div>
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <thead>
                    <tr>
                      <th>Person</th>
                      <th>Overdue</th>
                      <th>Due soon</th>
                      <th>Outstanding</th>
                      <th>Rectify</th>
                      <th>Next due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {peopleRows.slice(0, 10).map((row) => (
                      <tr key={row.user.id}>
                        <td>
                          <button type="button" className="tc-link-button" onMouseEnter={() => prefetchPerson(row.user.id)} onFocus={() => prefetchPerson(row.user.id)} onClick={() => openPerson(row.user.id)}>{row.user.full_name || row.user.email}</button>
                          <div className="tc-table__hint">{row.user.staff_code || "—"} · {row.user.position_title || row.user.role}</div>
                        </td>
                        <td>{row.overdue}</td>
                        <td>{row.dueSoon}</td>
                        <td>{row.outstanding}</td>
                        <td>{row.anomalyCount > 0 ? <span className="tc-status-pill overdue">{row.anomalyCount}</span> : "—"}</td>
                        <td>{row.nextDueLabel}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="tc-panel">
              <div className="tc-panel__header">
                <div>
                  <h3 className="tc-panel__title">Data rectification queue</h3>
                  <p className="tc-muted">Front-end flagged inconsistencies that should be corrected in the records.</p>
                </div>
              </div>
              {anomalies.length === 0 ? (
                <p className="tc-empty">No refresher-without-initial inconsistency detected in the currently loaded dataset.</p>
              ) : (
                <div className="tc-table-wrap">
                  <table className="tc-table">
                    <thead>
                      <tr>
                        <th>Person</th>
                        <th>Refresher course</th>
                        <th>Completed</th>
                        <th>Missing initial</th>
                      </tr>
                    </thead>
                    <tbody>
                      {anomalies.slice(0, 12).map((item) => (
                        <tr key={item.key}>
                          <td><button type="button" className="tc-link-button" onMouseEnter={() => prefetchPerson(item.userId)} onFocus={() => prefetchPerson(item.userId)} onClick={() => openPerson(item.userId)}>{item.userName}</button></td>
                          <td>{item.courseCode} · {item.courseName}</td>
                          <td>{compactDate(item.completionDate)}</td>
                          <td>{item.prerequisiteNames.join(", ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="tc-panel tc-panel--full">
              <div className="tc-panel__header">
                <div>
                  <h3 className="tc-panel__title">Upcoming sessions</h3>
                  <p className="tc-muted">Open sessions that are already in the training schedule.</p>
                </div>
              </div>
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Session</th>
                      <th>Starts</th>
                      <th>Status</th>
                      <th>Provider</th>
                    </tr>
                  </thead>
                  <tbody>
                    {upcomingEvents.length === 0 ? (
                      <tr><td colSpan={5}><p className="tc-empty">No upcoming sessions found.</p></td></tr>
                    ) : upcomingEvents.map((event) => {
                      const course = resolveCourse(courseLookup, eventCoursePk(event));
                      return (
                        <tr key={event.id}>
                          <td>{course?.course_id || "—"} · {course?.course_name || "Unmapped course"}</td>
                          <td>{event.title}</td>
                          <td>{compactDate(event.starts_on)}</td>
                          <td><span className={`tc-status-pill ${event.status === "IN_PROGRESS" ? "due-soon" : "ok"}`}>{event.status.replaceAll("_", " ")}</span></td>
                          <td>{event.provider || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        ) : null}

        {!loading && tab === "people" ? (
          <section className="tc-panel">
            <div className="tc-panel__header">
              <div>
                <h3 className="tc-panel__title">Personnel records</h3>
                <p className="tc-muted">Click a name to open the individual record page. Search and filter the personnel list directly from here.</p>
              </div>
            </div>

            <div className="tc-filterbar">
              <label className="tc-field tc-field--grow">
                <span className="tc-field__label">Search personnel</span>
                <div className="tc-input-with-icon">
                  <Search size={16} />
                  <input className="tc-input" value={personQuery} onChange={(e) => setPersonQuery(e.target.value)} placeholder="Search name, email, staff code or role" />
                </div>
              </label>
              <label className="tc-field">
                <span className="tc-field__label">Course</span>
                <select className="tc-select" value={personCourseFilter} onChange={(e) => updatePersonCourseFilter(e.target.value)}>
                  <option value="ALL">All courses</option>
                  {courses.map((course) => <option key={course.id} value={course.course_id}>{course.course_id} · {course.course_name}</option>)}
                </select>
              </label>
              <label className="tc-field">
                <span className="tc-field__label">Status</span>
                <select className="tc-select" value={personStatusFilter} onChange={(e) => setPersonStatusFilter(e.target.value)}>
                  <option value="ALL">All personnel</option>
                  <option value="OVERDUE">Has overdue</option>
                  <option value="DUE_SOON">Has due soon</option>
                  <option value="NOT_DONE">Has missing initial / no completion</option>
                  <option value="DEFERRED">Has deferral</option>
                  <option value="ANOMALY">Flagged inconsistency</option>
                </select>
              </label>
              <label className="tc-toggle">
                <input type="checkbox" checked={personAnomalyOnly} onChange={(e) => setPersonAnomalyOnly(e.target.checked)} />
                <span>Rectification only</span>
              </label>
            </div>

            <div className="tc-bulkbar">
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={toggleAllFiltered}><CheckSquare size={14} /> {filteredPeople.length > 0 && filteredPeople.every((row) => selectedUserIdSet.has(row.user.id)) ? "Clear selection" : "Select filtered"}</button>
                <span className="tc-chip"><Users size={14} /> {selectedUserIds.length} selected</span>
              </div>
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={() => openPeopleFilter("OVERDUE")}><AlertTriangle size={14} /> Overdue only</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openPeopleFilter("DUE_SOON")}><CalendarClock size={14} /> Due soon only</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openAutoGroupDrawer()} disabled={selectedUserIds.length === 0}><CalendarClock size={14} /> Auto-group selected</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openBatchScheduleDrawer()} disabled={selectedUserIds.length === 0}><GraduationCap size={14} /> Single course</button>
              </div>
            </div>

            <div className="tc-bulkbar" style={{ marginTop: 8 }}>
              <div className="tc-inline-actions">
                <span className="tc-chip">Page {peoplePage + 1}</span>
                <span className="tc-chip">Showing up to {PEOPLE_PAGE_SIZE} personnel</span>
              </div>
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={() => setPeoplePage((page) => Math.max(0, page - 1))} disabled={peoplePage === 0}>Previous</button>
                <button type="button" className="secondary-chip-btn" onClick={() => setPeoplePage((page) => page + 1)} disabled={!hasMorePeople}>Next</button>
              </div>
            </div>

            <div className="tc-table-wrap">
              <table className="tc-table tc-table--personnel">
                <thead>
                  <tr>
                    <th className="tc-col-checkbox"><input type="checkbox" checked={filteredPeople.length > 0 && filteredPeople.every((row) => selectedUserIdSet.has(row.user.id))} onChange={toggleAllFiltered} /></th>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Outstanding</th>
                    <th>Overdue</th>
                    <th>Due soon</th>
                    <th>Deferrals</th>
                    <th>Records</th>
                    <th>Certificates</th>
                    <th>Next due</th>
                    <th>Time left</th>
                    <th>Rectify</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPeople.length === 0 ? (
                    <tr><td colSpan={12}><p className="tc-empty">No personnel match the current training filters.</p></td></tr>
                  ) : filteredPeople.map((row) => {
                    const nextItem = row.items.find((item) => item.extended_due_date || item.valid_until);
                    return (
                      <tr key={row.user.id} className={row.anomalyCount > 0 ? "is-flagged" : undefined}>
                        <td className="tc-col-checkbox"><input type="checkbox" checked={selectedUserIdSet.has(row.user.id)} onChange={() => togglePersonSelection(row.user.id)} /></td>
                        <td>
                          <button type="button" className="tc-link-button" onMouseEnter={() => prefetchPerson(row.user.id)} onFocus={() => prefetchPerson(row.user.id)} onClick={() => openPerson(row.user.id)}>{row.user.full_name || row.user.email}</button>
                          <div className="tc-table__hint">{row.user.staff_code || "—"} · {row.user.email || "—"}</div>
                          {row.notDone > 0 ? (
                            <div className="tc-table__hint" style={{ marginTop: 6 }}>
                              <button type="button" className="tc-link-button" onClick={() => openPerson(row.user.id, { filter: "NOT_DONE" })}>Open missing courses</button>
                            </div>
                          ) : null}
                        </td>
                        <td>{row.user.position_title || row.user.role || "—"}</td>
                        <td>{row.outstanding}</td>
                        <td>{row.overdue}</td>
                        <td>{row.dueSoon}</td>
                        <td>{row.deferred}</td>
                        <td>{row.records.length}</td>
                        <td>{row.certificates.length}</td>
                        <td>{row.nextDueLabel}</td>
                        <td>{timeLeftLabel(nextItem?.days_until_due)}</td>
                        <td>{row.anomalyCount > 0 ? <span className="tc-status-pill overdue">{row.anomalyCount}</span> : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {!loading && tab === "matrix" ? (
          <div className="tc-content-grid">
            <section className="tc-panel tc-panel--full">
              <div className="tc-panel__header">
                <div>
                  <h3 className="tc-panel__title">Requirement rules</h3>
                  <p className="tc-muted">Scope rules attached to each course requirement.</p>
                </div>
                {canManageCourses ? (
                  <div className="tc-inline-actions">
                    <button type="button" className="secondary-chip-btn" onClick={openCreateRequirement}>Add rule</button>
                  </div>
                ) : null}
              </div>
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Scope</th>
                      <th>Department</th>
                      <th>Job role</th>
                      <th>Mandatory</th>
                      <th>Active</th>
                      <th>Effective window</th>
                      {canManageCourses ? <th>Actions</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {requirementRows.length === 0 ? (
                      <tr><td colSpan={canManageCourses ? 8 : 7}><p className="tc-empty">No requirement rules were returned from the server.</p></td></tr>
                    ) : requirementRows.map((row) => (
                      <tr key={row.id}>
                        <td>{row.course?.course_id || row.course_pk} · {row.course?.course_name || "Unknown course"}</td>
                        <td>{row.scope}</td>
                        <td>{row.department_code || "—"}</td>
                        <td>{row.scope === "USER" ? (users.find((user) => user.id === row.user_id)?.full_name || row.job_role || "—") : (row.job_role || "—")}</td>
                        <td>{row.is_mandatory ? "Yes" : "No"}</td>
                        <td>{row.is_active ? "Active" : "Inactive"}</td>
                        <td>{row.effective_from || row.effective_to ? `${compactDate(row.effective_from)} → ${compactDate(row.effective_to)}` : "Always on"}</td>
                        {canManageCourses ? (
                          <td>
                            <div className="tc-inline-actions">
                              <button type="button" className="secondary-chip-btn" onClick={() => openEditRequirement(row)}>Edit</button>
                              <button type="button" className="secondary-chip-btn" onClick={() => removeRequirement(row)}>Delete</button>
                            </div>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="tc-panel tc-panel--full">
              <div className="tc-panel__header">
                <div>
                  <h3 className="tc-panel__title">Course catalogue</h3>
                  <p className="tc-muted">Initial and refresher structure is shown here so the training chain is visible.</p>
                </div>
              </div>
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Course</th>
                      <th>Phase</th>
                      <th>Frequency</th>
                      <th>Required rules</th>
                      <th>Status</th>
                      {canManageCourses ? <th>Actions</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {courseRows.map(({ course, phase, requiredCount, isRequired }) => (
                      <tr key={course.id}>
                        <td>{course.course_id}</td>
                        <td>
                          <div>{course.course_name}</div>
                          <div className="tc-table__hint">{course.regulatory_reference || course.scope || "—"}</div>
                        </td>
                        <td><span className={`tc-status-pill ${phase === "REFRESHER" ? "due-soon" : phase === "INITIAL" ? "ok" : "not-done"}`}>{phase}</span></td>
                        <td>{course.frequency_months != null ? `${course.frequency_months} months` : "One-off / manual"}</td>
                        <td>{requiredCount}</td>
                        <td>{isRequired ? "Required" : "Optional"}</td>
                        {canManageCourses ? (
                          <td><button type="button" className="secondary-chip-btn" onClick={() => openEditCourse(course)}>Edit</button></td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        ) : null}

        {!loading && tab === "schedule" ? (
          <section className="tc-panel">
            <div className="tc-panel__header">
              <div>
                <h3 className="tc-panel__title">Schedule and attendance</h3>
                <p className="tc-muted">Create internal or external classes, batch-enrol due personnel, then close attendance from the same page.</p>
              </div>
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={() => openAutoGroupDrawer()} disabled={selectedUserIds.length === 0}><CalendarClock size={14} /> Auto-group selected</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openBatchScheduleDrawer()} disabled={selectedUserIds.length === 0}><GraduationCap size={14} /> Single course</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openPeopleFilter("OVERDUE")}><AlertTriangle size={14} /> Pull overdue roster</button>
                <button type="button" className="secondary-chip-btn" onClick={() => openPeopleFilter("DUE_SOON")}><CalendarClock size={14} /> Pull due-soon roster</button>
              </div>
            </div>
            <div className="tc-filterbar">
              <label className="tc-field tc-field--grow">
                <span className="tc-field__label">Session</span>
                <select className="tc-select" value={selectedEventId} onChange={(e) => setSelectedEventId(e.target.value)}>
                  <option value="">Select a session</option>
                  {events.map((event) => {
                    const course = resolveCourse(courseLookup, eventCoursePk(event));
                    return <option key={event.id} value={event.id}>{compactDate(event.starts_on)} · {course?.course_id || "—"} · {event.title}</option>;
                  })}
                </select>
              </label>
            </div>

            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Session</th>
                    <th>Mode</th>
                    <th>Starts</th>
                    <th>Ends</th>
                    <th>Status</th>
                    <th>Location</th>
                    <th>Provider</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr><td colSpan={8}><p className="tc-empty">No scheduled sessions.</p></td></tr>
                  ) : events.map((event) => {
                    const course = resolveCourse(courseLookup, eventCoursePk(event));
                    return (
                      <tr key={event.id} className={selectedEventId === event.id ? "is-selected" : undefined}>
                        <td>{course?.course_id || "—"} · {course?.course_name || "Unknown course"}</td>
                        <td>
                          <div>{event.title}</div>
                          <div className="tc-table__hint">{parseEventMeta(event.notes).plainNotes || "No schedule notes"}</div>
                        </td>
                        <td>{formatSessionMode(event)}</td>
                        <td>{compactDate(event.starts_on)}</td>
                        <td>{compactDate(event.ends_on)}</td>
                        <td><span className={`tc-status-pill ${event.status === "CANCELLED" ? "overdue" : event.status === "IN_PROGRESS" ? "due-soon" : "ok"}`}>{event.status.replaceAll("_", " ")}</span></td>
                        <td>{event.location || "—"}</td>
                        <td>{event.provider || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {selectedEventId ? (
              <section className="tc-subpanel">
                <div className="tc-panel__header">
                  <div>
                    <h4 className="tc-panel__title">Selected session roster</h4>
                    <p className="tc-muted">Mark attended to auto-create the completion record and certificate number. Use deferral when a learner is moving to the next approved class.</p>
                  </div>
                </div>
                <div className="tc-table-wrap">
                  <table className="tc-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Status</th>
                        <th>Attendance note</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentEventParticipants.length === 0 ? (
                        <tr><td colSpan={4}><p className="tc-empty">No participants were returned for this session.</p></td></tr>
                      ) : currentEventParticipants.map((participant) => {
                        const user = users.find((entry) => entry.id === participant.user_id);
                        return (
                          <tr key={participant.id}>
                            <td>
                              <div>{user?.full_name || participant.user_id}</div>
                              <div className="tc-table__hint">{user?.staff_code || "—"} · {user?.position_title || user?.role || "—"}</div>
                            </td>
                            <td><span className={`tc-status-pill ${participant.status === "DEFERRED" ? "deferred" : participant.status === "ATTENDED" ? "ok" : "due-soon"}`}>{participant.status}</span></td>
                            <td>{participant.attendance_note || "—"}</td>
                            <td>
                              <div className="tc-inline-actions">
                                <button
                                  type="button"
                                  className="secondary-chip-btn"
                                  onClick={async () => {
                                    await updateTrainingEventParticipant(participant.id, { status: "ATTENDED" });
                                    const refreshed = await listTrainingEventParticipants(selectedEventId);
                                    setParticipants(refreshed);
                                    await load();
                                    pushToast({ title: "Attendance closed", message: `${user?.full_name || participant.user_id} is now marked attended and the completion workflow has run.`, variant: "info" });
                                  }}
                                >
                                  Mark attended
                                </button>
                                <button type="button" className="secondary-chip-btn" onClick={() => openDeferralRequestForParticipant(participant)} disabled={participant.status === "ATTENDED"}>Request deferral</button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}
          </section>
        ) : null}

        {!loading && tab === "certificates" ? (
          <section className="tc-panel">
            <div className="tc-panel__header">
              <div>
                <h3 className="tc-panel__title">Certificate register</h3>
                <p className="tc-muted">Issue immutable certificate numbers, download branded certificate PDFs, and verify authenticity from one register.</p>
              </div>
              <div className="tc-inline-actions">
                <button type="button" className="secondary-chip-btn" onClick={() => setCertSetupOpen(true)}><ClipboardSignature size={14} /> Signature setup</button>
              </div>
            </div>
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Course</th>
                    <th>Completed</th>
                    <th>Valid until</th>
                    <th>Certificate</th>
                    <th>Verification</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {certificateRows.length === 0 ? (
                    <tr><td colSpan={7}><p className="tc-empty">No certificate records found.</p></td></tr>
                  ) : certificateRows.map((record) => {
                    const course = resolveCourse(courseLookup, record.course_id);
                    const user = users.find((entry) => entry.id === record.user_id);
                    return (
                      <tr key={record.id}>
                        <td><button type="button" className="tc-link-button" onMouseEnter={() => prefetchPerson(record.user_id)} onFocus={() => prefetchPerson(record.user_id)} onClick={() => openPerson(record.user_id)}>{user?.full_name || record.user_id}</button></td>
                        <td>{course?.course_id || "—"} · {course?.course_name || "Unknown course"}</td>
                        <td>{compactDate(record.completion_date)}</td>
                        <td>{compactDate(record.valid_until)}</td>
                        <td>{record.certificate_reference || "Not issued"}</td>
                        <td>{record.verification_status || "—"}</td>
                        <td>
                          <div className="tc-inline-actions">
                            {!record.certificate_reference ? (
                              <button type="button" className="secondary-chip-btn" onClick={async () => { await issueTrainingCertificate(record.id); await load(); }}><ShieldCheck size={14} /> Issue</button>
                            ) : null}
                            <button type="button" className="secondary-chip-btn" onClick={() => downloadCertificatePdf(record)}><Download size={14} /> PDF</button>
                            {record.certificate_reference ? <button type="button" className="secondary-chip-btn" onClick={() => window.open(`/verify/certificate/${record.certificate_reference}`, "_blank")}><ExternalLink size={14} /></button> : null}
                            <button type="button" className="secondary-chip-btn" onClick={() => window.open("/verify/scan", "_blank")}><ScanLine size={14} /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </div>

      <Drawer title={drawer?.title || "Details"} isOpen={Boolean(drawer)} onClose={() => setDrawer(null)}>
        <div style={{ padding: 16 }}>{drawer?.body}</div>
      </Drawer>

      <Drawer title="Auto-group due courses" isOpen={autoGroupOpen} onClose={() => setAutoGroupOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <div className="tc-drawer-summary">
            <span className="tc-chip"><Users size={14} /> {selectedUserIds.length} personnel selected</span>
            <span className="tc-chip"><CalendarClock size={14} /> Groups by due course, urgency, and availability</span>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(autoGroupForm.include_overdue)} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, include_overdue: e.target.checked }))} /><span>Include overdue</span></label>
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(autoGroupForm.include_due_soon)} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, include_due_soon: e.target.checked }))} /><span>Include due soon</span></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Scheduling floor date</span><input className="tc-input" type="date" value={autoGroupForm.base_start_on || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, base_start_on: e.target.value }))} /></label>
            <label className="tc-field"><span className="tc-field__label">Provider type</span><select className="tc-select" value={autoGroupForm.provider_kind || "INTERNAL"} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, provider_kind: e.target.value }))}><option value="INTERNAL">Internal</option><option value="EXTERNAL">External</option></select></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Delivery mode</span><select className="tc-select" value={autoGroupForm.delivery_mode || "CLASSROOM"} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, delivery_mode: e.target.value }))}><option value="CLASSROOM">Classroom</option><option value="ONLINE">Online</option><option value="MIXED">Mixed</option><option value="OJT">OJT</option></select></label>
            <label className="tc-field"><span className="tc-field__label">Venue mode</span><select className="tc-select" value={autoGroupForm.venue_mode || "OFFLINE"} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, venue_mode: e.target.value }))}><option value="OFFLINE">Offline / in-class</option><option value="ONLINE">Online</option><option value="BLENDED">Blended</option></select></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Provider / ATO</span><input className="tc-input" value={autoGroupForm.provider || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, provider: e.target.value }))} placeholder="Trainer or subcontracted ATO" /></label>
            <label className="tc-field"><span className="tc-field__label">Instructor</span><input className="tc-input" value={autoGroupForm.instructor_name || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, instructor_name: e.target.value }))} placeholder="Lead instructor / trainer" /></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Location</span><input className="tc-input" value={autoGroupForm.location || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, location: e.target.value }))} placeholder="Hangar / classroom / venue" /></label>
            <label className="tc-field"><span className="tc-field__label">Meeting link</span><input className="tc-input" value={autoGroupForm.meeting_link || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, meeting_link: e.target.value }))} placeholder="Teams / Zoom / Meet link" /></label>
          </div>
          <label className="tc-field"><span className="tc-field__label">Scheduler notes</span><textarea className="tc-textarea" rows={4} value={autoGroupForm.notes || ""} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, notes: e.target.value }))} placeholder="These notes will be carried onto each created session." /></label>
          <div className="tc-form-grid-2">
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(autoGroupForm.allow_self_attendance)} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, allow_self_attendance: e.target.checked }))} /><span>Allow portal self-attendance</span></label>
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(autoGroupForm.auto_issue_certificates)} onChange={(e) => setAutoGroupForm((prev) => ({ ...prev, auto_issue_certificates: e.target.checked }))} /><span>Auto-issue certificates on attendance close</span></label>
          </div>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setAutoGroupOpen(false)}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitAutoGroupSchedule} disabled={autoGrouping}>{autoGrouping ? "Scheduling…" : "Create grouped sessions"}</button>
          </div>
        </div>
      </Drawer>

      <Drawer title="Batch schedule class / course" isOpen={scheduleOpen} onClose={() => setScheduleOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <div className="tc-drawer-summary">
            <span className="tc-chip"><Users size={14} /> {selectedUserIds.length} personnel selected</span>
            <span className="tc-chip"><CalendarClock size={14} /> Multi-AMO direct scheduler</span>
          </div>
          <label className="tc-field">
            <span className="tc-field__label">Course / class</span>
            <select className="tc-select" value={scheduleForm.course_pk} onChange={(e) => setScheduleForm((prev) => ({ ...prev, course_pk: e.target.value }))}>
              <option value="">Choose course</option>
              {courses.filter((course) => course.is_active !== false).map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}
            </select>
          </label>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Provider type</span><select className="tc-select" value={scheduleForm.provider_kind || "INTERNAL"} onChange={(e) => setScheduleForm((prev) => ({ ...prev, provider_kind: e.target.value }))}><option value="INTERNAL">Internal</option><option value="EXTERNAL">External</option></select></label>
            <label className="tc-field"><span className="tc-field__label">Delivery mode</span><select className="tc-select" value={scheduleForm.delivery_mode || "CLASSROOM"} onChange={(e) => setScheduleForm((prev) => ({ ...prev, delivery_mode: e.target.value }))}><option value="CLASSROOM">Classroom</option><option value="ONLINE">Online</option><option value="MIXED">Mixed</option><option value="OJT">OJT</option></select></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Venue mode</span><select className="tc-select" value={scheduleForm.venue_mode || "OFFLINE"} onChange={(e) => setScheduleForm((prev) => ({ ...prev, venue_mode: e.target.value }))}><option value="OFFLINE">Offline / in-class</option><option value="ONLINE">Online</option><option value="BLENDED">Blended</option></select></label>
            <label className="tc-field"><span className="tc-field__label">Session title</span><input className="tc-input" value={scheduleForm.title || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="Defaults to course name" /></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Provider / ATO</span><input className="tc-input" value={scheduleForm.provider || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, provider: e.target.value }))} placeholder="Trainer or subcontracted ATO" /></label>
            <label className="tc-field"><span className="tc-field__label">Instructor</span><input className="tc-input" value={scheduleForm.instructor_name || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, instructor_name: e.target.value }))} placeholder="Lead instructor / trainer" /></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Start date</span><input className="tc-input" type="date" value={scheduleForm.starts_on} onChange={(e) => setScheduleForm((prev) => ({ ...prev, starts_on: e.target.value }))} /></label>
            <label className="tc-field"><span className="tc-field__label">End date</span><input className="tc-input" type="date" value={scheduleForm.ends_on || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, ends_on: e.target.value }))} /></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Location</span><input className="tc-input" value={scheduleForm.location || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, location: e.target.value }))} placeholder="Hangar / classroom / venue" /></label>
            <label className="tc-field"><span className="tc-field__label">Meeting link</span><input className="tc-input" value={scheduleForm.meeting_link || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, meeting_link: e.target.value }))} placeholder="Teams / Zoom / Meet link" /></label>
          </div>
          <label className="tc-field"><span className="tc-field__label">Session notes</span><textarea className="tc-textarea" rows={4} value={scheduleForm.notes || ""} onChange={(e) => setScheduleForm((prev) => ({ ...prev, notes: e.target.value }))} placeholder="Learning objectives, materials, roster notes, or access instructions" /></label>
          <div className="tc-form-grid-2">
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(scheduleForm.allow_self_attendance)} onChange={(e) => setScheduleForm((prev) => ({ ...prev, allow_self_attendance: e.target.checked }))} /><span>Allow portal self-attendance</span></label>
            <label className="tc-toggle"><input type="checkbox" checked={Boolean(scheduleForm.auto_issue_certificates)} onChange={(e) => setScheduleForm((prev) => ({ ...prev, auto_issue_certificates: e.target.checked }))} /><span>Auto-issue certificates on attendance close</span></label>
          </div>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setScheduleOpen(false)}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitBatchSchedule} disabled={scheduling}>{scheduling ? "Scheduling…" : "Create session"}</button>
          </div>
        </div>
      </Drawer>

      <Drawer title="Request training deferral" isOpen={deferralOpen} onClose={() => setDeferralOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <p className="tc-muted">Use the existing backend deferral workflow and tie the participant to the next approved due date.</p>
          <div className="tc-chip">{deferralTarget?.userName || "No participant selected"}</div>
          <label className="tc-field"><span className="tc-field__label">Original due date</span><input className="tc-input" value={compactDate(deferralTarget?.originalDueDate)} readOnly /></label>
          <label className="tc-field"><span className="tc-field__label">Requested new due date</span><input className="tc-input" type="date" value={deferralForm.requested_new_due_date} onChange={(e) => setDeferralForm((prev) => ({ ...prev, requested_new_due_date: e.target.value }))} /></label>
          <label className="tc-field"><span className="tc-field__label">Reason</span><select className="tc-select" value={deferralForm.reason_category} onChange={(e) => setDeferralForm((prev) => ({ ...prev, reason_category: e.target.value }))}><option value="OPERATIONAL_REQUIREMENTS">Operational requirements</option><option value="ILLNESS">Illness</option><option value="PERSONAL_EMERGENCY">Personal emergency</option><option value="PROVIDER_CANCELLATION">Provider cancellation</option><option value="SYSTEM_FAILURE">System failure</option><option value="OTHER">Other</option></select></label>
          <label className="tc-field"><span className="tc-field__label">Justification</span><textarea className="tc-textarea" rows={4} value={deferralForm.reason_text} onChange={(e) => setDeferralForm((prev) => ({ ...prev, reason_text: e.target.value }))} /></label>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setDeferralOpen(false)}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitDeferralRequest}>Submit deferral</button>
          </div>
        </div>
      </Drawer>

      <Drawer title="Certificate signature setup" isOpen={certSetupOpen} onClose={() => setCertSetupOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <p className="tc-muted">These signatory blocks are stored per AMO in this browser and applied to generated certificate PDFs.</p>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Signatory name</span><input className="tc-input" value={certificateSetup.signatory_name || ""} onChange={(e) => setCertificateSetup((prev) => ({ ...prev, signatory_name: e.target.value }))} /></label>
            <label className="tc-field"><span className="tc-field__label">Signatory title</span><input className="tc-input" value={certificateSetup.signatory_title || ""} onChange={(e) => setCertificateSetup((prev) => ({ ...prev, signatory_title: e.target.value }))} /></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Approver name</span><input className="tc-input" value={certificateSetup.approver_name || ""} onChange={(e) => setCertificateSetup((prev) => ({ ...prev, approver_name: e.target.value }))} /></label>
            <label className="tc-field"><span className="tc-field__label">Approver title</span><input className="tc-input" value={certificateSetup.approver_title || ""} onChange={(e) => setCertificateSetup((prev) => ({ ...prev, approver_title: e.target.value }))} /></label>
          </div>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setCertSetupOpen(false)}>Done</button>
          </div>
        </div>
      </Drawer>

      <Drawer title={editingRequirementId ? "Modify requirement rule" : "Create requirement rule"} isOpen={requirementFormOpen} onClose={() => setRequirementFormOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <label className="tc-field">
            <span className="tc-field__label">Course</span>
            <select className="tc-select" value={requirementForm.course_pk} onChange={(e) => setRequirementForm((prev) => ({ ...prev, course_pk: e.target.value }))}>
              <option value="">Select course</option>
              {courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}
            </select>
          </label>
          <label className="tc-field">
            <span className="tc-field__label">Scope</span>
            <select className="tc-select" value={requirementForm.scope} onChange={(e) => setRequirementForm((prev) => ({ ...prev, scope: e.target.value as TrainingRequirementScope, department_code: null, job_role: null, user_id: null }))}>
              <option value="ALL">All personnel</option>
              <option value="DEPARTMENT">Department</option>
              <option value="JOB_ROLE">Job role</option>
              <option value="USER">Specific user</option>
            </select>
          </label>
          {requirementForm.scope === "DEPARTMENT" ? (
            <label className="tc-field">
              <span className="tc-field__label">Department code</span>
              <input className="tc-input" list="training-known-departments" value={requirementForm.department_code || ""} onChange={(e) => setRequirementForm((prev) => ({ ...prev, department_code: e.target.value }))} placeholder="QUALITY / PLANNING / PRODUCTION" />
              <datalist id="training-known-departments">{knownDepartments.map((department) => <option key={department} value={department} />)}</datalist>
            </label>
          ) : null}
          {requirementForm.scope === "JOB_ROLE" ? (
            <label className="tc-field">
              <span className="tc-field__label">Job role</span>
              <input className="tc-input" list="training-known-roles" value={requirementForm.job_role || ""} onChange={(e) => setRequirementForm((prev) => ({ ...prev, job_role: e.target.value }))} placeholder="CERTIFYING TECHNICIAN" />
              <datalist id="training-known-roles">{knownRoles.map((role) => <option key={role} value={role} />)}</datalist>
            </label>
          ) : null}
          {requirementForm.scope === "USER" ? (
            <label className="tc-field">
              <span className="tc-field__label">User</span>
              <select className="tc-select" value={requirementForm.user_id || ""} onChange={(e) => setRequirementForm((prev) => ({ ...prev, user_id: e.target.value || null }))}>
                <option value="">Select user</option>
                {users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email} · {user.staff_code || "—"}</option>)}
              </select>
            </label>
          ) : null}
          <div className="tc-form-grid-2">
            <label className="tc-toggle"><input type="checkbox" checked={requirementForm.is_mandatory} onChange={(e) => setRequirementForm((prev) => ({ ...prev, is_mandatory: e.target.checked }))} /><span>Mandatory</span></label>
            <label className="tc-toggle"><input type="checkbox" checked={requirementForm.is_active} onChange={(e) => setRequirementForm((prev) => ({ ...prev, is_active: e.target.checked }))} /><span>Active</span></label>
          </div>
          <div className="tc-form-grid-2">
            <label className="tc-field"><span className="tc-field__label">Effective from</span><input className="tc-input" type="date" value={requirementForm.effective_from || ""} onChange={(e) => setRequirementForm((prev) => ({ ...prev, effective_from: e.target.value || null }))} /></label>
            <label className="tc-field"><span className="tc-field__label">Effective to</span><input className="tc-input" type="date" value={requirementForm.effective_to || ""} onChange={(e) => setRequirementForm((prev) => ({ ...prev, effective_to: e.target.value || null }))} /></label>
          </div>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setRequirementFormOpen(false)}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitRequirement} disabled={savingRequirement}>{savingRequirement ? "Saving…" : "Save rule"}</button>
          </div>
        </div>
      </Drawer>

      <Drawer title={editingCourseId ? "Modify course" : "Create course"} isOpen={courseFormOpen} onClose={() => setCourseFormOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <input className="tc-input" placeholder="Course ID" value={courseForm.course_id} onChange={(e) => setCourseForm((prev) => ({ ...prev, course_id: e.target.value }))} />
          <input className="tc-input" placeholder="Course name" value={courseForm.course_name} onChange={(e) => setCourseForm((prev) => ({ ...prev, course_name: e.target.value }))} />
          <input className="tc-input" placeholder="Frequency months (blank allowed)" value={courseForm.frequency_months} onChange={(e) => setCourseForm((prev) => ({ ...prev, frequency_months: e.target.value }))} />
          <select className="tc-select" value={courseForm.status} onChange={(e) => setCourseForm((prev) => ({ ...prev, status: e.target.value }))}>
            <option value="Initial">Initial</option>
            <option value="Recurrent">Recurrent</option>
            <option value="One_Off">One-off</option>
          </select>
          <input className="tc-input" placeholder="Category" value={courseForm.category_raw} onChange={(e) => setCourseForm((prev) => ({ ...prev, category_raw: e.target.value }))} />
          <input className="tc-input" placeholder="Scope / audience" value={courseForm.scope} onChange={(e) => setCourseForm((prev) => ({ ...prev, scope: e.target.value }))} />
          <input className="tc-input" placeholder="Regulatory reference" value={courseForm.regulatory_reference} onChange={(e) => setCourseForm((prev) => ({ ...prev, regulatory_reference: e.target.value }))} />
          <label className="tc-toggle"><input type="checkbox" checked={courseForm.is_mandatory} onChange={(e) => setCourseForm((prev) => ({ ...prev, is_mandatory: e.target.checked }))} /><span>Mandatory requirement</span></label>
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setCourseFormOpen(false)}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitCourse} disabled={savingCourse}>{savingCourse ? "Saving…" : "Save course"}</button>
          </div>
        </div>
      </Drawer>

      <Drawer title={importMode === "courses" ? "Import courses workbook" : "Import trainings workbook"} isOpen={importOpen} onClose={() => setImportOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <input type="file" accept=".xlsx,.xls" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
          <label className="tc-toggle"><input type="checkbox" checked={importDryRun} onChange={(e) => setImportDryRun(e.target.checked)} /><span>Dry run only</span></label>
          {importProgress ? <p className="tc-muted">Transferred {Math.round(importProgress.loadedBytes / 1024)} KB · {importProgress.percent ? `${Math.round(importProgress.percent)}%` : ""}</p> : null}
          <p className="tc-muted">{importMode === "courses" ? "Use the Courses sheet to create or update the course catalogue." : "Use the Training sheet to create or update individual training history records."}</p>
          {importSummary ? <pre className="tc-import-summary">{JSON.stringify(importSummary, null, 2)}</pre> : null}
          <div className="tc-inline-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setImportOpen(false)}>Close</button>
            <button type="button" className="secondary-chip-btn" onClick={runImport} disabled={importing}>{importing ? "Importing…" : "Run import"}</button>
          </div>
        </div>
      </Drawer>
    </QMSLayout>
  );
};

export default TrainingCompetencePage;

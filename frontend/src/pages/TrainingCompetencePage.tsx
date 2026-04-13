import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CalendarClock, Download, ExternalLink, FileSpreadsheet, RefreshCw, ScanLine, Search, Upload, Users } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import Drawer from "../components/shared/Drawer";
import { useToast } from "../components/feedback/ToastProvider";
import { getCachedUser } from "../services/auth";
import { listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";
import {
  createTrainingCourse,
  getBulkTrainingStatusForUsers,
  importTrainingCoursesWorkbook,
  importTrainingRecordsWorkbook,
  issueTrainingCertificate,
  listTrainingCertificates,
  listTrainingCourses,
  listTrainingDeferrals,
  listTrainingEventParticipants,
  listTrainingEvents,
  listTrainingRecords,
  listTrainingRequirements,
  type TransferProgress,
  updateTrainingCourse,
  updateTrainingEventParticipant,
} from "../services/training";
import type {
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventParticipantRead,
  TrainingEventRead,
  TrainingRecordRead,
  TrainingRequirementRead,
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

function statusClass(status: string): string {
  if (status === "OVERDUE") return "overdue";
  if (status === "DUE_SOON") return "due-soon";
  if (status === "DEFERRED") return "deferred";
  if (status === "NOT_DONE") return "not-done";
  return "ok";
}

function statusLabel(status: string): string {
  switch (status) {
    case "OVERDUE":
      return "Overdue";
    case "DUE_SOON":
      return "Due soon";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled";
    case "NOT_DONE":
      return "No completion";
    default:
      return "Compliant";
  }
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
  const courseById = new Map(courses.map((course) => [course.id, course]));
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
    completedByUser.get(record.user_id)!.add(record.course_id);
  });

  const userById = new Map(users.map((user) => [user.id, user]));
  const anomalies: RefresherAnomaly[] = [];
  const seen = new Set<string>();

  records.forEach((record) => {
    const course = courseById.get(record.course_id);
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
      prerequisiteNames: [...prerequisites].map((id) => courseById.get(id)?.course_name || courseById.get(id)?.course_id || id),
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
  const [deferrals, setDeferrals] = useState<TrainingDeferralRequestRead[]>([]);
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
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<"courses" | "trainings">("courses");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDryRun, setImportDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<TransferProgress | null>(null);
  const [importSummary, setImportSummary] = useState<any | null>(null);
  const loadSeq = useRef(0);
  const anomalyToastKey = useRef<string>("");
  const { pushToast } = useToast();
  const currentUser = getCachedUser();
  const canManageCourses = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER");

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
    setLoading(true);
    setError(null);

    const settled = await Promise.allSettled([
      listAdminUserSummaries({ limit: 250 }),
      listTrainingCourses({ include_inactive: true }),
      listTrainingRequirements({ include_inactive: true }),
      listTrainingEvents(),
      listTrainingRecords(),
      listTrainingCertificates(),
      listTrainingDeferrals({ limit: 200 }),
    ]);

    if (requestId !== loadSeq.current) return;

    const [usersRes, coursesRes, requirementsRes, eventsRes, recordsRes, certificatesRes, deferralsRes] = settled;
    const failures: string[] = [];

    const nextUsers = usersRes.status === "fulfilled" ? usersRes.value : [];
    if (usersRes.status !== "fulfilled") failures.push("users");
    const nextCourses = coursesRes.status === "fulfilled" ? coursesRes.value : [];
    if (coursesRes.status !== "fulfilled") failures.push("courses");
    const nextRequirements = requirementsRes.status === "fulfilled" ? requirementsRes.value : [];
    if (requirementsRes.status !== "fulfilled") failures.push("requirements");
    const nextEvents = eventsRes.status === "fulfilled" ? eventsRes.value : [];
    if (eventsRes.status !== "fulfilled") failures.push("events");
    const nextRecords = recordsRes.status === "fulfilled" ? recordsRes.value : [];
    if (recordsRes.status !== "fulfilled") failures.push("records");
    const nextCertificates = certificatesRes.status === "fulfilled" ? certificatesRes.value : [];
    if (certificatesRes.status !== "fulfilled") failures.push("certificates");
    const nextDeferrals = deferralsRes.status === "fulfilled" ? deferralsRes.value : [];
    if (deferralsRes.status !== "fulfilled") failures.push("deferrals");

    let nextStatusByUser: Record<string, TrainingStatusItem[]> = {};
    if (nextUsers.length > 0) {
      try {
        const response = await getBulkTrainingStatusForUsers(nextUsers.map((user) => user.id));
        if (requestId !== loadSeq.current) return;
        nextStatusByUser = response.users || {};
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
    setDeferrals(nextDeferrals);
    setStatusByUser(nextStatusByUser);
    setError(failures.length ? `Some datasets could not be loaded: ${failures.join(", ")}.` : null);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses]);
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

  const kpis = useMemo(() => {
    const allItems = Object.values(statusByUser).flat();
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
      const course = courseById.get(record.course_id);
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

  const openPerson = (userId: string, options?: { filter?: string; tab?: string }) => {
    const qs = new URLSearchParams();
    if (options?.filter) qs.set("filter", options.filter);
    if (options?.tab) qs.set("tab", options.tab);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    navigate(`/maintenance/${amoCode || "UNKNOWN"}/${department || "quality"}/qms/training/${userId}${suffix}`);
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
            <div className="tc-kpi-card"><span>Overdue</span><strong>{animatedOverdue}</strong></div>
            <div className="tc-kpi-card"><span>Due soon</span><strong>{animatedDueSoon}</strong></div>
            <div className="tc-kpi-card"><span>Requirement rules</span><strong>{animatedRequirements}</strong></div>
            <div className="tc-kpi-card"><span>Course catalogue</span><strong>{animatedCourses}</strong></div>
            <div className="tc-kpi-card"><span>Certificates</span><strong>{animatedCertificates}</strong></div>
            <div className="tc-kpi-card tc-kpi-card--warning"><span>Rectify data</span><strong>{animatedAnomalies}</strong></div>
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
                          <button type="button" className="tc-link-button" onClick={() => openPerson(row.user.id)}>{row.user.full_name || row.user.email}</button>
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
                          <td><button type="button" className="tc-link-button" onClick={() => openPerson(item.userId)}>{item.userName}</button></td>
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
                      const course = courseById.get(event.course_id);
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

            <div className="tc-table-wrap">
              <table className="tc-table tc-table--personnel">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Outstanding</th>
                    <th>Overdue</th>
                    <th>Due soon</th>
                    <th>Deferrals</th>
                    <th>Records</th>
                    <th>Certificates</th>
                    <th>Next due</th>
                    <th>Rectify</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPeople.length === 0 ? (
                    <tr><td colSpan={10}><p className="tc-empty">No personnel match the current training filters.</p></td></tr>
                  ) : filteredPeople.map((row) => (
                    <tr key={row.user.id} className={row.anomalyCount > 0 ? "is-flagged" : undefined}>
                      <td>
                        <button type="button" className="tc-link-button" onClick={() => openPerson(row.user.id)}>{row.user.full_name || row.user.email}</button>
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
                      <td>{row.anomalyCount > 0 ? <span className="tc-status-pill overdue">{row.anomalyCount}</span> : "—"}</td>
                    </tr>
                  ))}
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
                    </tr>
                  </thead>
                  <tbody>
                    {requirementRows.length === 0 ? (
                      <tr><td colSpan={7}><p className="tc-empty">No requirement rules were returned from the server.</p></td></tr>
                    ) : requirementRows.map((row) => (
                      <tr key={row.id}>
                        <td>{row.course?.course_id || row.course_pk} · {row.course?.course_name || "Unknown course"}</td>
                        <td>{row.scope}</td>
                        <td>{row.department_code || "—"}</td>
                        <td>{row.job_role || "—"}</td>
                        <td>{row.is_mandatory ? "Yes" : "No"}</td>
                        <td>{row.is_active ? "Active" : "Inactive"}</td>
                        <td>{row.effective_from || row.effective_to ? `${compactDate(row.effective_from)} → ${compactDate(row.effective_to)}` : "Always on"}</td>
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
                <p className="tc-muted">Use one page for sessions and roster status. Pick a session to inspect participants and close attendance.</p>
              </div>
            </div>
            <div className="tc-filterbar">
              <label className="tc-field tc-field--grow">
                <span className="tc-field__label">Session</span>
                <select className="tc-select" value={selectedEventId} onChange={(e) => setSelectedEventId(e.target.value)}>
                  <option value="">Select a session</option>
                  {events.map((event) => {
                    const course = courseById.get(event.course_id);
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
                    <th>Starts</th>
                    <th>Ends</th>
                    <th>Status</th>
                    <th>Location</th>
                    <th>Provider</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr><td colSpan={7}><p className="tc-empty">No scheduled sessions.</p></td></tr>
                  ) : events.map((event) => {
                    const course = courseById.get(event.course_id);
                    return (
                      <tr key={event.id} className={selectedEventId === event.id ? "is-selected" : undefined}>
                        <td>{course?.course_id || "—"} · {course?.course_name || "Unknown course"}</td>
                        <td>{event.title}</td>
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
                    <p className="tc-muted">Update attendance from here. This replaces the older duplicate attendance page.</p>
                  </div>
                </div>
                <div className="tc-table-wrap">
                  <table className="tc-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Status</th>
                        <th>Note</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentEventParticipants.length === 0 ? (
                        <tr><td colSpan={4}><p className="tc-empty">No participants were returned for this session.</p></td></tr>
                      ) : currentEventParticipants.map((participant) => (
                        <tr key={participant.id}>
                          <td>{participant.user_id}</td>
                          <td>{participant.status}</td>
                          <td>{participant.attendance_note || "—"}</td>
                          <td>
                            <button
                              type="button"
                              className="secondary-chip-btn"
                              onClick={async () => {
                                await updateTrainingEventParticipant(participant.id, { status: "ATTENDED" });
                                setParticipants((prev) => prev.map((row) => row.id === participant.id ? { ...row, status: "ATTENDED" } : row));
                              }}
                            >
                              Mark attended
                            </button>
                          </td>
                        </tr>
                      ))}
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
                <p className="tc-muted">Issue or verify certificate evidence against the individual record.</p>
              </div>
            </div>
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Course</th>
                    <th>Completed</th>
                    <th>Certificate</th>
                    <th>Verification</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {certificateRows.length === 0 ? (
                    <tr><td colSpan={6}><p className="tc-empty">No certificate records found.</p></td></tr>
                  ) : certificateRows.map((record) => {
                    const course = courseById.get(record.course_id);
                    const user = users.find((entry) => entry.id === record.user_id);
                    return (
                      <tr key={record.id}>
                        <td><button type="button" className="tc-link-button" onClick={() => openPerson(record.user_id)}>{user?.full_name || record.user_id}</button></td>
                        <td>{course?.course_id || "—"} · {course?.course_name || "Unknown course"}</td>
                        <td>{compactDate(record.completion_date)}</td>
                        <td>{record.certificate_reference || "Not issued"}</td>
                        <td>{record.verification_status || "—"}</td>
                        <td>
                          <div className="tc-inline-actions">
                            {!record.certificate_reference ? (
                              <button type="button" className="secondary-chip-btn" onClick={async () => { await issueTrainingCertificate(record.id); await load(); }}>Issue</button>
                            ) : (
                              <>
                                <button type="button" className="secondary-chip-btn" onClick={() => window.open(`/verify/certificate/${record.certificate_reference}`, "_blank")}><ExternalLink size={14} /></button>
                                <button type="button" className="secondary-chip-btn" onClick={() => window.open("/verify/scan", "_blank")}><ScanLine size={14} /></button>
                              </>
                            )}
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

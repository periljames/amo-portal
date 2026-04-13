import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import type { AdminUserRead } from "../services/adminUsers";
import { getAdminUser, getAdminUserWorkspace } from "../services/adminUsers";
import { getCachedUser, getContext, type PortalUser } from "../services/auth";
import {
  createTrainingDeferralRequest,
  createTrainingRecord,
  downloadTrainingUserEvidencePack,
  downloadTrainingUserRecordPdf,
  getMyTrainingStatus,
  getUserTrainingStatus,
  listMyTrainingDeferrals,
  listTrainingCourses,
  listTrainingDeferrals,
  listTrainingEvents,
  listTrainingFiles,
  listTrainingRecords,
  updateTrainingDeferralRequest,
  uploadTrainingFile,
  warmTrainingUserRecordPdf,
} from "../services/training";
import type {
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventRead,
  TrainingFileRead,
  TrainingRecordRead,
  TrainingStatusItem,
} from "../types/training";
import "../styles/training.css";

type LoadState = "idle" | "loading" | "ready" | "error";
type SortKey = "course" | "completion_date" | "valid_until" | "hours" | "score" | "certificate";
type SortDirection = "asc" | "desc";
type PanelKey = "compliance" | "schedule" | "deferrals" | "newRecord";
type ViewMode = "completed" | "missing";

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
    amo_id: user.amo_id,
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

function cleanRoleTitle(user: AdminUserRead | null): string {
  const preferred = user?.position_title?.trim() || user?.role?.trim() || "";
  if (!preferred) return "-";
  return preferred.replace(/^TECHNICIAN\s*[-·]\s*/i, "").replace(/\s+/g, " ").trim();
}

function dueDateForItem(item: TrainingStatusItem | null | undefined): string | null {
  if (!item) return null;
  return item.extended_due_date || item.valid_until || null;
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
      return "Not done";
    case "OK":
    default:
      return "Current";
  }
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
  if (item.status === "OVERDUE") return "Overdue";
  if (item.status === "OK") return "Current";
  if (item.status === "NOT_DONE") return "Not done";
  if (item.status === "DEFERRED") {
    const due = dueDateForItem(item);
    return due ? `Deferred to ${formatDate(due)}` : "Deferred";
  }
  const due = dueDateForItem(item);
  if (!due) return "-";
  const timeLeft = timeLeftFromDueDate(due);
  if (timeLeft === "-") return formatDate(due);
  return `Due in (${timeLeft})`;
}

function displayRecordLifecycleStatus(record: TrainingRecordRead | null | undefined): string | null {
  const raw = (record?.record_status || record?.source_status || "").trim().toUpperCase().replace(/\s+/g, "_");
  if (!raw) return null;
  if (raw === "SUPERSEDED") return "RENEWED";
  return raw;
}

function isHistoricalTrainingRecord(record: TrainingRecordRead | null | undefined): boolean {
  const status = displayRecordLifecycleStatus(record);
  return status === "RENEWED";
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(url);
}

function initialPanelState(searchParams: URLSearchParams, canEdit: boolean): Record<PanelKey, boolean> {
  const tab = searchParams.get("tab");
  return {
    compliance: true,
    schedule: tab === "schedule",
    deferrals: tab === "deferrals",
    newRecord: canEdit && tab === "new-record",
  };
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
  const canEdit = Boolean(cachedUser?.is_superuser || cachedUser?.is_amo_admin || cachedUser?.role === "QUALITY_MANAGER");

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
  const [panelOpen, setPanelOpen] = useState<Record<PanelKey, boolean>>(() => initialPanelState(searchParams, canEdit));
  const [viewMode, setViewMode] = useState<ViewMode>(searchParams.get("filter") === "NOT_DONE" ? "missing" : "completed");
  const [sortKey, setSortKey] = useState<SortKey>("completion_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [exportingEvidence, setExportingEvidence] = useState(false);
  const [exportingRecord, setExportingRecord] = useState(false);
  const [warmingRecordPdf, setWarmingRecordPdf] = useState(false);
  const [pdfReady, setPdfReady] = useState(false);

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
      canEdit ? getAdminUser(userId) : Promise.reject(new Error("admin-read-disabled")),
      canEdit ? getAdminUserWorkspace(userId) : Promise.reject(new Error("workspace-read-disabled")),
      listTrainingCourses({ include_inactive: true }),
      isOwnProfile && !canEdit ? getMyTrainingStatus() : getUserTrainingStatus(userId),
      listTrainingRecords({ user_id: userId }),
      isOwnProfile && !canEdit ? listMyTrainingDeferrals() : listTrainingDeferrals({ user_id: userId, limit: 200 }),
      listTrainingEvents(),
      listTrainingFiles({ owner_user_id: userId }),
    ]);

    const [userResult, workspaceResult, courseResult, statusResult, recordResult, deferralResult, eventResult, fileResult] = result;

    const resolvedUser =
      userResult.status === "fulfilled"
        ? userResult.value
        : isOwnProfile && cachedUser
          ? portalUserToAdminUser(cachedUser)
          : null;

    if (!resolvedUser) {
      const userError = userResult.status === "rejected" ? userResult.reason?.message || "Failed to load user profile." : "Failed to load user profile.";
      setError(userError);
      setState("error");
      return;
    }

    setUser(resolvedUser);
    setHireDate(workspaceResult.status === "fulfilled" ? workspaceResult.value.profile?.hire_date || null : null);
    setCourses(courseResult.status === "fulfilled" ? courseResult.value : []);
    setItems(statusResult.status === "fulfilled" ? statusResult.value : []);
    setRecords(recordResult.status === "fulfilled" ? recordResult.value : []);
    setDeferrals(deferralResult.status === "fulfilled" ? deferralResult.value : []);
    setEvents(eventResult.status === "fulfilled" ? eventResult.value : []);
    setFiles(fileResult.status === "fulfilled" ? fileResult.value : []);

    const errors: string[] = [];
    [courseResult, statusResult, recordResult, deferralResult, eventResult, fileResult].forEach((entry) => {
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
    if (!userId || state !== "ready") return;
    let cancelled = false;
    setWarmingRecordPdf(true);
    void warmTrainingUserRecordPdf(userId)
      .then((response) => {
        if (!cancelled) {
          setPdfReady(Boolean(response.ready));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPdfReady(false);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setWarmingRecordPdf(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [state, userId]);

  const handleExportEvidence = async () => {
    if (!userId) return;
    setExportingEvidence(true);
    try {
      const blob = await downloadTrainingUserEvidencePack(userId);
      const safeName = (user?.full_name || userId).replace(/\s+/g, "_");
      downloadBlob(blob, `${safeName}_training_evidence_pack.zip`);
    } catch (e: any) {
      setError(e?.message || "Failed to export training evidence pack.");
    } finally {
      setExportingEvidence(false);
    }
  };

  const handleExportRecord = async () => {
    if (!userId) return;
    setExportingRecord(true);
    try {
      const blob = await downloadTrainingUserRecordPdf(userId);
      const safeName = (user?.full_name || userId).replace(/\s+/g, "_");
      downloadBlob(blob, `${safeName}_training_record.pdf`);
      setPdfReady(true);
    } catch (e: any) {
      setError(e?.message || "Failed to export individual training record.");
    } finally {
      setExportingRecord(false);
    }
  };

  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses]);

  const itemByCoursePk = useMemo(() => {
    const map = new Map<string, TrainingStatusItem>();
    items.forEach((item) => {
      const match = courses.find((course) => course.course_id === item.course_id || course.course_name === item.course_name);
      if (match) map.set(match.id, item);
    });
    return map;
  }, [courses, items]);

  useEffect(() => {
    if (!deferralForm.coursePk && items.length > 0) {
      const target = items.find((item) => item.status === "OVERDUE" || item.status === "DUE_SOON" || item.status === "NOT_DONE") || items[0];
      const match = courses.find((course) => course.course_id === target.course_id || course.course_name === target.course_name);
      if (match) {
        setDeferralForm((prev) => ({ ...prev, coursePk: match.id }));
      }
    }
    if (!recordForm.coursePk && courses.length > 0) {
      setRecordForm((prev) => ({ ...prev, coursePk: prev.coursePk || courses[0].id }));
    }
  }, [courses, deferralForm.coursePk, items, recordForm.coursePk]);

  const selectedCourse = useMemo(() => courseById.get(recordForm.coursePk) || null, [courseById, recordForm.coursePk]);
  const selectedCourseStatus = useMemo(() => itemByCoursePk.get(recordForm.coursePk) || null, [itemByCoursePk, recordForm.coursePk]);
  const derivedValidUntil = useMemo(() => addMonthsIso(recordForm.completionDate, selectedCourse?.frequency_months), [recordForm.completionDate, selectedCourse?.frequency_months]);
  const derivedHours = selectedCourse?.nominal_hours ?? null;

  const sortedRecords = useMemo(() => {
    const rows = records.slice().sort((a, b) => {
      const leftCourse = courseById.get(a.course_id);
      const rightCourse = courseById.get(b.course_id);
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
  }, [courseById, records, sortDirection, sortKey]);

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
      { overdue: 0, dueSoon: 0, ok: 0, deferred: 0, scheduled: 0, notDone: 0 },
    );
  }, [items]);

  const compliance = useMemo(() => {
    const total = items.length;
    if (total === 0) return 0;
    return Math.round(((summary.ok || 0) / total) * 100);
  }, [items.length, summary.ok]);

  const nextDue = useMemo(() => {
    const withDue = items
      .filter((item) => Boolean(dueDateForItem(item)))
      .slice()
      .sort((a, b) => String(dueDateForItem(a) || "").localeCompare(String(dueDateForItem(b) || "")));
    return withDue[0] || null;
  }, [items]);

  const relevantCourseIds = useMemo(() => {
    const ids = new Set<string>();
    sortedRecords.forEach((record) => ids.add(record.course_id));
    itemByCoursePk.forEach((_item, coursePk) => ids.add(coursePk));
    return ids;
  }, [itemByCoursePk, sortedRecords]);

  const relevantEvents = useMemo(() => {
    return events
      .filter((event) => relevantCourseIds.has(event.course_id))
      .slice()
      .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)));
  }, [events, relevantCourseIds]);

  const visibleCompletedRows = useMemo(() => {
    return sortedRecords.filter((record) => !isHistoricalTrainingRecord(record));
  }, [sortedRecords]);

  const filteredCompletedRows = useMemo(() => {
    return visibleCompletedRows.filter((record) => {
      const item = itemByCoursePk.get(record.course_id);
      if (statusFilter === "ALL") return true;
      return item?.status === statusFilter;
    });
  }, [itemByCoursePk, statusFilter, visibleCompletedRows]);

  const filteredMissingRows = useMemo(() => {
    const base = items.filter((item) => item.status === "NOT_DONE");
    if (statusFilter === "ALL" || statusFilter === "NOT_DONE") return base;
    return base.filter((item) => item.status === statusFilter);
  }, [items, statusFilter]);

  const recentFiles = useMemo(
    () => files.slice().sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || ""))).slice(0, 12),
    [files],
  );

  const submitRecord = async () => {
    if (!recordForm.coursePk || !userId) {
      setError("Select a course before saving a training record.");
      return;
    }
    if (recordForm.certificateReference.trim() && !recordAttachment) {
      setError("Attach the certificate file before saving a certificate reference.");
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
        const uploaded = await uploadTrainingFile(payload);
        attachmentFileId = uploaded.id;
      }

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
      });
      await load();
      setRecordForm((prev) => ({
        ...prev,
        completionDate: new Date().toISOString().slice(0, 10),
        examScore: "",
        certificateReference: "",
        remarks: "",
      }));
      setRecordAttachment(null);
      setRecordAttachmentKind("EVIDENCE");
      setPanelOpen((prev) => ({ ...prev, newRecord: false }));
      setViewMode("completed");
      setStatusFilter("ALL");
    } catch (e: any) {
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

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection(key === "completion_date" ? "desc" : "asc");
  };

  const togglePanel = (key: PanelKey) => {
    setPanelOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const summaryCards = [
    { key: "overdue", label: "Overdue", value: summary.overdue, pill: "qms-pill qms-pill--danger", helper: "Immediate action needed." },
    { key: "dueSoon", label: "Due soon", value: summary.dueSoon, pill: "qms-pill qms-pill--warning", helper: "Track days, then hours on the final day." },
    { key: "current", label: "Current", value: summary.ok, pill: "qms-pill qms-pill--success", helper: "Accepted as current and in date." },
    { key: "deferred", label: "Deferred", value: summary.deferred, pill: "qms-pill qms-pill--info", helper: "Extension already on record." },
    { key: "scheduled", label: "Scheduled", value: summary.scheduled, pill: "qms-pill", helper: "Upcoming session already linked." },
    { key: "notDone", label: "Not done", value: summary.notDone, pill: "qms-pill", helper: "No completion captured yet." },
  ];

  const panelStats = {
    schedule: relevantEvents.length,
    deferrals: deferrals.length,
    newRecord: recentFiles.length,
  };

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Training Profile"
      subtitle="Individual training record, due status, deferrals and evidence"
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="primary-chip-btn" onClick={() => void load()}>
            Refresh profile
          </button>
          <button type="button" className="secondary-chip-btn" onClick={handleExportRecord} disabled={exportingRecord || !userId}>
            {exportingRecord ? "Downloading PDF..." : warmingRecordPdf && !pdfReady ? "Staging PDF..." : "Download training record"}
          </button>
          <button type="button" className="secondary-chip-btn" onClick={handleExportEvidence} disabled={exportingEvidence || !userId}>
            {exportingEvidence ? "Exporting..." : "Export evidence pack"}
          </button>
        </div>
      }
    >
      <div className="training-module training-module--qms training-profile-page">
        <section className="training-profile-toolbar">
          <label className="qms-field training-profile-toolbar__field">
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="ALL">All statuses</option>
              <option value="OK">Current</option>
              <option value="DUE_SOON">Due soon</option>
              <option value="OVERDUE">Overdue</option>
              <option value="DEFERRED">Deferred</option>
              <option value="SCHEDULED_ONLY">Scheduled</option>
              <option value="NOT_DONE">Not done</option>
            </select>
          </label>
          <div className="training-profile-toolbar__actions">
            <button
              type="button"
              className={viewMode === "completed" ? "primary-chip-btn" : "secondary-chip-btn"}
              onClick={() => {
                setViewMode("completed");
                if (statusFilter === "NOT_DONE") setStatusFilter("ALL");
              }}
            >
              Completed log
            </button>
            <button
              type="button"
              className={viewMode === "missing" ? "primary-chip-btn" : "secondary-chip-btn"}
              onClick={() => {
                setViewMode("missing");
                setStatusFilter("NOT_DONE");
              }}
            >
              Missing courses
            </button>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
              Back to training handler
            </button>
          </div>
        </section>

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
            <div className="qms-card qms-card--hero training-profile-hero">
              <div className="qms-card__header training-profile-hero__header">
                <div>
                  <p className="qms-card__eyebrow">Personnel record</p>
                  <h3 className="qms-card__title">{user.full_name || "Training profile"}</h3>
                </div>
                <span className="qms-pill qms-pill--info">Compliance {compliance}%</span>
              </div>

              <div className="training-profile-hero__meta">
                <div className="training-profile-hero__meta-card">
                  <span className="training-profile-hero__label">Role</span>
                  <strong>{cleanRoleTitle(user)}</strong>
                </div>
                <div className="training-profile-hero__meta-card">
                  <span className="training-profile-hero__label">Staff code</span>
                  <strong>{user.staff_code || "-"}</strong>
                </div>
                <div className="training-profile-hero__meta-card">
                  <span className="training-profile-hero__label">Date hired</span>
                  <strong>{formatDate(hireDate)}</strong>
                </div>
                <div className="training-profile-hero__meta-card">
                  <span className="training-profile-hero__label">Profile status</span>
                  <strong>{user.is_active ? "Active" : "Inactive"}</strong>
                </div>
              </div>
            </div>

            <div className="training-profile-toolbar training-profile-toolbar--surface">
              <div className="training-profile-toolbar__group">
                <label className="qms-field training-profile-toolbar__field">
                  <span>Status</span>
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                    <option value="ALL">All statuses</option>
                    <option value="OK">Current</option>
                    <option value="DUE_SOON">Due soon</option>
                    <option value="OVERDUE">Overdue</option>
                    <option value="DEFERRED">Deferred</option>
                    <option value="SCHEDULED_ONLY">Scheduled</option>
                    <option value="NOT_DONE">Not done</option>
                  </select>
                </label>
                <div className="training-profile-toolbar__actions">
                  <button
                    type="button"
                    className={viewMode === "completed" ? "primary-chip-btn" : "secondary-chip-btn"}
                    onClick={() => {
                      setViewMode("completed");
                      if (statusFilter === "NOT_DONE") setStatusFilter("ALL");
                    }}
                  >
                    Completed log
                  </button>
                  <button
                    type="button"
                    className={viewMode === "missing" ? "primary-chip-btn" : "secondary-chip-btn"}
                    onClick={() => {
                      setViewMode("missing");
                      setStatusFilter("NOT_DONE");
                    }}
                  >
                    Missing courses
                  </button>
                </div>
              </div>
              <div className="training-profile-toolbar__actions">
                <button type="button" className="secondary-chip-btn" onClick={() => togglePanel("schedule")}>
                  {panelOpen.schedule ? "Hide schedule" : "Show schedule"}
                </button>
                <button type="button" className="secondary-chip-btn" onClick={() => togglePanel("deferrals")}>
                  {panelOpen.deferrals ? "Hide deferrals" : "Show deferrals"}
                </button>
                {canEdit ? (
                  <button type="button" className="secondary-chip-btn" onClick={() => togglePanel("newRecord")}>
                    {panelOpen.newRecord ? "Hide new record" : "Show new record"}
                  </button>
                ) : null}
                <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
                  Back to training handler
                </button>
              </div>
            </div>

            <div className="training-profile-layout">
              <aside className="training-profile-sidebar">
                <div className="qms-card training-profile-sidecard training-profile-collapse-card qms-card--attention">
                  <button type="button" className="training-collapse-toggle" onClick={() => togglePanel("compliance")}>
                    <div>
                      <span className="training-collapse-toggle__eyebrow">Compliance posture</span>
                      <strong>Keep the control summary together</strong>
                    </div>
                    <span className="training-collapse-toggle__meta">{panelOpen.compliance ? "Hide" : "Show"}</span>
                  </button>
                  {panelOpen.compliance ? (
                    <div className="training-collapse-panel">
                      <div className="training-profile-summary-grid">
                        {summaryCards.map((card) => (
                          <div key={card.key} className="training-profile-summary-tile">
                            <span className={card.pill}>{card.label}: {card.value}</span>
                            <p className="text-muted">{card.helper}</p>
                          </div>
                        ))}
                      </div>
                      <div className="qms-list">
                        <div className="qms-list__item">
                          <div>
                            <strong>Next due</strong>
                            <span className="qms-list__meta">{nextDue ? `${nextDue.course_name} · ${dueLabel(nextDue)}` : "No due dates available"}</span>
                          </div>
                          <span className={`qms-pill ${nextDue ? statusPillClass(nextDue.status) : ""}`.trim()}>{nextDue ? dueCountdownLabel(nextDue) : "-"}</span>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="qms-card training-profile-sidecard">
                  <div className="qms-card__header">
                    <div>
                      <h3 className="qms-card__title">Quick sections</h3>
                      <p className="qms-card__subtitle">Open only what you need and keep the page short.</p>
                    </div>
                  </div>
                  <div className="training-quick-links">
                    <button type="button" className={`training-quick-link ${panelOpen.schedule ? "is-active" : ""}`} onClick={() => togglePanel("schedule")}>
                      <span>Schedule</span>
                      <strong>{panelStats.schedule}</strong>
                    </button>
                    <button type="button" className={`training-quick-link ${panelOpen.deferrals ? "is-active" : ""}`} onClick={() => togglePanel("deferrals")}>
                      <span>Deferrals</span>
                      <strong>{panelStats.deferrals}</strong>
                    </button>
                    {canEdit ? (
                      <button type="button" className={`training-quick-link ${panelOpen.newRecord ? "is-active" : ""}`} onClick={() => togglePanel("newRecord")}>
                        <span>New record</span>
                        <strong>{panelStats.newRecord}</strong>
                      </button>
                    ) : null}
                  </div>
                </div>
              </aside>

              <div className="training-profile-main">
                <div className="qms-card training-profile-logcard training-profile-section-card">
                  <div className="qms-card__header">
                    <div>
                      <h3 className="qms-card__title">{viewMode === "completed" ? "Training record log" : "Missing course view"}</h3>
                      <p className="qms-card__subtitle">
                        {viewMode === "completed"
                          ? "Completed records and current due status are shown together here. This is the main working view for the individual profile."
                          : "This view isolates courses that still have no captured completion for this person."}
                      </p>
                    </div>
                    {viewMode === "completed" ? (
                      <button type="button" className="secondary-chip-btn" onClick={handleExportRecord} disabled={exportingRecord || !userId}>
                        {exportingRecord ? "Preparing PDF..." : "Export PDF"}
                      </button>
                    ) : null}
                  </div>
                  <div className="table-responsive training-table-wrap">
                    {viewMode === "completed" ? (
                      <table className="table table-striped table-compact training-history-table training-history-table--banded training-history-table--responsive">
                        <thead>
                          <tr>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("course")}>Course</button></th>
                            <th>Status</th>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("completion_date")}>Completed</button></th>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("valid_until")}>Next due</button></th>
                            <th>Time left</th>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("hours")}>Hours</button></th>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("score")}>Score</button></th>
                            <th><button type="button" className="training-sort-button" onClick={() => toggleSort("certificate")}>Certificate</button></th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredCompletedRows.map((record) => {
                            const course = courseById.get(record.course_id);
                            const item = itemByCoursePk.get(record.course_id);
                            return (
                              <tr key={record.id}>
                                <td>
                                  <strong>{course?.course_name || record.course_name || record.course_id}</strong>
                                  <div className="text-muted">{course?.course_id || record.course_code || record.course_id}</div>
                                </td>
                                <td><span className={statusPillClass(item?.status || "OK")}>{statusLabel(item?.status || "OK")}</span></td>
                                <td>{formatDate(record.completion_date)}</td>
                                <td>{item ? dueLabel(item) : formatDate(record.valid_until)}</td>
                                <td>{item ? timeLeftFromDueDate(dueDateForItem(item)) : timeLeftFromDueDate(record.valid_until)}</td>
                                <td>{record.hours_completed ?? "-"}</td>
                                <td>{record.exam_score ?? "-"}</td>
                                <td>{record.certificate_reference || "-"}</td>
                              </tr>
                            );
                          })}
                          {filteredCompletedRows.length === 0 && (
                            <tr>
                              <td colSpan={8} className="text-muted">No completed training rows match the selected status filter.</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    ) : (
                      <table className="table table-striped table-compact training-history-table training-history-table--banded training-history-table--responsive">
                        <thead>
                          <tr>
                            <th>Course</th>
                            <th>Status</th>
                            <th>Last done</th>
                            <th>Due</th>
                            <th>Next event</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredMissingRows.map((item) => {
                            const course = courses.find((entry) => entry.course_id === item.course_id || entry.course_name === item.course_name);
                            return (
                              <tr key={item.course_id}>
                                <td>
                                  <strong>{item.course_name}</strong>
                                  <div className="text-muted">{item.course_id}</div>
                                </td>
                                <td><span className={statusPillClass(item.status)}>{statusLabel(item.status)}</span></td>
                                <td>{formatDate(item.last_completion_date)}</td>
                                <td>{dueLabel(item)}</td>
                                <td>{item.upcoming_event_date ? formatDate(item.upcoming_event_date) : "-"}</td>
                                <td>
                                  {canEdit && course ? (
                                    <button
                                      type="button"
                                      className="secondary-chip-btn"
                                      onClick={() => {
                                        setRecordForm((prev) => ({ ...prev, coursePk: course.id }));
                                        setPanelOpen((prev) => ({ ...prev, newRecord: true }));
                                      }}
                                    >
                                      Add record
                                    </button>
                                  ) : "-"}
                                </td>
                              </tr>
                            );
                          })}
                          {filteredMissingRows.length === 0 && (
                            <tr>
                              <td colSpan={6} className="text-muted">No missing course rows match the selected filter.</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>

                <section className="qms-card training-profile-section-card training-profile-collapse-card">
                  <button type="button" className="training-collapse-toggle" onClick={() => togglePanel("schedule")} aria-expanded={panelOpen.schedule}>
                    <div>
                      <span className="training-collapse-toggle__eyebrow">Sessions and linked events</span>
                      <strong>Schedule</strong>
                    </div>
                    <span className="training-collapse-toggle__meta">{panelOpen.schedule ? "Hide" : "Show"} · {panelStats.schedule}</span>
                  </button>
                  {panelOpen.schedule ? (
                    <div className="training-collapse-panel">
                      <div className="table-responsive training-table-wrap">
                        <table className="table training-history-table--responsive">
                          <thead>
                            <tr>
                              <th>Course</th>
                              <th>Session</th>
                              <th>Starts</th>
                              <th>Status</th>
                              <th>Location</th>
                            </tr>
                          </thead>
                          <tbody>
                            {relevantEvents.map((event) => {
                              const course = courseById.get(event.course_id);
                              return (
                                <tr key={event.id}>
                                  <td>{course?.course_name || event.course_id}</td>
                                  <td>{event.title}</td>
                                  <td>{formatDate(event.starts_on)}</td>
                                  <td><span className={statusPillClass(event.status)}>{event.status.replaceAll("_", " ")}</span></td>
                                  <td>{event.location || "-"}</td>
                                </tr>
                              );
                            })}
                            {relevantEvents.length === 0 && (
                              <tr>
                                <td colSpan={5} className="text-muted">No relevant training sessions are scheduled for this profile.</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className="qms-card training-profile-section-card training-profile-collapse-card">
                  <button type="button" className="training-collapse-toggle" onClick={() => togglePanel("deferrals")} aria-expanded={panelOpen.deferrals}>
                    <div>
                      <span className="training-collapse-toggle__eyebrow">Extensions and due-date changes</span>
                      <strong>Deferrals</strong>
                    </div>
                    <span className="training-collapse-toggle__meta">{panelOpen.deferrals ? "Hide" : "Show"} · {panelStats.deferrals}</span>
                  </button>
                  {panelOpen.deferrals ? (
                    <div className="training-collapse-panel training-profile-stack">
                      <div className="table-responsive training-table-wrap">
                        <table className="table training-history-table--responsive">
                          <thead>
                            <tr>
                              <th>Course</th>
                              <th>Original due</th>
                              <th>Requested due</th>
                              <th>Status</th>
                              <th>Reason</th>
                              <th>Requested</th>
                              {canEdit ? <th>Decision</th> : null}
                            </tr>
                          </thead>
                          <tbody>
                            {deferrals.map((deferral) => {
                              const course = courseById.get(deferral.course_id);
                              return (
                                <tr key={deferral.id}>
                                  <td>{course?.course_name || deferral.course_id}</td>
                                  <td>{formatDate(deferral.original_due_date)}</td>
                                  <td>{formatDate(deferral.requested_new_due_date)}</td>
                                  <td><span className={deferralStatusPill(deferral.status)}>{deferral.status}</span></td>
                                  <td>{deferral.reason_text || deferral.reason_category}</td>
                                  <td>{formatDateTime(deferral.requested_at)}</td>
                                  {canEdit ? (
                                    <td>
                                      {deferral.status === "PENDING" ? (
                                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                          <button type="button" className="secondary-chip-btn" onClick={() => void handleDeferralDecision(deferral.id, "APPROVED")}>Approve</button>
                                          <button type="button" className="secondary-chip-btn" onClick={() => void handleDeferralDecision(deferral.id, "REJECTED")}>Reject</button>
                                        </div>
                                      ) : "-"}
                                    </td>
                                  ) : null}
                                </tr>
                              );
                            })}
                            {deferrals.length === 0 && (
                              <tr>
                                <td colSpan={canEdit ? 7 : 6} className="text-muted">No deferral requests have been captured for this user.</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      <div className="qms-card training-profile-inner-card">
                        <div className="qms-card__header">
                          <div>
                            <h3 className="qms-card__title">Request a deferral</h3>
                            <p className="qms-card__subtitle">Select the course and requested new due date.</p>
                          </div>
                        </div>
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
                          <label className="qms-field">
                            <span>Reason</span>
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
                        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                          <button type="button" className="secondary-chip-btn" onClick={() => void submitDeferral()} disabled={savingDeferral}>
                            {savingDeferral ? "Submitting..." : "Submit deferral request"}
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </section>

                {canEdit ? (
                  <section className="qms-card training-profile-section-card training-profile-collapse-card">
                    <button type="button" className="training-collapse-toggle" onClick={() => togglePanel("newRecord")} aria-expanded={panelOpen.newRecord}>
                      <div>
                        <span className="training-collapse-toggle__eyebrow">Completion capture and attachments</span>
                        <strong>New record</strong>
                      </div>
                      <span className="training-collapse-toggle__meta">{panelOpen.newRecord ? "Hide" : "Show"} · {panelStats.newRecord}</span>
                    </button>
                    {panelOpen.newRecord ? (
                      <div className="training-collapse-panel training-profile-split training-profile-split--balanced">
                        <div className="qms-card qms-card--wide training-profile-inner-card">
                          <div className="qms-card__header">
                            <div>
                              <h3 className="qms-card__title">Completion and evidence</h3>
                              <p className="qms-card__subtitle">Hours and next due are pulled from the selected course. The certificate rule is enforced here.</p>
                            </div>
                          </div>
                          <div className="training-profile-form-grid">
                            <label className="qms-field">
                              <span>Course</span>
                              <select value={recordForm.coursePk} onChange={(e) => setRecordForm((prev) => ({ ...prev, coursePk: e.target.value }))}>
                                <option value="">Select course</option>
                                {courses.map((course) => (
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
                            <label className="qms-field">
                              <span>Next due</span>
                              <input value={derivedValidUntil !== "-" ? formatDate(derivedValidUntil) : "-"} disabled />
                            </label>
                            <label className="qms-field">
                              <span>Current course status</span>
                              <input value={selectedCourseStatus ? statusLabel(selectedCourseStatus.status) : "-"} disabled />
                            </label>
                            <label className="qms-field">
                              <span>Exam score</span>
                              <input value={recordForm.examScore} onChange={(e) => setRecordForm((prev) => ({ ...prev, examScore: e.target.value }))} placeholder="Optional" />
                            </label>
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
                            <label className="qms-field" style={{ gridColumn: "1 / -1" }}>
                              <span>Remarks</span>
                              <textarea value={recordForm.remarks} onChange={(e) => setRecordForm((prev) => ({ ...prev, remarks: e.target.value }))} rows={3} />
                            </label>
                          </div>
                          <div className="training-profile-form-note">
                            <span className="qms-pill qms-pill--info">Rule</span>
                            <p>Hours are read from the selected course. The next due date is calculated from the course recurrence. When a certificate reference is entered, a certificate attachment is mandatory.</p>
                          </div>
                          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                            <button type="button" className="secondary-chip-btn" onClick={() => void submitRecord()} disabled={savingRecord}>
                              {savingRecord ? "Saving..." : "Save training record"}
                            </button>
                          </div>
                        </div>

                        <div className="qms-card training-profile-inner-card">
                          <div className="qms-card__header">
                            <div>
                              <h3 className="qms-card__title">Recent attachments</h3>
                              <p className="qms-card__subtitle">Latest evidence already uploaded for this person.</p>
                            </div>
                          </div>
                          <div className="table-responsive training-table-wrap">
                            <table className="table training-history-table--responsive">
                              <thead>
                                <tr>
                                  <th>Filename</th>
                                  <th>Type</th>
                                  <th>Review</th>
                                  <th>Uploaded</th>
                                </tr>
                              </thead>
                              <tbody>
                                {recentFiles.map((file) => (
                                  <tr key={file.id}>
                                    <td>{file.original_filename}</td>
                                    <td>{file.kind}</td>
                                    <td><span className={deferralStatusPill(file.review_status)}>{file.review_status}</span></td>
                                    <td>{formatDateTime(file.uploaded_at)}</td>
                                  </tr>
                                ))}
                                {recentFiles.length === 0 && (
                                  <tr>
                                    <td colSpan={4} className="text-muted">No attachments have been uploaded for this profile yet.</td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {error ? (
                  <div className="card card--error">
                    <p>{error}</p>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        )}
      </div>
    </QMSLayout>
  );
};

export default QMSTrainingUserPage;

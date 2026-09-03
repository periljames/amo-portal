import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
import { useToast } from "../components/feedback/ToastProvider";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getCachedUser, getContext } from "../services/auth";
import { saveDownloadedFile } from "../utils/downloads";
import {
  type CARAttachmentOut,
  type CARAssignee,
  type CAROut,
  type CARPriority,
  type CARProgram,
  type CARStatus,
  downloadCarEvidencePack,
  qmsCreateCar,
  qmsDeleteCar,
  qmsDownloadCarAttachmentBlob,
  qmsGetCarInvite,
  qmsListCarAssignees,
  qmsListCarAttachments,
  qmsListCarResponses,
  qmsReviewCarResponse,
  qmsUpdateCar,
} from "../services/qms";
import {
  qmsGetCarRegisterPage,
  type QmsCarRegisterScope,
} from "../services/qmsRegisters";

type CarStatusFilter = "ALL" | "ACTIVE" | CARStatus;
type CarPageSize = 25 | 50 | 100;

type CarFormState = {
  title: string;
  summary: string;
  program: CARProgram;
  priority: CARPriority;
  due_date: string;
  target_closure_date: string;
  assigned_department_id: string;
  assigned_to_user_id: string;
  finding_id: string;
};

type CarReviewForm = {
  root_cause_status: "ACCEPTED" | "REJECTED" | "";
  root_cause_review_note: string;
  capa_status: "ACCEPTED" | "REJECTED" | "NEEDS_EVIDENCE" | "";
  capa_review_note: string;
  message: string;
};

type AttachmentPreview = {
  attachment: CARAttachmentOut;
  url: string;
  contentType: string;
};

type AssigneeFieldsProps = {
  assignees: CARAssignee[];
  departmentId: string;
  assignedUserId: string;
  search: string;
  onDepartmentChange: (departmentId: string) => void;
  onAssignedUserChange: (userId: string) => void;
  onSearchChange: (search: string) => void;
};

const PROGRAM_OPTIONS: Array<{ value: CARProgram; label: string }> = [
  { value: "QUALITY", label: "Quality" },
  { value: "RELIABILITY", label: "Reliability" },
];

const PRIORITY_OPTIONS: CARPriority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const STATUS_OPTIONS: Array<{ value: CarStatusFilter; label: string }> = [
  { value: "ALL", label: "All statuses" },
  { value: "ACTIVE", label: "Open / active" },
  { value: "DRAFT", label: "Draft" },
  { value: "OPEN", label: "Open" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "PENDING_VERIFICATION", label: "Pending verification" },
  { value: "ESCALATED", label: "Escalated" },
  { value: "CLOSED", label: "Closed" },
  { value: "CANCELLED", label: "Cancelled" },
];

const STATUS_CLASS: Record<CARStatus, string> = {
  DRAFT: "badge--neutral",
  OPEN: "badge--info",
  IN_PROGRESS: "badge--warning",
  PENDING_VERIFICATION: "badge--warning",
  CLOSED: "badge--success",
  ESCALATED: "badge--danger",
  CANCELLED: "badge--neutral",
};

const EMPTY_FORM: CarFormState = {
  title: "",
  summary: "",
  program: "QUALITY",
  priority: "MEDIUM",
  due_date: "",
  target_closure_date: "",
  assigned_department_id: "",
  assigned_to_user_id: "",
  finding_id: "",
};

const EMPTY_REVIEW: CarReviewForm = {
  root_cause_status: "",
  root_cause_review_note: "",
  capa_status: "",
  capa_review_note: "",
  message: "",
};

function humanize(value?: string | null): string {
  if (!value) return "—";
  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateOnly(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10) || "—";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function formatFileSize(bytes?: number | null): string {
  if (!bytes || bytes < 1) return "Size not recorded";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function workflowStep(car: CAROut): string {
  if (car.status === "CLOSED") return "Closed";
  if (car.status === "PENDING_VERIFICATION") return "Effectiveness / closeout review";
  if (car.root_cause_status === "REJECTED" || car.capa_status === "REJECTED") return "Returned to auditee";
  if (car.capa_status === "NEEDS_EVIDENCE") return "Additional evidence required";
  if (car.root_cause_status === "SUBMITTED" || car.capa_status === "SUBMITTED") return "Quality review required";
  if (!car.submitted_at) return "Awaiting auditee response";
  return "Corrective action in progress";
}

function routeScope(pathname: string, queryStatus: string | null): QmsCarRegisterScope {
  const normalized = pathname.toLowerCase();
  if (normalized.endsWith("/overdue") || queryStatus === "overdue") return "overdue";
  if (normalized.endsWith("/due-soon")) return "due_soon";
  if (normalized.endsWith("/awaiting-auditee")) return "awaiting_auditee";
  if (normalized.endsWith("/awaiting-quality-review")) return "awaiting_quality_review";
  if (normalized.endsWith("/awaiting-effectiveness-review")) return "awaiting_effectiveness_review";
  if (normalized.endsWith("/closed")) return "closed";
  return "all";
}

function scopeLabel(scope: QmsCarRegisterScope): string {
  const labels: Record<QmsCarRegisterScope, string> = {
    all: "All corrective actions",
    active: "Open / active corrective actions",
    overdue: "Overdue corrective actions",
    due_soon: "Corrective actions due soon",
    awaiting_auditee: "Awaiting auditee response",
    awaiting_quality_review: "Awaiting Quality review",
    awaiting_effectiveness_review: "Awaiting effectiveness review",
    closed: "Closed corrective actions",
  };
  return labels[scope];
}

const AssigneeFields: React.FC<AssigneeFieldsProps> = ({
  assignees,
  departmentId,
  assignedUserId,
  search,
  onDepartmentChange,
  onAssignedUserChange,
  onSearchChange,
}) => {
  const departments = useMemo(() => {
    const values = new Map<string, string>();
    assignees.forEach((assignee) => {
      if (assignee.department_id && assignee.department_name) {
        values.set(assignee.department_id, assignee.department_name);
      }
    });
    return Array.from(values.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [assignees]);

  const filteredAssignees = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return assignees.filter((assignee) => {
      if (departmentId && assignee.department_id !== departmentId) return false;
      if (!needle) return true;
      return [assignee.full_name, assignee.email, assignee.staff_code, assignee.department_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [assignees, departmentId, search]);

  return (
    <>
      <label>Responsible department
        <select
          className="input"
          value={departmentId}
          onChange={(event) => onDepartmentChange(event.target.value)}
        >
          <option value="">All departments</option>
          {departments.map((department) => (
            <option key={department.id} value={department.id}>{department.name}</option>
          ))}
        </select>
      </label>
      <label>Find responsible person
        <input
          className="input"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Name, staff code, email, or department"
        />
      </label>
      <label>Responsible person
        <select
          className="input"
          value={assignedUserId}
          onChange={(event) => onAssignedUserChange(event.target.value)}
        >
          <option value="">Unassigned</option>
          {filteredAssignees.map((assignee) => (
            <option key={assignee.id} value={assignee.id}>
              {assignee.full_name}{assignee.department_name ? ` · ${assignee.department_name}` : ""}
            </option>
          ))}
        </select>
      </label>
    </>
  );
};

const QualityCarsPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams<{ amoCode?: string; department?: string; carId?: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const context = getContext();
  const currentUser = getCachedUser();

  const amoSlug = params.amoCode ?? context.amoSlug ?? context.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const directCarId = params.carId ?? searchParams.get("carId") ?? "";
  const routeRequestedScope = routeScope(location.pathname, searchParams.get("status"));
  const routeRequestsCreate = /\/quality\/cars\/new\/?$/i.test(location.pathname);

  const [programFilter, setProgramFilter] = useState<CARProgram>("QUALITY");
  const [statusFilter, setStatusFilter] = useState<CarStatusFilter>("ALL");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [registerSearch, setRegisterSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [pageSize, setPageSize] = useState<CarPageSize>(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [showCreateForm, setShowCreateForm] = useState(routeRequestsCreate);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [createAssigneeSearch, setCreateAssigneeSearch] = useState("");
  const [editAssigneeSearch, setEditAssigneeSearch] = useState("");
  const [form, setForm] = useState<CarFormState>(() => ({
    ...EMPTY_FORM,
    finding_id: searchParams.get("findingId") ?? "",
    title: searchParams.get("title") ?? "",
    due_date: searchParams.get("due_date") ?? "",
  }));
  const [createBusy, setCreateBusy] = useState(false);
  const [editingCar, setEditingCar] = useState<CAROut | null>(null);
  const [editForm, setEditForm] = useState<CarFormState | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [deleteBusyId, setDeleteBusyId] = useState<string | null>(null);
  const [inviteBusyId, setInviteBusyId] = useState<string | null>(null);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);
  const [reviewCar, setReviewCar] = useState<CAROut | null>(null);
  const [reviewForm, setReviewForm] = useState<CarReviewForm>(EMPTY_REVIEW);
  const [reviewAttachments, setReviewAttachments] = useState<CARAttachmentOut[]>([]);
  const [reviewAttachmentsLoading, setReviewAttachmentsLoading] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [attachmentBusyId, setAttachmentBusyId] = useState<string | null>(null);
  const [attachmentPreview, setAttachmentPreview] = useState<AttachmentPreview | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const canManageCars = Boolean(
    currentUser?.is_superuser
      || currentUser?.is_amo_admin
      || currentUser?.role === "QUALITY_MANAGER",
  );

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(registerSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [registerSearch]);

  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, directCarId, ownerFilter, pageSize, programFilter, routeRequestedScope, statusFilter]);

  useEffect(() => {
    if (routeRequestsCreate) setShowCreateForm(true);
  }, [routeRequestsCreate]);

  useEffect(() => {
    if (!routeRequestsCreate) return;
    const title = searchParams.get("title");
    const dueDate = searchParams.get("due_date");
    const findingId = searchParams.get("findingId");
    if (!title && !dueDate && !findingId) return;
    setForm((current) => ({
      ...current,
      title: title ?? current.title,
      due_date: dueDate ?? current.due_date,
      finding_id: findingId ?? current.finding_id,
    }));
  }, [routeRequestsCreate, searchParams]);

  useEffect(() => {
    return () => {
      if (attachmentPreview?.url) window.URL.revokeObjectURL(attachmentPreview.url);
    };
  }, [attachmentPreview]);

  const dueWindow = searchParams.get("dueWindow");
  const dueSoonDays = dueWindow === "today" ? 0 : dueWindow === "week" ? 7 : 30;
  const exactStatus = statusFilter !== "ALL" && statusFilter !== "ACTIVE" ? statusFilter : undefined;
  const effectiveScope: QmsCarRegisterScope = directCarId
    ? "all"
    : statusFilter === "ACTIVE"
      ? "active"
      : routeRequestedScope;

  const registerQuery = useQuery({
    queryKey: [
      "qms-car-register-paged",
      amoSlug,
      directCarId ? "any-program" : programFilter,
      effectiveScope,
      exactStatus ?? "",
      directCarId,
      ownerFilter,
      debouncedSearch,
      dueSoonDays,
      pageSize,
      currentPage,
    ],
    queryFn: ({ signal }) => qmsGetCarRegisterPage({
      program: directCarId ? undefined : programFilter,
      status: exactStatus,
      scope: effectiveScope,
      carId: directCarId || undefined,
      assignedToUserId: directCarId ? undefined : ownerFilter || undefined,
      search: directCarId ? undefined : debouncedSearch || undefined,
      dueSoonDays,
      limit: directCarId ? 1 : pageSize,
      offset: directCarId ? 0 : (currentPage - 1) * pageSize,
      signal,
    }),
    placeholderData: (previous) => previous,
    staleTime: 20_000,
  });

  const assigneesQuery = useQuery({
    queryKey: ["qms-car-assignees", amoSlug],
    queryFn: () => qmsListCarAssignees(),
    staleTime: 60_000,
  });

  const cars = registerQuery.data?.items ?? [];
  const summary = registerQuery.data?.summary ?? { total: 0, open: 0, overdue: 0, in_review: 0 };
  const total = registerQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(total, (safePage - 1) * pageSize + cars.length);
  const assignees = assigneesQuery.data ?? [];

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const assigneeLookup = useMemo(() => {
    const lookup = new Map<string, CARAssignee>();
    assignees.forEach((assignee) => lookup.set(assignee.id, assignee));
    return lookup;
  }, [assignees]);

  const selectedCreateAssignee = form.assigned_to_user_id
    ? assigneeLookup.get(form.assigned_to_user_id)
    : undefined;

  const refreshRegister = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-car-register-paged"] });
  };

  const closeCreate = () => {
    setPreviewOpen(false);
    setShowCreateForm(false);
    setCreateAssigneeSearch("");
    if (routeRequestsCreate) navigate(`/maintenance/${amoSlug}/quality/cars/register`);
  };

  const requestCreatePreview = () => {
    if (!form.title.trim() || !form.summary.trim() || !form.finding_id.trim()) {
      setLocalError("Title, summary, and linked finding ID are required.");
      return;
    }
    setLocalError(null);
    setPreviewOpen(true);
  };

  const handleConfirmCreate = async () => {
    setCreateBusy(true);
    setLocalError(null);
    try {
      const created = await qmsCreateCar({
        program: form.program,
        title: form.title.trim(),
        summary: form.summary.trim(),
        priority: form.priority,
        due_date: form.due_date || null,
        target_closure_date: form.target_closure_date || null,
        assigned_to_user_id: form.assigned_to_user_id || null,
        finding_id: form.finding_id.trim(),
        evidence_required: true,
      });
      setForm({ ...EMPTY_FORM, program: form.program });
      setCreateAssigneeSearch("");
      setPreviewOpen(false);
      setShowCreateForm(false);
      await refreshRegister();
      pushToast({ title: "Corrective action created", message: created.car_number, variant: "info" });
      navigate(`/maintenance/${amoSlug}/quality/cars?carId=${encodeURIComponent(created.id)}`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Failed to create corrective action.");
    } finally {
      setCreateBusy(false);
    }
  };

  const openEdit = (car: CAROut) => {
    const assignee = car.assigned_to_user_id ? assigneeLookup.get(car.assigned_to_user_id) : undefined;
    setEditingCar(car);
    setEditAssigneeSearch("");
    setEditForm({
      title: car.title,
      summary: car.summary,
      program: car.program,
      priority: car.priority,
      due_date: car.due_date ?? "",
      target_closure_date: car.target_closure_date ?? "",
      assigned_department_id: assignee?.department_id ?? "",
      assigned_to_user_id: car.assigned_to_user_id ?? "",
      finding_id: car.finding_id ?? "",
    });
  };

  const handleEditSave = async () => {
    if (!editingCar || !editForm) return;
    if (!editForm.title.trim() || !editForm.summary.trim()) {
      setLocalError("Title and summary are required.");
      return;
    }
    setEditBusy(true);
    setLocalError(null);
    try {
      await qmsUpdateCar(editingCar.id, {
        title: editForm.title.trim(),
        summary: editForm.summary.trim(),
        priority: editForm.priority,
        due_date: editForm.due_date || null,
        target_closure_date: editForm.target_closure_date || null,
        assigned_to_user_id: editForm.assigned_to_user_id || null,
      });
      setEditingCar(null);
      setEditForm(null);
      setEditAssigneeSearch("");
      await refreshRegister();
      pushToast({ title: "Corrective action updated", message: editingCar.car_number, variant: "info" });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Failed to update corrective action.");
    } finally {
      setEditBusy(false);
    }
  };

  const handleDelete = async (car: CAROut) => {
    if (!window.confirm(`Permanently remove ${car.car_number}?`)) return;
    setDeleteBusyId(car.id);
    setLocalError(null);
    try {
      await qmsDeleteCar(car.id);
      await refreshRegister();
      pushToast({ title: "Corrective action removed", message: car.car_number, variant: "info" });
      if (directCarId === car.id) navigate(`/maintenance/${amoSlug}/quality/cars/register`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Failed to delete corrective action.");
    } finally {
      setDeleteBusyId(null);
    }
  };

  const handleCopyInvite = async (car: CAROut) => {
    setInviteBusyId(car.id);
    try {
      const invite = await qmsGetCarInvite(car.id);
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(invite.invite_url);
        pushToast({ title: "Invite link copied", message: invite.invite_url, variant: "info" });
      } else {
        window.prompt("Copy invite link:", invite.invite_url);
      }
    } catch (error) {
      pushToast({
        title: "Invite failed",
        message: error instanceof Error ? error.message : "Unable to fetch the invite link.",
        variant: "error",
      });
    } finally {
      setInviteBusyId(null);
    }
  };

  const handleExport = async (car: CAROut) => {
    setExportingId(car.id);
    setLocalError(null);
    try {
      const blob = await downloadCarEvidencePack(car.id);
      saveDownloadedFile(blob, `${car.car_number}-evidence-pack.zip`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Failed to export the evidence pack.");
    } finally {
      setExportingId(null);
    }
  };

  const openReview = async (car: CAROut) => {
    setReviewCar(car);
    setReviewForm({
      root_cause_status: car.root_cause_status === "REJECTED" ? "REJECTED" : "ACCEPTED",
      root_cause_review_note: car.root_cause_review_note ?? "",
      capa_status: car.capa_status === "REJECTED"
        ? "REJECTED"
        : car.capa_status === "NEEDS_EVIDENCE"
          ? "NEEDS_EVIDENCE"
          : "ACCEPTED",
      capa_review_note: car.capa_review_note ?? "",
      message: "",
    });
    setReviewAttachmentsLoading(true);
    setLocalError(null);
    try {
      await qmsListCarResponses(car.id, true);
      setReviewAttachments(await qmsListCarAttachments(car.id));
    } catch (error) {
      pushToast({
        title: "Evidence fetch failed",
        message: error instanceof Error ? error.message : "Could not load submitted evidence.",
        variant: "error",
      });
      setReviewAttachments([]);
    } finally {
      setReviewAttachmentsLoading(false);
    }
  };

  const submitReview = async () => {
    if (!reviewCar) return;
    const rootDecision = reviewForm.root_cause_status || "ACCEPTED";
    const capaDecision = reviewForm.capa_status || "ACCEPTED";
    if (rootDecision === "REJECTED" && !reviewForm.root_cause_review_note.trim()) {
      setLocalError("Root cause rejection requires a review note.");
      return;
    }
    if ((capaDecision === "REJECTED" || capaDecision === "NEEDS_EVIDENCE") && !reviewForm.capa_review_note.trim()) {
      setLocalError("Corrective action rejection or evidence request requires a review note.");
      return;
    }
    setReviewBusy(true);
    setLocalError(null);
    try {
      await qmsReviewCarResponse(reviewCar.id, {
        root_cause_status: rootDecision,
        root_cause_review_note: reviewForm.root_cause_review_note.trim() || null,
        capa_status: capaDecision,
        capa_review_note: reviewForm.capa_review_note.trim() || null,
        message: reviewForm.message.trim() || null,
      });
      setReviewCar(null);
      setReviewAttachments([]);
      await refreshRegister();
      pushToast({ title: "Review submitted", message: reviewCar.car_number, variant: "info" });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Failed to submit review.");
    } finally {
      setReviewBusy(false);
    }
  };

  const downloadAttachment = async (attachment: CARAttachmentOut) => {
    if (!reviewCar) return;
    setAttachmentBusyId(attachment.id);
    try {
      const blob = await qmsDownloadCarAttachmentBlob(reviewCar.id, attachment.id);
      saveDownloadedFile(blob, attachment.filename);
    } catch (error) {
      pushToast({
        title: "Evidence download failed",
        message: error instanceof Error ? error.message : "Could not download this evidence file.",
        variant: "error",
      });
    } finally {
      setAttachmentBusyId(null);
    }
  };

  const previewAttachment = async (attachment: CARAttachmentOut) => {
    if (!reviewCar) return;
    setAttachmentBusyId(attachment.id);
    try {
      const blob = await qmsDownloadCarAttachmentBlob(reviewCar.id, attachment.id);
      if (attachmentPreview?.url) window.URL.revokeObjectURL(attachmentPreview.url);
      setAttachmentPreview({
        attachment,
        url: window.URL.createObjectURL(blob),
        contentType: blob.type || attachment.content_type || "application/octet-stream",
      });
    } catch (error) {
      pushToast({
        title: "Evidence preview failed",
        message: error instanceof Error ? error.message : "Could not preview this evidence file.",
        variant: "error",
      });
    } finally {
      setAttachmentBusyId(null);
    }
  };

  const clearRouteScope = () => {
    setStatusFilter("ALL");
    setOwnerFilter("");
    navigate(`/maintenance/${amoSlug}/quality/cars/register`);
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <div className="qms-surface-root qms-car-ops">
      <header className="page-header qms-car-page-heading">
        <div>
          <p className="page-header__eyebrow">Quality · Corrective action control</p>
          <h1 className="page-header__title">Corrective action register</h1>
          <p className="page-header__subtitle">
            Server-bounded register with governed auditee response, Quality review, evidence, and closeout actions.
          </p>
        </div>
        <div className="audit-chip-list">
          <button type="button" className="secondary-chip-btn" onClick={() => setHistoryOpen((open) => !open)}>
            {historyOpen ? "Hide history" : "History"}
          </button>
          {canManageCars ? (
            <button type="button" className="primary-chip-btn" onClick={() => setShowCreateForm(true)}>
              New CAR
            </button>
          ) : null}
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoSlug}/quality`)}>
            Back to QMS
          </button>
        </div>
      </header>

      {localError ? (
        <div className="card card--error" role="alert" style={{ marginBottom: 12 }}>
          <strong>Action could not be completed.</strong>
          <p style={{ marginBottom: 0 }}>{localError}</p>
        </div>
      ) : null}

      <section className="audit-stats-grid" aria-label="Corrective action summary">
        <div className="audit-stat-card">
          <div className="audit-stat-card__label">Total in {humanize(programFilter)}</div>
          <div className="audit-stat-card__value">{summary.total}</div>
        </div>
        <div className="audit-stat-card">
          <div className="audit-stat-card__label">Open / active</div>
          <div className="audit-stat-card__value">{summary.open}</div>
        </div>
        <div className="audit-stat-card">
          <div className="audit-stat-card__label">Overdue</div>
          <div className="audit-stat-card__value">{summary.overdue}</div>
        </div>
        <div className="audit-stat-card">
          <div className="audit-stat-card__label">In review</div>
          <div className="audit-stat-card__value">{summary.in_review}</div>
        </div>
      </section>

      <section className="audit-panel" style={{ marginTop: 12 }}>
        <div className="audit-panel__header">
          <div>
            <h2 className="audit-panel__title">{directCarId ? "Corrective action record" : scopeLabel(effectiveScope)}</h2>
            <p className="audit-panel__subtitle">
              {directCarId
                ? "This deep link loads only the requested CAR record."
                : `${rangeStart}-${rangeEnd} of ${total} matched records${registerQuery.isFetching && !registerQuery.isLoading ? " · refreshing" : ""}.`}
            </p>
          </div>
          {routeRequestedScope !== "all" || directCarId ? (
            <button type="button" className="secondary-chip-btn" onClick={clearRouteScope}>Open full register</button>
          ) : null}
        </div>

        {!directCarId ? (
          <div className="audit-workspace__toolbar-row" style={{ marginBottom: 12 }}>
            <label>
              <span className="text-muted">Programme</span>
              <select className="input" value={programFilter} onChange={(event) => setProgramFilter(event.target.value as CARProgram)}>
                {PROGRAM_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              <span className="text-muted">Status</span>
              <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as CarStatusFilter)}>
                {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              <span className="text-muted">Responsible</span>
              <select className="input" value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}>
                <option value="">All owners</option>
                {assignees.map((assignee) => (
                  <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>
                ))}
              </select>
            </label>
            <label className="audit-search" aria-label="Search corrective actions">
              <input
                value={registerSearch}
                onChange={(event) => setRegisterSearch(event.target.value)}
                placeholder="Search CAR, audit, finding, status, or summary"
              />
            </label>
            <label>
              <span className="text-muted">Rows</span>
              <select className="input" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value) as CarPageSize)}>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          </div>
        ) : null}

        {registerQuery.isError ? (
          <div className="card card--error" role="alert">
            <p>{registerQuery.error instanceof Error ? registerQuery.error.message : "Failed to load corrective actions."}</p>
            <button type="button" className="secondary-chip-btn" onClick={() => void registerQuery.refetch()}>Retry</button>
          </div>
        ) : null}

        <div className="table-wrapper">
          <table className="table table-row--compact">
            <thead>
              <tr>
                <th>CAR</th>
                <th>Audit / finding</th>
                <th>Corrective action</th>
                <th>Workflow</th>
                <th>Status</th>
                <th>Due</th>
                <th>Responsible</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {registerQuery.isLoading ? (
                <tr><td colSpan={8}>Loading corrective actions…</td></tr>
              ) : cars.length === 0 ? (
                <tr><td colSpan={8}>No corrective actions match the current server-side filters.</td></tr>
              ) : cars.map((car) => {
                const assignee = car.assigned_to_user_id ? assigneeLookup.get(car.assigned_to_user_id) : undefined;
                const canModify = car.can_current_user_modify ?? canManageCars;
                const canReview = (car.can_current_user_review ?? canManageCars) && canManageCars;
                return (
                  <tr key={car.id}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => navigate(`/maintenance/${amoSlug}/quality/cars?carId=${encodeURIComponent(car.id)}`)}
                      >
                        <strong>{car.car_number}</strong>
                      </button>
                      <div className="text-muted">{humanize(car.program)} · {humanize(car.priority)}</div>
                    </td>
                    <td>
                      <strong>{car.audit_ref || "No audit reference"}</strong>
                      <div className="text-muted">{car.finding_ref || car.finding_id || "No linked finding"}</div>
                    </td>
                    <td>
                      <strong>{car.title}</strong>
                      <div className="qms-cell-text qms-cell-text--wrap text-muted">{car.summary}</div>
                    </td>
                    <td>
                      <strong>{workflowStep(car)}</strong>
                      <div className="text-muted">
                        RC {humanize(car.root_cause_status)} · CAP {humanize(car.capa_status)}
                      </div>
                    </td>
                    <td><span className={`badge ${STATUS_CLASS[car.status]}`}>{humanize(car.status)}</span></td>
                    <td>
                      <strong>{dateOnly(car.due_date)}</strong>
                      <div className="text-muted">Target {dateOnly(car.target_closure_date)}</div>
                    </td>
                    <td>
                      {car.responsible_personnel || assignee?.full_name || car.submitted_by_name || "Unassigned"}
                      <div className="text-muted">{car.responsible_department || assignee?.department_name || "—"}</div>
                    </td>
                    <td>
                      <div className="audit-chip-list">
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => setPanelContext({
                            type: "car",
                            id: car.id,
                            title: car.car_number,
                            status: car.status,
                            ownerId: car.assigned_to_user_id,
                          })}
                        >
                          Manage
                        </button>
                        {canReview ? <button type="button" className="secondary-chip-btn" onClick={() => void openReview(car)}>Review</button> : null}
                        <button type="button" className="secondary-chip-btn" disabled={inviteBusyId === car.id} onClick={() => void handleCopyInvite(car)}>
                          {inviteBusyId === car.id ? "Loading…" : "Invite"}
                        </button>
                        <button type="button" className="secondary-chip-btn" disabled={exportingId === car.id} onClick={() => void handleExport(car)}>
                          {exportingId === car.id ? "Exporting…" : "Evidence pack"}
                        </button>
                        {canModify ? <button type="button" className="secondary-chip-btn" onClick={() => openEdit(car)}>Edit</button> : null}
                        {canManageCars ? (
                          <button type="button" className="secondary-chip-btn" disabled={deleteBusyId === car.id} onClick={() => void handleDelete(car)}>
                            {deleteBusyId === car.id ? "Removing…" : "Delete"}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!directCarId ? (
          <div className="qms-car-pagination" aria-label="Corrective action register pagination">
            <button
              type="button"
              className="secondary-chip-btn"
              disabled={safePage <= 1 || registerQuery.isFetching}
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
            >
              Previous
            </button>
            <span>Page {safePage} of {totalPages}</span>
            <button
              type="button"
              className="secondary-chip-btn"
              disabled={!registerQuery.data?.has_more || registerQuery.isFetching}
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
            >
              Next
            </button>
          </div>
        ) : null}
      </section>

      {historyOpen ? (
        <div style={{ marginTop: 12 }}>
          <AuditHistoryPanel
            title={directCarId ? "Corrective action history" : "Corrective action register history"}
            entityType={directCarId ? "qms_car" : undefined}
            entityId={directCarId || undefined}
            limit={12}
            currentUserId={currentUser?.id}
            onEventOpen={(event) => {
              if (!event.entity_id) return;
              navigate(`/maintenance/${amoSlug}/quality/cars?carId=${encodeURIComponent(event.entity_id)}`);
            }}
          />
        </div>
      ) : null}

      {!canManageCars ? (
        <div className="card card--info" style={{ marginTop: 12 }}>
          <p style={{ margin: 0 }}>Updates remain available to assigned users through the governed CAR controls; management actions remain limited to Quality Managers, AMO Admins, and superusers.</p>
        </div>
      ) : null}

      {showCreateForm ? (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true" aria-label="Create corrective action">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Governed workflow</p>
                <h3 className="upsell-modal__title">Create corrective action</h3>
                <p className="upsell-modal__subtitle">Link the CAR to its authoritative finding and confirm the issue details before creation.</p>
              </div>
              <button type="button" className="upsell-modal__close" onClick={closeCreate}>✕</button>
            </div>
            <div className="qms-form-grid">
              <label>Programme
                <select className="input" value={form.program} onChange={(event) => setForm((current) => ({ ...current, program: event.target.value as CARProgram }))}>
                  {PROGRAM_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>Priority
                <select className="input" value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value as CARPriority }))}>
                  {PRIORITY_OPTIONS.map((priority) => <option key={priority} value={priority}>{humanize(priority)}</option>)}
                </select>
              </label>
              <label>Finding ID
                <input className="input" value={form.finding_id} onChange={(event) => setForm((current) => ({ ...current, finding_id: event.target.value }))} placeholder="Authoritative finding UUID" />
              </label>
              <AssigneeFields
                assignees={assignees}
                departmentId={form.assigned_department_id}
                assignedUserId={form.assigned_to_user_id}
                search={createAssigneeSearch}
                onDepartmentChange={(departmentId) => {
                  setForm((current) => ({ ...current, assigned_department_id: departmentId, assigned_to_user_id: "" }));
                  setCreateAssigneeSearch("");
                }}
                onAssignedUserChange={(userId) => setForm((current) => ({ ...current, assigned_to_user_id: userId }))}
                onSearchChange={setCreateAssigneeSearch}
              />
              <label>Due date
                <input className="input" type="date" value={form.due_date} onChange={(event) => setForm((current) => ({ ...current, due_date: event.target.value }))} />
              </label>
              <label>Target closure
                <input className="input" type="date" value={form.target_closure_date} onChange={(event) => setForm((current) => ({ ...current, target_closure_date: event.target.value }))} />
              </label>
            </div>
            <label>Title
              <input className="input" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
            </label>
            <label>Summary
              <textarea className="input" rows={4} value={form.summary} onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))} />
            </label>
            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={closeCreate} disabled={createBusy}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={requestCreatePreview} disabled={createBusy || !canManageCars}>
                Review & create
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {previewOpen ? (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true" aria-label="Confirm corrective action details">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Preview</p>
                <h3 className="upsell-modal__title">Confirm corrective action details</h3>
                <p className="upsell-modal__subtitle">Confirm the controlled issue information before the CAR is created.</p>
              </div>
              <button type="button" className="upsell-modal__close" onClick={() => setPreviewOpen(false)} disabled={createBusy}>✕</button>
            </div>
            <dl className="qms-detail-grid">
              <div><dt>Finding</dt><dd>{form.finding_id}</dd></div>
              <div><dt>Programme</dt><dd>{humanize(form.program)}</dd></div>
              <div><dt>Priority</dt><dd>{humanize(form.priority)}</dd></div>
              <div><dt>Responsible</dt><dd>{selectedCreateAssignee?.full_name || "Unassigned"}</dd></div>
              <div><dt>Department</dt><dd>{selectedCreateAssignee?.department_name || "Unassigned"}</dd></div>
              <div><dt>Due</dt><dd>{dateOnly(form.due_date)}</dd></div>
              <div><dt>Target closure</dt><dd>{dateOnly(form.target_closure_date)}</dd></div>
            </dl>
            <div className="qms-card">
              <strong>{form.title}</strong>
              <p>{form.summary}</p>
            </div>
            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => setPreviewOpen(false)} disabled={createBusy}>Go back</button>
              <button type="button" className="primary-chip-btn" onClick={() => void handleConfirmCreate()} disabled={createBusy}>
                {createBusy ? "Creating…" : "Confirm & create"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {editingCar && editForm ? (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true" aria-label="Edit corrective action">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">{editingCar.car_number}</p>
                <h3 className="upsell-modal__title">Edit corrective action</h3>
              </div>
              <button type="button" className="upsell-modal__close" onClick={() => { setEditingCar(null); setEditForm(null); setEditAssigneeSearch(""); }}>✕</button>
            </div>
            <label>Title
              <input className="input" value={editForm.title} onChange={(event) => setEditForm((current) => current ? ({ ...current, title: event.target.value }) : current)} />
            </label>
            <label>Summary
              <textarea className="input" rows={4} value={editForm.summary} onChange={(event) => setEditForm((current) => current ? ({ ...current, summary: event.target.value }) : current)} />
            </label>
            <div className="qms-form-grid">
              <label>Priority
                <select className="input" value={editForm.priority} onChange={(event) => setEditForm((current) => current ? ({ ...current, priority: event.target.value as CARPriority }) : current)}>
                  {PRIORITY_OPTIONS.map((priority) => <option key={priority} value={priority}>{humanize(priority)}</option>)}
                </select>
              </label>
              <AssigneeFields
                assignees={assignees}
                departmentId={editForm.assigned_department_id}
                assignedUserId={editForm.assigned_to_user_id}
                search={editAssigneeSearch}
                onDepartmentChange={(departmentId) => {
                  setEditForm((current) => current ? ({ ...current, assigned_department_id: departmentId, assigned_to_user_id: "" }) : current);
                  setEditAssigneeSearch("");
                }}
                onAssignedUserChange={(userId) => setEditForm((current) => current ? ({ ...current, assigned_to_user_id: userId }) : current)}
                onSearchChange={setEditAssigneeSearch}
              />
              <label>Due date
                <input className="input" type="date" value={editForm.due_date} onChange={(event) => setEditForm((current) => current ? ({ ...current, due_date: event.target.value }) : current)} />
              </label>
              <label>Target closure
                <input className="input" type="date" value={editForm.target_closure_date} onChange={(event) => setEditForm((current) => current ? ({ ...current, target_closure_date: event.target.value }) : current)} />
              </label>
            </div>
            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => { setEditingCar(null); setEditForm(null); setEditAssigneeSearch(""); }} disabled={editBusy}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={() => void handleEditSave()} disabled={editBusy}>
                {editBusy ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {reviewCar ? (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true" aria-label="Review corrective action response">
          <div className="upsell-modal" style={{ maxWidth: 920 }}>
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">{reviewCar.car_number} · {workflowStep(reviewCar)}</p>
                <h3 className="upsell-modal__title">Quality response review</h3>
                <p className="upsell-modal__subtitle">Review root cause, corrective action, and submitted evidence before accepting or returning the response.</p>
              </div>
              <button type="button" className="upsell-modal__close" onClick={() => { setReviewCar(null); setReviewAttachments([]); }}>✕</button>
            </div>

            <div className="qms-form-grid">
              <div className="qms-card">
                <strong>Root cause submitted</strong>
                <p>{reviewCar.register_root_cause || reviewCar.root_cause_text || reviewCar.root_cause || "No root cause submitted."}</p>
              </div>
              <div className="qms-card">
                <strong>Corrective / preventive action</strong>
                <p>{reviewCar.register_cap || reviewCar.capa_text || reviewCar.corrective_action || "No corrective action submitted."}</p>
                <p className="text-muted">{reviewCar.register_pap || reviewCar.preventive_action || "No preventive action recorded."}</p>
              </div>
            </div>

            <div className="qms-form-grid">
              <label>Root cause decision
                <select className="input" value={reviewForm.root_cause_status} onChange={(event) => setReviewForm((current) => ({ ...current, root_cause_status: event.target.value as CarReviewForm["root_cause_status"] }))}>
                  <option value="ACCEPTED">Accept</option>
                  <option value="REJECTED">Return</option>
                </select>
              </label>
              <label>Corrective action decision
                <select className="input" value={reviewForm.capa_status} onChange={(event) => setReviewForm((current) => ({ ...current, capa_status: event.target.value as CarReviewForm["capa_status"] }))}>
                  <option value="ACCEPTED">Accept</option>
                  <option value="REJECTED">Return</option>
                  <option value="NEEDS_EVIDENCE">Request more evidence</option>
                </select>
              </label>
            </div>
            <label>Root cause review note
              <textarea className="input" rows={2} value={reviewForm.root_cause_review_note} onChange={(event) => setReviewForm((current) => ({ ...current, root_cause_review_note: event.target.value }))} />
            </label>
            <label>Corrective action review note
              <textarea className="input" rows={2} value={reviewForm.capa_review_note} onChange={(event) => setReviewForm((current) => ({ ...current, capa_review_note: event.target.value }))} />
            </label>
            <label>Message to auditee
              <textarea className="input" rows={2} value={reviewForm.message} onChange={(event) => setReviewForm((current) => ({ ...current, message: event.target.value }))} />
            </label>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h4 className="qms-card__title">Submitted evidence</h4>
                  <p className="qms-card__subtitle">Evidence remains attached to the governed CAR record.</p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => setPanelContext({ type: "car", id: reviewCar.id, title: reviewCar.car_number, status: reviewCar.status, ownerId: reviewCar.assigned_to_user_id })}
                >
                  Manage evidence
                </button>
              </div>
              {reviewAttachmentsLoading ? <p>Loading evidence…</p> : reviewAttachments.length === 0 ? <p className="text-muted">No evidence attachments submitted.</p> : (
                <div className="qms-list">
                  {reviewAttachments.map((attachment) => (
                    <div className="qms-list__item" key={attachment.id}>
                      <div>
                        <strong>{attachment.filename}</strong>
                        <span className="qms-list__meta">{attachment.content_type || "File"} · {formatFileSize(attachment.size_bytes)}</span>
                      </div>
                      <div className="audit-chip-list">
                        <button type="button" className="secondary-chip-btn" disabled={attachmentBusyId === attachment.id} onClick={() => void previewAttachment(attachment)}>Open</button>
                        <button type="button" className="secondary-chip-btn" disabled={attachmentBusyId === attachment.id} onClick={() => void downloadAttachment(attachment)}>Download</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => { setReviewCar(null); setReviewAttachments([]); }} disabled={reviewBusy}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={() => void submitReview()} disabled={reviewBusy}>
                {reviewBusy ? "Saving review…" : "Record review decision"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {attachmentPreview ? (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true" aria-label={`Preview ${attachmentPreview.attachment.filename}`}>
          <div className="upsell-modal" style={{ maxWidth: 1000 }}>
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Evidence preview</p>
                <h3 className="upsell-modal__title">{attachmentPreview.attachment.filename}</h3>
              </div>
              <button type="button" className="upsell-modal__close" onClick={() => setAttachmentPreview(null)}>✕</button>
            </div>
            {attachmentPreview.contentType.startsWith("image/") ? (
              <img src={attachmentPreview.url} alt={attachmentPreview.attachment.filename} style={{ maxWidth: "100%", maxHeight: "70vh", objectFit: "contain" }} />
            ) : attachmentPreview.contentType === "application/pdf" || attachmentPreview.attachment.filename.toLowerCase().endsWith(".pdf") ? (
              <iframe title={attachmentPreview.attachment.filename} src={attachmentPreview.url} style={{ width: "100%", height: "70vh", border: 0 }} />
            ) : (
              <div className="card card--info">
                <p>This file type is not rendered inline. Use Download to inspect it with its native application.</p>
              </div>
            )}
            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => setAttachmentPreview(null)}>Close</button>
              <button type="button" className="primary-chip-btn" onClick={() => void downloadAttachment(attachmentPreview.attachment)}>Download</button>
            </div>
          </div>
        </div>
      ) : null}

      <ActionPanel
        isOpen={Boolean(panelContext)}
        context={panelContext}
        onClose={() => {
          setPanelContext(null);
          void refreshRegister();
        }}
      />
      </div>
    </DepartmentLayout>
  );
};

export default QualityCarsPage;

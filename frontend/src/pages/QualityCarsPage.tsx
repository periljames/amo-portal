import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
import { useToast } from "../components/feedback/ToastProvider";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getCachedUser, getContext } from "../services/auth";
import { deriveCarMetrics, isCarOverdue, isCarClosedStatus } from "../utils/carMetrics";
import { saveDownloadedFile } from "../utils/downloads";
import {
  type CAROut,
  type CARAssignee,
  type CARPriority,
  type CARProgram,
  type CARStatus,
  downloadCarEvidencePack,
  qmsDeleteCar,
  qmsListCarAssignees,
  qmsCreateCar,
  qmsGetCarInvite,
  qmsListCarRegister,
  qmsListCarAttachments,
  qmsListCarResponses,
  qmsDownloadCarAttachmentBlob,
  qmsReviewCarResponse,
  qmsUpdateCar,
  type CARAttachmentOut,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";
type AssigneeLoadState = "idle" | "loading" | "ready" | "error";

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

const getCarWorkflowStep = (car: CAROut): string => {
  if (!car.submitted_at) return "Awaiting auditee response";
  if ((car.root_cause_status === "REJECTED") || (car.capa_status === "REJECTED")) return "Returned to auditee";
  if (car.root_cause_status === "ACCEPTED" && car.capa_status === "NEEDS_EVIDENCE") return "Waiting for more evidence";
  if (car.status === "PENDING_VERIFICATION") return "Pending verification / closeout";
  if (car.status === "CLOSED") return "Closed";
  return "Under reviewer assessment";
};

type ReviewAttachmentPreview = {
  attachment: CARAttachmentOut;
  objectUrl: string;
  contentType: string;
  carNumber: string;
};

type CarStatusFilter = "ALL" | "ACTIVE" | CARStatus;
type CarPageSize = 20 | 50;

const CAR_STATUS_FILTERS: Array<{ value: CarStatusFilter; label: string }> = [
  { value: "ALL", label: "All statuses" },
  { value: "ACTIVE", label: "Open / active" },
  { value: "DRAFT", label: "Draft" },
  { value: "OPEN", label: "Open" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "PENDING_VERIFICATION", label: "Pending review" },
  { value: "CLOSED", label: "Closed" },
  { value: "ESCALATED", label: "Escalated" },
  { value: "CANCELLED", label: "Cancelled" },
];

const formatFileSize = (bytes?: number | null): string => {
  if (!bytes || bytes < 1) return "Size not recorded";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};


const dateOnly = (value?: string | null): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10) || "—";
  return date.toLocaleDateString(undefined, { year: "2-digit", month: "short", day: "2-digit" });
};

const daysBetween = (start?: string | null, end?: string | null): string => {
  if (!start) return "—";
  const startDate = new Date(`${String(start).slice(0, 10)}T00:00:00Z`);
  const endDate = end ? new Date(`${String(end).slice(0, 10)}T00:00:00Z`) : new Date();
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return "—";
  return String(Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 86400000)));
};

const daysRemaining = (due?: string | null): string => {
  if (!due) return "—";
  const today = new Date();
  const todayUtc = new Date(`${today.toISOString().slice(0, 10)}T00:00:00Z`);
  const dueDate = new Date(`${String(due).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(dueDate.getTime())) return "—";
  return String(Math.round((dueDate.getTime() - todayUtc.getTime()) / 86400000));
};

const firstText = (...values: Array<string | null | undefined>): string => {
  for (const value of values) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (text) return text;
  }
  return "—";
};

const cleanCarDescription = (car: CAROut): string => {
  if (car.finding_description?.trim()) return car.finding_description.trim();
  const stripped = (car.title || "").replace(/^CAR\s+for\s+/i, "").trim();
  if (car.summary && car.summary.trim() && car.summary.trim() !== stripped) return car.summary.trim();
  return stripped || car.title || "Corrective action";
};

const deriveFindingRef = (car: CAROut): string => {
  const source = `${car.title || ""} ${car.summary || ""}`;
  const match = source.match(/\b[A-Z]{2,4}\/[A-Z]{2,4}\/\d{2}\/\d{3}(?:-F-\d{3})?\b/i);
  if (match) return match[0].toUpperCase();
  return car.car_number;
};

const deriveAuditRef = (car: CAROut): string => {
  if (car.audit_ref?.trim()) return car.audit_ref.trim();
  const findingRef = car.finding_ref?.trim() || deriveFindingRef(car);
  return findingRef.replace(/-F-\d+$/i, "");
};

const deriveAuditTitle = (car: CAROut): string => {
  const title = car.audit_title;
  if (title?.trim()) return title.trim();
  const ref = deriveAuditRef(car);
  const maybe = (car.summary || car.title || "").replace(ref, "").replace(/^CAR\s+for\s+/i, "").trim();
  if (maybe && !maybe.match(/^[A-Z]{2,4}\//)) return maybe;
  return car.program === "RELIABILITY" ? "Reliability action" : "Quality audit";
};

const shortCarNumber = (car: CAROut): string => {
  const match = car.car_number.match(/(\d+)$/);
  if (!match) return car.car_number;
  return String(Number(match[1]));
};

const carStatusLabel = (status: CARStatus): string =>
  String(status)
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());

const buildAuditorRemarks = (car: CAROut): string => {
  if (car.auditor_remarks?.trim()) return car.auditor_remarks.trim();
  const parts: string[] = [];
  if (car.root_cause_status) parts.push(`RC ${carStatusLabel(car.root_cause_status as CARStatus)}`);
  if (car.capa_status) parts.push(`CAP ${carStatusLabel(car.capa_status as CARStatus)}`);
  if (car.evidence_verified_at) parts.push("EV Verified");
  return parts.length ? parts.join(" · ") : "—";
};

const responsibleParty = (car: CAROut, assignee?: CARAssignee): string => {
  if (car.responsible_personnel && car.responsible_department) return `${car.responsible_department}\n${car.responsible_personnel}`;
  if (car.responsible_personnel) return car.responsible_personnel;
  if (assignee?.full_name && assignee?.department_name) return `${assignee.department_name}\n${assignee.full_name}`;
  if (assignee?.full_name) return assignee.full_name;
  if (car.submitted_by_name) return car.submitted_by_name;
  return car.assigned_to_user_id ? "Assigned user" : "Unassigned";
};

const evidenceKind = (attachment: CARAttachmentOut): "image" | "video" | "pdf" | "document" | "file" => {
  const type = (attachment.content_type || "").toLowerCase();
  const name = attachment.filename.toLowerCase();
  if (type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|heic)$/i.test(name)) return "image";
  if (type.startsWith("video/") || /\.(mp4|webm|mov|m4v|avi|mkv)$/i.test(name)) return "video";
  if (type.includes("pdf") || name.endsWith(".pdf")) return "pdf";
  if (/\.(docx?|xlsx?|pptx?|csv|txt)$/i.test(name)) return "document";
  return "file";
};

const evidenceIcon = (attachment: CARAttachmentOut): string => {
  const kind = evidenceKind(attachment);
  if (kind === "image") return "▧";
  if (kind === "video") return "▶";
  if (kind === "pdf") return "PDF";
  if (kind === "document") return "DOC";
  return "FILE";
};

type CarRowActionIcon = "open" | "review" | "link" | "download" | "trash";

type CompactRowActionProps = {
  icon: CarRowActionIcon;
  label: string;
  title?: string;
  disabled?: boolean;
  danger?: boolean;
  onClick: () => void;
};

const CarRowActionIconGlyph: React.FC<{ name: CarRowActionIcon }> = ({ name }) => {
  if (name === "open") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 5h11v11h-2V8.4l-9.3 9.3-1.4-1.4L15.6 7H8V5Z" />
      </svg>
    );
  }
  if (name === "review") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9.2 16.8 4.9 12.5l1.4-1.4 2.9 2.9 8.5-8.5 1.4 1.4-9.9 9.9Z" />
      </svg>
    );
  }
  if (name === "link") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10.6 13.4a1 1 0 0 1 0-1.4l2.8-2.8a3 3 0 0 1 4.2 4.2l-2.1 2.1a3 3 0 0 1-4.2 0l1.4-1.4a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0-1.4-1.4L12 13.4a1 1 0 0 1-1.4 0Zm2.8-2.8a1 1 0 0 1 0 1.4l-2.8 2.8a3 3 0 0 1-4.2-4.2l2.1-2.1a3 3 0 0 1 4.2 0l-1.4 1.4a1 1 0 0 0-1.4 0L7.8 12a1 1 0 0 0 1.4 1.4l2.8-2.8a1 1 0 0 1 1.4 0Z" />
      </svg>
    );
  }
  if (name === "download") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M11 4h2v8.2l3.3-3.3 1.4 1.4L12 16l-5.7-5.7 1.4-1.4 3.3 3.3V4Zm-5 14h12v2H6v-2Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-2 6h10l-.7 11H7.7L7 9Zm3 2 .3 7h1.5l-.2-7H10Zm3.4 0-.2 7h1.5l.3-7h-1.6Z" />
    </svg>
  );
};

const CompactRowAction: React.FC<CompactRowActionProps> = ({
  icon,
  label,
  title,
  disabled,
  danger,
  onClick,
}) => (
  <button
    type="button"
    className={`qms-car-row-action ${danger ? "is-danger" : ""}`}
    title={title || label}
    aria-label={title || label}
    onClick={onClick}
    disabled={disabled}
  >
    <CarRowActionIconGlyph name={icon} />
    <span>{label}</span>
  </button>
);

const QualityCarsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [programFilter, setProgramFilter] = useState<CARProgram>("QUALITY");
  const [registerSearch, setRegisterSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<CarStatusFilter>("ALL");
  const [pageSize, setPageSize] = useState<CarPageSize>(20);
  const [currentPage, setCurrentPage] = useState(1);
  const inviteToken = searchParams.get("invite");
  const [showCreateForm, setShowCreateForm] = useState<boolean>(!!inviteToken);

  const [form, setForm] = useState<CarFormState>({
    title: "",
    summary: "",
    program: "QUALITY",
    priority: "MEDIUM",
    due_date: "",
    target_closure_date: "",
    assigned_department_id: "",
    assigned_to_user_id: "",
    finding_id: "",
  });

  const [assignees, setAssignees] = useState<CARAssignee[]>([]);
  const [assigneesState, setAssigneesState] = useState<AssigneeLoadState>("idle");
  const [assigneesError, setAssigneesError] = useState<string | null>(null);
  const [assigneeSearch, setAssigneeSearch] = useState("");

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);

  const [editingCar, setEditingCar] = useState<CAROut | null>(null);
  const [editForm, setEditForm] = useState<CarFormState | null>(null);
  const [editBusy, setEditBusy] = useState(false);

  const [deleteCar, setDeleteCar] = useState<CAROut | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [inviteBusyId, setInviteBusyId] = useState<string | null>(null);
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);
  const [reviewCar, setReviewCar] = useState<CAROut | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewAttachments, setReviewAttachments] = useState<CARAttachmentOut[]>([]);
  const [reviewAttachmentsLoading, setReviewAttachmentsLoading] = useState(false);
  const [attachmentPreview, setAttachmentPreview] = useState<ReviewAttachmentPreview | null>(null);
  const [attachmentPreviewLoadingId, setAttachmentPreviewLoadingId] = useState<string | null>(null);
  const [attachmentPreviewError, setAttachmentPreviewError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reviewForm, setReviewForm] = useState<CarReviewForm>({
    root_cause_status: "",
    root_cause_review_note: "",
    capa_status: "",
    capa_review_note: "",
    message: "",
  });
  const { pushToast } = useToast();

  useEffect(() => {
    return () => {
      if (attachmentPreview?.objectUrl) {
        window.URL.revokeObjectURL(attachmentPreview.objectUrl);
      }
    };
  }, [attachmentPreview?.objectUrl]);

  const assigneeLookup = useMemo(() => {
    const map = new Map<string, CARAssignee>();
    assignees.forEach((assignee) => map.set(assignee.id, assignee));
    return map;
  }, [assignees]);

  const sharedScopeCars = useMemo(() => cars, [cars]);

  const filteredCars = useMemo(() => {
    const statusParam = searchParams.get("status");
    const dueWindow = searchParams.get("dueWindow");
    const carId = searchParams.get("carId");
    const search = registerSearch.trim().toLowerCase();
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    return cars.filter((car) => {
      if (carId && car.id !== carId) return false;
      if (statusParam === "overdue") {
        return isCarOverdue(car, today);
      }
      if (statusParam === "open" && isCarClosedStatus(car.status)) return false;
      if (statusFilter === "ACTIVE" && isCarClosedStatus(car.status)) return false;
      if (statusFilter !== "ALL" && statusFilter !== "ACTIVE" && car.status !== statusFilter) return false;
      if (dueWindow && car.due_date) {
        const due = new Date(`${car.due_date}T00:00:00Z`).getTime();
        const todayMs = new Date(`${today}T00:00:00Z`).getTime();
        const diff = Math.floor((due - todayMs) / (1000 * 60 * 60 * 24));
        if (dueWindow === "now" && diff >= 0) return false;
        if (dueWindow === "today" && diff !== 0) return false;
        if (dueWindow === "week" && !(diff >= 0 && diff <= 7)) return false;
        if (dueWindow === "month" && !(diff >= 0 && diff <= 30)) return false;
      }
      if (search) {
        const owner = car.assigned_to_user_id ? assigneeLookup.get(car.assigned_to_user_id)?.full_name || "" : "";
        const haystack = [
          car.car_number,
          car.title,
          car.summary,
          car.status,
          car.priority,
          owner,
          deriveAuditRef(car),
          deriveAuditTitle(car),
          firstText(car.root_cause_text, car.root_cause),
          firstText(car.capa_text, car.corrective_action),
          firstText(car.preventive_action),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }, [assigneeLookup, cars, registerSearch, searchParams, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredCars.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStartIndex = filteredCars.length === 0 ? 0 : (safeCurrentPage - 1) * pageSize + 1;
  const pageEndIndex = Math.min(filteredCars.length, safeCurrentPage * pageSize);
  const pagedCars = useMemo(() => {
    const start = (safeCurrentPage - 1) * pageSize;
    return filteredCars.slice(start, start + pageSize);
  }, [filteredCars, pageSize, safeCurrentPage]);

  const auditBandMap = useMemo(() => {
    const map = new Map<string, number>();
    let band = 0;
    filteredCars.forEach((car) => {
      const key = deriveAuditRef(car);
      if (!map.has(key)) {
        map.set(key, band % 4);
        band += 1;
      }
    });
    return map;
  }, [filteredCars]);

  const reviewQueue = useMemo(() => {
    return cars
      .filter((car) => car.status === "PENDING_VERIFICATION" || car.root_cause_status === "SUBMITTED" || car.capa_status === "SUBMITTED")
      .sort((a, b) => (new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()));
  }, [cars]);

  const overviewStats = useMemo(() => deriveCarMetrics(sharedScopeCars), [sharedScopeCars]);

  const departmentOptions = useMemo(() => {
    const map = new Map<string, { id: string; name: string }>();
    assignees.forEach((assignee) => {
      if (assignee.department_id) {
        map.set(assignee.department_id, {
          id: assignee.department_id,
          name: assignee.department_name || assignee.department_code || "Department",
        });
      }
    });
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [assignees]);

  const filteredAssignees = useMemo(() => {
    const search = assigneeSearch.trim().toLowerCase();
    return assignees.filter((assignee) => {
      if (form.assigned_department_id && assignee.department_id !== form.assigned_department_id) {
        return false;
      }
      if (!search) return true;
      const name = assignee.full_name.toLowerCase();
      const email = (assignee.email || "").toLowerCase();
      const staff = (assignee.staff_code || "").toLowerCase();
      return name.includes(search) || email.includes(search) || staff.includes(search);
    });
  }, [assignees, assigneeSearch, form.assigned_department_id]);

  const assigneeSuggestions = useMemo(() => filteredAssignees.slice(0, 6), [filteredAssignees]);

  const selectedAssignee = useMemo(() => {
    if (!form.assigned_to_user_id) return null;
    return assigneeLookup.get(form.assigned_to_user_id) || null;
  }, [assigneeLookup, form.assigned_to_user_id]);

  const selectAssignee = (assigneeId: string) => {
    setForm((prev) => ({ ...prev, assigned_to_user_id: assigneeId }));
    setAssigneeSearch("");
  };

  const handleAssigneeSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    if (assigneeSuggestions.length === 0) return;
    event.preventDefault();
    selectAssignee(assigneeSuggestions[0].id);
  };

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const next = await qmsListCarRegister({ program: programFilter, limit: 1000 });
      setCars(next.items);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load corrective action register.");
      setState("error");
    }
  };

  const loadAssignees = async () => {
    setAssigneesState("loading");
    setAssigneesError(null);
    try {
      const next = await qmsListCarAssignees();
      setAssignees(next);
      setAssigneesState("ready");
    } catch (e: any) {
      setAssigneesError(e?.message || "Failed to load assignees.");
      setAssigneesState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programFilter]);

  useEffect(() => {
    loadAssignees();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize, programFilter, registerSearch, statusFilter, searchParams]);

  const handleSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!form.title.trim() || !form.summary.trim() || !form.finding_id.trim()) return;
    setPreviewOpen(true);
  };

  const handleConfirmCreate = async () => {
    setPreviewBusy(true);
    setError(null);
    try {
      await qmsCreateCar({
        program: form.program,
        title: form.title.trim(),
        summary: form.summary.trim(),
        priority: form.priority,
        due_date: form.due_date || null,
        target_closure_date: form.target_closure_date || null,
        assigned_to_user_id: form.assigned_to_user_id || null,
        finding_id: form.finding_id.trim(),
      });
      setForm({
        title: "",
        summary: "",
        program: form.program,
        priority: "MEDIUM",
        due_date: "",
        target_closure_date: "",
        assigned_department_id: "",
        assigned_to_user_id: "",
        finding_id: "",
      });
      setPreviewOpen(false);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to create corrective action.");
    } finally {
      setPreviewBusy(false);
    }
  };

  const handleCopyInvite = async (car: CAROut) => {
    setInviteBusyId(car.id);
    try {
      const invite = await qmsGetCarInvite(car.id);
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(invite.invite_url);
        pushToast({
          title: "Invite link copied",
          message: invite.invite_url,
          variant: "info",
        });
      } else {
        window.prompt("Copy invite link:", invite.invite_url);
      }
    } catch (e: any) {
      pushToast({
        title: "Invite failed",
        message: e?.message || "Unable to fetch the invite link.",
        variant: "error",
      });
    } finally {
      setInviteBusyId(null);
    }
  };

  const openEdit = (car: CAROut) => {
    setEditingCar(car);
    setEditForm({
      title: car.title,
      summary: car.summary,
      program: car.program,
      priority: car.priority,
      due_date: car.due_date || "",
      target_closure_date: car.target_closure_date || "",
      assigned_department_id: assigneeLookup.get(car.assigned_to_user_id || "")?.department_id || "",
      assigned_to_user_id: car.assigned_to_user_id || "",
      finding_id: car.finding_id || "",
    });
  };

  const handleExport = async (car: CAROut) => {
    setError(null);
    setExportingId(car.id);
    try {
      const downloaded = await downloadCarEvidencePack(car.id);
      saveDownloadedFile(downloaded);
    } catch (e: any) {
      setError(e?.message || "Failed to export evidence pack.");
    } finally {
      setExportingId(null);
    }
  };

  const openReview = async (car: CAROut) => {
    setReviewCar(car);
    const rootCauseDefault = car.root_cause_status === "SUBMITTED" || car.root_cause_status === "PENDING" ? "ACCEPTED" : ((car.root_cause_status as CarReviewForm["root_cause_status"]) || "");
    const capaDefault = car.capa_status === "SUBMITTED" || car.capa_status === "PENDING" ? "ACCEPTED" : ((car.capa_status as CarReviewForm["capa_status"]) || "");
    setReviewForm({
      root_cause_status: rootCauseDefault as CarReviewForm["root_cause_status"],
      root_cause_review_note: car.root_cause_review_note || "",
      capa_status: capaDefault as CarReviewForm["capa_status"],
      capa_review_note: car.capa_review_note || "",
      message: "",
    });
    setReviewAttachmentsLoading(true);
    try {
      await qmsListCarResponses(car.id, true);
      const files = await qmsListCarAttachments(car.id);
      setReviewAttachments(files);
    } catch (e: any) {
      pushToast({
        title: "Attachment fetch failed",
        message: e?.message || "Could not load submitted evidence attachments.",
        variant: "error",
      });
      setReviewAttachments([]);
    } finally {
      setReviewAttachmentsLoading(false);
    }
  };

  const openReviewAttachmentPreview = async (attachment: CARAttachmentOut) => {
    if (!reviewCar) return;
    setAttachmentPreviewError(null);
    setAttachmentPreviewLoadingId(attachment.id);
    try {
      const blob = await qmsDownloadCarAttachmentBlob(reviewCar.id, attachment.id);
      const objectUrl = window.URL.createObjectURL(blob);
      setAttachmentPreview({
        attachment,
        objectUrl,
        contentType: blob.type || attachment.content_type || "application/octet-stream",
        carNumber: reviewCar.car_number,
      });
    } catch (e: any) {
      const message = e?.message || "Could not open this evidence file.";
      setAttachmentPreviewError(message);
      pushToast({
        title: "Evidence preview failed",
        message,
        variant: "error",
      });
    } finally {
      setAttachmentPreviewLoadingId(null);
    }
  };

  const downloadReviewAttachment = async (attachment: CARAttachmentOut) => {
    if (!reviewCar) return;
    setAttachmentPreviewError(null);
    setAttachmentPreviewLoadingId(attachment.id);
    try {
      const blob = await qmsDownloadCarAttachmentBlob(reviewCar.id, attachment.id);
      saveDownloadedFile(blob, attachment.filename);
    } catch (e: any) {
      const message = e?.message || "Could not download this evidence file.";
      setAttachmentPreviewError(message);
      pushToast({
        title: "Evidence download failed",
        message,
        variant: "error",
      });
    } finally {
      setAttachmentPreviewLoadingId(null);
    }
  };

  const closeReviewAttachmentPreview = () => {
    setAttachmentPreview(null);
  };

  const closeReviewWorkspace = () => {
    setReviewCar(null);
    setReviewAttachments([]);
    setAttachmentPreview(null);
    setAttachmentPreviewError(null);
  };

  const submitReview = async () => {
    if (!reviewCar) return;
    const rootDecision = reviewForm.root_cause_status || "ACCEPTED";
    const capaDecision = reviewForm.capa_status || "ACCEPTED";
    if (rootDecision === "REJECTED" && !reviewForm.root_cause_review_note.trim()) {
      setError("Root cause return requires a review note.");
      return;
    }
    if ((capaDecision === "REJECTED" || capaDecision === "NEEDS_EVIDENCE") && !reviewForm.capa_review_note.trim()) {
      setError("Corrective action return or evidence request requires a review note.");
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      await qmsReviewCarResponse(reviewCar.id, {
        root_cause_status: rootDecision,
        root_cause_review_note: reviewForm.root_cause_review_note.trim() || null,
        capa_status: capaDecision,
        capa_review_note: reviewForm.capa_review_note.trim() || null,
        message: reviewForm.message.trim() || null,
      });
      pushToast({
        title: "Review submitted",
        message: `Review outcome saved for ${reviewCar.car_number}.`,
        variant: "info",
      });
      setReviewCar(null);
      setReviewAttachments([]);
      setAttachmentPreview(null);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to submit review.");
    } finally {
      setReviewBusy(false);
    }
  };

  const handleEditSave = async () => {
    if (!editingCar || !editForm) return;
    setEditBusy(true);
    setError(null);
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
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to update corrective action.");
    } finally {
      setEditBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteCar) return;
    setDeleteBusy(true);
    setError(null);
    try {
      await qmsDeleteCar(deleteCar.id);
      setDeleteCar(null);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to delete corrective action.");
    } finally {
      setDeleteBusy(false);
    }
  };

  const canManageCars =
    !!currentUser?.is_superuser ||
    !!currentUser?.is_amo_admin ||
    currentUser?.role === "QUALITY_MANAGER";

  const openCarFromHistory = (entityId: string) => {
    if (!entityId) return;
    setHistoryOpen(false);
    const next = new URLSearchParams(searchParams);
    next.set("carId", entityId);
    navigate({
      pathname: `/maintenance/${amoSlug}/quality/cars`,
      search: `?${next.toString()}`,
    });
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header qms-car-page-heading">
        <div>
          <p className="page-header__eyebrow">Quality</p>
          <h1 className="page-header__title">Corrective action register</h1>
        </div>
        <button
          type="button"
          className="secondary-chip-btn"
          onClick={() => navigate(`/maintenance/${amoSlug}/quality`)}
        >
          Back to QMS
        </button>
      </header>

      <section className="qms-car-workbench">
        <div className="qms-car-filterbar">
          <label className="qms-car-filterbar__field">
            <span>Programme</span>
            <select
              value={programFilter}
              onChange={(e) => setProgramFilter(e.target.value as CARProgram)}
            >
              {PROGRAM_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="qms-car-filterbar__field qms-car-filterbar__field--search">
            <span>Search</span>
            <input
              type="search"
              value={registerSearch}
              onChange={(e) => setRegisterSearch(e.target.value)}
              placeholder="Action reference, issue, owner, status…"
            />
          </label>
          <label className="qms-car-filterbar__field">
            <span>Status</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as CarStatusFilter)}>
              {CAR_STATUS_FILTERS.map((filter) => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
            </select>
          </label>
          <div className="qms-car-filterbar__metrics" aria-label="Corrective action summary">
            <span><strong>{overviewStats.total}</strong>Total</span>
            <span><strong>{overviewStats.open}</strong>Open</span>
            <span><strong>{overviewStats.overdue}</strong>Overdue</span>
            <span><strong>{overviewStats.inReview}</strong>Review</span>
          </div>
        </div>
      </section>

      {inviteToken && (
        <div className="card card--info" style={{ marginBottom: 12 }}>
          <p style={{ margin: 0 }}>
            Invitation token detected. Log or update the corrective action linked to the invite.
            The Quality team will be notified automatically.
          </p>
        </div>
      )}

      {state === "error" && (
        <div className="card card--error">
          <p>{error}</p>
          <button type="button" className="primary-chip-btn" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {assigneesState === "error" && assigneesError && (
        <div className="card card--warning" style={{ marginBottom: 12 }}>
          <p>{assigneesError}</p>
          <button type="button" className="secondary-chip-btn" onClick={loadAssignees}>
            Retry assignees
          </button>
        </div>
      )}

      <section className="page-section qms-car-register-shell">
        <div className="qms-car-register-card">
          <div className="qms-car-register-bar">
            <div className="qms-car-register-tabs" role="tablist" aria-label="Corrective action register sections">
              <button
                type="button"
                role="tab"
                id="car-register-tab"
                className={`qms-car-register-tab ${!historyOpen ? "is-active" : ""}`}
                aria-selected={!historyOpen}
                aria-controls="car-register-panel"
                onClick={() => setHistoryOpen(false)}
              >
                Register
              </button>
              <button
                type="button"
                role="tab"
                id="car-history-tab"
                className={`qms-car-register-tab ${historyOpen ? "is-active" : ""}`}
                aria-selected={historyOpen}
                aria-controls="car-history-panel"
                onClick={() => setHistoryOpen(true)}
              >
                Activity
              </button>
            </div>
            <div className="qms-car-register-bar__actions">
              {canManageCars && (
                <button
                  type="button"
                  className="primary-chip-btn"
                  onClick={() => setShowCreateForm((open) => !open)}
                  aria-expanded={showCreateForm}
                >
                  {showCreateForm ? "Close form" : "Log action"}
                </button>
              )}
            </div>
          </div>

          {state === "loading" && !historyOpen && <p id="car-register-panel">Loading register…</p>}

          {state === "ready" && !historyOpen && (
            <div id="car-register-panel" role="tabpanel" aria-labelledby="car-register-tab">
              <div className="qms-car-table-toolbar">
                <span>Showing {pageStartIndex}-{pageEndIndex} of {filteredCars.length}</span>
                <label>
                  Rows
                  <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value) as CarPageSize)}>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                </label>
              </div>
              <div className="table-responsive qms-car-table-wrap">
                <table className="table table-compact qms-car-table qms-car-index-table">
                  <thead>
                    <tr>
                      <th>Audit №</th>
                      <th>Audit title</th>
                      <th>CAR №</th>
                      <th>Description</th>
                      <th>Date issued</th>
                      <th>CAR category / limit</th>
                      <th>Due date</th>
                      <th>Date closed</th>
                      <th>Days out</th>
                      <th>Days remaining<br />(-Past)</th>
                      <th>Auditor remarks</th>
                      <th>Root cause</th>
                      <th>CAP<br />(Immediate / short term)</th>
                      <th>PAP<br />(Long term)</th>
                      <th>Auditor</th>
                      <th>Responsible dept. / personnel</th>
                      <th className="qms-car-index-actions-head" aria-label="Row actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedCars.map((car) => {
                      const auditKey = deriveAuditRef(car);
                      const band = auditBandMap.get(auditKey) ?? 0;
                      const assignee = car.assigned_to_user_id ? assigneeLookup.get(car.assigned_to_user_id) : undefined;
                      const canReview = car.status === "PENDING_VERIFICATION" || car.root_cause_status === "SUBMITTED" || car.capa_status === "SUBMITTED";
                      const auditorRemarks = buildAuditorRemarks(car);
                      return (
                        <tr key={car.id} className={`qms-car-index-row qms-car-index-row--band-${band}`}>
                          <td className="qms-car-index-cell qms-car-index-cell--audit-ref">{auditKey}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--audit-title">{deriveAuditTitle(car)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--number">{car.car_sequence_no || shortCarNumber(car)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--description">{cleanCarDescription(car)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--date">{dateOnly(car.date_issued || car.created_at)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--category">
                            <span className="badge badge--neutral">{car.car_category_limit || PRIORITY_LABELS[car.priority]}</span>
                          </td>
                          <td className="qms-car-index-cell qms-car-index-cell--due">{dateOnly(car.due_date)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--date">{dateOnly(car.closed_at)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--number">{car.days_out ?? daysBetween(car.date_issued || car.created_at, car.date_closed || car.closed_at)}</td>
                          <td className={`qms-car-index-cell qms-car-index-cell--number ${Number(daysRemaining(car.due_date)) < 0 && !car.closed_at ? "is-past" : ""}`}>
                            {car.days_remaining_past ?? daysRemaining(car.due_date)}
                          </td>
                          <td className="qms-car-index-cell qms-car-index-cell--remarks">
                            <span className="qms-car-remarks-note" title={auditorRemarks}>{auditorRemarks}</span>
                          </td>
                          <td className="qms-car-index-cell qms-car-index-cell--longtext">{firstText(car.register_root_cause, car.root_cause_text, car.root_cause)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--longtext">{firstText(car.register_cap, car.capa_text, car.corrective_action, car.containment_action)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--longtext">{firstText(car.register_pap, car.preventive_action)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--auditor">{firstText(car.auditor_name, car.requested_by_name, car.requested_by_user_id)}</td>
                          <td className="qms-car-index-cell qms-car-index-cell--responsible">
                            <span>{responsibleParty(car, assignee)}</span>
                          </td>
                          <td className="qms-car-index-cell qms-car-index-cell--actions">
                            <div className="qms-car-hover-actions" aria-label={`Actions for ${car.car_number}`}>
                              <CompactRowAction
                                icon="open"
                                label="Manage"
                                title="Open corrective action controls"
                                onClick={() =>
                                  setPanelContext({
                                    type: "car",
                                    id: car.id,
                                    title: car.title,
                                    status: car.status,
                                    ownerId: car.assigned_to_user_id,
                                  })
                                }
                              />
                              {canReview && (
                                <CompactRowAction
                                  icon="review"
                                  label="Review"
                                  title="Review submitted response"
                                  onClick={() => void openReview(car)}
                                />
                              )}
                              <CompactRowAction
                                icon="link"
                                label={inviteBusyId === car.id ? "Copying" : "Invite"}
                                title="Copy invite link"
                                onClick={() => handleCopyInvite(car)}
                                disabled={inviteBusyId === car.id}
                              />
                              <CompactRowAction
                                icon="download"
                                label={exportingId === car.id ? "Exporting" : "Export"}
                                title="Export evidence pack"
                                onClick={() => handleExport(car)}
                                disabled={exportingId === car.id}
                              />
                              {canManageCars && (
                                <CompactRowAction
                                  icon="trash"
                                  label="Delete"
                                  title="Delete corrective action"
                                  danger
                                  onClick={() => setDeleteCar(car)}
                                />
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {filteredCars.length === 0 && (
                      <tr>
                        <td colSpan={17} className="text-muted">
                          No corrective actions logged for this programme yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="qms-car-pagination" aria-label="Corrective action register pagination">
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={safeCurrentPage <= 1}
                >
                  Previous
                </button>
                <span>Page {safeCurrentPage} of {totalPages}</span>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={safeCurrentPage >= totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {historyOpen && (
            <div
              id="car-history-panel"
              className="qms-car-history-panel"
              role="tabpanel"
              aria-labelledby="car-history-tab"
            >
              <p className="text-muted" style={{ margin: 0 }}>
                Activity timeline for changes, responses, and reviewer decisions.
              </p>
              <AuditHistoryPanel
                title="Activity timeline"
                entityType="qms_car"
                limit={16}
                currentUserId={currentUser?.id}
                onEventOpen={(event) => openCarFromHistory(event.entity_id)}
              />
            </div>
          )}
        </div>
      </section>

      {canManageCars && showCreateForm && (
      <section className="page-section">
        <div className="card qms-car-form-card">
          <div className="card-header">
            <h2>Log corrective action</h2>
            <p className="text-muted">
              Assign an owner, priority, due date, and concise action summary.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="form-grid qms-car-form">
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

            <label className="form-control form-control--full">
              <span>Title</span>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="Short, action-oriented title"
                required
              />
            </label>

            <label className="form-control form-control--full">
              <span>Summary</span>
              <textarea
                value={form.summary}
                onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
                placeholder="Detail the finding, containment, and requested corrective actions."
                rows={3}
                required
              />
            </label>


            <label className="form-control form-control--full">
              <span>Finding ID (NC finding)</span>
              <input
                type="text"
                value={form.finding_id}
                onChange={(e) => setForm((f) => ({ ...f, finding_id: e.target.value }))}
                placeholder="Paste non-conformity finding ID"
                required
              />
            </label>
            <label className="form-control">
              <span>Target closure date</span>
              <input
                type="date"
                value={form.target_closure_date}
                onChange={(e) =>
                  setForm((f) => ({ ...f, target_closure_date: e.target.value }))
                }
              />
            </label>

            <label className="form-control">
              <span>Due date</span>
              <input
                type="date"
                value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              />
            </label>

            <label className="form-control">
              <span>Responsible department</span>
              <select
                value={form.assigned_department_id}
                onChange={(e) => {
                  setForm((f) => ({
                    ...f,
                    assigned_department_id: e.target.value,
                    assigned_to_user_id: "",
                  }));
                  setAssigneeSearch("");
                }}
              >
                <option value="">All departments</option>
                {departmentOptions.map((dept) => (
                  <option key={dept.id} value={dept.id}>
                    {dept.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-control qms-car-assignee-search">
              <span>Search assignees</span>
              <input
                type="text"
                value={assigneeSearch}
                onChange={(e) => setAssigneeSearch(e.target.value)}
                onKeyDown={handleAssigneeSearchKeyDown}
                placeholder="Search by name, email, or staff code"
                autoComplete="off"
              />
              {assigneeSearch.trim() && assigneeSuggestions.length > 0 && (
                <ul className="qms-car-assignee-suggestions" role="listbox" aria-label="Assignee suggestions">
                  {assigneeSuggestions.map((assignee) => (
                    <li key={assignee.id}>
                      <button
                        type="button"
                        className="qms-car-assignee-suggestion"
                        onClick={() => selectAssignee(assignee.id)}
                      >
                        <strong>{assignee.full_name}</strong>
                        <span>
                          {assignee.email || assignee.staff_code || "No contact info"}
                          {assignee.department_name ? ` · ${assignee.department_name}` : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {assigneeSearch.trim() && assigneeSuggestions.length === 0 && (
                <span className="text-muted">No matching assignees.</span>
              )}
            </label>

            <div className="form-control form-control--full qms-car-assignee-selected" aria-live="polite">
              <span>Responsible owner</span>
              {selectedAssignee ? (
                <div className="qms-car-assignee-pill">
                  <div>
                    <strong>{selectedAssignee.full_name}</strong>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {selectedAssignee.email || selectedAssignee.staff_code || "No contact info"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={() => setForm((prev) => ({ ...prev, assigned_to_user_id: "" }))}
                  >
                    Clear
                  </button>
                </div>
              ) : (
                <p className="text-muted" style={{ margin: 0 }}>
                  Unassigned. Type in the search box to select an owner.
                </p>
              )}
            </div>

            <div>
              <button type="submit" className="primary-chip-btn">
                Preview & create
              </button>
            </div>
          </form>
        </div>
      </section>
      )}

      {reviewQueue.length > 0 && (
        <section className="page-section qms-car-review-queue">
          <div className="qms-car-register-card">
            <div className="qms-car-register-bar">
              <div>
                <h2>Review queue</h2>
                <p className="text-muted">Submitted responses awaiting auditor decision.</p>
              </div>
              <span className="badge badge--warning">{reviewQueue.length} pending</span>
            </div>
            <div className="table-responsive qms-car-table-wrap">
              <table className="table table-compact qms-car-table">
                <thead>
                  <tr>
                    <th>Action ref</th>
                    <th>Submission</th>
                    <th>Root cause</th>
                    <th>Corrective action</th>
                    <th>Evidence</th>
                    <th>Stage</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {reviewQueue.map((car) => (
                    <tr key={`review-${car.id}`}>
                      <td>{car.car_number}</td>
                      <td>
                        <div>{car.submitted_by_name || "Auditee"}</div>
                        <div className="text-muted">{car.submitted_at ? new Date(car.submitted_at).toLocaleString() : "Not submitted"}</div>
                      </td>
                      <td>{car.root_cause_status || "Pending"}</td>
                      <td>{car.capa_status || "Pending"}</td>
                      <td>{car.evidence_received_at ? "Received" : "Missing"}</td>
                      <td>{getCarWorkflowStep(car)}</td>
                      <td>
                        <button type="button" className="secondary-chip-btn" onClick={() => void openReview(car)}>
                          Review
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {reviewCar && (
        <div className="upsell-modal__backdrop qms-car-review-backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal qms-car-review-modal">
            <div className="upsell-modal__header qms-car-review-header">
              <div>
                <p className="upsell-modal__eyebrow">Reviewer workspace</p>
                <h3 className="upsell-modal__title">{reviewCar.car_number} · {reviewCar.title}</h3>
                <p className="text-muted" style={{ marginTop: 4 }}>
                  {getCarWorkflowStep(reviewCar)} · Submitted {reviewCar.submitted_at ? new Date(reviewCar.submitted_at).toLocaleString() : "not yet"}
                </p>
              </div>
              <button type="button" className="upsell-modal__close" onClick={closeReviewWorkspace} disabled={reviewBusy}>×</button>
            </div>

            <div className="upsell-modal__body qms-car-review-body">
              <section className="qms-car-review-section qms-car-review-section--finding">
                <div>
                  <span className="qms-car-review-kicker">Finding to close</span>
                  <h4>{reviewCar.summary || reviewCar.title}</h4>
                  <p className="text-muted">
                    Finding ref: {reviewCar.title?.replace(/^CAR for\s+/i, "") || reviewCar.finding_id || "—"}
                  </p>
                </div>
                <div className="qms-car-review-status-grid">
                  <span><strong>Status</strong>{reviewCar.status}</span>
                  <span><strong>Priority</strong>{PRIORITY_LABELS[reviewCar.priority]}</span>
                  <span><strong>Due</strong>{reviewCar.due_date || "—"}</span>
                </div>
              </section>

              <div className="qms-car-review-grid">
                <section className="qms-car-review-section">
                  <span className="qms-car-review-kicker">Submitted by auditee</span>
                  <dl className="qms-car-review-dl">
                    <div><dt>Name</dt><dd>{reviewCar.submitted_by_name || "—"}</dd></div>
                    <div><dt>Email</dt><dd>{reviewCar.submitted_by_email || "—"}</dd></div>
                    <div><dt>Containment</dt><dd>{reviewCar.containment_action || "—"}</dd></div>
                    <div><dt>Root cause</dt><dd>{reviewCar.root_cause_text || reviewCar.root_cause || "—"}</dd></div>
                    <div><dt>Corrective action</dt><dd>{reviewCar.capa_text || reviewCar.corrective_action || "—"}</dd></div>
                    <div><dt>Evidence reference</dt><dd>{reviewCar.evidence_ref || "—"}</dd></div>
                  </dl>
                </section>

                <section className="qms-car-review-section qms-car-review-section--evidence">
                  <div className="qms-car-review-section-head">
                    <div>
                      <span className="qms-car-review-kicker">Evidence submitted</span>
                      <h4>{reviewAttachments.length} attachment{reviewAttachments.length === 1 ? "" : "s"}</h4>
                    </div>
                    {reviewAttachmentsLoading && <span className="badge badge--info">Loading…</span>}
                  </div>
                  {attachmentPreviewError && <p className="qms-car-review-error">{attachmentPreviewError}</p>}
                  {!reviewAttachmentsLoading && reviewAttachments.length === 0 ? (
                    <p className="text-muted">No evidence files have been attached.</p>
                  ) : null}
                  <div className="qms-car-review-evidence-list">
                    {reviewAttachments.map((file) => (
                      <article key={file.id} className="qms-car-review-evidence-item">
                        <button
                          type="button"
                          className="qms-car-review-evidence-main"
                          onClick={() => void openReviewAttachmentPreview(file)}
                          disabled={attachmentPreviewLoadingId === file.id}
                        >
                          <span className="qms-car-review-file-icon">{evidenceIcon(file)}</span>
                          <span>
                            <strong>{file.description || file.filename}</strong>
                            {file.description && <small>{file.filename}</small>}
                            <small>{file.content_type || "file"} · {formatFileSize(file.size_bytes)}</small>
                          </span>
                        </button>
                        <div className="qms-car-review-evidence-actions">
                          <button type="button" className="secondary-chip-btn" onClick={() => void openReviewAttachmentPreview(file)} disabled={attachmentPreviewLoadingId === file.id}>
                            {attachmentPreviewLoadingId === file.id ? "Opening…" : "Preview"}
                          </button>
                          <button type="button" className="secondary-chip-btn" onClick={() => void downloadReviewAttachment(file)} disabled={attachmentPreviewLoadingId === file.id}>
                            Download
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              </div>

              <section className="qms-car-review-section qms-car-review-section--decision">
                <div className="qms-car-review-section-head">
                  <div>
                    <span className="qms-car-review-kicker">Reviewer decision</span>
                    <h4>Accept, return, or request evidence</h4>
                  </div>
                </div>
                <div className="qms-grid qms-car-review-decision-grid">
                  <label className="qms-field">
                    Root cause decision
                    <select value={reviewForm.root_cause_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_status: e.target.value as CarReviewForm["root_cause_status"] }))}>
                      <option value="ACCEPTED">Accept root cause</option>
                      <option value="REJECTED">Return root cause</option>
                    </select>
                  </label>
                  <label className="qms-field">
                    Corrective action decision
                    <select value={reviewForm.capa_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_status: e.target.value as CarReviewForm["capa_status"] }))}>
                      <option value="ACCEPTED">Accept action</option>
                      <option value="NEEDS_EVIDENCE">Needs evidence</option>
                      <option value="REJECTED">Return action</option>
                    </select>
                  </label>
                </div>
                <div className="qms-grid qms-car-review-decision-grid">
                  <label className="qms-field">
                    Root cause note
                    <textarea rows={3} value={reviewForm.root_cause_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_review_note: e.target.value }))} placeholder="Required when returning root cause." />
                  </label>
                  <label className="qms-field">
                    Action note
                    <textarea rows={3} value={reviewForm.capa_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_review_note: e.target.value }))} placeholder="Required when returning or requesting more evidence." />
                  </label>
                </div>
                <label className="qms-field">
                  Reviewer message / action note
                  <textarea rows={3} value={reviewForm.message} onChange={(e) => setReviewForm((prev) => ({ ...prev, message: e.target.value }))} placeholder="Visible in the action log." />
                </label>
              </section>
            </div>
            <div className="upsell-modal__actions qms-car-review-actions">
              <button type="button" className="secondary-chip-btn" onClick={closeReviewWorkspace} disabled={reviewBusy}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={() => void submitReview()} disabled={reviewBusy}>
                {reviewBusy ? "Submitting…" : "Submit review"}
              </button>
            </div>
          </div>
        </div>
      )}

      {attachmentPreview && (() => {
        const kind = evidenceKind({ ...attachmentPreview.attachment, content_type: attachmentPreview.contentType });
        const canEmbed = kind === "image" || kind === "video" || kind === "pdf";
        return (
          <div className="qms-car-evidence-preview-backdrop" role="dialog" aria-modal="true" aria-label="Evidence preview">
            <div className="qms-car-evidence-preview">
              <header className="qms-car-evidence-preview__header">
                <div>
                  <p className="qms-car-review-kicker">Evidence preview · {attachmentPreview.carNumber}</p>
                  <h3>{attachmentPreview.attachment.description || attachmentPreview.attachment.filename}</h3>
                  {attachmentPreview.attachment.description && <p className="text-muted">{attachmentPreview.attachment.filename}</p>}
                </div>
                <div className="qms-car-review-evidence-actions">
                  <button type="button" className="secondary-chip-btn" onClick={() => void downloadReviewAttachment(attachmentPreview.attachment)}>Download</button>
                  <button type="button" className="upsell-modal__close" onClick={closeReviewAttachmentPreview}>×</button>
                </div>
              </header>
              <div className="qms-car-evidence-preview__surface">
                {kind === "image" && <img src={attachmentPreview.objectUrl} alt={attachmentPreview.attachment.filename} />}
                {kind === "video" && <video src={attachmentPreview.objectUrl} controls playsInline />}
                {kind === "pdf" && <iframe src={attachmentPreview.objectUrl} title={attachmentPreview.attachment.filename} />}
                {!canEmbed && (
                  <div className="qms-car-evidence-preview__fallback">
                    <span className="qms-car-review-file-icon">{evidenceIcon(attachmentPreview.attachment)}</span>
                    <h4>Preview not supported by this browser</h4>
                    <p>{attachmentPreview.attachment.filename}</p>
                    <button type="button" className="primary-chip-btn" onClick={() => void downloadReviewAttachment(attachmentPreview.attachment)}>Download file</button>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {previewOpen && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Preview</p>
                <h3 className="upsell-modal__title">Confirm corrective action details</h3>
                <p className="upsell-modal__subtitle">
                  Please confirm the information below before creating this action.
                </p>
              </div>
              <button
                type="button"
                className="upsell-modal__close"
                onClick={() => setPreviewOpen(false)}
              >
                ✕
              </button>
            </div>

            <div className="upsell-modal__body">
              <div className="modal-field">
                <strong>Programme</strong>
                <span>{form.program}</span>
              </div>
              <div className="modal-field">
                <strong>Priority</strong>
                <span>{PRIORITY_LABELS[form.priority]}</span>
              </div>
              <div className="modal-field">
                <strong>Title</strong>
                <span>{form.title.trim()}</span>
              </div>
              <div className="modal-field">
                <strong>Summary</strong>
                <span>{form.summary.trim()}</span>
              </div>
              <div className="modal-field">
                <strong>Target closure date</strong>
                <span>{form.target_closure_date || "—"}</span>
              </div>
              <div className="modal-field">
                <strong>Due date</strong>
                <span>{form.due_date || "—"}</span>
              </div>
              <div className="modal-field">
                <strong>Responsible owner</strong>
                <span>
                  {form.assigned_to_user_id
                    ? assigneeLookup.get(form.assigned_to_user_id)?.full_name || "Assigned user"
                    : "Unassigned"}
                </span>
              </div>
            </div>

            <div className="upsell-modal__actions">
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => setPreviewOpen(false)}
                disabled={previewBusy}
              >
                Go back
              </button>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={handleConfirmCreate}
                disabled={previewBusy}
              >
                {previewBusy ? "Creating…" : "Confirm & create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {editingCar && editForm && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Edit</p>
                <h3 className="upsell-modal__title">Update corrective action</h3>
                <p className="upsell-modal__subtitle">
                  Adjust details for {editingCar.car_number}.
                </p>
              </div>
              <button
                type="button"
                className="upsell-modal__close"
                onClick={() => {
                  setEditingCar(null);
                  setEditForm(null);
                }}
              >
                ✕
              </button>
            </div>

            <div className="upsell-modal__body">
              <label className="modal-field">
                <span>Title</span>
                <input
                  value={editForm.title}
                  onChange={(e) =>
                    setEditForm((prev) => (prev ? { ...prev, title: e.target.value } : prev))
                  }
                />
              </label>
              <label className="modal-field">
                <span>Summary</span>
                <textarea
                  value={editForm.summary}
                  onChange={(e) =>
                    setEditForm((prev) => (prev ? { ...prev, summary: e.target.value } : prev))
                  }
                  rows={4}
                />
              </label>
              <label className="modal-field">
                <span>Priority</span>
                <select
                  value={editForm.priority}
                  onChange={(e) =>
                    setEditForm((prev) =>
                      prev ? { ...prev, priority: e.target.value as CARPriority } : prev
                    )
                  }
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Critical</option>
                </select>
              </label>
              <label className="modal-field">
                <span>Target closure date</span>
                <input
                  type="date"
                  value={editForm.target_closure_date}
                  onChange={(e) =>
                    setEditForm((prev) =>
                      prev ? { ...prev, target_closure_date: e.target.value } : prev
                    )
                  }
                />
              </label>
              <label className="modal-field">
                <span>Due date</span>
                <input
                  type="date"
                  value={editForm.due_date}
                  onChange={(e) =>
                    setEditForm((prev) =>
                      prev ? { ...prev, due_date: e.target.value } : prev
                    )
                  }
                />
              </label>
              <label className="modal-field">
                <span>Responsible department</span>
                <select
                  value={editForm.assigned_department_id}
                  onChange={(e) =>
                    setEditForm((prev) =>
                      prev
                        ? {
                            ...prev,
                            assigned_department_id: e.target.value,
                            assigned_to_user_id: "",
                          }
                        : prev
                    )
                  }
                >
                  <option value="">All departments</option>
                  {departmentOptions.map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="modal-field">
                <span>Assignee search</span>
                <input
                  value={assigneeSearch}
                  onChange={(e) => setAssigneeSearch(e.target.value)}
                  placeholder="Search by name, email, or staff code"
                />
              </label>
              <label className="modal-field">
                <span>Responsible owner</span>
                <select
                  value={editForm.assigned_to_user_id}
                  onChange={(e) =>
                    setEditForm((prev) =>
                      prev ? { ...prev, assigned_to_user_id: e.target.value } : prev
                    )
                  }
                >
                  <option value="">Unassigned</option>
                  {assignees
                    .filter((assignee) => {
                      if (
                        editForm.assigned_department_id &&
                        assignee.department_id !== editForm.assigned_department_id
                      ) {
                        return false;
                      }
                      const search = assigneeSearch.trim().toLowerCase();
                      if (!search) return true;
                      return (
                        assignee.full_name.toLowerCase().includes(search) ||
                        (assignee.email || "").toLowerCase().includes(search) ||
                        (assignee.staff_code || "").toLowerCase().includes(search)
                      );
                    })
                    .map((assignee) => (
                      <option key={assignee.id} value={assignee.id}>
                        {assignee.full_name}
                        {assignee.department_name ? ` · ${assignee.department_name}` : ""}
                      </option>
                    ))}
                </select>
              </label>
            </div>

            <div className="upsell-modal__actions">
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => {
                  setEditingCar(null);
                  setEditForm(null);
                }}
                disabled={editBusy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={handleEditSave}
                disabled={editBusy}
              >
                {editBusy ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteCar && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Delete</p>
                <h3 className="upsell-modal__title">Remove corrective action?</h3>
                <p className="upsell-modal__subtitle">
                  {deleteCar.car_number} will be permanently removed.
                </p>
              </div>
              <button
                type="button"
                className="upsell-modal__close"
                onClick={() => setDeleteCar(null)}
              >
                ✕
              </button>
            </div>
            <div className="upsell-modal__actions">
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => setDeleteCar(null)}
                disabled={deleteBusy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={handleDelete}
                disabled={deleteBusy}
              >
                {deleteBusy ? "Deleting…" : "Confirm delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {!canManageCars && (
        <div className="card card--info" style={{ marginTop: 12 }}>
          <p style={{ margin: 0 }}>
            Updates are limited to assigned auditors, Quality Managers, AMO Admins, and superusers.
          </p>
        </div>
      )}
      <ActionPanel
        isOpen={!!panelContext}
        context={panelContext}
        onClose={() => setPanelContext(null)}
      />
    </DepartmentLayout>
  );
};

export default QualityCarsPage;

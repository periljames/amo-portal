import React, { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronRight, ChevronsLeft, ChevronsRight, FileUp, Loader2, Plus, Search, ShieldCheck, TriangleAlert, UserRound, X } from "lucide-react";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { useToast } from "../components/feedback/ToastProvider";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getCachedUser, getContext } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import {
  type CAROut,
  type CARAssignee,
  type CARPriority,
  type CARProgram,
  type CARStatus,
  type CARAttachmentOut,
  downloadCarEvidencePack,
  qmsCreateCar,
  qmsDeleteCar,
  qmsGetCarInvite,
  qmsListCarAssignees,
  qmsListCarAttachments,
  qmsListCars,
  qmsReviewCarResponse,
  qmsUpdateCar,
  qmsUploadCarAttachment,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";
type AssigneeLoadState = "idle" | "loading" | "ready" | "error";
type FormStep = 1 | 2;

type CarReviewForm = {
  root_cause_status: "ACCEPTED" | "REJECTED" | "";
  root_cause_review_note: string;
  capa_status: "ACCEPTED" | "REJECTED" | "NEEDS_EVIDENCE" | "";
  capa_review_note: string;
  message: string;
};

const PROGRAM_OPTIONS: Array<{ value: CARProgram; label: string }> = [
  { value: "QUALITY", label: "Quality" },
  { value: "RELIABILITY", label: "Reliability" },
];

const PRIORITY_META: Record<CARPriority, { label: string; className: string }> = {
  LOW: { label: "Low", className: "border border-emerald-500/30 bg-emerald-500/15 text-emerald-200" },
  MEDIUM: { label: "Medium", className: "border border-amber-500/30 bg-amber-500/15 text-amber-200" },
  HIGH: { label: "High", className: "border border-rose-500/30 bg-rose-500/15 text-rose-200" },
  CRITICAL: { label: "Critical", className: "border border-rose-400/40 bg-rose-400/20 text-rose-100" },
};

const STATUS_META: Record<CARStatus, { label: string; className: string }> = {
  DRAFT: { label: "Draft", className: "border border-slate-600 bg-slate-800/70 text-slate-200" },
  OPEN: { label: "Open", className: "border border-sky-500/30 bg-sky-500/15 text-sky-200" },
  IN_PROGRESS: { label: "In progress", className: "border border-amber-500/30 bg-amber-500/15 text-amber-200" },
  PENDING_VERIFICATION: { label: "Pending verification", className: "border border-violet-500/30 bg-violet-500/15 text-violet-200" },
  CLOSED: { label: "Closed", className: "border border-emerald-500/30 bg-emerald-500/15 text-emerald-200" },
  ESCALATED: { label: "Escalated", className: "border border-rose-500/30 bg-rose-500/15 text-rose-200" },
  CANCELLED: { label: "Cancelled", className: "border border-slate-600 bg-slate-800/70 text-slate-300" },
};

const WORKFLOW_STAGES = ["Root Cause", "CAPA", "Evidence", "Closure"] as const;

const carFormSchema = z
  .object({
    title: z.string().trim().min(3, "Title is required"),
    summary: z.string().trim().min(10, "Summary should explain the finding and action requested"),
    program: z.enum(["QUALITY", "RELIABILITY"]),
    priority: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
    target_closure_date: z.string().optional().default(""),
    due_date: z.string().optional().default(""),
    assigned_department_id: z.string().optional().default(""),
    assigned_to_user_id: z.string().optional().default(""),
    finding_id: z.string().trim().min(1, "Finding ID is required"),
  })
  .superRefine((values, ctx) => {
    if (values.target_closure_date && values.due_date && values.target_closure_date > values.due_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Target closure date must be on or before the due date",
        path: ["target_closure_date"],
      });
    }
  });

type CarFormValues = z.infer<typeof carFormSchema>;

const getCarWorkflowIndex = (car: CAROut): number => {
  if (car.status === "CLOSED") return 4;
  if (car.evidence_received_at || car.evidence_verified_at) return 3;
  if (car.capa_status === "ACCEPTED" || car.capa_status === "NEEDS_EVIDENCE" || car.capa_status === "REJECTED") return 2;
  if (car.root_cause_status === "ACCEPTED" || car.root_cause_status === "REJECTED" || car.submitted_at) return 1;
  return 0;
};

const getCarWorkflowStep = (car: CAROut): string => {
  if (!car.submitted_at) return "Awaiting auditee response";
  if (car.root_cause_status === "REJECTED" || car.capa_status === "REJECTED") return "Returned to auditee";
  if (car.root_cause_status === "ACCEPTED" && car.capa_status === "NEEDS_EVIDENCE") return "Waiting for more evidence";
  if (car.status === "PENDING_VERIFICATION") return "Pending verification / closeout";
  if (car.status === "CLOSED") return "Closed";
  return "Under reviewer assessment";
};

const formatDate = (value?: string | null) => (value ? new Date(value).toLocaleDateString() : "—");
const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "—");

const dueHeatClass = (value?: string | null) => {
  if (!value) return "text-slate-400";
  const diffHours = (new Date(value).getTime() - Date.now()) / (1000 * 60 * 60);
  if (diffHours < 0) return "text-rose-300";
  if (diffHours <= 48) return "text-orange-300";
  return "text-slate-200";
};

const WorkflowPips: React.FC<{ car: CAROut }> = ({ car }) => {
  const currentIndex = getCarWorkflowIndex(car);
  return (
    <div className="flex items-center gap-1.5" aria-label={`Workflow stage ${getCarWorkflowStep(car)}`}>
      {WORKFLOW_STAGES.map((stage, index) => {
        const complete = index < currentIndex;
        const active = index === currentIndex && currentIndex < WORKFLOW_STAGES.length;
        return (
          <div
            key={stage}
            className={[
              "h-2.5 w-2.5 rounded-full border transition-all",
              complete ? "border-cyan-300 bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.45)]" : "border-slate-600 bg-slate-800",
              active ? "scale-110 ring-2 ring-cyan-400/30" : "",
            ].join(" ")}
            title={stage}
          />
        );
      })}
    </div>
  );
};

const QualityCarsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";
  const { pushToast } = useToast();

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [programFilter, setProgramFilter] = useState<CARProgram>("QUALITY");
  const inviteToken = searchParams.get("invite");
  const [showCreatePanel, setShowCreatePanel] = useState(Boolean(inviteToken));

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
  const [editAssigneeSearch, setEditAssigneeSearch] = useState("");

  const [submittingCreate, setSubmittingCreate] = useState(false);
  const [editingCar, setEditingCar] = useState<CAROut | null>(null);
  const [editForm, setEditForm] = useState<CarFormValues | null>(null);
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
  const [uploadingEvidenceId, setUploadingEvidenceId] = useState<string | null>(null);
  const [draggedCarId, setDraggedCarId] = useState<string | null>(null);
  const [reviewForm, setReviewForm] = useState<CarReviewForm>({
    root_cause_status: "",
    root_cause_review_note: "",
    capa_status: "",
    capa_review_note: "",
    message: "",
  });

  const inviteToken = searchParams.get("invite");

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<CarFormValues>({
    resolver: zodResolver(carFormSchema),
    defaultValues: {
      title: "",
      summary: "",
      program: "QUALITY",
      priority: "MEDIUM",
      due_date: "",
      target_closure_date: "",
      assigned_department_id: "",
      assigned_to_user_id: "",
      finding_id: "",
    },
  });

  const watchedFindingId = watch("finding_id");
  const watchedAssignedDepartmentId = watch("assigned_department_id");
  const watchedAssignedOwnerId = watch("assigned_to_user_id");

  const assigneeLookup = useMemo(() => new Map(assignees.map((a) => [a.id, a])), [assignees]);

  const selectedCar = useMemo(() => cars.find((car) => car.id === selectedCarId) ?? null, [cars, selectedCarId]);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const next = await qmsListCars({ program: programFilter });
      setCars(next);
      setState("ready");
      setSelectedCarId((current) => current ?? next[0]?.id ?? null);
    } catch (e: any) {
      setError(e?.message || "Failed to load CAR register.");
      setState("error");
    }
  };

  const loadAssignees = async () => {
    setAssigneesState("loading");
    setAssigneesError(null);
    try {
      setAssignees(await qmsListCarAssignees());
      setAssigneesState("ready");
    } catch (e: any) {
      setAssigneesError(e?.message || "Failed to load assignees.");
      setAssigneesState("error");
    }
  };

  useEffect(() => { void load(); }, [programFilter]);
  useEffect(() => { void loadAssignees(); }, []);

  useEffect(() => {
    const finding = watchedFindingId.trim();
    if (!finding) {
      setFindingLookupState("idle");
      setFindingLookupMessage("Enter a non-conformity finding ID.");
      return;
    }
    setFindingLookupState("checking");
    const timer = window.setTimeout(() => {
      const duplicate = cars.some((car) => (car.finding_id || "").toLowerCase() === finding.toLowerCase());
      if (duplicate) {
        setFindingLookupState("warning");
        setFindingLookupMessage("A CAR already exists for this finding in the current register.");
      } else {
        setFindingLookupState("valid");
        setFindingLookupMessage("Finding ID looks clear for CAR creation.");
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [watchedFindingId, cars]);

  useEffect(() => {
    setValue("program", programFilter);
  }, [programFilter, setValue]);

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

  const ownerSuggestions = useMemo(() => {
    const search = assigneeSearch.trim().toLowerCase();
    return assignees
      .filter((assignee) => {
        if (watchedAssignedDepartmentId && assignee.department_id !== watchedAssignedDepartmentId) return false;
        if (!search) return true;
        return [assignee.full_name, assignee.email || "", assignee.staff_code || "", assignee.department_name || ""]
          .join(" ")
          .toLowerCase()
          .includes(search);
      })
      .slice(0, 8);
  }, [assignees, assigneeSearch, watchedAssignedDepartmentId]);

  const filteredCars = useMemo(() => {
    const dueWindow = searchParams.get("dueWindow");
    const carId = searchParams.get("carId");
    const now = new Date();
    return cars.filter((car) => {
      if (carId && car.id !== carId) return false;
      if (statusFilter === "overdue") {
        if (!car.due_date) return false;
        return new Date(car.due_date) < now && car.status !== "CLOSED";
      }
      if (statusFilter !== "all" && statusFilter !== "open" && car.status !== statusFilter) return false;
      if (statusFilter === "open" && car.status === "CLOSED") return false;
      if (dueWindow && car.due_date) {
        const diff = (new Date(car.due_date).getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
        if (dueWindow === "now" && diff >= 0) return false;
        if (dueWindow === "today" && Math.floor(diff) !== 0) return false;
        if (dueWindow === "week" && !(diff >= 0 && diff <= 7)) return false;
        if (dueWindow === "month" && !(diff >= 0 && diff <= 30)) return false;
      }
      return true;
    });
  }, [cars, searchParams, statusFilter]);

  const reviewQueue = useMemo(() => cars
    .filter((car) => !!car.submitted_at || car.status === "IN_PROGRESS" || car.status === "PENDING_VERIFICATION")
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()), [cars]);

  const statusCounts = useMemo(() => ({
    all: cars.length,
    overdue: cars.filter((car) => car.due_date && new Date(car.due_date) < new Date() && car.status !== "CLOSED").length,
    open: cars.filter((car) => car.status !== "CLOSED").length,
    PENDING_VERIFICATION: cars.filter((car) => car.status === "PENDING_VERIFICATION").length,
    ESCALATED: cars.filter((car) => car.status === "ESCALATED").length,
    CLOSED: cars.filter((car) => car.status === "CLOSED").length,
  }), [cars]);

  const submitCreate = handleSubmit(async (values) => {
    setSubmittingCreate(true);
    setError(null);

    const tempId = `temp-${Date.now()}`;
    const optimisticCar: CAROut = {
      id: tempId,
      program: values.program,
      car_number: "Generating…",
      title: values.title.trim(),
      summary: values.summary.trim(),
      priority: values.priority,
      status: "OPEN",
      due_date: values.due_date || null,
      target_closure_date: values.target_closure_date || null,
      closed_at: null,
      escalated_at: null,
      finding_id: values.finding_id.trim(),
      requested_by_user_id: currentUser?.id || null,
      assigned_to_user_id: values.assigned_to_user_id || null,
      invite_token: "",
      reminder_interval_days: 7,
      next_reminder_at: null,
      evidence_required: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    setCars((prev) => [optimisticCar, ...prev]);
    setSelectedCarId(tempId);
    setDrawerOpen(false);

    try {
      const created = await qmsCreateCar({
        program: values.program,
        title: values.title.trim(),
        summary: values.summary.trim(),
        priority: values.priority,
        due_date: values.due_date || null,
        target_closure_date: values.target_closure_date || null,
        assigned_to_user_id: values.assigned_to_user_id || null,
        finding_id: values.finding_id.trim(),
      });
      setCars((prev) => prev.map((car) => (car.id === tempId ? created : car)));
      setSelectedCarId(created.id);
      reset({
        title: "",
        summary: "",
        program: values.program,
        priority: "MEDIUM",
        due_date: "",
        target_closure_date: "",
        assigned_department_id: "",
        assigned_to_user_id: "",
        finding_id: "",
      });
      setAssigneeSearch("");
      setFormStep(1);
      pushToast({ title: "CAR created", message: `${created.car_number} synced to the register.`, variant: "info" });
    } catch (e: any) {
      setCars((prev) => prev.filter((car) => car.id !== tempId));
      setError(e?.message || "Failed to create CAR");
      setDrawerOpen(true);
    } finally {
      setSubmittingCreate(false);
    }
  });

  const handleCopyInvite = async (car: CAROut) => {
    setInviteBusyId(car.id);
    try {
      const invite = await qmsGetCarInvite(car.id);
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(invite.invite_url);
        pushToast({ title: "Invite link copied", message: invite.invite_url, variant: "info" });
      } else {
        window.prompt("Copy CAR invite link:", invite.invite_url);
      }
    } catch (e: any) {
      pushToast({ title: "Invite failed", message: e?.message || "Unable to fetch the invite link.", variant: "error" });
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
    setEditAssigneeSearch("");
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
      setError(e?.message || "Failed to update CAR");
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
      setError(e?.message || "Failed to delete CAR");
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleExport = async (car: CAROut) => {
    setExportingId(car.id);
    setError(null);
    try {
      const blob = await downloadCarEvidencePack(car.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `car_${car.car_number}_evidence_pack.zip`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.message || "Failed to export CAR evidence pack.");
    } finally {
      setExportingId(null);
    }
  };

  const openReview = async (car: CAROut) => {
    setReviewCar(car);
    setReviewForm({
      root_cause_status: (car.root_cause_status as CarReviewForm["root_cause_status"]) || "",
      root_cause_review_note: car.root_cause_review_note || "",
      capa_status: (car.capa_status as CarReviewForm["capa_status"]) || "",
      capa_review_note: car.capa_review_note || "",
      message: "",
    });
    setReviewAttachmentsLoading(true);
    try {
      setReviewAttachments(await qmsListCarAttachments(car.id));
    } catch (e: any) {
      pushToast({ title: "Attachment fetch failed", message: e?.message || "Could not load submitted evidence attachments.", variant: "error" });
      setReviewAttachments([]);
    } finally {
      setReviewAttachmentsLoading(false);
    }
  };

  const submitReview = async () => {
    if (!reviewCar) return;
    setReviewBusy(true);
    setError(null);
    try {
      await qmsReviewCarResponse(reviewCar.id, {
        root_cause_status: reviewForm.root_cause_status || undefined,
        root_cause_review_note: reviewForm.root_cause_review_note.trim() || null,
        capa_status: reviewForm.capa_status || undefined,
        capa_review_note: reviewForm.capa_review_note.trim() || null,
        message: reviewForm.message.trim() || null,
      });
      pushToast({ title: "CAR review submitted", message: `Review outcome saved for ${reviewCar.car_number}.`, variant: "info" });
      setReviewCar(null);
      setReviewAttachments([]);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to submit CAR review.");
    } finally {
      setReviewBusy(false);
    }
  };

  const uploadEvidence = async (car: CAROut, files: FileList | File[]) => {
    const uploadList = Array.from(files);
    if (uploadList.length === 0) return;
    setUploadingEvidenceId(car.id);
    try {
      await Promise.all(uploadList.map((file) => qmsUploadCarAttachment(car.id, file)));
      pushToast({ title: "Evidence uploaded", message: `${uploadList.length} file(s) attached to ${car.car_number}.`, variant: "info" });
      if (reviewCar?.id === car.id) {
        setReviewAttachments(await qmsListCarAttachments(car.id));
      }
      await load();
    } catch (e: any) {
      pushToast({ title: "Upload failed", message: e?.message || "Could not upload evidence.", variant: "error" });
    } finally {
      setUploadingEvidenceId(null);
      setDraggedCarId(null);
    }
  };

  const canManageCars = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER";

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">
          Corrective Action Requests · {amoDisplay}
        </h1>
        <p className="page-header__subtitle">
          Focused command center for the live CAR register, review queue, and owner follow-up.
        </p>
      </header>

      <section className="page-section" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <select
          value={programFilter}
          onChange={(e) => setProgramFilter(e.target.value as CARProgram)}
          className="form-control"
          style={{ width: 220 }}
        >
          {PROGRAM_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} programme
            </option>
          ))}
        </select>
        {canManageCars ? (
          <button
            type="button"
            className="secondary-chip-btn"
            onClick={() => setShowCreatePanel((current) => !current)}
          >
            {showCreatePanel ? "Hide CAR intake" : "Open CAR intake"}
          </button>
        ) : null}
        <button
          type="button"
          className="secondary-chip-btn"
          onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms`)}
        >
          Back to QMS overview
        </button>
      </section>

      {inviteToken && (
        <div className="card card--info" style={{ marginBottom: 12 }}>
          <p style={{ margin: 0 }}>
            Invitation token detected. Please log a CAR or update the assigned CAR linked to your email invite.
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

      {canManageCars && showCreatePanel ? (
        <section className="page-section">
          <div className="card qms-car-form-card">
          <div className="card-header">
            <h2>CAR intake</h2>
            <p className="text-muted">
              Open only when needed by a manager; the main page stays focused on the active register and review workload.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select value={programFilter} onChange={(e) => setProgramFilter(e.target.value as CARProgram)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none ring-0">
              {PROGRAM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label} programme</option>)}
            </select>
            <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400" onClick={() => setDrawerOpen(true)}>
              <Plus className="h-4 w-4" /> Log new CAR
            </button>
          </div>
        </div>

        {inviteToken ? <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">Invitation token detected. Log or update the assigned CAR linked to your email invite. The Quality team will be notified automatically.</div> : null}
        {error ? <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}
        {assigneesState === "error" && assigneesError ? <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">{assigneesError}</div> : null}

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[auto_minmax(0,1fr)]">
          <aside className={["relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 transition-all", sidebarCollapsed ? "w-20" : "w-full xl:w-[280px]"] .join(" ")}>
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              {!sidebarCollapsed ? <div><h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Filters</h2><p className="mt-1 text-xs text-slate-500">Programme signals & workflow counts.</p></div> : <ShieldCheck className="h-5 w-5 text-cyan-300" />}
              <button type="button" className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-slate-600 hover:text-white" onClick={() => setSidebarCollapsed((prev) => !prev)}>
                {sidebarCollapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
              </button>
            </div>

            <div className="space-y-4 p-4">
              {!sidebarCollapsed && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    {PROGRAM_OPTIONS.map((opt) => (
                      <button key={opt.value} type="button" onClick={() => setProgramFilter(opt.value)} className={["rounded-xl border px-3 py-2 text-left text-sm", programFilter === opt.value ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-600"] .join(" ")}>
                        <div className="font-medium">{opt.label}</div>
                        <div className="text-xs text-slate-500">{cars.filter((car) => car.program === opt.value).length} active rows</div>
                      </button>
                    ))}
                  </div>

                  <div className="space-y-2">
                    {[
                      { key: "all", label: "All CARs", count: statusCounts.all },
                      { key: "overdue", label: "Overdue", count: statusCounts.overdue },
                      { key: "open", label: "Open", count: statusCounts.open },
                      { key: "PENDING_VERIFICATION", label: "Pending review", count: statusCounts.PENDING_VERIFICATION },
                      { key: "ESCALATED", label: "Escalated", count: statusCounts.ESCALATED },
                      { key: "CLOSED", label: "Closed", count: statusCounts.CLOSED },
                    ].map((item) => (
                      <button key={item.key} type="button" onClick={() => setStatusFilter(item.key)} className={["flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm", statusFilter === item.key ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-600"] .join(" ")}>
                        <span>{item.label}</span>
                        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-200">{item.count}</span>
                      </button>
                    ))}
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Review queue</div>
                      <div className="mt-2 text-2xl font-semibold text-slate-50">{reviewQueue.length}</div>
                    </div>
                    <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Overdue within 48h</div>
                      <div className="mt-2 text-2xl font-semibold text-orange-300">{cars.filter((car) => car.due_date && (new Date(car.due_date).getTime() - Date.now()) / (1000 * 60 * 60) <= 48 && car.status !== "CLOSED").length}</div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                    <h3 className="text-sm font-medium text-slate-200">Append-only timeline</h3>
                    <p className="mt-1 text-xs text-slate-500">History remains immutable for audit-trail integrity.</p>
                    <div className="mt-3 max-h-[320px] overflow-auto pr-1">
                      <AuditHistoryPanel title="CAR history" entityType="qms_car" />
                    </div>
                  </div>
                </>
              )}
            </div>
          </aside>

          <main className="min-w-0 rounded-2xl border border-slate-800 bg-slate-900/70">
            <div className="grid min-h-[calc(100vh-16rem)] grid-cols-1 xl:grid-cols-[minmax(0,1fr)_370px]">
              <section className="min-w-0 border-b border-slate-800 xl:border-b-0 xl:border-r">
                <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-50">Register</h2>
                    <p className="text-sm text-slate-400">Persistent source of truth for issued CARs and auditee submissions.</p>
                  </div>
                  {state === "loading" ? <div className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Syncing register</div> : null}
                </div>
                <div className="overflow-auto">
                  <table className="min-w-full text-left text-sm text-slate-200">
                    <thead className="sticky top-0 z-10 bg-slate-950/95 text-xs uppercase tracking-[0.18em] text-slate-500 backdrop-blur">
                      <tr>
                        <th className="px-4 py-3">CAR #</th>
                        <th className="px-4 py-3">Finding</th>
                        <th className="px-4 py-3">Title</th>
                        <th className="px-4 py-3">Owner</th>
                        <th className="px-4 py-3">Priority</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">Workflow</th>
                        <th className="px-4 py-3">Date band</th>
                        <th className="px-4 py-3">Updated</th>
                        <th className="px-4 py-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCars.map((car) => {
                        const owner = car.assigned_to_user_id ? assigneeLookup.get(car.assigned_to_user_id)?.full_name || "Assigned user" : "Unassigned";
                        const selected = car.id === selectedCarId;
                        const isSkeleton = car.id.startsWith("temp-");
                        return (
                          <tr key={car.id} className={["border-b border-slate-800/80 transition", selected ? "bg-slate-800/70 shadow-[inset_4px_0_0_0_rgb(34,211,238)]" : "hover:bg-slate-800/40"] .join(" ")} onClick={() => setSelectedCarId(car.id)}>
                            <td className="px-4 py-3 font-medium text-slate-50">{isSkeleton ? <div className="h-5 w-28 animate-pulse rounded bg-slate-700" /> : car.car_number}</td>
                            <td className="px-4 py-3 text-slate-400">{car.finding_id || "—"}</td>
                            <td className="px-4 py-3">
                              <div className="max-w-[280px] truncate font-medium text-slate-100">{car.title}</div>
                              <div className="max-w-[280px] truncate text-xs text-slate-500">{car.summary}</div>
                            </td>
                            <td className="px-4 py-3">{owner}</td>
                            <td className="px-4 py-3"><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${PRIORITY_META[car.priority].className}`}>{PRIORITY_META[car.priority].label}</span></td>
                            <td className="px-4 py-3"><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_META[car.status].className}`}>{STATUS_META[car.status].label}</span></td>
                            <td className="px-4 py-3"><WorkflowPips car={car} /></td>
                            <td className="px-4 py-3 text-xs">
                              <div className="text-slate-400">Target: <span className="text-slate-200">{formatDate(car.target_closure_date)}</span></div>
                              <div className={dueHeatClass(car.due_date)}>Due: {formatDate(car.due_date)}</div>
                            </td>
                            <td className="px-4 py-3 text-slate-400">{formatDate(car.updated_at)}</td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-2">
                                <button type="button" className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:border-slate-500" onClick={(e) => { e.stopPropagation(); openEdit(car); }}>Edit</button>
                                <button type="button" className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:border-slate-500" onClick={(e) => { e.stopPropagation(); void openReview(car); }}>Review</button>
                                <button type="button" className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:border-slate-500" onClick={(e) => { e.stopPropagation(); setPanelContext({ type: "car", id: car.id, title: car.title, status: car.status, ownerId: car.assigned_to_user_id }); }}>Actions</button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                      {filteredCars.length === 0 ? <tr><td colSpan={10} className="px-4 py-10 text-center text-sm text-slate-500">No CARs logged for this programme and filter combination yet.</td></tr> : null}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="min-w-0 bg-slate-950/50">
                <div className="border-b border-slate-800 px-4 py-3">
                  <h2 className="text-lg font-semibold text-slate-50">Auditee submissions</h2>
                  <p className="text-sm text-slate-400">Reviewer queue, evidence intake, and workflow progress at row level.</p>
                </div>
                <div className="max-h-[calc(100vh-16rem)] space-y-3 overflow-auto p-4">
                  {reviewQueue.map((car) => {
                    const dragActive = draggedCarId === car.id;
                    return (
                      <article key={`review-${car.id}`} className={["rounded-2xl border p-4 transition", dragActive ? "border-cyan-400 bg-cyan-400/10" : "border-slate-800 bg-slate-900/80"] .join(" ")} onDragOver={(e) => { e.preventDefault(); setDraggedCarId(car.id); }} onDragLeave={() => setDraggedCarId((current) => (current === car.id ? null : current))} onDrop={(e) => { e.preventDefault(); void uploadEvidence(car, e.dataTransfer.files); }}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-semibold text-slate-50">{car.car_number}</h3>
                              <WorkflowPips car={car} />
                            </div>
                            <p className="mt-1 text-sm text-slate-300">{car.title}</p>
                            <p className="mt-1 text-xs text-slate-500">{getCarWorkflowStep(car)}</p>
                          </div>
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_META[car.status].className}`}>{STATUS_META[car.status].label}</span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
                          <div>
                            <div className="text-slate-500">Submission</div>
                            <div className="mt-1 text-slate-200">{car.submitted_by_name || "Awaiting auditee"}</div>
                            <div>{formatDateTime(car.submitted_at)}</div>
                          </div>
                          <div>
                            <div className="text-slate-500">Review path</div>
                            <div className="mt-1 text-slate-200">Root cause: {car.root_cause_status || "Pending"}</div>
                            <div>CAPA: {car.capa_status || "Pending"}</div>
                          </div>
                        </div>
                        <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/70 p-3 text-xs text-slate-400">
                          <div className="flex items-center gap-2 text-slate-300"><FileUp className="h-4 w-4" /> Drag files here to attach evidence directly to this CAR.</div>
                          <div className="mt-2 flex items-center justify-between gap-2">
                            <span className={car.evidence_received_at ? "text-emerald-300" : "text-slate-500"}>{car.evidence_received_at ? `Evidence received ${formatDateTime(car.evidence_received_at)}` : "No evidence received yet."}</span>
                            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-slate-500">
                              <input type="file" multiple className="hidden" onChange={(e) => { if (e.target.files) void uploadEvidence(car, e.target.files); e.target.value = ""; }} />
                              {uploadingEvidenceId === car.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                              Upload
                            </label>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button type="button" className="rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-medium text-slate-950 hover:bg-cyan-400" onClick={() => void openReview(car)}>Open review</button>
                          <button type="button" className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-slate-500" onClick={() => setSelectedCarId(car.id)}>Focus row</button>
                        </div>
                      </article>
                    );
                  })}
                  {reviewQueue.length === 0 ? <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 text-center text-sm text-slate-500">No auditee submissions in the review queue yet.</div> : null}
                </div>
              </section>
            </div>
          </form>
          </div>
        </section>
      ) : null}

        {selectedCar ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold text-slate-50">{selectedCar.car_number}</h2>
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${PRIORITY_META[selectedCar.priority].className}`}>{PRIORITY_META[selectedCar.priority].label}</span>
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_META[selectedCar.status].className}`}>{STATUS_META[selectedCar.status].label}</span>
                </div>
                <p className="mt-1 text-sm text-slate-300">{selectedCar.title}</p>
                <p className="mt-2 max-w-5xl text-sm text-slate-400">{selectedCar.summary}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-slate-500" onClick={() => void handleExport(selectedCar)} disabled={exportingId === selectedCar.id}>{exportingId === selectedCar.id ? "Exporting…" : "Export pack"}</button>
                <button type="button" className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-slate-500" onClick={() => void handleCopyInvite(selectedCar)} disabled={inviteBusyId === selectedCar.id}>{inviteBusyId === selectedCar.id ? "Copying…" : "Copy invite"}</button>
                <button type="button" className="rounded-lg border border-rose-500/30 px-3 py-2 text-sm text-rose-200 hover:border-rose-400" onClick={() => setDeleteCar(selectedCar)}>Delete</button>
              </div>
            </div>
          </div>
        ) : null}

        {!canManageCars ? <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">CAR updates are limited to assigned auditors, Quality Managers, AMO Admins, and superusers.</div> : null}

        {drawerOpen ? (
          <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/70 backdrop-blur-sm">
            <div className="flex h-full w-full max-w-2xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl">
              <div className="flex items-start justify-between border-b border-slate-800 px-6 py-5">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-cyan-300">Contextual action</p>
                  <h2 className="mt-2 text-xl font-semibold text-slate-50">Log a new CAR</h2>
                  <p className="mt-1 text-sm text-slate-400">Step {formStep} of 2 · capture the finding, then assign ownership and dates.</p>
                </div>
                <button type="button" onClick={() => setDrawerOpen(false)} className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-slate-600 hover:text-white"><X className="h-4 w-4" /></button>
              </div>
              <form onSubmit={submitCreate} className="flex flex-1 flex-col overflow-hidden">
                <div className="flex items-center gap-2 border-b border-slate-800 px-6 py-4 text-sm">
                  <button type="button" onClick={() => setFormStep(1)} className={formStep === 1 ? "font-semibold text-cyan-300" : "text-slate-500"}>1. Finding</button>
                  <ChevronRight className="h-4 w-4 text-slate-600" />
                  <button type="button" onClick={() => setFormStep(2)} className={formStep === 2 ? "font-semibold text-cyan-300" : "text-slate-500"}>2. Action</button>
                </div>
                <div className="flex-1 space-y-5 overflow-auto px-6 py-5">
                  {formStep === 1 ? (
                    <>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Programme</span>
                        <select {...register("program")} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">
                          {PROGRAM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                        </select>
                      </label>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Priority</span>
                        <select {...register("priority")} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">
                          {(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as CARPriority[]).map((priority) => <option key={priority} value={priority}>{PRIORITY_META[priority].label}</option>)}
                        </select>
                      </label>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Title</span>
                        <input {...register("title")} type="text" placeholder="Short, action-oriented title" className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500" />
                        {errors.title ? <span className="text-xs text-rose-300">{errors.title.message}</span> : null}
                      </label>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Summary</span>
                        <textarea {...register("summary")} rows={5} placeholder="Detail the finding, containment, and requested corrective actions." className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500" />
                        {errors.summary ? <span className="text-xs text-rose-300">{errors.summary.message}</span> : null}
                      </label>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Finding ID</span>
                        <div className="relative">
                          <input {...register("finding_id")} type="text" placeholder="Paste non-conformity finding ID" className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 pr-10 text-sm text-slate-100 placeholder:text-slate-500" />
                          <div className="absolute inset-y-0 right-3 flex items-center">
                            {findingLookupState === "checking" ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : null}
                            {findingLookupState === "valid" ? <ShieldCheck className="h-4 w-4 text-emerald-300" /> : null}
                            {findingLookupState === "warning" ? <TriangleAlert className="h-4 w-4 text-amber-300" /> : null}
                          </div>
                        </div>
                        <div className={["text-xs", findingLookupState === "warning" ? "text-amber-300" : findingLookupState === "valid" ? "text-emerald-300" : "text-slate-500"].join(" ")}>{findingLookupMessage}</div>
                        {errors.finding_id ? <span className="text-xs text-rose-300">{errors.finding_id.message}</span> : null}
                      </label>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <label className="block space-y-2">
                          <span className="text-sm font-medium text-slate-200">Target closure</span>
                          <input {...register("target_closure_date")} type="date" className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" />
                          {errors.target_closure_date ? <span className="text-xs text-rose-300">{errors.target_closure_date.message}</span> : <span className="text-xs text-slate-500">Compact date band: target closure and due date stay on one row.</span>}
                        </label>
                        <label className="block space-y-2">
                          <span className="text-sm font-medium text-slate-200">Due date</span>
                          <input {...register("due_date")} type="date" className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" />
                        </label>
                      </div>
                      <label className="block space-y-2">
                        <span className="text-sm font-medium text-slate-200">Responsible department</span>
                        <select {...register("assigned_department_id")} onChange={(e) => { setValue("assigned_department_id", e.target.value); setValue("assigned_to_user_id", ""); setAssigneeSearch(""); }} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">
                          <option value="">All departments</option>
                          {departmentOptions.map((dept) => <option key={dept.id} value={dept.id}>{dept.name}</option>)}
                        </select>
                      </label>
                      <div className="space-y-2">
                        <span className="text-sm font-medium text-slate-200">Responsible owner / assignees</span>
                        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-3">
                          <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2">
                            <Search className="h-4 w-4 text-slate-500" />
                            <input value={assigneeSearch} onChange={(e) => setAssigneeSearch(e.target.value)} className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500" placeholder="Search by name, email, staff code, or department" />
                          </div>
                          <div className="mt-3 max-h-64 space-y-2 overflow-auto">
                            {ownerSuggestions.map((assignee) => (
                              <button key={assignee.id} type="button" onClick={() => { setValue("assigned_to_user_id", assignee.id); setAssigneeSearch(""); }} className={["flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left", watchedAssignedOwnerId === assignee.id ? "border-cyan-400/30 bg-cyan-400/10" : "border-slate-800 bg-slate-950 hover:border-slate-700"] .join(" ")}>
                                <div>
                                  <div className="text-sm font-medium text-slate-100">{assignee.full_name}</div>
                                  <div className="text-xs text-slate-500">{assignee.department_name || assignee.department_code || "No department"} · {assignee.email || assignee.staff_code || "No contact info"}</div>
                                </div>
                                <UserRound className="h-4 w-4 text-slate-500" />
                              </button>
                            ))}
                            {ownerSuggestions.length === 0 ? <div className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-4 text-xs text-slate-500">No matching staff in the current tenant directory.</div> : null}
                          </div>
                        </div>
                        <input type="hidden" {...register("assigned_to_user_id")} />
                      </div>
                    </>
                  )}
                </div>
                <div className="flex items-center justify-between border-t border-slate-800 px-6 py-4">
                  <button type="button" onClick={() => setFormStep(1)} className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-600">{formStep === 1 ? "Stay on finding" : "Back"}</button>
                  <div className="flex items-center gap-2">
                    {formStep === 1 ? <button type="button" onClick={() => setFormStep(2)} className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400">Next: Action</button> : <button type="submit" disabled={submittingCreate || findingLookupState === "warning"} className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50">{submittingCreate ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Preview & create</button>}
                  </div>
                </div>
              </form>
            </div>
          </div>
        ) : null}

        {reviewCar ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
            <div className="max-h-[90vh] w-full max-w-5xl overflow-auto rounded-3xl border border-slate-800 bg-slate-950 shadow-2xl">
              <div className="flex items-start justify-between border-b border-slate-800 px-6 py-5">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-cyan-300">Reviewer workspace</p>
                  <h3 className="mt-2 text-xl font-semibold text-slate-50">CAR {reviewCar.car_number} · {reviewCar.title}</h3>
                  <p className="mt-1 text-sm text-slate-400">Current step: {getCarWorkflowStep(reviewCar)}</p>
                </div>
                <button type="button" className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-slate-600 hover:text-white" onClick={() => setReviewCar(null)} disabled={reviewBusy}><X className="h-4 w-4" /></button>
              </div>
              <div className="grid gap-4 px-6 py-5 lg:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <h4 className="text-sm font-semibold text-slate-50">Auditee payload</h4>
                  <div className="mt-3 space-y-2 text-sm text-slate-300">
                    <p><strong>Name:</strong> {reviewCar.submitted_by_name || "—"}</p>
                    <p><strong>Email:</strong> {reviewCar.submitted_by_email || "—"}</p>
                    <p><strong>Containment:</strong> {reviewCar.containment_action || "—"}</p>
                    <p><strong>Root cause:</strong> {reviewCar.root_cause_text || reviewCar.root_cause || "—"}</p>
                    <p><strong>CAPA:</strong> {reviewCar.capa_text || reviewCar.corrective_action || "—"}</p>
                    <p><strong>Evidence ref:</strong> {reviewCar.evidence_ref || "—"}</p>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <h4 className="text-sm font-semibold text-slate-50">Evidence attachments</h4>
                  {reviewAttachmentsLoading ? <div className="mt-3 inline-flex items-center gap-2 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" /> Loading evidence…</div> : null}
                  {!reviewAttachmentsLoading && reviewAttachments.length === 0 ? <p className="mt-3 text-sm text-slate-500">No attachments.</p> : null}
                  <div className="mt-3 space-y-2 text-sm">
                    {reviewAttachments.map((file) => <div key={file.id}><a href={file.download_url} target="_blank" rel="noreferrer" className="text-cyan-300 hover:text-cyan-200">{file.filename}</a></div>)}
                  </div>
                </div>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-200">Root cause decision</span>
                  <select value={reviewForm.root_cause_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_status: e.target.value as CarReviewForm["root_cause_status"] }))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">
                    <option value="">No change</option><option value="ACCEPTED">Accept</option><option value="REJECTED">Reject</option>
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-200">CAPA decision</span>
                  <select value={reviewForm.capa_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_status: e.target.value as CarReviewForm["capa_status"] }))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">
                    <option value="">No change</option><option value="ACCEPTED">Accept</option><option value="NEEDS_EVIDENCE">Needs evidence</option><option value="REJECTED">Reject</option>
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-200">Root cause note</span>
                  <textarea rows={4} value={reviewForm.root_cause_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_review_note: e.target.value }))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-200">CAPA note</span>
                  <textarea rows={4} value={reviewForm.capa_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_review_note: e.target.value }))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" />
                </label>
                <label className="space-y-2 lg:col-span-2">
                  <span className="text-sm font-medium text-slate-200">Reviewer message / action note</span>
                  <textarea rows={4} value={reviewForm.message} onChange={(e) => setReviewForm((prev) => ({ ...prev, message: e.target.value }))} placeholder="Visible in CAR action log for full audit traceability." className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" />
                </label>
              </div>
              <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
                <button type="button" className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-600" onClick={() => setReviewCar(null)} disabled={reviewBusy}>Cancel</button>
                <button type="button" className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400" onClick={() => void submitReview()} disabled={reviewBusy}>{reviewBusy ? "Submitting…" : "Submit review"}</button>
              </div>
            </div>
          </div>
        ) : null}

        {editingCar && editForm ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
            <div className="w-full max-w-2xl rounded-3xl border border-slate-800 bg-slate-950 shadow-2xl">
              <div className="flex items-start justify-between border-b border-slate-800 px-6 py-5">
                <div><p className="text-xs uppercase tracking-[0.24em] text-cyan-300">Edit</p><h3 className="mt-2 text-xl font-semibold text-slate-50">Update CAR</h3><p className="mt-1 text-sm text-slate-400">Adjust details for {editingCar.car_number}.</p></div>
                <button type="button" className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-slate-600 hover:text-white" onClick={() => { setEditingCar(null); setEditForm(null); }}><X className="h-4 w-4" /></button>
              </div>
              <div className="grid gap-4 px-6 py-5">
                <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Title</span><input value={editForm.title} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, title: e.target.value } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" /></label>
                <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Summary</span><textarea value={editForm.summary} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, summary: e.target.value } : prev))} rows={4} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" /></label>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Priority</span><select value={editForm.priority} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, priority: e.target.value as CARPriority } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100">{(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as CARPriority[]).map((priority) => <option key={priority} value={priority}>{PRIORITY_META[priority].label}</option>)}</select></label>
                  <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Target closure</span><input type="date" value={editForm.target_closure_date} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, target_closure_date: e.target.value } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" /></label>
                  <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Due date</span><input type="date" value={editForm.due_date} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, due_date: e.target.value } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100" /></label>
                  <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Responsible department</span><select value={editForm.assigned_department_id} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, assigned_department_id: e.target.value, assigned_to_user_id: "" } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100"><option value="">All departments</option>{departmentOptions.map((dept) => <option key={dept.id} value={dept.id}>{dept.name}</option>)}</select></label>
                </div>
                <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Assignee search</span><input value={editAssigneeSearch} onChange={(e) => setEditAssigneeSearch(e.target.value)} placeholder="Search by name, email, or staff code" className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500" /></label>
                <label className="space-y-2"><span className="text-sm font-medium text-slate-200">Responsible owner</span><select value={editForm.assigned_to_user_id} onChange={(e) => setEditForm((prev) => (prev ? { ...prev, assigned_to_user_id: e.target.value } : prev))} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100"><option value="">Unassigned</option>{assignees.filter((assignee) => { if (editForm.assigned_department_id && assignee.department_id !== editForm.assigned_department_id) return false; const search = editAssigneeSearch.trim().toLowerCase(); if (!search) return true; return [assignee.full_name, assignee.email || "", assignee.staff_code || ""].join(" ").toLowerCase().includes(search); }).map((assignee) => <option key={assignee.id} value={assignee.id}>{assignee.full_name}{assignee.department_name ? ` · ${assignee.department_name}` : ""}</option>)}</select></label>
              </div>
              <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
                <button type="button" className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-600" onClick={() => { setEditingCar(null); setEditForm(null); }} disabled={editBusy}>Cancel</button>
                <button type="button" className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400" onClick={() => void handleEditSave()} disabled={editBusy}>{editBusy ? "Saving…" : "Save changes"}</button>
              </div>
            </div>
          </div>
        ) : null}

        {deleteCar ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
            <div className="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-950 shadow-2xl">
              <div className="border-b border-slate-800 px-6 py-5"><p className="text-xs uppercase tracking-[0.24em] text-rose-300">Delete</p><h3 className="mt-2 text-xl font-semibold text-slate-50">Remove CAR?</h3><p className="mt-1 text-sm text-slate-400">{deleteCar.car_number} will be permanently removed.</p></div>
              <div className="flex justify-end gap-2 px-6 py-4"><button type="button" className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-600" onClick={() => setDeleteCar(null)} disabled={deleteBusy}>Cancel</button><button type="button" className="rounded-xl bg-rose-500 px-4 py-2 text-sm font-medium text-white hover:bg-rose-400" onClick={() => void handleDelete()} disabled={deleteBusy}>{deleteBusy ? "Deleting…" : "Confirm delete"}</button></div>
            </div>
          </div>
        ) : null}

        <ActionPanel isOpen={!!panelContext} context={panelContext} onClose={() => setPanelContext(null)} />
      </div>
    </DepartmentLayout>
  );
};

export default QualityCarsPage;

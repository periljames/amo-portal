import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
import { useToast } from "../components/feedback/ToastProvider";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import { getCachedUser, getContext } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import { deriveCarMetrics, isCarOverdue, isCarClosedStatus } from "../utils/carMetrics";
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
  qmsListCars,
  qmsListCarAttachments,
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

const QualityCarsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [programFilter, setProgramFilter] = useState<CARProgram>("QUALITY");
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reviewForm, setReviewForm] = useState<CarReviewForm>({
    root_cause_status: "",
    root_cause_review_note: "",
    capa_status: "",
    capa_review_note: "",
    message: "",
  });
  const { pushToast } = useToast();

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
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    return cars.filter((car) => {
      if (carId && car.id !== carId) return false;
      if (statusParam === "overdue") {
        return isCarOverdue(car, today);
      }
      if (statusParam === "open") {
        if (isCarClosedStatus(car.status)) return false;
      }
      if (dueWindow && car.due_date) {
        const due = new Date(`${car.due_date}T00:00:00Z`).getTime();
        const todayMs = new Date(`${today}T00:00:00Z`).getTime();
        const diff = Math.floor((due - todayMs) / (1000 * 60 * 60 * 24));
        if (dueWindow === "now" && diff >= 0) return false;
        if (dueWindow === "today" && diff !== 0) return false;
        if (dueWindow === "week" && !(diff >= 0 && diff <= 7)) return false;
        if (dueWindow === "month" && !(diff >= 0 && diff <= 30)) return false;
      }
      return true;
    });
  }, [cars, searchParams]);

  const reviewQueue = useMemo(() => {
    return cars
      .filter((car) => !!car.submitted_at || car.status === "IN_PROGRESS" || car.status === "PENDING_VERIFICATION")
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
      const next = await qmsListCars({ program: programFilter });
      setCars(next);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load CAR register.");
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
      setError(e?.message || "Failed to create CAR");
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
        window.prompt("Copy CAR invite link:", invite.invite_url);
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
      pushToast({
        title: "CAR review submitted",
        message: `Review outcome saved for ${reviewCar.car_number}.`,
        variant: "info",
      });
      setReviewCar(null);
      setReviewAttachments([]);
      await load();
    } catch (e: any) {
      setError(e?.message || "Failed to submit CAR review.");
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
      pathname: `/maintenance/${amoSlug}/${department}/cars`,
      search: `?${next.toString()}`,
    });
  };

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">
          Corrective Action Requests · {amoDisplay}
        </h1>
        <p className="page-header__subtitle">
          Register for Quality & Reliability programmes with escalation tracking.
        </p>
      </header>

      <section className="page-section qms-car-toolbar">
        <div className="page-section__actions">
          <button
            type="button"
            className="secondary-chip-btn"
            onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms`)}
          >
            Back to QMS overview
          </button>
          <label className="form-control qms-car-toolbar__filter">
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
        </div>
        <div className="qms-car-overview">
          <div className="qms-car-overview__item">
            <span>Total</span>
            <strong>{overviewStats.total}</strong>
          </div>
          <div className="qms-car-overview__item">
            <span>Open</span>
            <strong>{overviewStats.open}</strong>
          </div>
          <div className="qms-car-overview__item">
            <span>Overdue</span>
            <strong>{overviewStats.overdue}</strong>
          </div>
          <div className="qms-car-overview__item">
            <span>In review</span>
            <strong>{overviewStats.inReview}</strong>
          </div>
        </div>
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

      <section className="page-section">
        <div className="card">
          <div className="qms-car-register-tabs" role="tablist" aria-label="CAR register sections">
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
              CAR history
            </button>
          </div>
          <div className="card-header">
            <h2>Register</h2>
            <p className="text-muted">Auto-numbered entries with status, priority, and ownership.</p>
            {canManageCars && (
              <button
                type="button"
                className="primary-chip-btn"
                onClick={() => setShowCreateForm((open) => !open)}
                aria-expanded={showCreateForm}
              >
                {showCreateForm ? "Hide create form" : "Log new CAR"}
              </button>
            )}
          </div>

          {state === "loading" && !historyOpen && <p id="car-register-panel">Loading register…</p>}

          {state === "ready" && !historyOpen && (
            <div className="table-responsive" id="car-register-panel" role="tabpanel" aria-labelledby="car-register-tab">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>CAR #</th>
                    <th>Title</th>
                    <th>Owner</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Due</th>
                    <th>Next reminder</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCars.map((car) => (
                    <tr key={car.id}>
                      <td>{car.car_number}</td>
                      <td>{car.title}</td>
                      <td>
                        {car.assigned_to_user_id
                          ? assigneeLookup.get(car.assigned_to_user_id)?.full_name ||
                            "Assigned user"
                          : "Unassigned"}
                      </td>
                      <td>
                        <span className="badge badge--neutral">
                          {PRIORITY_LABELS[car.priority]}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${STATUS_COLORS[car.status] || "badge--neutral"}`}>
                          {car.status}
                        </span>
                      </td>
                      <td>{car.due_date || "—"}</td>
                      <td>{car.next_reminder_at ? new Date(car.next_reminder_at).toLocaleString() : "—"}</td>
                      <td>{new Date(car.updated_at).toLocaleDateString()}</td>
                      <td>
                        <div style={{ display: "flex", gap: 8 }}>
                          {car.assigned_to_user_id && (
                            <button
                              type="button"
                              className="secondary-chip-btn"
                              onClick={() =>
                                navigate(`/maintenance/${amoSlug}/admin/users/${car.assigned_to_user_id}`)
                              }
                            >
                              Owner
                            </button>
                          )}
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => openEdit(car)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => void openReview(car)}
                          >
                            Review
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() =>
                              setPanelContext({
                                type: "car",
                                id: car.id,
                                title: car.title,
                                status: car.status,
                                ownerId: car.assigned_to_user_id,
                              })
                            }
                          >
                            Quick actions
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleExport(car)}
                            disabled={exportingId === car.id}
                          >
                            {exportingId === car.id ? "Exporting…" : "Export pack"}
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleCopyInvite(car)}
                            disabled={inviteBusyId === car.id}
                          >
                            {inviteBusyId === car.id ? "Copying…" : "Copy invite"}
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => setDeleteCar(car)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filteredCars.length === 0 && (
                    <tr>
                      <td colSpan={9} className="text-muted">
                        No CARs logged for this programme yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
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
                Review completed activity and jump straight to the selected CAR to continue or collaborate.
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
            <h2>Log a new CAR</h2>
            <p className="text-muted">
              Assign programme, priority, and a concise summary. Numbers are auto-generated per programme and year.
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

      <section className="page-section">
        <div className="card">
          <div className="card-header">
            <h2>Auditee submissions & review queue</h2>
            <p className="text-muted">Track internal/external CAR submissions, reviewer decisions, and workflow stage.</p>
          </div>
          <div className="table-responsive">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>CAR #</th>
                  <th>Auditee submission</th>
                  <th>Root cause review</th>
                  <th>CAPA review</th>
                  <th>Evidence</th>
                  <th>Workflow stage</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {reviewQueue.map((car) => (
                  <tr key={`review-${car.id}`}>
                    <td>{car.car_number}</td>
                    <td>
                      <div>{car.submitted_by_name || "—"}</div>
                      <div className="text-muted">{car.submitted_at ? new Date(car.submitted_at).toLocaleString() : "Not submitted"}</div>
                    </td>
                    <td>{car.root_cause_status || "Pending"}</td>
                    <td>{car.capa_status || "Pending"}</td>
                    <td>{car.evidence_received_at ? "Received" : "Missing"}</td>
                    <td>{getCarWorkflowStep(car)}</td>
                    <td>
                      <button type="button" className="secondary-chip-btn" onClick={() => void openReview(car)}>
                        Open review
                      </button>
                    </td>
                  </tr>
                ))}
                {reviewQueue.length === 0 && (
                  <tr>
                    <td colSpan={7}>No auditee submissions in review queue yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {reviewCar && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal" style={{ maxWidth: 920 }}>
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Reviewer workspace</p>
                <h3 className="upsell-modal__title">CAR {reviewCar.car_number} · {reviewCar.title}</h3>
                <p className="text-muted" style={{ marginTop: 4 }}>Current step: {getCarWorkflowStep(reviewCar)}</p>
              </div>
              <button type="button" className="upsell-modal__close" onClick={() => setReviewCar(null)} disabled={reviewBusy}>×</button>
            </div>
            <div className="upsell-modal__body" style={{ display: "grid", gap: 12 }}>
              <div className="qms-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <div className="qms-card">
                  <h4 style={{ marginTop: 0 }}>Auditee payload</h4>
                  <p><strong>Name:</strong> {reviewCar.submitted_by_name || "—"}</p>
                  <p><strong>Email:</strong> {reviewCar.submitted_by_email || "—"}</p>
                  <p><strong>Containment:</strong> {reviewCar.containment_action || "—"}</p>
                  <p><strong>Root cause:</strong> {reviewCar.root_cause_text || reviewCar.root_cause || "—"}</p>
                  <p><strong>CAPA:</strong> {reviewCar.capa_text || reviewCar.corrective_action || "—"}</p>
                  <p><strong>Evidence ref:</strong> {reviewCar.evidence_ref || "—"}</p>
                </div>
                <div className="qms-card">
                  <h4 style={{ marginTop: 0 }}>Evidence attachments</h4>
                  {reviewAttachmentsLoading ? <p>Loading evidence…</p> : null}
                  {!reviewAttachmentsLoading && reviewAttachments.map((file) => (
                    <div key={file.id} style={{ marginBottom: 8 }}>
                      <a href={file.download_url} target="_blank" rel="noreferrer">{file.filename}</a>
                    </div>
                  ))}
                  {!reviewAttachmentsLoading && reviewAttachments.length === 0 ? <p className="text-muted">No attachments.</p> : null}
                </div>
              </div>

              <div className="qms-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <label className="qms-field">
                  Root cause decision
                  <select value={reviewForm.root_cause_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_status: e.target.value as CarReviewForm["root_cause_status"] }))}>
                    <option value="">No change</option>
                    <option value="ACCEPTED">Accept</option>
                    <option value="REJECTED">Reject</option>
                  </select>
                </label>
                <label className="qms-field">
                  CAPA decision
                  <select value={reviewForm.capa_status} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_status: e.target.value as CarReviewForm["capa_status"] }))}>
                    <option value="">No change</option>
                    <option value="ACCEPTED">Accept</option>
                    <option value="NEEDS_EVIDENCE">Needs evidence</option>
                    <option value="REJECTED">Reject</option>
                  </select>
                </label>
              </div>
              <div className="qms-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <label className="qms-field">
                  Root cause note (required for rejection)
                  <textarea rows={3} value={reviewForm.root_cause_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, root_cause_review_note: e.target.value }))} />
                </label>
                <label className="qms-field">
                  CAPA note (required for reject/needs evidence)
                  <textarea rows={3} value={reviewForm.capa_review_note} onChange={(e) => setReviewForm((prev) => ({ ...prev, capa_review_note: e.target.value }))} />
                </label>
              </div>
              <label className="qms-field">
                Reviewer message / action note
                <textarea rows={3} value={reviewForm.message} onChange={(e) => setReviewForm((prev) => ({ ...prev, message: e.target.value }))} placeholder="Visible in CAR action log for full audit traceability." />
              </label>
            </div>
            <div className="upsell-modal__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => setReviewCar(null)} disabled={reviewBusy}>Cancel</button>
              <button type="button" className="primary-chip-btn" onClick={() => void submitReview()} disabled={reviewBusy}>
                {reviewBusy ? "Submitting…" : "Submit review"}
              </button>
            </div>
          </div>
        </div>
      )}

      {previewOpen && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Preview</p>
                <h3 className="upsell-modal__title">Confirm CAR details</h3>
                <p className="upsell-modal__subtitle">
                  Please confirm the information below before creating this CAR.
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
                <h3 className="upsell-modal__title">Update CAR</h3>
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
                <h3 className="upsell-modal__title">Remove CAR?</h3>
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
            CAR updates are limited to assigned auditors, Quality Managers, AMO Admins, and superusers.
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

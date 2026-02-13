import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
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
  downloadCarEvidencePack,
  qmsDeleteCar,
  qmsListCarAssignees,
  qmsCreateCar,
  qmsGetCarInvite,
  qmsListCars,
  qmsUpdateCar,
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
  const { pushToast } = useToast();

  const assigneeLookup = useMemo(() => {
    const map = new Map<string, CARAssignee>();
    assignees.forEach((assignee) => map.set(assignee.id, assignee));
    return map;
  }, [assignees]);

  const filteredCars = useMemo(() => {
    const statusParam = searchParams.get("status");
    const dueWindow = searchParams.get("dueWindow");
    const carId = searchParams.get("carId");
    const now = new Date();
    return cars.filter((car) => {
      if (carId && car.id !== carId) return false;
      if (statusParam === "overdue") {
        if (!car.due_date) return false;
        return new Date(car.due_date) < now && car.status !== "CLOSED";
      }
      if (statusParam === "open") {
        if (car.status === "CLOSED") return false;
      }
      if (dueWindow && car.due_date) {
        const diff = (new Date(car.due_date).getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
        if (dueWindow === "now" && diff >= 0) return false;
        if (dueWindow === "today" && Math.floor(diff) !== 0) return false;
        if (dueWindow === "week" && !(diff >= 0 && diff <= 7)) return false;
        if (dueWindow === "month" && !(diff >= 0 && diff <= 30)) return false;
      }
      return true;
    });
  }, [cars, searchParams]);

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

      <section className="page-section" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button
          type="button"
          className="secondary-chip-btn"
          onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms`)}
        >
          Back to QMS overview
        </button>
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
      </section>

      <section className="page-section">
        <AuditHistoryPanel title="CAR history" entityType="qms_car" />
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

      <section className="page-section">
        <div className="card">
          <div className="card-header">
            <h2>Register</h2>
            <p className="text-muted">Auto-numbered entries with status, priority, and ownership.</p>
          </div>

          {state === "loading" && <p>Loading register…</p>}

          {state === "ready" && (
            <div className="table-responsive">
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
        </div>
      </section>

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

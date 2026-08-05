import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  BriefcaseBusiness,
  ChevronRight,
  GitBranch,
  Network,
  PencilLine,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  UserCog,
  UserMinus,
  UserPlus,
  X,
} from "lucide-react";
import {
  createGuidedAssignment,
  createReportingChain,
  decideTitlePreference,
  endReportingAssignment,
  getReportingWorkspace,
  transferReportingAssignment,
  updateReportingAssignment,
  updateReportingPosition,
  type ChainRoleInput,
  type GuidedAssignmentInput,
  type ReportingAssignmentTransferInput,
  type ReportingAssignmentUpdateInput,
  type ReportingOccupant,
  type ReportingPosition,
  type ReportingWorkspace,
} from "../../services/reportingLines";
import "../../styles/admin-corporate-structure.css";
import "../../styles/reporting-line-builder.css";

type PanelState =
  | { type: "chain"; parentPositionId?: string }
  | { type: "create-assignment"; positionId?: string }
  | { type: "position"; positionId: string }
  | { type: "assignment"; positionId: string; assignmentId: string }
  | null;

type ChainDraft = {
  title: string;
  code: string;
  headcount: string;
  supervisory: boolean;
};

type AssignmentAction = "update" | "end" | "transfer";

const today = new Date().toISOString().slice(0, 10);

function nextCalendarDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function latestDate(...values: string[]): string {
  return values.reduce((latest, current) => current > latest ? current : latest);
}

function message(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The reporting-line operation could not be completed.";
}

function directManager(position: ReportingPosition | undefined) {
  const direct = position?.manager_candidates.filter(
    (item) => item.relationship === "DIRECT_PARENT",
  ) ?? [];
  return direct.length === 1 ? direct[0] : null;
}

function canEditPosition(
  workspace: ReportingWorkspace,
  position: ReportingPosition,
): boolean {
  if (!position.editable) return false;
  return workspace.actor_mode === "ADMIN"
    || (!position.is_regulatory_post && !position.authority_acceptance_required);
}

function pathFor(amoCode: string | undefined, suffix: string): string {
  return amoCode
    ? `/maintenance/${encodeURIComponent(amoCode)}/${suffix.replace(/^\//, "")}`
    : `/${suffix.replace(/^\//, "")}`;
}

export default function ReportingLineBuilderPage() {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const [workspace, setWorkspace] = useState<ReportingWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelState>(null);
  const [unitFilter, setUnitFilter] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkspace(await getReportingWorkspace());
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const editableUnits = useMemo(
    () => workspace?.units.filter((unit) => unit.editable) ?? [],
    [workspace],
  );
  const editablePositions = useMemo(
    () => workspace?.positions.filter(
      (position) => canEditPosition(workspace, position),
    ) ?? [],
    [workspace],
  );
  const visiblePositions = useMemo(() => {
    if (!workspace) return [];
    const term = search.trim().toLowerCase();
    return workspace.positions.filter((position) => {
      if (unitFilter && position.unit_id !== unitFilter) return false;
      if (!term) return true;
      return [
        position.canonical_title,
        position.code,
        position.unit_name,
        position.reports_to_title ?? "",
        ...position.occupants.flatMap((item) => [
          item.user_name,
          item.display_title,
          item.reporting_manager_name ?? "",
        ]),
      ].some((value) => value.toLowerCase().includes(term));
    });
  }, [search, unitFilter, workspace]);

  async function run(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      setPanel(null);
      await load();
    } catch (saveError) {
      setError(message(saveError));
    } finally {
      setSaving(false);
    }
  }

  const selectedPosition = panel && "positionId" in panel
    ? workspace?.positions.find((item) => item.id === panel.positionId)
    : undefined;
  const selectedOccupant = panel?.type === "assignment"
    ? selectedPosition?.occupants.find(
      (item) => item.assignment_id === panel.assignmentId,
    )
    : undefined;

  const occupied = workspace?.positions.reduce(
    (sum, item) => sum + item.occupied_count,
    0,
  ) ?? 0;
  const vacancies = workspace?.positions.reduce(
    (sum, item) => sum + item.vacancy_count,
    0,
  ) ?? 0;

  const backPath = workspace?.actor_mode === "ADMIN"
    ? pathFor(amoCode, "admin/organization")
    : pathFor(amoCode, "manager/team");
  const backLabel = workspace?.actor_mode === "ADMIN"
    ? "Corporate structure"
    : "My team";

  return (
    <main className="corp-page reporting-builder">
      <header className="corp-page__header reporting-builder__header">
        <div>
          <Link className="workforce-back" to={backPath}>
            <ArrowLeft size={15} /> {backLabel}
          </Link>
          <span className="corp-eyebrow">
            <GitBranch size={15} /> Guided organization mapping
          </span>
          <h1>Reporting lines</h1>
          <p>
            Create any number of levels, assign people, correct manager mappings,
            transfer staff and keep preferred display titles separate from
            controlled positions and aviation authority.
          </p>
        </div>
        <div className="corp-header-actions">
          {workspace?.actor_mode === "ADMIN" ? (
            <Link
              className="corp-button corp-button--quiet"
              to={pathFor(amoCode, "admin/organization")}
            >
              <Network size={16} /> Corporate structure
            </Link>
          ) : (
            <Link
              className="corp-button corp-button--quiet"
              to={pathFor(amoCode, "manager/team")}
            >
              <BriefcaseBusiness size={16} /> My team
            </Link>
          )}
          <button
            className="corp-icon-button"
            type="button"
            onClick={() => void load()}
            disabled={loading}
            aria-label="Refresh reporting lines"
          >
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      {error ? (
        <div className="corp-alert" role="alert">
          <AlertTriangle size={17} />
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            <X size={15} />
          </button>
        </div>
      ) : null}

      <section className="reporting-builder__boundary">
        <ShieldCheck size={18} />
        <div>
          <strong>Authority remains independent</strong>
          <span>
            {workspace?.authorization_boundary ?? "Loading control boundary…"}
          </span>
        </div>
      </section>

      <section className="reporting-builder__metrics">
        <article><strong>{editableUnits.length}</strong><span>manageable units</span></article>
        <article><strong>{editablePositions.length}</strong><span>editable positions</span></article>
        <article><strong>{occupied}</strong><span>active occupants</span></article>
        <article className={vacancies ? "is-risk" : ""}><strong>{vacancies}</strong><span>open places</span></article>
        <article className={workspace?.pending_title_preferences.length ? "is-risk" : ""}>
          <strong>{workspace?.pending_title_preferences.length ?? 0}</strong>
          <span>title requests</span>
        </article>
      </section>

      <section className="reporting-builder__toolbar">
        <div>
          <select
            value={unitFilter}
            onChange={(event) => setUnitFilter(event.target.value)}
            aria-label="Filter by organization unit"
          >
            <option value="">All visible units</option>
            {workspace?.units.map((unit) => (
              <option key={unit.id} value={unit.id}>{unit.name}</option>
            ))}
          </select>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title, person, manager or unit"
            aria-label="Search reporting lines"
          />
        </div>
        <div>
          <button
            className="corp-button corp-button--quiet"
            type="button"
            onClick={() => setPanel({ type: "chain" })}
            disabled={!editableUnits.length}
          >
            <Plus size={16} /> Add reporting levels
          </button>
          <button
            className="corp-button"
            type="button"
            onClick={() => setPanel({ type: "create-assignment" })}
            disabled={!editablePositions.length}
          >
            <UserPlus size={16} /> Assign person
          </button>
        </div>
      </section>

      <div className={`reporting-builder__workspace${panel ? " is-split" : ""}`}>
        <section
          className="corp-table-shell reporting-builder__table"
          aria-busy={loading}
        >
          <table className="corp-table">
            <thead>
              <tr>
                <th>Reporting hierarchy</th>
                <th>Unit</th>
                <th>Occupants and titles</th>
                <th>Manager mapping</th>
                <th>Capacity</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visiblePositions.map((position) => {
                const editable = workspace
                  ? canEditPosition(workspace, position)
                  : false;
                return (
                  <tr key={position.id}>
                    <td>
                      <div
                        className="reporting-builder__position"
                        style={{
                          paddingInlineStart: `${Math.min(position.depth, 8) * 18}px`,
                        }}
                      >
                        {position.depth ? <ChevronRight size={14} /> : <GitBranch size={14} />}
                        <span>
                          <strong>{position.canonical_title}</strong>
                          <small>
                            {position.code} · {position.reports_to_title
                              ? `reports to ${position.reports_to_title}`
                              : "top position"}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <strong>{position.unit_name}</strong>
                      <small>
                        {position.is_supervisory ? "Supervisory" : "Individual role"}
                      </small>
                    </td>
                    <td>
                      {position.occupants.length ? position.occupants.map((occupant) => (
                        <div
                          className="reporting-builder__occupant reporting-builder__occupant--actionable"
                          key={occupant.assignment_id}
                        >
                          <div>
                            <strong>{occupant.user_name}</strong>
                            <span>{occupant.display_title}</span>
                            {occupant.display_title !== occupant.canonical_title ? (
                              <small>Canonical: {occupant.canonical_title}</small>
                            ) : (
                              <small>{occupant.staff_code}</small>
                            )}
                          </div>
                          {editable ? (
                            <button
                              type="button"
                              className="corp-row-link"
                              onClick={() => setPanel({
                                type: "assignment",
                                positionId: position.id,
                                assignmentId: occupant.assignment_id,
                              })}
                            >
                              Manage <UserCog size={14} />
                            </button>
                          ) : null}
                        </div>
                      )) : (
                        <span className="reporting-builder__muted">Vacant</span>
                      )}
                    </td>
                    <td>
                      {position.occupants.length ? position.occupants.map((occupant) => (
                        <div key={occupant.assignment_id}>
                          <strong>{occupant.reporting_manager_name ?? "Not mapped"}</strong>
                          <small>
                            {occupant.assignment_type}
                            {occupant.effective_to ? ` · ends ${occupant.effective_to}` : ""}
                          </small>
                        </div>
                      )) : (
                        <span className="reporting-builder__muted">
                          Parent: {position.reports_to_title ?? "none"}
                        </span>
                      )}
                    </td>
                    <td>
                      <strong>{position.occupied_count} / {position.headcount_limit}</strong>
                      <small>{position.vacancy_count} open</small>
                    </td>
                    <td>
                      <div className="reporting-builder__row-actions">
                        {editable ? (
                          <>
                            <button
                              className="corp-row-link"
                              type="button"
                              onClick={() => setPanel({
                                type: "position",
                                positionId: position.id,
                              })}
                            >
                              Edit position <PencilLine size={14} />
                            </button>
                            {position.vacancy_count > 0 ? (
                              <button
                                className="corp-row-link"
                                type="button"
                                onClick={() => setPanel({
                                  type: "create-assignment",
                                  positionId: position.id,
                                })}
                              >
                                Assign <UserPlus size={14} />
                              </button>
                            ) : null}
                            <button
                              className="corp-row-link"
                              type="button"
                              onClick={() => setPanel({
                                type: "chain",
                                parentPositionId: position.id,
                              })}
                            >
                              Add below <Plus size={14} />
                            </button>
                          </>
                        ) : (
                          <span className="corp-chip">View only</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!visiblePositions.length && !loading ? (
            <div className="corp-empty">
              <GitBranch size={26} />
              <strong>No reporting positions in view</strong>
              <span>
                Add a chain such as Supervisor → Chief Crew → Engineer under the
                correct organization unit.
              </span>
            </div>
          ) : null}
        </section>

        {panel?.type === "chain" && workspace ? (
          <ChainPanel
            workspace={workspace}
            saving={saving}
            initialParent={panel.parentPositionId ?? ""}
            onClose={() => setPanel(null)}
            onSubmit={(payload) => run(
              () => createReportingChain(workspace.actor_mode, payload),
            )}
          />
        ) : null}

        {panel?.type === "create-assignment" && workspace ? (
          <CreateAssignmentPanel
            workspace={workspace}
            saving={saving}
            initialPosition={panel.positionId ?? ""}
            onClose={() => setPanel(null)}
            onSubmit={(payload) => run(
              () => createGuidedAssignment(workspace.actor_mode, payload),
            )}
          />
        ) : null}

        {panel?.type === "position" && workspace && selectedPosition ? (
          <PositionPanel
            workspace={workspace}
            position={selectedPosition}
            saving={saving}
            onClose={() => setPanel(null)}
            onSubmit={(payload) => run(
              () => updateReportingPosition(
                workspace.actor_mode,
                selectedPosition.id,
                payload,
              ),
            )}
          />
        ) : null}

        {panel?.type === "assignment"
          && workspace
          && selectedPosition
          && selectedOccupant ? (
            <AssignmentLifecyclePanel
              workspace={workspace}
              position={selectedPosition}
              occupant={selectedOccupant}
              saving={saving}
              onClose={() => setPanel(null)}
              onUpdate={(payload) => run(
                () => updateReportingAssignment(
                  workspace.actor_mode,
                  selectedOccupant.assignment_id,
                  payload,
                ),
              )}
              onEnd={(endOn, reason) => run(
                () => endReportingAssignment(
                  workspace.actor_mode,
                  selectedOccupant.assignment_id,
                  endOn,
                  reason,
                ),
              )}
              onTransfer={(payload) => run(
                () => transferReportingAssignment(
                  workspace.actor_mode,
                  selectedOccupant.assignment_id,
                  payload,
                ),
              )}
            />
          ) : null}
      </div>

      <section className="corp-panel reporting-builder__requests">
        <header>
          <div>
            <h2><BadgeCheck size={17} /> Preferred title requests</h2>
            <p>
              Approval changes only the displayed working title. The canonical
              position and every access or authorisation control remain unchanged.
            </p>
          </div>
        </header>
        {workspace?.pending_title_preferences.length ? (
          <div className="reporting-builder__request-list">
            {workspace.pending_title_preferences.map((request) => (
              <article key={request.id}>
                <div>
                  <strong>{request.user_name}</strong>
                  <span>
                    {request.canonical_title} → <b>{request.requested_title}</b>
                  </span>
                  <small>{request.reason || "No reason supplied"}</small>
                </div>
                <div>
                  <button
                    className="corp-button corp-button--quiet"
                    type="button"
                    disabled={saving}
                    onClick={() => void run(
                      () => decideTitlePreference(
                        workspace.actor_mode,
                        request.id,
                        "REJECT",
                      ),
                    )}
                  >
                    Reject
                  </button>
                  <button
                    className="corp-button"
                    type="button"
                    disabled={saving}
                    onClick={() => void run(
                      () => decideTitlePreference(
                        workspace.actor_mode,
                        request.id,
                        "APPROVE",
                      ),
                    )}
                  >
                    Approve display title
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="corp-empty">
            <BadgeCheck size={24} />
            <strong>No pending title requests</strong>
            <span>
              Users can request a preferred display title from their organization profile.
            </span>
          </div>
        )}
      </section>
    </main>
  );
}

function PanelHeader({
  eyebrow,
  title,
  onClose,
}: {
  eyebrow: string;
  title: string;
  onClose: () => void;
}) {
  return (
    <header>
      <div><span>{eyebrow}</span><h2>{title}</h2></div>
      <button type="button" onClick={onClose} aria-label="Close panel">
        <X size={18} />
      </button>
    </header>
  );
}

function ChainPanel({
  workspace,
  saving,
  initialParent,
  onClose,
  onSubmit,
}: {
  workspace: ReportingWorkspace;
  saving: boolean;
  initialParent: string;
  onClose: () => void;
  onSubmit: (payload: {
    unit_id: string;
    parent_position_id: string | null;
    roles: ChainRoleInput[];
  }) => Promise<void>;
}) {
  const editableUnits = workspace.units.filter((unit) => unit.editable);
  const editablePositions = workspace.positions.filter(
    (position) => canEditPosition(workspace, position),
  );
  const initialPosition = editablePositions.find((item) => item.id === initialParent);
  const [unitId, setUnitId] = useState(
    initialPosition?.unit_id ?? editableUnits[0]?.id ?? "",
  );
  const [parentId, setParentId] = useState(initialParent);
  const [roles, setRoles] = useState<ChainDraft[]>([
    { title: "", code: "", headcount: "1", supervisory: true },
  ]);

  const update = (index: number, patch: Partial<ChainDraft>) => {
    setRoles((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onSubmit({
      unit_id: unitId,
      parent_position_id: parentId || null,
      roles: roles.map((role) => ({
        title: role.title.trim(),
        code: role.code.trim() || null,
        headcount_limit: Number(role.headcount || 1),
        is_supervisory: role.supervisory,
      })),
    });
  };

  return (
    <aside className="reporting-builder__panel">
      <PanelHeader
        eyebrow="Quick hierarchy wizard"
        title="Add reporting levels"
        onClose={onClose}
      />
      <form onSubmit={(event) => void submit(event)}>
        <label>
          <span>Organization unit</span>
          <select
            required
            value={unitId}
            onChange={(event) => {
              setUnitId(event.target.value);
              if (parentId) {
                const parent = editablePositions.find((item) => item.id === parentId);
                if (parent?.unit_id !== event.target.value) setParentId("");
              }
            }}
          >
            {editableUnits.map((unit) => (
              <option key={unit.id} value={unit.id}>{unit.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Attach beneath</span>
          <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">Create at top of this chain</option>
            {editablePositions
              .filter((position) => position.unit_id === unitId)
              .map((position) => (
                <option key={position.id} value={position.id}>
                  {position.path_titles.join(" › ")}
                </option>
              ))}
          </select>
        </label>
        <div className="reporting-builder__levels">
          <div>
            <strong>Levels are created top to bottom</strong>
            <small>Example: Supervisor, then Chief Crew, then Engineer.</small>
          </div>
          {roles.map((role, index) => (
            <article key={`${index}-${role.code}`}>
              <span>{index + 1}</span>
              <div>
                <input
                  required
                  value={role.title}
                  onChange={(event) => update(index, { title: event.target.value })}
                  placeholder={index === 0
                    ? "Supervisor"
                    : index === 1
                      ? "Chief Crew"
                      : "Engineer"}
                />
                <div>
                  <input
                    value={role.code}
                    onChange={(event) => update(index, { code: event.target.value })}
                    placeholder="Code auto-generated"
                  />
                  <input
                    required
                    type="number"
                    min="1"
                    value={role.headcount}
                    onChange={(event) => update(index, { headcount: event.target.value })}
                    aria-label="Headcount"
                  />
                </div>
                <label className="corp-check">
                  <input
                    type="checkbox"
                    checked={role.supervisory}
                    onChange={(event) => update(index, { supervisory: event.target.checked })}
                  />
                  <span>Can supervise lower levels</span>
                </label>
              </div>
              {roles.length > 1 ? (
                <button
                  type="button"
                  onClick={() => setRoles((current) => current.filter(
                    (_, itemIndex) => itemIndex !== index,
                  ))}
                  aria-label={`Remove level ${index + 1}`}
                >
                  <X size={15} />
                </button>
              ) : <span />}
            </article>
          ))}
        </div>
        <button
          className="corp-button corp-button--quiet reporting-builder__add-level"
          type="button"
          onClick={() => setRoles((current) => [
            ...current,
            {
              title: "",
              code: "",
              headcount: "1",
              supervisory: current.length < 2,
            },
          ])}
        >
          <Plus size={15} /> Add another level
        </button>
        <footer>
          <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="corp-button" type="submit" disabled={saving || !unitId}>
            {saving ? "Creating…" : "Create reporting chain"}
          </button>
        </footer>
      </form>
    </aside>
  );
}

function CreateAssignmentPanel({
  workspace,
  saving,
  initialPosition,
  onClose,
  onSubmit,
}: {
  workspace: ReportingWorkspace;
  saving: boolean;
  initialPosition: string;
  onClose: () => void;
  onSubmit: (payload: GuidedAssignmentInput) => Promise<void>;
}) {
  const positions = workspace.positions.filter(
    (position) => canEditPosition(workspace, position) && position.vacancy_count > 0,
  );
  const initial = positions.find((item) => item.id === initialPosition) ?? positions[0];
  const [userId, setUserId] = useState("");
  const [positionId, setPositionId] = useState(initial?.id ?? "");
  const [managerId, setManagerId] = useState(directManager(initial)?.user_id ?? "");
  const [displayTitle, setDisplayTitle] = useState(initial?.canonical_title ?? "");
  const [assignmentType, setAssignmentType] = useState("SUBSTANTIVE");
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [effectiveTo, setEffectiveTo] = useState("");
  const [fte, setFte] = useState("100");
  const [matrix, setMatrix] = useState(false);
  const [matrixReason, setMatrixReason] = useState("");
  const [appointmentReference, setAppointmentReference] = useState("");
  const [authorityReference, setAuthorityReference] = useState("");

  const position = positions.find((item) => item.id === positionId);
  const managerOptions = matrix
    ? workspace.users.map((user) => ({ user_id: user.id, user_name: user.full_name }))
    : position?.manager_candidates ?? [];

  const choosePosition = (id: string) => {
    const next = positions.find((item) => item.id === id);
    setPositionId(id);
    setManagerId(directManager(next)?.user_id ?? "");
    setDisplayTitle(next?.canonical_title ?? "");
    setAppointmentReference("");
    setAuthorityReference("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onSubmit({
      user_id: userId,
      position_id: positionId,
      reporting_manager_user_id: managerId || null,
      assignment_type: assignmentType,
      is_primary: true,
      effective_from: effectiveFrom,
      effective_to: effectiveTo || null,
      fte_percent: fte,
      matrix_reporting: matrix,
      matrix_reason: matrix ? matrixReason.trim() || null : null,
      display_title: displayTitle.trim() || null,
      appointment_reference: appointmentReference.trim() || null,
      authority_acceptance_reference: authorityReference.trim() || null,
      authority_accepted_on: null,
      delegation_limitations: null,
    });
  };

  return (
    <aside className="reporting-builder__panel">
      <PanelHeader
        eyebrow="Guided placement"
        title="Assign person"
        onClose={onClose}
      />
      <form onSubmit={(event) => void submit(event)}>
        <label>
          <span>Person</span>
          <select required value={userId} onChange={(event) => setUserId(event.target.value)}>
            <option value="">Select an active person</option>
            {workspace.users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name} · {user.staff_code}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Canonical position</span>
          <select required value={positionId} onChange={(event) => choosePosition(event.target.value)}>
            {positions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.path_titles.join(" › ")} · {item.vacancy_count} open
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Displayed working title</span>
          <input
            required
            minLength={2}
            maxLength={128}
            value={displayTitle}
            onChange={(event) => setDisplayTitle(event.target.value)}
          />
          <small>
            This may differ from the canonical position. It never grants access or aviation authority.
          </small>
        </label>
        <label>
          <span>Actual reporting manager</span>
          <select value={managerId} onChange={(event) => setManagerId(event.target.value)}>
            <option value="">Use the single occupied parent automatically</option>
            {managerOptions.map((candidate) => (
              <option key={`${candidate.user_id}-${"position_id" in candidate ? candidate.position_id : "matrix"}`} value={candidate.user_id}>
                {candidate.user_name}{"position_title" in candidate ? ` · ${candidate.position_title}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="corp-check">
          <input
            type="checkbox"
            checked={matrix}
            onChange={(event) => {
              setMatrix(event.target.checked);
              setManagerId("");
            }}
          />
          <span>Select a manager outside the position chain</span>
        </label>
        {matrix ? (
          <label>
            <span>Matrix-reporting reason</span>
            <textarea
              required
              rows={3}
              value={matrixReason}
              onChange={(event) => setMatrixReason(event.target.value)}
            />
          </label>
        ) : null}
        <div className="reporting-builder__form-row">
          <label>
            <span>Assignment type</span>
            <select value={assignmentType} onChange={(event) => setAssignmentType(event.target.value)}>
              {[
                "SUBSTANTIVE",
                "ACTING",
                "INTERIM",
                "SECONDMENT",
                "TEMPORARY",
                "INTERNSHIP",
                "APPRENTICESHIP",
                "CONTRACT",
              ].map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label>
            <span>Starts</span>
            <input
              required
              type="date"
              value={effectiveFrom}
              onChange={(event) => setEffectiveFrom(event.target.value)}
            />
          </label>
          <label>
            <span>Ends</span>
            <input
              type="date"
              min={effectiveFrom}
              value={effectiveTo}
              onChange={(event) => setEffectiveTo(event.target.value)}
            />
          </label>
        </div>
        <label>
          <span>FTE percentage</span>
          <input
            required
            type="number"
            min="0.01"
            max="100"
            step="0.01"
            value={fte}
            onChange={(event) => setFte(event.target.value)}
          />
        </label>
        {position?.is_regulatory_post ? (
          <label>
            <span>Appointment reference</span>
            <input
              required
              value={appointmentReference}
              onChange={(event) => setAppointmentReference(event.target.value)}
            />
          </label>
        ) : null}
        {position?.authority_acceptance_required ? (
          <label>
            <span>Authority acceptance reference</span>
            <input
              required
              value={authorityReference}
              onChange={(event) => setAuthorityReference(event.target.value)}
            />
          </label>
        ) : null}
        <div className="reporting-builder__notice">
          <ShieldCheck size={15} />
          <span>
            The portal checks effective-date overlap, primary placement, approved
            headcount, manager-chain cycles and regulatory evidence before saving.
          </span>
        </div>
        <footer>
          <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="corp-button"
            type="submit"
            disabled={saving || !userId || !positionId}
          >
            {saving ? "Assigning…" : "Create assignment"}
          </button>
        </footer>
      </form>
    </aside>
  );
}

function PositionPanel({
  workspace,
  position,
  saving,
  onClose,
  onSubmit,
}: {
  workspace: ReportingWorkspace;
  position: ReportingPosition;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [title, setTitle] = useState(position.canonical_title);
  const [parentId, setParentId] = useState(position.reports_to_position_id ?? "");
  const [headcount, setHeadcount] = useState(String(position.headcount_limit));
  const [supervisory, setSupervisory] = useState(position.is_supervisory);
  const [syncManagers, setSyncManagers] = useState(true);

  const parents = workspace.positions.filter(
    (item) => item.id !== position.id
      && item.unit_id === position.unit_id
      && canEditPosition(workspace, item),
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onSubmit({
      title: title.trim(),
      reports_to_position_id: parentId || null,
      headcount_limit: Number(headcount),
      is_supervisory: supervisory,
      sync_reporting_managers: syncManagers,
    });
  };

  return (
    <aside className="reporting-builder__panel">
      <PanelHeader
        eyebrow={position.code}
        title="Edit canonical position"
        onClose={onClose}
      />
      <form onSubmit={(event) => void submit(event)}>
        <label>
          <span>Canonical title</span>
          <input
            required
            minLength={2}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <small>
            Changing this updates occupants who do not have an approved preferred title.
          </small>
        </label>
        <label>
          <span>Reports to position</span>
          <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">Top of this chain</option>
            {parents.map((item) => (
              <option key={item.id} value={item.id}>
                {item.path_titles.join(" › ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Approved headcount</span>
          <input
            required
            type="number"
            min={Math.max(1, position.occupied_count)}
            value={headcount}
            onChange={(event) => setHeadcount(event.target.value)}
          />
          <small>Cannot be reduced below current active occupancy.</small>
        </label>
        <label className="corp-check">
          <input
            type="checkbox"
            checked={supervisory}
            onChange={(event) => setSupervisory(event.target.checked)}
          />
          <span>This position may supervise lower reporting levels</span>
        </label>
        <label className="corp-check">
          <input
            type="checkbox"
            checked={syncManagers}
            onChange={(event) => setSyncManagers(event.target.checked)}
          />
          <span>Update occupants to the single occupied parent manager where unambiguous</span>
        </label>
        <div className="reporting-builder__notice">
          <AlertTriangle size={15} />
          <span>
            Circular position chains are rejected. Regulatory positions remain
            tenant-administrator controlled.
          </span>
        </div>
        <footer>
          <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="corp-button" type="submit" disabled={saving}>
            <Save size={15} /> {saving ? "Saving…" : "Save position"}
          </button>
        </footer>
      </form>
    </aside>
  );
}

function AssignmentLifecyclePanel({
  workspace,
  position,
  occupant,
  saving,
  onClose,
  onUpdate,
  onEnd,
  onTransfer,
}: {
  workspace: ReportingWorkspace;
  position: ReportingPosition;
  occupant: ReportingOccupant;
  saving: boolean;
  onClose: () => void;
  onUpdate: (payload: ReportingAssignmentUpdateInput) => Promise<void>;
  onEnd: (endOn: string, reason: string) => Promise<void>;
  onTransfer: (payload: ReportingAssignmentTransferInput) => Promise<void>;
}) {
  const minimumEndDate = occupant.effective_from;
  const minimumTransferDate = nextCalendarDate(occupant.effective_from);
  const [action, setAction] = useState<AssignmentAction>("update");
  const [managerId, setManagerId] = useState(occupant.reporting_manager_user_id ?? "");
  const [displayTitle, setDisplayTitle] = useState(occupant.display_title);
  const [assignmentType, setAssignmentType] = useState(occupant.assignment_type);
  const [effectiveTo, setEffectiveTo] = useState(occupant.effective_to ?? "");
  const [fte, setFte] = useState(occupant.fte_percent);
  const [matrix, setMatrix] = useState(occupant.matrix_reporting);
  const [matrixReason, setMatrixReason] = useState(occupant.matrix_reason ?? "");
  const [notes, setNotes] = useState("");
  const [endOn, setEndOn] = useState(latestDate(today, minimumEndDate));
  const [endReason, setEndReason] = useState("");

  const transferPositions = workspace.positions.filter(
    (item) => item.id !== position.id
      && item.vacancy_count > 0
      && canEditPosition(workspace, item),
  );
  const [targetPositionId, setTargetPositionId] = useState(
    transferPositions[0]?.id ?? "",
  );
  const [transferDate, setTransferDate] = useState(
    latestDate(today, minimumTransferDate),
  );
  const [transferManagerId, setTransferManagerId] = useState(
    directManager(transferPositions[0])?.user_id ?? "",
  );
  const [transferDisplayTitle, setTransferDisplayTitle] = useState(
    transferPositions[0]?.canonical_title ?? "",
  );
  const [transferType, setTransferType] = useState(occupant.assignment_type);
  const [transferFte, setTransferFte] = useState(occupant.fte_percent);
  const [transferMatrix, setTransferMatrix] = useState(false);
  const [transferMatrixReason, setTransferMatrixReason] = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [appointmentReference, setAppointmentReference] = useState("");
  const [authorityReference, setAuthorityReference] = useState("");

  const updateManagerOptions = matrix
    ? workspace.users.map((user) => ({ user_id: user.id, user_name: user.full_name }))
    : position.manager_candidates;
  const targetPosition = transferPositions.find((item) => item.id === targetPositionId);
  const transferManagerOptions = transferMatrix
    ? workspace.users.map((user) => ({ user_id: user.id, user_name: user.full_name }))
    : targetPosition?.manager_candidates ?? [];

  const chooseTransferPosition = (id: string) => {
    const next = transferPositions.find((item) => item.id === id);
    setTargetPositionId(id);
    setTransferManagerId(directManager(next)?.user_id ?? "");
    setTransferDisplayTitle(next?.canonical_title ?? "");
    setAppointmentReference("");
    setAuthorityReference("");
  };

  const submitUpdate = async (event: FormEvent) => {
    event.preventDefault();
    await onUpdate({
      reporting_manager_user_id: managerId || null,
      assignment_type: assignmentType,
      effective_to: effectiveTo || null,
      fte_percent: fte,
      matrix_reporting: matrix,
      matrix_reason: matrix ? matrixReason.trim() || null : null,
      display_title: displayTitle.trim() || position.canonical_title,
      notes: notes.trim() || null,
    });
  };

  const submitEnd = async (event: FormEvent) => {
    event.preventDefault();
    await onEnd(endOn, endReason);
  };

  const submitTransfer = async (event: FormEvent) => {
    event.preventDefault();
    await onTransfer({
      target_position_id: targetPositionId,
      effective_from: transferDate,
      reporting_manager_user_id: transferManagerId || null,
      assignment_type: transferType,
      fte_percent: transferFte,
      matrix_reporting: transferMatrix,
      matrix_reason: transferMatrix ? transferMatrixReason.trim() || null : null,
      display_title: transferDisplayTitle.trim() || null,
      appointment_reference: appointmentReference.trim() || null,
      authority_acceptance_reference: authorityReference.trim() || null,
      authority_accepted_on: null,
      delegation_limitations: null,
      reason: transferReason.trim(),
    });
  };

  return (
    <aside className="reporting-builder__panel reporting-builder__panel--assignment">
      <PanelHeader
        eyebrow={`${occupant.staff_code} · ${position.code}`}
        title={occupant.user_name}
        onClose={onClose}
      />
      <div className="reporting-builder__action-tabs" role="tablist">
        <button
          type="button"
          className={action === "update" ? "is-active" : ""}
          onClick={() => setAction("update")}
        >
          <UserCog size={15} /> Correct mapping
        </button>
        <button
          type="button"
          className={action === "transfer" ? "is-active" : ""}
          onClick={() => setAction("transfer")}
        >
          <BriefcaseBusiness size={15} /> Transfer
        </button>
        <button
          type="button"
          className={action === "end" ? "is-active" : ""}
          onClick={() => setAction("end")}
        >
          <UserMinus size={15} /> End
        </button>
      </div>

      {action === "update" ? (
        <form onSubmit={(event) => void submitUpdate(event)}>
          <div className="reporting-builder__assignment-summary">
            <span>Canonical position</span>
            <strong>{position.canonical_title}</strong>
            <small>{position.path_titles.join(" › ")}</small>
          </div>
          <label>
            <span>Displayed working title</span>
            <input
              required
              minLength={2}
              maxLength={128}
              value={displayTitle}
              onChange={(event) => setDisplayTitle(event.target.value)}
            />
            <small>Enter the canonical title to remove a previous preferred title.</small>
          </label>
          <label>
            <span>Actual reporting manager</span>
            <select value={managerId} onChange={(event) => setManagerId(event.target.value)}>
              <option value="">Resolve from the occupied parent position</option>
              {updateManagerOptions.map((candidate) => (
                <option key={`${candidate.user_id}-${"position_id" in candidate ? candidate.position_id : "matrix"}`} value={candidate.user_id}>
                  {candidate.user_name}{"position_title" in candidate ? ` · ${candidate.position_title}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="corp-check">
            <input
              type="checkbox"
              checked={matrix}
              onChange={(event) => {
                setMatrix(event.target.checked);
                setManagerId("");
              }}
            />
            <span>Use a documented manager outside the position hierarchy</span>
          </label>
          {matrix ? (
            <label>
              <span>Matrix-reporting reason</span>
              <textarea
                required
                rows={3}
                value={matrixReason}
                onChange={(event) => setMatrixReason(event.target.value)}
              />
            </label>
          ) : null}
          <div className="reporting-builder__form-row">
            <label>
              <span>Assignment type</span>
              <select value={assignmentType} onChange={(event) => setAssignmentType(event.target.value)}>
                {[
                  "SUBSTANTIVE",
                  "ACTING",
                  "INTERIM",
                  "SECONDMENT",
                  "TEMPORARY",
                  "INTERNSHIP",
                  "APPRENTICESHIP",
                  "CONTRACT",
                ].map((value) => <option key={value}>{value}</option>)}
              </select>
            </label>
            <label>
              <span>FTE percentage</span>
              <input
                required
                type="number"
                min="0.01"
                max="100"
                step="0.01"
                value={fte}
                onChange={(event) => setFte(event.target.value)}
              />
            </label>
            <label>
              <span>Scheduled end</span>
              <input
                type="date"
                min={minimumEndDate}
                value={effectiveTo}
                onChange={(event) => setEffectiveTo(event.target.value)}
              />
            </label>
          </div>
          <label>
            <span>Change note</span>
            <textarea
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Reason for correcting the mapping or title"
            />
          </label>
          <footer>
            <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="corp-button" type="submit" disabled={saving}>
              <Save size={15} /> {saving ? "Saving…" : "Save assignment"}
            </button>
          </footer>
        </form>
      ) : null}

      {action === "end" ? (
        <form onSubmit={(event) => void submitEnd(event)}>
          <div className="reporting-builder__notice reporting-builder__notice--danger">
            <AlertTriangle size={16} />
            <span>
              Ending the assignment preserves its history. It does not delete the
              user account, revoke credentials or automatically change aviation
              authorisations; those remain controlled by their respective workflows.
            </span>
          </div>
          <label>
            <span>Last effective day</span>
            <input
              required
              type="date"
              min={minimumEndDate}
              value={endOn}
              onChange={(event) => setEndOn(event.target.value)}
            />
          </label>
          <label>
            <span>Reason</span>
            <textarea
              required
              minLength={2}
              rows={4}
              value={endReason}
              onChange={(event) => setEndReason(event.target.value)}
              placeholder="End of acting duty, transfer, separation or correction"
            />
          </label>
          <footer>
            <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="corp-button corp-button--danger" type="submit" disabled={saving || endReason.trim().length < 2}>
              <UserMinus size={15} /> {saving ? "Ending…" : "End assignment"}
            </button>
          </footer>
        </form>
      ) : null}

      {action === "transfer" ? (
        <form onSubmit={(event) => void submitTransfer(event)}>
          {!transferPositions.length ? (
            <div className="corp-empty">
              <BriefcaseBusiness size={23} />
              <strong>No available target position</strong>
              <span>Create a position or increase approved headcount first.</span>
            </div>
          ) : (
            <>
              <label>
                <span>Target position</span>
                <select
                  required
                  value={targetPositionId}
                  onChange={(event) => chooseTransferPosition(event.target.value)}
                >
                  {transferPositions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.path_titles.join(" › ")} · {item.vacancy_count} open
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Transfer effective date</span>
                <input
                  required
                  type="date"
                  min={minimumTransferDate}
                  value={transferDate}
                  onChange={(event) => setTransferDate(event.target.value)}
                />
                <small>The current assignment ends on the previous calendar day.</small>
              </label>
              <label>
                <span>Displayed working title</span>
                <input
                  required
                  minLength={2}
                  value={transferDisplayTitle}
                  onChange={(event) => setTransferDisplayTitle(event.target.value)}
                />
              </label>
              <label>
                <span>New reporting manager</span>
                <select
                  value={transferManagerId}
                  onChange={(event) => setTransferManagerId(event.target.value)}
                >
                  <option value="">Resolve from the occupied parent position</option>
                  {transferManagerOptions.map((candidate) => (
                    <option key={`${candidate.user_id}-${"position_id" in candidate ? candidate.position_id : "matrix"}`} value={candidate.user_id}>
                      {candidate.user_name}{"position_title" in candidate ? ` · ${candidate.position_title}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="corp-check">
                <input
                  type="checkbox"
                  checked={transferMatrix}
                  onChange={(event) => {
                    setTransferMatrix(event.target.checked);
                    setTransferManagerId("");
                  }}
                />
                <span>Use a documented matrix manager</span>
              </label>
              {transferMatrix ? (
                <label>
                  <span>Matrix-reporting reason</span>
                  <textarea
                    required
                    rows={3}
                    value={transferMatrixReason}
                    onChange={(event) => setTransferMatrixReason(event.target.value)}
                  />
                </label>
              ) : null}
              <div className="reporting-builder__form-row">
                <label>
                  <span>New assignment type</span>
                  <select value={transferType} onChange={(event) => setTransferType(event.target.value)}>
                    {[
                      "SUBSTANTIVE",
                      "ACTING",
                      "INTERIM",
                      "SECONDMENT",
                      "TEMPORARY",
                    ].map((value) => <option key={value}>{value}</option>)}
                  </select>
                </label>
                <label>
                  <span>New FTE percentage</span>
                  <input
                    required
                    type="number"
                    min="0.01"
                    max="100"
                    step="0.01"
                    value={transferFte}
                    onChange={(event) => setTransferFte(event.target.value)}
                  />
                </label>
              </div>
              {targetPosition?.is_regulatory_post ? (
                <label>
                  <span>Appointment reference</span>
                  <input
                    required
                    value={appointmentReference}
                    onChange={(event) => setAppointmentReference(event.target.value)}
                  />
                </label>
              ) : null}
              {targetPosition?.authority_acceptance_required ? (
                <label>
                  <span>Authority acceptance reference</span>
                  <input
                    required
                    value={authorityReference}
                    onChange={(event) => setAuthorityReference(event.target.value)}
                  />
                </label>
              ) : null}
              <label>
                <span>Transfer reason</span>
                <textarea
                  required
                  minLength={2}
                  rows={4}
                  value={transferReason}
                  onChange={(event) => setTransferReason(event.target.value)}
                />
              </label>
              <footer>
                <button className="corp-button corp-button--quiet" type="button" onClick={onClose}>
                  Cancel
                </button>
                <button
                  className="corp-button"
                  type="submit"
                  disabled={saving || !targetPositionId || transferReason.trim().length < 2}
                >
                  <BriefcaseBusiness size={15} /> {saving ? "Transferring…" : "Transfer person"}
                </button>
              </footer>
            </>
          )}
        </form>
      ) : null}
    </aside>
  );
}

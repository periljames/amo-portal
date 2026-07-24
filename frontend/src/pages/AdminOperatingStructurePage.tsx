import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, Building2, CalendarRange, CheckCircle2, Pencil, Plus, RefreshCw, UserRoundCheck, X } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { ContextualHelp } from "../components/UI/ContextualHelp";
import {
  cancelUserBaseAssignment,
  createBaseStation,
  createUserBaseAssignment,
  getBaseStationImpact,
  listBaseStations,
  listUserBaseAssignments,
  updateBaseStation,
  updateUserBaseAssignment,
} from "../services/foundations";
import { listAllRosterPeople, type RosterPersonRead } from "../services/rosterPeople";
import { getCurrentWorkforcePermissions } from "../services/workforce";
import type {
  BaseAssignmentKind,
  BaseStationCreate,
  BaseStationImpactRead,
  BaseStationRead,
  BaseStationType,
  UserBaseAssignmentRead,
} from "../types/foundations";
import "../styles/admin-operating-structure.css";

type Tab = "bases" | "deployments";
type SourceKey = "permissions" | "bases" | "people" | "deployments" | "action";
type DeploymentAction = { assignment: UserBaseAssignmentRead; mode: "cancel" | "end"; reason: string };
type BaseAction = { base: BaseStationRead; impact: BaseStationImpactRead; reason: string };

const BASE_TYPES: BaseStationType[] = ["MAIN_BASE", "LINE_STATION", "OUTSTATION", "WORKSHOP", "HANGAR", "TRAINING_SITE", "OTHER"];
const ASSIGNMENT_KINDS: BaseAssignmentKind[] = ["HOME_BASE", "TEMPORARY", "RELIEF", "TRAINING", "OTHER"];
const DATED_KINDS = new Set<BaseAssignmentKind>(["TEMPORARY", "RELIEF", "TRAINING"]);
const EMPTY_BASE: BaseStationCreate = {
  code: "", name: "", base_type: "LINE_STATION", icao_code: "", iata_code: "",
  time_zone: "Africa/Nairobi", aliases: [], description: "", is_active: true,
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const value = error as { message?: string; detail?: unknown; response?: { data?: { detail?: unknown } } };
    const detail = value.response?.data?.detail ?? value.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const record = detail as Record<string, unknown>;
      return String(record.message || record.detail || record.error_code || value.message || "The request could not be completed.");
    }
    return value.message || "The request could not be completed.";
  }
  return String(error || "The request could not be completed.");
}

export default function AdminOperatingStructurePage() {
  const { amoCode = "UNKNOWN" } = useParams();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("returnTo") || "";

  const [permissionsReady, setPermissionsReady] = useState(false);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("bases");
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [people, setPeople] = useState<RosterPersonRead[]>([]);
  const [assignments, setAssignments] = useState<UserBaseAssignmentRead[]>([]);
  const [loading, setLoading] = useState<Record<Exclude<SourceKey, "action">, boolean>>({ permissions: true, bases: false, people: false, deployments: false });
  const [errors, setErrors] = useState<Partial<Record<SourceKey, string>>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const [editingBase, setEditingBase] = useState<BaseStationRead | null>(null);
  const [baseForm, setBaseForm] = useState<BaseStationCreate>(EMPTY_BASE);
  const [aliases, setAliases] = useState("");
  const [baseReason, setBaseReason] = useState("");
  const [baseAction, setBaseAction] = useState<BaseAction | null>(null);
  const [deploymentAction, setDeploymentAction] = useState<DeploymentAction | null>(null);
  const [deploymentForm, setDeploymentForm] = useState({
    user_id: "", base_station_id: "", assignment_kind: "TEMPORARY" as BaseAssignmentKind,
    effective_from: todayIso(), effective_to: "", note: "",
  });

  const has = useCallback((code: string) => permissions.includes(code), [permissions]);
  const canViewBases = has("organisation.bases.view");
  const canManageBases = has("organisation.bases.manage");
  const canViewDeployments = has("workforce.deployments.view");
  const canManageDeployments = has("workforce.deployments.manage");

  const sourceError = useCallback((key: SourceKey, value?: string) => {
    setErrors((current) => ({ ...current, [key]: value }));
  }, []);
  const sourceLoading = useCallback((key: Exclude<SourceKey, "action">, value: boolean) => {
    setLoading((current) => ({ ...current, [key]: value }));
  }, []);

  const loadPermissions = useCallback(async () => {
    sourceLoading("permissions", true);
    sourceError("permissions");
    try {
      setPermissions((await getCurrentWorkforcePermissions()).permissions);
    } catch (cause) {
      sourceError("permissions", errorMessage(cause));
    } finally {
      setPermissionsReady(true);
      sourceLoading("permissions", false);
    }
  }, [sourceError, sourceLoading]);

  const loadBases = useCallback(async () => {
    sourceLoading("bases", true);
    sourceError("bases");
    try {
      setBases(await listBaseStations({ include_inactive: canManageBases }));
    } catch (cause) {
      sourceError("bases", errorMessage(cause));
    } finally {
      sourceLoading("bases", false);
    }
  }, [canManageBases, sourceError, sourceLoading]);

  const loadPeople = useCallback(async () => {
    if (!canManageDeployments) return;
    sourceLoading("people", true);
    sourceError("people");
    try {
      const result = await listAllRosterPeople({ page_size: 250, active_only: true, roster_eligible_only: false });
      setPeople(result.items);
    } catch (cause) {
      sourceError("people", errorMessage(cause));
    } finally {
      sourceLoading("people", false);
    }
  }, [canManageDeployments, sourceError, sourceLoading]);

  const loadDeployments = useCallback(async () => {
    if (!canViewDeployments) return;
    sourceLoading("deployments", true);
    sourceError("deployments");
    try {
      setAssignments(await listUserBaseAssignments({ include_expired: true }));
    } catch (cause) {
      sourceError("deployments", errorMessage(cause));
    } finally {
      sourceLoading("deployments", false);
    }
  }, [canViewDeployments, sourceError, sourceLoading]);

  useEffect(() => { void loadPermissions(); }, [loadPermissions]);
  useEffect(() => {
    if (!permissionsReady) return;
    if (canViewBases) void loadBases();
    else if (canViewDeployments) setTab("deployments");
  }, [canViewBases, canViewDeployments, loadBases, permissionsReady]);
  useEffect(() => {
    if (tab !== "deployments" || !canViewDeployments) return;
    void loadDeployments();
    void loadPeople();
  }, [canViewDeployments, loadDeployments, loadPeople, tab]);

  const peopleById = useMemo(() => new Map(people.map((person) => [person.user_id, person])), [people]);
  const activeBases = useMemo(() => bases.filter((base) => base.is_active), [bases]);
  const needsEnd = DATED_KINDS.has(deploymentForm.assignment_kind);
  const deploymentReady = Boolean(
    deploymentForm.user_id && deploymentForm.base_station_id && deploymentForm.effective_from
    && (!needsEnd || deploymentForm.effective_to)
    && (deploymentForm.assignment_kind === "HOME_BASE" || deploymentForm.note.trim()),
  );

  const resetBase = () => {
    setEditingBase(null);
    setBaseForm(EMPTY_BASE);
    setAliases("");
    setBaseReason("");
  };

  const editBase = (base: BaseStationRead) => {
    setEditingBase(base);
    setBaseForm({
      code: base.code, name: base.name, base_type: base.base_type,
      icao_code: base.icao_code || "", iata_code: base.iata_code || "",
      time_zone: base.time_zone || "Africa/Nairobi", description: base.description || "",
      aliases: base.aliases.map((alias) => alias.alias), is_active: base.is_active,
    });
    setAliases(base.aliases.map((alias) => alias.alias).join(", "));
    setBaseReason("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveBase = async () => {
    if (!canManageBases || !baseForm.code.trim() || !baseForm.name.trim()) return;
    if (editingBase && !baseReason.trim()) return sourceError("action", "A change reason is required.");
    setBusy("base");
    sourceError("action");
    const payload: BaseStationCreate = {
      ...baseForm,
      code: baseForm.code.trim().toUpperCase(),
      name: baseForm.name.trim(),
      icao_code: baseForm.icao_code?.trim().toUpperCase() || null,
      iata_code: baseForm.iata_code?.trim().toUpperCase() || null,
      time_zone: baseForm.time_zone?.trim() || null,
      description: baseForm.description?.trim() || null,
      aliases: aliases.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
    };
    try {
      if (editingBase) await updateBaseStation(editingBase.id, { ...payload, expected_updated_at: editingBase.updated_at, reason: baseReason.trim() });
      else await createBaseStation(payload);
      resetBase();
      await loadBases();
    } catch (cause) {
      sourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const beginToggleBase = async (base: BaseStationRead) => {
    if (!canManageBases) return;
    sourceError("action");
    if (!base.is_active) {
      setBusy(`base:${base.id}`);
      try {
        await updateBaseStation(base.id, { is_active: true, expected_updated_at: base.updated_at, reason: "Reactivated from Operating Structure" });
        await loadBases();
      } catch (cause) {
        sourceError("action", errorMessage(cause));
      } finally {
        setBusy(null);
      }
      return;
    }
    setBusy(`impact:${base.id}`);
    try {
      setBaseAction({ base, impact: await getBaseStationImpact(base.id), reason: "" });
    } catch (cause) {
      sourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const deactivateBase = async () => {
    if (!baseAction?.impact.can_deactivate || !baseAction.reason.trim()) return;
    setBusy(`base:${baseAction.base.id}`);
    try {
      await updateBaseStation(baseAction.base.id, {
        is_active: false,
        expected_updated_at: baseAction.base.updated_at,
        reason: baseAction.reason.trim(),
      });
      setBaseAction(null);
      await loadBases();
    } catch (cause) {
      sourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const createDeployment = async () => {
    if (!canManageDeployments || !deploymentReady) return;
    setBusy("deployment");
    sourceError("action");
    try {
      await createUserBaseAssignment({
        user_id: deploymentForm.user_id,
        base_station_id: deploymentForm.base_station_id,
        assignment_kind: deploymentForm.assignment_kind,
        effective_from: deploymentForm.effective_from,
        effective_to: deploymentForm.effective_to || null,
        is_primary: true,
        note: deploymentForm.note.trim() || null,
      });
      setDeploymentForm({ user_id: "", base_station_id: "", assignment_kind: "TEMPORARY", effective_from: todayIso(), effective_to: "", note: "" });
      await loadDeployments();
    } catch (cause) {
      sourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const beginDeploymentAction = (assignment: UserBaseAssignmentRead) => {
    setDeploymentAction({ assignment, mode: assignment.effective_from > todayIso() ? "cancel" : "end", reason: "" });
  };

  const applyDeploymentAction = async () => {
    if (!deploymentAction?.reason.trim()) return;
    const { assignment, mode, reason } = deploymentAction;
    setBusy(`deployment:${assignment.id}`);
    try {
      if (mode === "cancel") {
        await cancelUserBaseAssignment(assignment.id, { reason: reason.trim(), expected_updated_at: assignment.updated_at });
      } else {
        await updateUserBaseAssignment(assignment.id, { effective_to: todayIso(), expected_updated_at: assignment.updated_at, reason: reason.trim() });
      }
      setDeploymentAction(null);
      await loadDeployments();
    } catch (cause) {
      sourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const refresh = () => tab === "bases" ? void loadBases() : void Promise.allSettled([loadDeployments(), loadPeople()]);
  const currentLoading = loading.permissions || (tab === "bases" ? loading.bases : loading.deployments);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={canManageBases ? "admin-assets" : "rostering"}>
      <div className="operating-structure">
        <header className="operating-structure__header">
          <div><h1>Operating structure</h1><p>One canonical base master and effective-dated personnel deployments for the entire tenant.</p></div>
          <div className="operating-structure__actions">
            {returnTo ? <Link className="btn btn-secondary" to={returnTo}><ArrowLeft size={16} /> Return to planner</Link> : null}
            <ContextualHelp
              topic="admin-operating-structure"
              version={2}
              title="One base master for every module"
              description="Create each physical base once. Use dated deployments for temporary movement rather than overwriting the home base."
              checklist={["HOME BASE remains durable.", "Temporary, relief and training movements require exact dates.", "A deployment does not grant technical authorisation."]}
            />
            <button className="btn btn-secondary" type="button" onClick={refresh} disabled={currentLoading}><RefreshCw size={16} className={currentLoading ? "is-spinning" : ""} /> Refresh</button>
          </div>
        </header>

        {(Object.entries(errors) as [SourceKey, string | undefined][]).map(([key, message]) => message ? <div key={key} className="operating-structure__error" role="alert">{key === "action" ? message : `${key}: ${message}`}</div> : null)}
        {permissionsReady && !canViewBases && !canViewDeployments ? <div className="operating-structure__error">No operating-structure capability is assigned to this account.</div> : null}

        <div className="operating-structure__tabs" role="tablist" aria-label="Operating structure sections">
          {canViewBases ? <button type="button" role="tab" aria-selected={tab === "bases"} className={tab === "bases" ? "is-active" : ""} onClick={() => setTab("bases")}><Building2 size={16} /> Bases and stations</button> : null}
          {canViewDeployments ? <button type="button" role="tab" aria-selected={tab === "deployments"} className={tab === "deployments" ? "is-active" : ""} onClick={() => setTab("deployments")}><UserRoundCheck size={16} /> Personnel deployments</button> : null}
        </div>

        {tab === "bases" && canViewBases ? (
          <section className="operating-structure__panel">
            {canManageBases ? <>
              <div className="operating-structure__section-head"><div><h2>{editingBase ? "Edit base" : "Add base"}</h2><p>These records are tenant-wide and audited.</p></div>{editingBase ? <button className="btn btn-secondary" onClick={resetBase}>Cancel edit</button> : null}</div>
              <div className="operating-structure__form">
                <label>Code<input value={baseForm.code} onChange={(e) => setBaseForm((v) => ({ ...v, code: e.target.value }))} /></label>
                <label>Name<input value={baseForm.name} onChange={(e) => setBaseForm((v) => ({ ...v, name: e.target.value }))} /></label>
                <label>Type<select value={baseForm.base_type} onChange={(e) => setBaseForm((v) => ({ ...v, base_type: e.target.value as BaseStationType }))}>{BASE_TYPES.map((value) => <option key={value}>{value}</option>)}</select></label>
                <label>Time zone<input value={baseForm.time_zone || ""} onChange={(e) => setBaseForm((v) => ({ ...v, time_zone: e.target.value }))} placeholder="Africa/Nairobi" /></label>
                <label>ICAO<input value={baseForm.icao_code || ""} onChange={(e) => setBaseForm((v) => ({ ...v, icao_code: e.target.value }))} /></label>
                <label>IATA<input value={baseForm.iata_code || ""} onChange={(e) => setBaseForm((v) => ({ ...v, iata_code: e.target.value }))} /></label>
                <label className="operating-structure__span-2">Aliases<input value={aliases} onChange={(e) => setAliases(e.target.value)} /></label>
                <label className="operating-structure__span-4">Description<textarea rows={2} value={baseForm.description || ""} onChange={(e) => setBaseForm((v) => ({ ...v, description: e.target.value }))} /></label>
                {editingBase ? <label className="operating-structure__span-4">Change reason<input value={baseReason} onChange={(e) => setBaseReason(e.target.value)} /></label> : null}
                <div className="operating-structure__span-4 operating-structure__actions"><span /><button className="btn btn-primary" onClick={() => void saveBase()} disabled={!baseForm.code.trim() || !baseForm.name.trim() || Boolean(editingBase && !baseReason.trim()) || busy === "base"}><Plus size={16} /> {editingBase ? "Save base" : "Create base"}</button></div>
              </div>
            </> : <div className="operating-structure__empty">Viewing only. <code>organisation.bases.manage</code> is required to change bases.</div>}

            {loading.bases && !bases.length ? <div className="operating-structure__empty">Loading bases…</div> : null}
            {!loading.bases && !bases.length ? <div className="operating-structure__empty">No canonical bases exist.</div> : null}
            <div className="operating-structure__grid">{bases.map((base) => <article className="operating-structure__card" key={base.id}>
              <header><div><strong>{base.code} · {base.name}</strong><small>{base.base_type.replace(/_/g, " ")} · {base.time_zone || "No time zone"}</small></div><span className={`operating-structure__status${base.is_active ? "" : " is-inactive"}`}>{base.is_active ? "ACTIVE" : "INACTIVE"}</span></header>
              <small>{[base.icao_code, base.iata_code, base.aliases.map((a) => a.alias).join(", ")].filter(Boolean).join(" · ") || "No external codes or aliases"}</small>
              {canManageBases ? <div className="operating-structure__actions"><button className="btn btn-secondary" onClick={() => editBase(base)}><Pencil size={15} /> Edit</button><button className="btn btn-secondary" disabled={busy === `base:${base.id}` || busy === `impact:${base.id}`} onClick={() => void beginToggleBase(base)}>{base.is_active ? "Check deactivation" : "Reactivate"}</button></div> : null}
            </article>)}</div>
          </section>
        ) : null}

        {tab === "deployments" && canViewDeployments ? (
          <section className="operating-structure__panel">
            <div className="operating-structure__section-head"><div><h2>Personnel base deployments</h2><p>Home base stays intact while temporary movement overlays exact dates.</p></div></div>
            {canManageDeployments ? <div className="operating-structure__form">
              <label className="operating-structure__span-2">Person<select value={deploymentForm.user_id} onChange={(e) => setDeploymentForm((v) => ({ ...v, user_id: e.target.value }))}><option value="">Select person</option>{people.map((p) => <option key={p.user_id} value={p.user_id}>{p.staff_code} · {p.full_name}</option>)}</select></label>
              <label>Base<select value={deploymentForm.base_station_id} onChange={(e) => setDeploymentForm((v) => ({ ...v, base_station_id: e.target.value }))}><option value="">Select base</option>{activeBases.map((b) => <option key={b.id} value={b.id}>{b.code} · {b.name}</option>)}</select></label>
              <label>Movement type<select value={deploymentForm.assignment_kind} onChange={(e) => setDeploymentForm((v) => ({ ...v, assignment_kind: e.target.value as BaseAssignmentKind }))}>{ASSIGNMENT_KINDS.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>Starts<input type="date" value={deploymentForm.effective_from} onChange={(e) => setDeploymentForm((v) => ({ ...v, effective_from: e.target.value }))} /></label>
              <label>Ends{needsEnd ? " *" : ""}<input type="date" value={deploymentForm.effective_to} onChange={(e) => setDeploymentForm((v) => ({ ...v, effective_to: e.target.value }))} /></label>
              <label className="operating-structure__span-2">Reason / note<input value={deploymentForm.note} onChange={(e) => setDeploymentForm((v) => ({ ...v, note: e.target.value }))} /></label>
              <div className="operating-structure__span-4 operating-structure__actions"><small>Dated movements require an end date and reason.</small><button className="btn btn-primary" onClick={() => void createDeployment()} disabled={!deploymentReady || busy === "deployment"}><CalendarRange size={16} /> Create deployment</button></div>
            </div> : <div className="operating-structure__empty">Assurance view only. <code>workforce.deployments.manage</code> is required to move personnel.</div>}

            {!loading.deployments && !assignments.length ? <div className="operating-structure__empty">No personnel base assignments exist.</div> : null}
            <div className="operating-structure__grid">{assignments.map((assignment) => {
              const person = peopleById.get(assignment.user_id);
              const ended = Boolean(assignment.effective_to && assignment.effective_to < todayIso());
              const future = assignment.effective_from > todayIso();
              return <article className="operating-structure__deployment" key={assignment.id}>
                <header><div><strong>{person?.full_name || assignment.user_id}</strong><small>{person?.staff_code || "Personnel record"} · {assignment.base_station?.code || assignment.base_station_id}</small></div><span className={`operating-structure__status${ended ? " is-inactive" : ""}`}>{assignment.assignment_kind.replace(/_/g, " ")}</span></header>
                <small>{assignment.effective_from} → {assignment.effective_to || "Open ended"}</small>{assignment.note ? <small>{assignment.note}</small> : null}
                {canManageDeployments && !ended && assignment.assignment_kind !== "HOME_BASE" ? <div className="operating-structure__actions"><span /><button className="btn btn-secondary" disabled={busy === `deployment:${assignment.id}`} onClick={() => beginDeploymentAction(assignment)}>{future ? "Cancel deployment" : "End today"}</button></div> : null}
              </article>;
            })}</div>
          </section>
        ) : null}
      </div>

      {baseAction ? <div className="portal-help-backdrop" role="presentation"><section className="portal-help-dialog" role="dialog" aria-modal="true" aria-label={`Deactivate ${baseAction.base.code}`}>
        <header className="portal-help-dialog__header"><div><span className="portal-help-dialog__eyebrow">Dependency check</span><h2>Deactivate {baseAction.base.code}?</h2></div><button className="portal-help-dialog__close" onClick={() => setBaseAction(null)} aria-label="Close"><X size={19} /></button></header>
        <div className="portal-help-dialog__body">{baseAction.impact.can_deactivate ? <p><CheckCircle2 size={18} /> No active deployment, contract or roster dependency blocks deactivation.</p> : <><p><AlertTriangle size={18} /> This base cannot be deactivated yet.</p><div className="portal-prerequisite-list">{baseAction.impact.dependencies.map((d) => <article className="portal-prerequisite-item" key={d.dependency_type}><AlertTriangle size={18} /><div><strong>{d.count} affected record{d.count === 1 ? "" : "s"}</strong><p>{d.detail}</p></div></article>)}</div></>}{baseAction.impact.can_deactivate ? <label>Reason<textarea rows={3} value={baseAction.reason} onChange={(e) => setBaseAction((v) => v ? { ...v, reason: e.target.value } : v)} /></label> : null}</div>
        <footer className="portal-help-dialog__footer"><button className="portal-help-button portal-help-button--secondary" onClick={() => setBaseAction(null)}>Close</button>{baseAction.impact.can_deactivate ? <button className="portal-help-button portal-help-button--primary" disabled={!baseAction.reason.trim()} onClick={() => void deactivateBase()}>Deactivate base</button> : null}</footer>
      </section></div> : null}

      {deploymentAction ? <div className="portal-help-backdrop" role="presentation"><section className="portal-help-dialog" role="dialog" aria-modal="true" aria-label="Deployment action">
        <header className="portal-help-dialog__header"><div><span className="portal-help-dialog__eyebrow">Controlled movement</span><h2>{deploymentAction.mode === "cancel" ? "Cancel future deployment" : "End active deployment today"}</h2></div><button className="portal-help-dialog__close" onClick={() => setDeploymentAction(null)} aria-label="Close"><X size={19} /></button></header>
        <div className="portal-help-dialog__body"><p>{deploymentAction.assignment.base_station?.code || deploymentAction.assignment.base_station_id} · {deploymentAction.assignment.effective_from} → {deploymentAction.assignment.effective_to || "Open ended"}</p><label>Reason<textarea rows={3} value={deploymentAction.reason} onChange={(e) => setDeploymentAction((v) => v ? { ...v, reason: e.target.value } : v)} /></label></div>
        <footer className="portal-help-dialog__footer"><button className="portal-help-button portal-help-button--secondary" onClick={() => setDeploymentAction(null)}>Keep deployment</button><button className="portal-help-button portal-help-button--primary" disabled={!deploymentAction.reason.trim()} onClick={() => void applyDeploymentAction()}>{deploymentAction.mode === "cancel" ? "Cancel deployment" : "End today"}</button></footer>
      </section></div> : null}
    </DepartmentLayout>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CalendarRange,
  CheckCircle2,
  Pencil,
  Plus,
  RefreshCw,
  UserRoundCheck,
  X,
} from "lucide-react";
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
type LoadingKey = "permissions" | "bases" | "people" | "deployments";

type DeploymentAction = {
  assignment: UserBaseAssignmentRead;
  mode: "cancel" | "end";
  reason: string;
};

type BaseAction = {
  base: BaseStationRead;
  impact: BaseStationImpactRead;
  reason: string;
};

const BASE_TYPES: BaseStationType[] = [
  "MAIN_BASE", "LINE_STATION", "OUTSTATION", "WORKSHOP", "HANGAR", "TRAINING_SITE", "OTHER",
];
const ASSIGNMENT_KINDS: BaseAssignmentKind[] = ["HOME_BASE", "TEMPORARY", "RELIEF", "TRAINING", "OTHER"];
const DATED_DEPLOYMENTS = new Set<BaseAssignmentKind>(["TEMPORARY", "RELIEF", "TRAINING"]);

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const candidate = error as {
      message?: string;
      detail?: unknown;
      responseBody?: unknown;
      response?: { data?: { detail?: unknown } };
    };
    const nested = candidate.response?.data?.detail ?? candidate.detail;
    if (typeof nested === "string") return nested;
    if (nested && typeof nested === "object") {
      const detail = nested as Record<string, unknown>;
      return String(detail.message || detail.detail || detail.error_code || candidate.message || "The request could not be completed.");
    }
    return candidate.message || "The request could not be completed.";
  }
  return String(error || "The request could not be completed.");
}

const EMPTY_BASE: BaseStationCreate = {
  code: "",
  name: "",
  base_type: "LINE_STATION",
  icao_code: "",
  iata_code: "",
  time_zone: "Africa/Nairobi",
  aliases: [],
  description: "",
  is_active: true,
};

export default function AdminOperatingStructurePage() {
  const { amoCode = "UNKNOWN" } = useParams();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("returnTo") || "";

  const [permissions, setPermissions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("bases");
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [people, setPeople] = useState<RosterPersonRead[]>([]);
  const [assignments, setAssignments] = useState<UserBaseAssignmentRead[]>([]);
  const [loading, setLoading] = useState<Set<LoadingKey>>(new Set(["permissions", "bases"]));
  const [errors, setErrors] = useState<Partial<Record<LoadingKey | "action", string>>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const [editingBase, setEditingBase] = useState<BaseStationRead | null>(null);
  const [baseForm, setBaseForm] = useState<BaseStationCreate>(EMPTY_BASE);
  const [aliasText, setAliasText] = useState("");
  const [baseReason, setBaseReason] = useState("");
  const [baseAction, setBaseAction] = useState<BaseAction | null>(null);
  const [deploymentAction, setDeploymentAction] = useState<DeploymentAction | null>(null);
  const [deploymentForm, setDeploymentForm] = useState({
    user_id: "",
    base_station_id: "",
    assignment_kind: "TEMPORARY" as BaseAssignmentKind,
    effective_from: todayIso(),
    effective_to: "",
    note: "",
  });

  const canViewBases = permissions.includes("organisation.bases.view");
  const canManageBases = permissions.includes("organisation.bases.manage");
  const canViewDeployments = permissions.includes("workforce.deployments.view");
  const canManageDeployments = permissions.includes("workforce.deployments.manage");

  const markLoading = useCallback((key: LoadingKey, value: boolean) => {
    setLoading((current) => {
      const next = new Set(current);
      if (value) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const setSourceError = useCallback((key: LoadingKey | "action", value?: string) => {
    setErrors((current) => ({ ...current, [key]: value }));
  }, []);

  const loadPermissions = useCallback(async () => {
    markLoading("permissions", true);
    setSourceError("permissions");
    try {
      const result = await getCurrentWorkforcePermissions();
      setPermissions(result.permissions);
    } catch (cause) {
      setSourceError("permissions", errorMessage(cause));
    } finally {
      markLoading("permissions", false);
    }
  }, [markLoading, setSourceError]);

  const loadBases = useCallback(async () => {
    markLoading("bases", true);
    setSourceError("bases");
    try {
      const nextBases = await listBaseStations({ include_inactive: canManageBases });
      setBases(nextBases);
    } catch (cause) {
      setSourceError("bases", errorMessage(cause));
    } finally {
      markLoading("bases", false);
    }
  }, [canManageBases, markLoading, setSourceError]);

  const loadPeople = useCallback(async () => {
    if (!canManageDeployments) return;
    markLoading("people", true);
    setSourceError("people");
    try {
      const result = await listAllRosterPeople({
        page_size: 250,
        active_only: true,
        roster_eligible_only: false,
      });
      setPeople(result.items);
    } catch (cause) {
      setSourceError("people", errorMessage(cause));
    } finally {
      markLoading("people", false);
    }
  }, [canManageDeployments, markLoading, setSourceError]);

  const loadDeployments = useCallback(async () => {
    if (!canViewDeployments) return;
    markLoading("deployments", true);
    setSourceError("deployments");
    try {
      setAssignments(await listUserBaseAssignments({ include_expired: true }));
    } catch (cause) {
      setSourceError("deployments", errorMessage(cause));
    } finally {
      markLoading("deployments", false);
    }
  }, [canViewDeployments, markLoading, setSourceError]);

  useEffect(() => {
    void loadPermissions();
  }, [loadPermissions]);

  useEffect(() => {
    if (loading.has("permissions")) return;
    if (canViewBases) void loadBases();
    if (!canViewBases && canViewDeployments) setTab("deployments");
  }, [canViewBases, canViewDeployments, loadBases, loading]);

  useEffect(() => {
    if (tab !== "deployments" || !canViewDeployments) return;
    void loadDeployments();
    void loadPeople();
  }, [canViewDeployments, loadDeployments, loadPeople, tab]);

  const peopleById = useMemo(() => new Map(people.map((person) => [person.user_id, person])), [people]);
  const activeBases = useMemo(() => bases.filter((base) => base.is_active), [bases]);
  const selectedRequiresEnd = DATED_DEPLOYMENTS.has(deploymentForm.assignment_kind);
  const deploymentCanSubmit = Boolean(
    deploymentForm.user_id
    && deploymentForm.base_station_id
    && deploymentForm.effective_from
    && (!selectedRequiresEnd || deploymentForm.effective_to)
    && (deploymentForm.assignment_kind === "HOME_BASE" || deploymentForm.note.trim()),
  );

  const resetBase = () => {
    setEditingBase(null);
    setBaseForm(EMPTY_BASE);
    setAliasText("");
    setBaseReason("");
  };

  const editBase = (base: BaseStationRead) => {
    if (!canManageBases) return;
    setEditingBase(base);
    setBaseForm({
      code: base.code,
      name: base.name,
      base_type: base.base_type,
      icao_code: base.icao_code || "",
      iata_code: base.iata_code || "",
      time_zone: base.time_zone || "Africa/Nairobi",
      description: base.description || "",
      aliases: base.aliases.map((alias) => alias.alias),
      is_active: base.is_active,
    });
    setAliasText(base.aliases.map((alias) => alias.alias).join(", "));
    setBaseReason("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveBase = async () => {
    if (!canManageBases || !baseForm.code.trim() || !baseForm.name.trim()) return;
    if (editingBase && !baseReason.trim()) {
      setSourceError("action", "Explain why this tenant-wide base record is being changed.");
      return;
    }
    setBusy("base");
    setSourceError("action");
    const payload: BaseStationCreate = {
      ...baseForm,
      code: baseForm.code.trim().toUpperCase(),
      name: baseForm.name.trim(),
      icao_code: baseForm.icao_code?.trim().toUpperCase() || null,
      iata_code: baseForm.iata_code?.trim().toUpperCase() || null,
      time_zone: baseForm.time_zone?.trim() || null,
      description: baseForm.description?.trim() || null,
      aliases: aliasText.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
    };
    try {
      if (editingBase) {
        await updateBaseStation(editingBase.id, {
          ...payload,
          expected_updated_at: editingBase.updated_at,
          reason: baseReason.trim(),
        });
      } else {
        await createBaseStation(payload);
      }
      resetBase();
      await loadBases();
    } catch (cause) {
      setSourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const beginBaseToggle = async (base: BaseStationRead) => {
    if (!canManageBases) return;
    setSourceError("action");
    if (!base.is_active) {
      setBusy(`base:${base.id}`);
      try {
        await updateBaseStation(base.id, {
          is_active: true,
          expected_updated_at: base.updated_at,
          reason: "Reactivated from Operating Structure",
        });
        await loadBases();
      } catch (cause) {
        setSourceError("action", errorMessage(cause));
      } finally {
        setBusy(null);
      }
      return;
    }

    setBusy(`impact:${base.id}`);
    try {
      const impact = await getBaseStationImpact(base.id);
      setBaseAction({ base, impact, reason: "" });
    } catch (cause) {
      setSourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const confirmDeactivate = async () => {
    if (!baseAction || !baseAction.impact.can_deactivate || !baseAction.reason.trim()) return;
    setBusy(`base:${baseAction.base.id}`);
    setSourceError("action");
    try {
      await updateBaseStation(baseAction.base.id, {
        is_active: false,
        expected_updated_at: baseAction.base.updated_at,
        reason: baseAction.reason.trim(),
      });
      setBaseAction(null);
      await loadBases();
    } catch (cause) {
      setSourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const createDeployment = async () => {
    if (!canManageDeployments || !deploymentCanSubmit) return;
    setBusy("deployment");
    setSourceError("action");
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
      setDeploymentForm({
        user_id: "",
        base_station_id: "",
        assignment_kind: "TEMPORARY",
        effective_from: todayIso(),
        effective_to: "",
        note: "",
      });
      await loadDeployments();
    } catch (cause) {
      setSourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const beginDeploymentAction = (assignment: UserBaseAssignmentRead) => {
    const future = assignment.effective_from > todayIso();
    setDeploymentAction({ assignment, mode: future ? "cancel" : "end", reason: "" });
  };

  const confirmDeploymentAction = async () => {
    if (!deploymentAction || !deploymentAction.reason.trim()) return;
    const { assignment, mode, reason } = deploymentAction;
    setBusy(`deployment:${assignment.id}`);
    setSourceError("action");
    try {
      if (mode === "cancel") {
        await cancelUserBaseAssignment(assignment.id, {
          reason: reason.trim(),
          expected_updated_at: assignment.updated_at,
        });
      } else {
        await updateUserBaseAssignment(assignment.id, {
          effective_to: todayIso(),
          expected_updated_at: assignment.updated_at,
          reason: reason.trim(),
        });
      }
      setDeploymentAction(null);
      await loadDeployments();
    } catch (cause) {
      setSourceError("action", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const refreshActive = () => {
    if (tab === "bases") void loadBases();
    else {
      void loadDeployments();
      void loadPeople();
    }
  };

  const pageLoading = loading.has("permissions") || (tab === "bases" ? loading.has("bases") : loading.has("deployments"));

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={canManageBases ? "admin-assets" : "rostering"}>
      <div className="operating-structure">
        <header className="operating-structure__header">
          <div>
            <h1>Operating structure</h1>
            <p>One canonical base master and effective-dated personnel deployments for the entire tenant.</p>
          </div>
          <div className="operating-structure__actions">
            {returnTo ? <Link className="btn btn-secondary" to={returnTo}><ArrowLeft size={16} /> Return to planner</Link> : null}
            <ContextualHelp
              topic="admin-operating-structure"
              version={2}
              title="One base master for every module"
              description="Administrators create each physical base, station, hangar or workshop once. Rostering, Planning, Production, Quality, Training and Stores consume those same records. A short transfer is recorded as a dated deployment instead of overwriting the employee's permanent home base."
              checklist={[
                "HOME BASE is the durable personnel station.",
                "TEMPORARY, RELIEF and TRAINING require exact dates and overlay the home base.",
                "A deployment changes placement; it does not grant technical authorisation.",
              ]}
            />
            <button className="btn btn-secondary" type="button" onClick={refreshActive} disabled={pageLoading}>
              <RefreshCw size={16} className={pageLoading ? "is-spinning" : ""} /> Refresh
            </button>
          </div>
        </header>

        {errors.permissions ? <div className="operating-structure__error" role="alert">Permissions could not be loaded: {errors.permissions}</div> : null}
        {errors.bases ? <div className="operating-structure__error" role="alert">Bases could not be loaded: {errors.bases}</div> : null}
        {errors.people ? <div className="operating-structure__error" role="alert">Personnel search is degraded: {errors.people}</div> : null}
        {errors.deployments ? <div className="operating-structure__error" role="alert">Deployments could not be loaded: {errors.deployments}</div> : null}
        {errors.action ? <div className="operating-structure__error" role="alert">{errors.action}</div> : null}

        {!loading.has("permissions") && !canViewBases && !canViewDeployments ? (
          <div className="operating-structure__error" role="alert">
            Your role cannot view operating structure or personnel deployments. Ask an AMO administrator to grant the required scoped capability.
          </div>
        ) : null}

        <div className="operating-structure__tabs" role="tablist" aria-label="Operating structure sections">
          {canViewBases ? (
            <button type="button" role="tab" aria-selected={tab === "bases"} className={tab === "bases" ? "is-active" : ""} onClick={() => setTab("bases")}>
              <Building2 size={16} /> Bases and stations
            </button>
          ) : null}
          {canViewDeployments ? (
            <button type="button" role="tab" aria-selected={tab === "deployments"} className={tab === "deployments" ? "is-active" : ""} onClick={() => setTab("deployments")}>
              <UserRoundCheck size={16} /> Personnel deployments
            </button>
          ) : null}
        </div>

        {tab === "bases" && canViewBases ? (
          <section className="operating-structure__panel">
            {canManageBases ? (
              <>
                <div className="operating-structure__section-head">
                  <div><h2>{editingBase ? "Edit base" : "Add base"}</h2><p>These records are tenant-wide; operational modules must not create their own base lists.</p></div>
                  {editingBase ? <button className="btn btn-secondary" type="button" onClick={resetBase}>Cancel edit</button> : null}
                </div>
                <div className="operating-structure__form">
                  <label>Code<input value={baseForm.code} onChange={(event) => setBaseForm((current) => ({ ...current, code: event.target.value }))} placeholder="WIL" /></label>
                  <label>Name<input value={baseForm.name} onChange={(event) => setBaseForm((current) => ({ ...current, name: event.target.value }))} placeholder="Wilson Airport" /></label>
                  <label>Type<select value={baseForm.base_type} onChange={(event) => setBaseForm((current) => ({ ...current, base_type: event.target.value as BaseStationType }))}>{BASE_TYPES.map((value) => <option key={value}>{value}</option>)}</select></label>
                  <label>Time zone<input value={baseForm.time_zone || ""} onChange={(event) => setBaseForm((current) => ({ ...current, time_zone: event.target.value }))} placeholder="Africa/Nairobi" /></label>
                  <label>ICAO<input value={baseForm.icao_code || ""} onChange={(event) => setBaseForm((current) => ({ ...current, icao_code: event.target.value }))} /></label>
                  <label>IATA<input value={baseForm.iata_code || ""} onChange={(event) => setBaseForm((current) => ({ ...current, iata_code: event.target.value }))} /></label>
                  <label className="operating-structure__span-2">Aliases<input value={aliasText} onChange={(event) => setAliasText(event.target.value)} placeholder="WILSON, HKNW" /></label>
                  <label className="operating-structure__span-4">Description<textarea rows={2} value={baseForm.description || ""} onChange={(event) => setBaseForm((current) => ({ ...current, description: event.target.value }))} /></label>
                  {editingBase ? <label className="operating-structure__span-4">Change reason<input value={baseReason} onChange={(event) => setBaseReason(event.target.value)} placeholder="Why is this tenant-wide record changing?" /></label> : null}
                  <div className="operating-structure__span-4 operating-structure__actions"><span /><button className="btn btn-primary" type="button" onClick={() => void saveBase()} disabled={!baseForm.code.trim() || !baseForm.name.trim() || Boolean(editingBase && !baseReason.trim()) || busy === "base"}><Plus size={16} /> {editingBase ? "Save base" : "Create base"}</button></div>
                </div>
              </>
            ) : <div className="operating-structure__empty">You can view active bases but need <code>organisation.bases.manage</code> to change them.</div>}

            {loading.has("bases") && !bases.length ? <div className="operating-structure__empty">Loading bases…</div> : null}
            {!loading.has("bases") && !bases.length ? <div className="operating-structure__empty">No bases exist. An administrator must create the first operating location.</div> : null}
            <div className="operating-structure__grid">
              {bases.map((base) => (
                <article className="operating-structure__card" key={base.id}>
                  <header><div><strong>{base.code} · {base.name}</strong><small>{base.base_type.replace(/_/g, " ")} · {base.time_zone || "No time zone"}</small></div><span className={`operating-structure__status${base.is_active ? "" : " is-inactive"}`}>{base.is_active ? "ACTIVE" : "INACTIVE"}</span></header>
                  <small>{[base.icao_code, base.iata_code, base.aliases.map((alias) => alias.alias).join(", ")].filter(Boolean).join(" · ") || "No external codes or aliases"}</small>
                  {canManageBases ? <div className="operating-structure__actions"><button className="btn btn-secondary" type="button" onClick={() => editBase(base)}><Pencil size={15} /> Edit</button><button className="btn btn-secondary" type="button" disabled={busy === `base:${base.id}` || busy === `impact:${base.id}`} onClick={() => void beginBaseToggle(base)}>{base.is_active ? "Check deactivation" : "Reactivate"}</button></div> : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "deployments" && canViewDeployments ? (
          <section className="operating-structure__panel">
            <div className="operating-structure__section-head"><div><h2>Personnel base deployments</h2><p>Keep the home base intact and overlay temporary, relief or training movement for an exact date range.</p></div></div>
            {canManageDeployments ? (
              <div className="operating-structure__form">
                <label className="operating-structure__span-2">Person<select value={deploymentForm.user_id} onChange={(event) => setDeploymentForm((current) => ({ ...current, user_id: event.target.value }))}><option value="">Select person</option>{people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
                <label>Base<select value={deploymentForm.base_station_id} onChange={(event) => setDeploymentForm((current) => ({ ...current, base_station_id: event.target.value }))}><option value="">Select base</option>{activeBases.map((base) => <option key={base.id} value={base.id}>{base.code} · {base.name}</option>)}</select></label>
                <label>Movement type<select value={deploymentForm.assignment_kind} onChange={(event) => setDeploymentForm((current) => ({ ...current, assignment_kind: event.target.value as BaseAssignmentKind, effective_to: DATED_DEPLOYMENTS.has(event.target.value as BaseAssignmentKind) ? current.effective_to : "" }))}>{ASSIGNMENT_KINDS.map((value) => <option key={value}>{value}</option>)}</select></label>
                <label>Starts<input type="date" value={deploymentForm.effective_from} onChange={(event) => setDeploymentForm((current) => ({ ...current, effective_from: event.target.value }))} /></label>
                <label>Ends{selectedRequiresEnd ? " *" : ""}<input type="date" value={deploymentForm.effective_to} onChange={(event) => setDeploymentForm((current) => ({ ...current, effective_to: event.target.value }))} /></label>
                <label className="operating-structure__span-2">Reason / note<input value={deploymentForm.note} onChange={(event) => setDeploymentForm((current) => ({ ...current, note: event.target.value }))} placeholder="Relief coverage for end-of-month check" /></label>
                <div className="operating-structure__span-4 operating-structure__actions"><small>Temporary, relief and training records require an end date and a reason. Two primary temporary deployments may not overlap.</small><button className="btn btn-primary" type="button" onClick={() => void createDeployment()} disabled={!deploymentCanSubmit || busy === "deployment"}><CalendarRange size={16} /> Create deployment</button></div>
              </div>
            ) : <div className="operating-structure__empty">You have assurance visibility only. The <code>workforce.deployments.manage</code> capability is required to move personnel.</div>}

            {!assignments.length && !loading.has("deployments") ? <div className="operating-structure__empty">No personnel base assignments exist.</div> : null}
            <div className="operating-structure__grid">
              {assignments.map((assignment) => {
                const person = peopleById.get(assignment.user_id);
                const ended = Boolean(assignment.effective_to && assignment.effective_to < todayIso());
                const future = assignment.effective_from > todayIso();
                return (
                  <article className="operating-structure__deployment" key={assignment.id}>
                    <header><div><strong>{person?.full_name || assignment.user_id}</strong><small>{person?.staff_code || "Personnel record"} · {assignment.base_station?.code || assignment.base_station_id}</small></div><span className={`operating-structure__status${ended ? " is-inactive" : ""}`}>{assignment.assignment_kind.replace(/_/g, " ")}</span></header>
                    <small>{assignment.effective_from} → {assignment.effective_to || "Open ended"}</small>
                    {assignment.note ? <small>{assignment.note}</small> : null}
                    {canManageDeployments && !ended && assignment.assignment_kind !== "HOME_BASE" ? <div className="operating-structure__actions"><span /><button className="btn btn-secondary" type="button" disabled={busy === `deployment:${assignment.id}`} onClick={() => beginDeploymentAction(assignment)}>{future ? "Cancel deployment" : "End today"}</button></div> : null}
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}
      </div>

      {baseAction ? (
        <div className="portal-help-backdrop" role="presentation">
          <section className="portal-help-dialog" role="dialog" aria-modal="true" aria-label={`Deactivate ${baseAction.base.code}`}>
            <header className="portal-help-dialog__header"><div><span className="portal-help-dialog__eyebrow">Dependency check</span><h2>Deactivate {baseAction.base.code}?</h2></div><button type="button" className="portal-help-dialog__close" onClick={() => setBaseAction(null)} aria-label="Close"><X size={19} /></button></header>
            <div className="portal-help-dialog__body">
              {baseAction.impact.can_deactivate ? <p><CheckCircle2 size={18} /> No active deployment, contract or roster dependency blocks deactivation.</p> : <><p><AlertTriangle size={18} /> This base cannot be deactivated yet.</p><div className="portal-prerequisite-list">{baseAction.impact.dependencies.map((dependency) => <article className="portal-prerequisite-item" key={dependency.dependency_type}><AlertTriangle size={18} /><div><strong>{dependency.count} affected record{dependency.count === 1 ? "" : "s"}</strong><p>{dependency.detail}</p></div></article>)}</div></>}
              {baseAction.impact.can_deactivate ? <label>Reason<textarea rows={3} value={baseAction.reason} onChange={(event) => setBaseAction((current) => current ? { ...current, reason: event.target.value } : current)} /></label> : null}
            </div>
            <footer className="portal-help-dialog__footer"><button type="button" className="portal-help-button portal-help-button--secondary" onClick={() => setBaseAction(null)}>Close</button>{baseAction.impact.can_deactivate ? <button type="button" className="portal-help-button portal-help-button--primary" disabled={!baseAction.reason.trim() || busy === `base:${baseAction.base.id}`} onClick={() => void confirmDeactivate()}>Deactivate base</button> : null}</footer>
          </section>
        </div>
      ) : null}

      {deploymentAction ? (
        <div className="portal-help-backdrop" role="presentation">
          <section className="portal-help-dialog" role="dialog" aria-modal="true" aria-label={deploymentAction.mode === "cancel" ? "Cancel deployment" : "End deployment"}>
            <header className="portal-help-dialog__header"><div><span className="portal-help-dialog__eyebrow">Controlled personnel movement</span><h2>{deploymentAction.mode === "cancel" ? "Cancel future deployment" : "End active deployment today"}</h2></div><button type="button" className="portal-help-dialog__close" onClick={() => setDeploymentAction(null)} aria-label="Close"><X size={19} /></button></header>
            <div className="portal-help-dialog__body"><p>{deploymentAction.assignment.base_station?.code || deploymentAction.assignment.base_station_id} · {deploymentAction.assignment.effective_from} → {deploymentAction.assignment.effective_to || "Open ended"}</p><label>Reason<textarea rows={3} value={deploymentAction.reason} onChange={(event) => setDeploymentAction((current) => current ? { ...current, reason: event.target.value } : current)} /></label></div>
            <footer className="portal-help-dialog__footer"><button type="button" className="portal-help-button portal-help-button--secondary" onClick={() => setDeploymentAction(null)}>Keep deployment</button><button type="button" className="portal-help-button portal-help-button--primary" disabled={!deploymentAction.reason.trim() || busy === `deployment:${deploymentAction.assignment.id}`} onClick={() => void confirmDeploymentAction()}>{deploymentAction.mode === "cancel" ? "Cancel deployment" : "End today"}</button></footer>
          </section>
        </div>
      ) : null}
    </DepartmentLayout>
  );
}

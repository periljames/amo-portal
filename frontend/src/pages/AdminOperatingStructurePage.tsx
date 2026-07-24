import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, CalendarRange, Pencil, Plus, RefreshCw, UserRoundCheck } from "lucide-react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { ContextualHelp } from "../components/UI/ContextualHelp";
import { getCachedUser } from "../services/auth";
import {
  createBaseStation,
  createUserBaseAssignment,
  listBaseStations,
  listUserBaseAssignments,
  updateBaseStation,
  updateUserBaseAssignment,
} from "../services/foundations";
import { listAllRosterPeople, type RosterPersonRead } from "../services/rosterPeople";
import type {
  BaseAssignmentKind,
  BaseStationCreate,
  BaseStationRead,
  BaseStationType,
  UserBaseAssignmentRead,
} from "../types/foundations";
import "../styles/admin-operating-structure.css";

type Tab = "bases" | "deployments";

const BASE_TYPES: BaseStationType[] = [
  "MAIN_BASE", "LINE_STATION", "OUTSTATION", "WORKSHOP", "HANGAR", "TRAINING_SITE", "OTHER",
];
const ASSIGNMENT_KINDS: BaseAssignmentKind[] = ["HOME_BASE", "TEMPORARY", "RELIEF", "TRAINING", "OTHER"];
const DEPLOYMENT_ROLES = new Set(["QUALITY_MANAGER", "PLANNING_ENGINEER", "PRODUCTION_ENGINEER"]);

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const candidate = error as { message?: string; response?: { data?: { detail?: string } } };
    return candidate.response?.data?.detail || candidate.message || "The request could not be completed.";
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
  const currentUser = useMemo(() => getCachedUser(), []);
  const role = String(currentUser?.role || "");
  const canManageBaseMaster = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin);
  const canManageDeployments = canManageBaseMaster || DEPLOYMENT_ROLES.has(role);

  const [tab, setTab] = useState<Tab>(canManageBaseMaster ? "bases" : "deployments");
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [people, setPeople] = useState<RosterPersonRead[]>([]);
  const [assignments, setAssignments] = useState<UserBaseAssignmentRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [editingBaseId, setEditingBaseId] = useState<string | null>(null);
  const [baseForm, setBaseForm] = useState<BaseStationCreate>(EMPTY_BASE);
  const [aliasText, setAliasText] = useState("");
  const [deploymentForm, setDeploymentForm] = useState({
    user_id: "",
    base_station_id: "",
    assignment_kind: "TEMPORARY" as BaseAssignmentKind,
    effective_from: todayIso(),
    effective_to: "",
    note: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextBases, nextPeople, nextAssignments] = await Promise.all([
        listBaseStations({ include_inactive: true }),
        listAllRosterPeople({ page_size: 250, active_only: true, roster_eligible_only: false }),
        listUserBaseAssignments({ include_expired: true }),
      ]);
      setBases(nextBases);
      setPeople(nextPeople.items);
      setAssignments(nextAssignments);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const peopleById = useMemo(() => new Map(people.map((person) => [person.user_id, person])), [people]);
  const activeBases = useMemo(() => bases.filter((base) => base.is_active), [bases]);

  const resetBase = () => {
    setEditingBaseId(null);
    setBaseForm(EMPTY_BASE);
    setAliasText("");
  };

  const editBase = (base: BaseStationRead) => {
    if (!canManageBaseMaster) return;
    setEditingBaseId(base.id);
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
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveBase = async () => {
    if (!canManageBaseMaster || !baseForm.code.trim() || !baseForm.name.trim()) return;
    setBusy("base");
    setError(null);
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
      if (editingBaseId) await updateBaseStation(editingBaseId, payload);
      else await createBaseStation(payload);
      resetBase();
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const toggleBase = async (base: BaseStationRead) => {
    if (!canManageBaseMaster) return;
    setBusy(`base:${base.id}`);
    setError(null);
    try {
      await updateBaseStation(base.id, { is_active: !base.is_active });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const createDeployment = async () => {
    if (!canManageDeployments || !deploymentForm.user_id || !deploymentForm.base_station_id || !deploymentForm.effective_from) return;
    setBusy("deployment");
    setError(null);
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
      setDeploymentForm((current) => ({ ...current, effective_from: todayIso(), effective_to: "", note: "" }));
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const endDeployment = async (assignment: UserBaseAssignmentRead) => {
    if (!canManageDeployments) return;
    setBusy(`deployment:${assignment.id}`);
    setError(null);
    try {
      await updateUserBaseAssignment(assignment.id, { effective_to: todayIso() });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={canManageBaseMaster ? "admin-assets" : "rostering"}>
      <div className="operating-structure">
        <header className="operating-structure__header">
          <div>
            <h1>Operating structure</h1>
            <p>One canonical base master and dated personnel deployments for the entire tenant.</p>
          </div>
          <div className="operating-structure__actions">
            <ContextualHelp
              topic="admin-operating-structure"
              version={1}
              title="One base master for every module"
              description="Administrators create each physical base, station, hangar or workshop once. Rostering, Planning, Production, Quality, Training and Stores consume those same records. A short transfer is recorded as a dated deployment instead of overwriting the employee's permanent home base."
              checklist={[
                "HOME BASE is the durable personnel station.",
                "TEMPORARY, RELIEF and TRAINING overlay the home base for exact dates.",
                "End a deployment when the employee returns; never duplicate the person or station.",
              ]}
            />
            <button className="btn btn-secondary" type="button" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={16} className={loading ? "is-spinning" : ""} /> Refresh
            </button>
          </div>
        </header>

        {!canManageBaseMaster && !canManageDeployments ? (
          <div className="operating-structure__error" role="alert">Your role cannot change operating structure or personnel deployments. Ask an AMO administrator to complete this setup.</div>
        ) : null}

        <div className="operating-structure__tabs" role="tablist" aria-label="Operating structure sections">
          {canManageBaseMaster ? (
            <button type="button" role="tab" aria-selected={tab === "bases"} className={tab === "bases" ? "is-active" : ""} onClick={() => setTab("bases")}>
              <Building2 size={16} /> Bases and stations
            </button>
          ) : null}
          {canManageDeployments ? (
            <button type="button" role="tab" aria-selected={tab === "deployments"} className={tab === "deployments" ? "is-active" : ""} onClick={() => setTab("deployments")}>
              <UserRoundCheck size={16} /> Personnel deployments
            </button>
          ) : null}
        </div>

        {error ? <div className="operating-structure__error" role="alert">{error}</div> : null}

        {tab === "bases" && canManageBaseMaster ? (
          <section className="operating-structure__panel">
            <div className="operating-structure__section-head">
              <div><h2>{editingBaseId ? "Edit base" : "Add base"}</h2><p>These records are tenant-wide; operational modules must not create their own base lists.</p></div>
              {editingBaseId ? <button className="btn btn-secondary" type="button" onClick={resetBase}>Cancel edit</button> : null}
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
              <div className="operating-structure__span-4 operating-structure__actions"><span /><button className="btn btn-primary" type="button" onClick={() => void saveBase()} disabled={!baseForm.code.trim() || !baseForm.name.trim() || busy === "base"}><Plus size={16} /> {editingBaseId ? "Save base" : "Create base"}</button></div>
            </div>
            {loading && !bases.length ? <div className="operating-structure__empty">Loading bases…</div> : null}
            {!loading && !bases.length ? <div className="operating-structure__empty">No bases exist. Create the first operating location above.</div> : null}
            <div className="operating-structure__grid">
              {bases.map((base) => (
                <article className="operating-structure__card" key={base.id}>
                  <header><div><strong>{base.code} · {base.name}</strong><small>{base.base_type.replace(/_/g, " ")} · {base.time_zone || "No time zone"}</small></div><span className={`operating-structure__status${base.is_active ? "" : " is-inactive"}`}>{base.is_active ? "ACTIVE" : "INACTIVE"}</span></header>
                  <small>{[base.icao_code, base.iata_code, base.aliases.map((alias) => alias.alias).join(", ")].filter(Boolean).join(" · ") || "No external codes or aliases"}</small>
                  <div className="operating-structure__actions"><button className="btn btn-secondary" type="button" onClick={() => editBase(base)}><Pencil size={15} /> Edit</button><button className="btn btn-secondary" type="button" disabled={busy === `base:${base.id}`} onClick={() => void toggleBase(base)}>{base.is_active ? "Deactivate" : "Reactivate"}</button></div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "deployments" && canManageDeployments ? (
          <section className="operating-structure__panel">
            <div className="operating-structure__section-head"><div><h2>Personnel base deployments</h2><p>Keep the home base intact and overlay temporary, relief or training movement for an exact date range.</p></div></div>
            <div className="operating-structure__form">
              <label className="operating-structure__span-2">Person<select value={deploymentForm.user_id} onChange={(event) => setDeploymentForm((current) => ({ ...current, user_id: event.target.value }))}><option value="">Select person</option>{people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
              <label>Base<select value={deploymentForm.base_station_id} onChange={(event) => setDeploymentForm((current) => ({ ...current, base_station_id: event.target.value }))}><option value="">Select base</option>{activeBases.map((base) => <option key={base.id} value={base.id}>{base.code} · {base.name}</option>)}</select></label>
              <label>Movement type<select value={deploymentForm.assignment_kind} onChange={(event) => setDeploymentForm((current) => ({ ...current, assignment_kind: event.target.value as BaseAssignmentKind }))}>{ASSIGNMENT_KINDS.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>Starts<input type="date" value={deploymentForm.effective_from} onChange={(event) => setDeploymentForm((current) => ({ ...current, effective_from: event.target.value }))} /></label>
              <label>Ends<input type="date" value={deploymentForm.effective_to} onChange={(event) => setDeploymentForm((current) => ({ ...current, effective_to: event.target.value }))} /></label>
              <label className="operating-structure__span-2">Reason / note<input value={deploymentForm.note} onChange={(event) => setDeploymentForm((current) => ({ ...current, note: event.target.value }))} placeholder="Relief coverage for end-of-month check" /></label>
              <div className="operating-structure__span-4 operating-structure__actions"><small>A home base may overlap one dated temporary deployment. Two primary temporary deployments may not overlap.</small><button className="btn btn-primary" type="button" onClick={() => void createDeployment()} disabled={!deploymentForm.user_id || !deploymentForm.base_station_id || !deploymentForm.effective_from || busy === "deployment"}><CalendarRange size={16} /> Create deployment</button></div>
            </div>
            {!assignments.length && !loading ? <div className="operating-structure__empty">No personnel base assignments exist.</div> : null}
            <div className="operating-structure__grid">
              {assignments.map((assignment) => {
                const person = peopleById.get(assignment.user_id);
                const ended = Boolean(assignment.effective_to && assignment.effective_to < todayIso());
                return (
                  <article className="operating-structure__deployment" key={assignment.id}>
                    <header><div><strong>{person?.full_name || assignment.user_id}</strong><small>{person?.staff_code || "No staff code"} · {assignment.base_station?.code || assignment.base_station_id}</small></div><span className={`operating-structure__status${ended ? " is-inactive" : ""}`}>{assignment.assignment_kind.replace(/_/g, " ")}</span></header>
                    <small>{assignment.effective_from} → {assignment.effective_to || "Open ended"}</small>
                    {assignment.note ? <small>{assignment.note}</small> : null}
                    {!ended && assignment.assignment_kind !== "HOME_BASE" ? <div className="operating-structure__actions"><span /><button className="btn btn-secondary" type="button" disabled={busy === `deployment:${assignment.id}`} onClick={() => void endDeployment(assignment)}>End today</button></div> : null}
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}
      </div>
    </DepartmentLayout>
  );
}

import "./workforce-governance.css";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Building2, CircleAlert, Landmark, Plus, RefreshCw, Save, ShieldCheck, UsersRound } from "lucide-react";

import { listBaseStations } from "../../../services/foundations";
import {
  getWorkforceHrBulkOperation,
  getWorkforceHrHierarchyBlueprint,
  getWorkforceHrPeopleFacets,
  initializeWorkforceHrKcars2025Hierarchy,
  listWorkforceHrGrades,
  listWorkforceHrJobFamilies,
  listWorkforceHrOrgUnits,
  listWorkforceHrPeople,
  listWorkforceHrPositions,
  listWorkforceHrSupervisors,
  previewWorkforceHrSelection,
  saveWorkforceHrGrade,
  saveWorkforceHrJobFamily,
  saveWorkforceHrOrgUnit,
  saveWorkforceHrPosition,
  submitWorkforceHrPersonnelMutation,
} from "../../../services/workforceHr";
import type {
  HrBulkOperation,
  HrFilterOption,
  HrGrade,
  HrHierarchyBlueprint,
  HrJobFamily,
  HrManagementLevel,
  HrOrgUnit,
  HrPeopleFilters,
  HrPeopleSelection,
  HrPersonnelMutationPayload,
  HrPersonnelMutationType,
  HrPosition,
  HrTenantFunction,
} from "../../../types/workforceHr";
import { errorMessage, isoDate } from "../rosterUi";
import { RosterLoading, StatusPill } from "./RosterShell";

const TERMINAL = new Set(["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]);
const newKey = () => `personnel-${crypto.randomUUID()}`;
const PAGE_SIZES = [25, 50, 100, 250] as const;

const initialGovernanceFilters = (): HrPeopleFilters => {
  const params = new URLSearchParams(window.location.search);
  return {
    search: params.get("gov_search") || null,
    org_unit_id: params.get("gov_org") || null,
    include_descendants: params.get("gov_descendants") !== "false",
    placement_type: (params.get("gov_placement") as HrPeopleFilters["placement_type"]) || null,
    position_id: params.get("gov_position") || null,
    job_family_id: params.get("gov_family") || null,
    grade_id: params.get("gov_grade") || null,
    supervisor_user_id: params.get("gov_supervisor") || null,
    base_station_id: params.get("gov_primary_base") || null,
    secondary_base_station_id: params.get("gov_secondary_base") || null,
    contract_state: (params.get("gov_contract_state") as HrPeopleFilters["contract_state"]) || null,
    lifecycle_state: (params.get("gov_lifecycle") as HrPeopleFilters["lifecycle_state"]) || null,
    contract_effective_from_on_or_after: params.get("gov_contract_start_from") || null,
    contract_effective_from_on_or_before: params.get("gov_contract_start_to") || null,
    contract_effective_to_on_or_after: params.get("gov_contract_end_from") || null,
    contract_effective_to_on_or_before: params.get("gov_contract_end_to") || null,
    sort_by: (params.get("gov_sort") as HrPeopleFilters["sort_by"]) || "name",
    sort_dir: (params.get("gov_direction") as HrPeopleFilters["sort_dir"]) || "asc",
  };
};

type Props = { canManage: boolean };
type Catalogue = "hierarchy" | "org" | "family" | "grade" | "position";

type OrgDraft = { id?: string; parent_id: string; legacy_department_id: string; code: string; name: string; unit_type: string; description: string; is_active: boolean; sort_order: number };
type FamilyDraft = { id?: string; code: string; name: string; description: string; is_active: boolean };
type GradeDraft = { id?: string; code: string; name: string; rank_order: number; description: string; is_active: boolean };
type PositionDraft = {
  id?: string; code: string; canonical_title: string; job_family_id: string; grade_id: string;
  description: string; management_level: HrManagementLevel; tenant_function: HrTenantFunction | "";
  role_source: "TENANT" | "KCAR_2025"; is_supervisory: boolean; is_active: boolean;
};

const emptyOrg = (): OrgDraft => ({ parent_id: "", legacy_department_id: "", code: "", name: "", unit_type: "TEAM", description: "", is_active: true, sort_order: 100 });
const emptyFamily = (): FamilyDraft => ({ code: "", name: "", description: "", is_active: true });
const emptyGrade = (): GradeDraft => ({ code: "", name: "", rank_order: 100, description: "", is_active: true });
const emptyPosition = (): PositionDraft => ({
  code: "", canonical_title: "", job_family_id: "", grade_id: "", description: "",
  management_level: "STAFF", tenant_function: "", role_source: "TENANT", is_supervisory: false, is_active: true,
});

export function WorkforceGovernancePanel({ canManage }: Props) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"structure" | "personnel">("structure");
  const [catalogue, setCatalogue] = useState<Catalogue>("hierarchy");
  const [orgDraft, setOrgDraft] = useState<OrgDraft>(emptyOrg);
  const [familyDraft, setFamilyDraft] = useState<FamilyDraft>(emptyFamily);
  const [gradeDraft, setGradeDraft] = useState<GradeDraft>(emptyGrade);
  const [positionDraft, setPositionDraft] = useState<PositionDraft>(emptyPosition);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const orgUnits = useQuery({ queryKey: ["workforce", "governance", "org"], queryFn: () => listWorkforceHrOrgUnits(true) });
  const families = useQuery({ queryKey: ["workforce", "governance", "families"], queryFn: () => listWorkforceHrJobFamilies(true) });
  const grades = useQuery({ queryKey: ["workforce", "governance", "grades"], queryFn: () => listWorkforceHrGrades(true) });
  const positions = useQuery({ queryKey: ["workforce", "governance", "positions"], queryFn: () => listWorkforceHrPositions(true) });
  const hierarchy = useQuery({ queryKey: ["workforce", "governance", "hierarchy"], queryFn: getWorkforceHrHierarchyBlueprint });
  const peopleFacets = useQuery({ queryKey: ["workforce", "hr", "people", "facets"], queryFn: getWorkforceHrPeopleFacets });

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key); setError(null); setNotice(null);
    try { await action(); } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(null); }
  };
  const refreshCatalogues = async () => {
    await queryClient.invalidateQueries({ queryKey: ["workforce", "governance"] });
    await queryClient.invalidateQueries({ queryKey: ["workforce", "hr", "people"] });
  };

  const saveOrg = () => void run("save-org", async () => {
    await saveWorkforceHrOrgUnit({
      parent_id: orgDraft.parent_id || null, legacy_department_id: orgDraft.legacy_department_id || null,
      code: orgDraft.code, name: orgDraft.name, unit_type: orgDraft.unit_type,
      description: orgDraft.description || null, is_active: orgDraft.is_active, sort_order: orgDraft.sort_order,
    }, orgDraft.id);
    setOrgDraft(emptyOrg()); setNotice("Organisation unit saved."); await refreshCatalogues();
  });
  const saveFamily = () => void run("save-family", async () => {
    await saveWorkforceHrJobFamily({ code: familyDraft.code, name: familyDraft.name, description: familyDraft.description || null, is_active: familyDraft.is_active }, familyDraft.id);
    setFamilyDraft(emptyFamily()); setNotice("Job family saved."); await refreshCatalogues();
  });
  const saveGrade = () => void run("save-grade", async () => {
    await saveWorkforceHrGrade({ code: gradeDraft.code, name: gradeDraft.name, rank_order: gradeDraft.rank_order, description: gradeDraft.description || null, is_active: gradeDraft.is_active }, gradeDraft.id);
    setGradeDraft(emptyGrade()); setNotice("Grade saved."); await refreshCatalogues();
  });
  const savePosition = () => void run("save-position", async () => {
    await saveWorkforceHrPosition({
      code: positionDraft.code, canonical_title: positionDraft.canonical_title,
      job_family_id: positionDraft.job_family_id || null, grade_id: positionDraft.grade_id || null,
      description: positionDraft.description || null, management_level: positionDraft.management_level,
      tenant_function: positionDraft.tenant_function || null, is_supervisory: positionDraft.is_supervisory,
      is_active: positionDraft.is_active,
    }, positionDraft.id);
    setPositionDraft(emptyPosition()); setNotice("Canonical position saved."); await refreshCatalogues();
  });

  const initializeHierarchy = () => void run("initialize-hierarchy", async () => {
    const result = await initializeWorkforceHrKcars2025Hierarchy();
    const outcomes: string[] = [];
    if (result.accounts_synced) outcomes.push(`${result.accounts_synced} account role${result.accounts_synced === 1 ? "" : "s"} aligned`);
    if (result.supervisor_links_cleared) outcomes.push(`${result.supervisor_links_cleared} invalid supervisor link${result.supervisor_links_cleared === 1 ? "" : "s"} cleared`);
    setNotice(outcomes.length ? `KCAR hierarchy ready: ${outcomes.join(" · ")}.` : "KCAR hierarchy ready.");
    await refreshCatalogues();
  });

  const configureTenantFunction = (key: HrTenantFunction, code: string, title: string, positionId?: string | null) => {
    const existing = (positions.data || []).find((position) => position.id === positionId || position.role_key === key);
    setPositionDraft(existing ? {
      id: existing.id, code: existing.code, canonical_title: existing.canonical_title,
      job_family_id: existing.job_family_id || "", grade_id: existing.grade_id || "",
      description: existing.description || "", management_level: existing.management_level,
      tenant_function: key, role_source: existing.role_source, is_supervisory: existing.is_supervisory,
      is_active: existing.is_active,
    } : {
      ...emptyPosition(), code, canonical_title: title, management_level: "MANAGER",
      tenant_function: key, is_supervisory: true,
    });
    setCatalogue("position");
  };

  if (orgUnits.isPending || families.isPending || grades.isPending || positions.isPending || hierarchy.isPending || peopleFacets.isPending) {
    return <RosterLoading label="Loading Workforce governance…" />;
  }

  return <section className="wr-panel workforce-governance">
    <header className="workforce-governance__header">
      <div><span className="wr-eyebrow">Workforce hierarchy</span><h2>Define roles, then assign people</h2><p>KCAR management is controlled here. Tenant support roles stay yours.</p></div>
      <button type="button" className="wr-icon-button" aria-label="Refresh governance" onClick={() => void refreshCatalogues()}><RefreshCw size={16} /></button>
    </header>
    <nav className="workforce-governance__mode">
      <button type="button" className={mode === "structure" ? "is-active" : ""} onClick={() => setMode("structure")}><Building2 size={15} /> Structure & positions</button>
      <button type="button" className={mode === "personnel" ? "is-active" : ""} onClick={() => setMode("personnel")}><UsersRound size={15} /> Personnel changes</button>
    </nav>
    {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
    {notice ? <div className="workforce-governance__notice" role="status">{notice}</div> : null}
    {mode === "structure" ? <StructureEditor
      catalogue={catalogue} setCatalogue={setCatalogue} canManage={canManage} busy={busy}
      orgUnits={orgUnits.data || []} families={families.data || []} grades={grades.data || []} positions={positions.data || []}
      hierarchy={hierarchy.data!} initializeHierarchy={initializeHierarchy} configureTenantFunction={configureTenantFunction}
      departments={peopleFacets.data?.departments || []}
      orgDraft={orgDraft} setOrgDraft={setOrgDraft} familyDraft={familyDraft} setFamilyDraft={setFamilyDraft}
      gradeDraft={gradeDraft} setGradeDraft={setGradeDraft} positionDraft={positionDraft} setPositionDraft={setPositionDraft}
      saveOrg={saveOrg} saveFamily={saveFamily} saveGrade={saveGrade} savePosition={savePosition}
    /> : <PersonnelMutations
      canManage={canManage} orgUnits={(orgUnits.data || []).filter((x) => x.is_active)}
      positions={(positions.data || []).filter((x) => x.is_active)}
    />}
  </section>;
}

function StructureEditor(props: {
  catalogue: Catalogue; setCatalogue: (value: Catalogue) => void; canManage: boolean; busy: string | null;
  orgUnits: HrOrgUnit[]; families: HrJobFamily[]; grades: HrGrade[]; positions: HrPosition[]; departments: HrFilterOption[];
  hierarchy: HrHierarchyBlueprint; initializeHierarchy: () => void;
  configureTenantFunction: (key: HrTenantFunction, code: string, title: string, positionId?: string | null) => void;
  orgDraft: OrgDraft; setOrgDraft: (value: OrgDraft) => void; familyDraft: FamilyDraft; setFamilyDraft: (value: FamilyDraft) => void;
  gradeDraft: GradeDraft; setGradeDraft: (value: GradeDraft) => void; positionDraft: PositionDraft; setPositionDraft: (value: PositionDraft) => void;
  saveOrg: () => void; saveFamily: () => void; saveGrade: () => void; savePosition: () => void;
}) {
  const { catalogue, setCatalogue } = props;
  return <div className="workforce-governance__structure">
    <nav className="workforce-governance__catalogue-tabs">
      {(["hierarchy", "position", "org", "family", "grade"] as Catalogue[]).map((value) => <button type="button" key={value} className={catalogue === value ? "is-active" : ""} onClick={() => setCatalogue(value)}>{value === "hierarchy" ? "Role hierarchy" : value === "org" ? "Organization" : value === "family" ? "Job families" : value === "grade" ? "Grades" : "Positions"}</button>)}
    </nav>
    {catalogue === "hierarchy" ? <HierarchySetup
      blueprint={props.hierarchy}
      canManage={props.canManage}
      busy={props.busy === "initialize-hierarchy"}
      onInitialize={props.initializeHierarchy}
      onConfigureTenant={props.configureTenantFunction}
    /> : null}
    {catalogue === "org" ? <div className="workforce-governance__split"><CatalogueTable
      headers={["Code", "Unit", "Type", "Path", "State"]}
      rows={props.orgUnits.map((row) => ({ id: row.id, cells: [row.code, row.name, row.unit_type, row.path_names.join(" / "), row.is_active ? "Active" : "Inactive"], edit: () => props.setOrgDraft({ id: row.id, parent_id: row.parent_id || "", legacy_department_id: row.legacy_department_id || "", code: row.code, name: row.name, unit_type: row.unit_type, description: row.description || "", is_active: row.is_active, sort_order: row.sort_order }) }))}
    /><Editor title={props.orgDraft.id ? "Edit unit" : "Add unit"} disabled={!props.canManage || props.busy === "save-org"} onSave={props.saveOrg} onReset={() => props.setOrgDraft(emptyOrg())}>
      <Field label="Code"><input value={props.orgDraft.code} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, code: e.target.value })} /></Field>
      <Field label="Name"><input value={props.orgDraft.name} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, name: e.target.value })} /></Field>
      <Field label="Parent"><select value={props.orgDraft.parent_id} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, parent_id: e.target.value })}><option value="">Root</option>{props.orgUnits.filter((x) => x.id !== props.orgDraft.id).map((x) => <option key={x.id} value={x.id}>{"—".repeat(x.depth)} {x.name}</option>)}</select></Field>
      <Field label="Legacy department projection"><select value={props.orgDraft.legacy_department_id} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, legacy_department_id: e.target.value })}><option value="">None</option>{props.departments.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select></Field>
      <Field label="Unit type"><select value={props.orgDraft.unit_type} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, unit_type: e.target.value })}><option>DEPARTMENT</option><option>SECTION</option><option>TEAM</option><option>MATRIX</option><option>OTHER</option></select></Field>
      <Field label="Sort order"><input type="number" value={props.orgDraft.sort_order} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, sort_order: Number(e.target.value) })} /></Field>
      <Field label="Description"><textarea value={props.orgDraft.description} onChange={(e) => props.setOrgDraft({ ...props.orgDraft, description: e.target.value })} /></Field>
      <Check label="Active" checked={props.orgDraft.is_active} onChange={(value) => props.setOrgDraft({ ...props.orgDraft, is_active: value })} />
    </Editor></div> : null}
    {catalogue === "family" ? <div className="workforce-governance__split"><CatalogueTable headers={["Code", "Family", "State"]} rows={props.families.map((row) => ({ id: row.id, cells: [row.code, row.name, row.is_active ? "Active" : "Inactive"], edit: () => props.setFamilyDraft({ id: row.id, code: row.code, name: row.name, description: row.description || "", is_active: row.is_active }) }))} /><Editor title={props.familyDraft.id ? "Edit family" : "Add family"} disabled={!props.canManage || props.busy === "save-family"} onSave={props.saveFamily} onReset={() => props.setFamilyDraft(emptyFamily())}><Field label="Code"><input value={props.familyDraft.code} onChange={(e) => props.setFamilyDraft({ ...props.familyDraft, code: e.target.value })} /></Field><Field label="Name"><input value={props.familyDraft.name} onChange={(e) => props.setFamilyDraft({ ...props.familyDraft, name: e.target.value })} /></Field><Field label="Description"><textarea value={props.familyDraft.description} onChange={(e) => props.setFamilyDraft({ ...props.familyDraft, description: e.target.value })} /></Field><Check label="Active" checked={props.familyDraft.is_active} onChange={(value) => props.setFamilyDraft({ ...props.familyDraft, is_active: value })} /></Editor></div> : null}
    {catalogue === "grade" ? <div className="workforce-governance__split"><CatalogueTable headers={["Code", "Grade", "Rank", "State"]} rows={props.grades.map((row) => ({ id: row.id, cells: [row.code, row.name, String(row.rank_order), row.is_active ? "Active" : "Inactive"], edit: () => props.setGradeDraft({ id: row.id, code: row.code, name: row.name, rank_order: row.rank_order, description: row.description || "", is_active: row.is_active }) }))} /><Editor title={props.gradeDraft.id ? "Edit grade" : "Add grade"} disabled={!props.canManage || props.busy === "save-grade"} onSave={props.saveGrade} onReset={() => props.setGradeDraft(emptyGrade())}><Field label="Code"><input value={props.gradeDraft.code} onChange={(e) => props.setGradeDraft({ ...props.gradeDraft, code: e.target.value })} /></Field><Field label="Name"><input value={props.gradeDraft.name} onChange={(e) => props.setGradeDraft({ ...props.gradeDraft, name: e.target.value })} /></Field><Field label="Rank"><input type="number" value={props.gradeDraft.rank_order} onChange={(e) => props.setGradeDraft({ ...props.gradeDraft, rank_order: Number(e.target.value) })} /></Field><Field label="Description"><textarea value={props.gradeDraft.description} onChange={(e) => props.setGradeDraft({ ...props.gradeDraft, description: e.target.value })} /></Field><Check label="Active" checked={props.gradeDraft.is_active} onChange={(value) => props.setGradeDraft({ ...props.gradeDraft, is_active: value })} /></Editor></div> : null}
    {catalogue === "position" ? <div className="workforce-governance__split"><CatalogueTable
      headers={["Code", "Position", "Source", "Level", "Supervisor allowed", "State"]}
      rows={props.positions.map((row) => ({
        id: row.id,
        cells: [
          row.code,
          row.canonical_title,
          row.role_source === "KCAR_2025" ? "KCAR 2025" : "Tenant",
          row.management_level,
          row.can_have_supervisor ? "Yes" : "No",
          row.is_active ? "Active" : "Inactive",
        ],
        edit: () => props.setPositionDraft({
          id: row.id,
          code: row.code,
          canonical_title: row.canonical_title,
          job_family_id: row.job_family_id || "",
          grade_id: row.grade_id || "",
          description: row.description || "",
          management_level: row.management_level,
          tenant_function: (["HUMAN_RESOURCES", "INFORMATION_TECHNOLOGY", "FINANCE"].includes(row.role_key || "")
            ? row.role_key as HrTenantFunction
            : ""),
          role_source: row.role_source,
          is_supervisory: row.is_supervisory,
          is_active: row.is_active,
        }),
      }))}
    /><Editor title={props.positionDraft.id ? "Edit position" : "Create position"} disabled={!props.canManage || props.busy === "save-position"} onSave={props.savePosition} onReset={() => props.setPositionDraft(emptyPosition())}>
      {props.positionDraft.role_source === "KCAR_2025" ? <div className="workforce-governance__locked"><ShieldCheck size={15} /><span>KCAR identity and management level are protected.</span></div> : null}
      <Field label="Code"><input disabled={props.positionDraft.role_source === "KCAR_2025"} value={props.positionDraft.code} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, code: e.target.value })} /></Field>
      <Field label="Position title"><input disabled={props.positionDraft.role_source === "KCAR_2025"} value={props.positionDraft.canonical_title} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, canonical_title: e.target.value })} /></Field>
      <Field label="Role level"><select disabled={props.positionDraft.role_source === "KCAR_2025"} value={props.positionDraft.management_level} onChange={(e) => {
        const managementLevel = e.target.value as HrManagementLevel;
        props.setPositionDraft({ ...props.positionDraft, management_level: managementLevel, is_supervisory: managementLevel !== "STAFF" });
      }}><option value="STAFF">Staff</option><option value="SUPERVISOR">Supervisor</option><option value="MANAGER">Manager</option><option value="EXECUTIVE">Executive</option></select></Field>
      {props.positionDraft.role_source === "TENANT" ? <Field label="Tenant function"><select value={props.positionDraft.tenant_function} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, tenant_function: e.target.value as HrTenantFunction | "" })}><option value="">General / operational</option><option value="HUMAN_RESOURCES">Human Resources</option><option value="INFORMATION_TECHNOLOGY">Information Technology</option><option value="FINANCE">Finance</option></select></Field> : null}
      <Field label="Job family"><select value={props.positionDraft.job_family_id} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, job_family_id: e.target.value })}><option value="">None</option>{props.families.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
      <Field label="Grade"><select value={props.positionDraft.grade_id} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, grade_id: e.target.value })}><option value="">None</option>{props.grades.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
      <Field label="Description"><textarea value={props.positionDraft.description} onChange={(e) => props.setPositionDraft({ ...props.positionDraft, description: e.target.value })} /></Field>
      {props.positionDraft.management_level === "MANAGER" || props.positionDraft.management_level === "EXECUTIVE" ? <div className="workforce-governance__rule"><CircleAlert size={15} /><span>This role cannot be assigned a supervisor.</span></div> : null}
      {props.positionDraft.role_source === "TENANT" ? <Check label="Active" checked={props.positionDraft.is_active} onChange={(value) => props.setPositionDraft({ ...props.positionDraft, is_active: value })} /> : null}
    </Editor></div> : null}
  </div>;
}

function HierarchySetup({
  blueprint,
  canManage,
  busy,
  onInitialize,
  onConfigureTenant,
}: {
  blueprint: HrHierarchyBlueprint;
  canManage: boolean;
  busy: boolean;
  onInitialize: () => void;
  onConfigureTenant: (key: HrTenantFunction, code: string, title: string, positionId?: string | null) => void;
}) {
  const complete = blueprint.missing_role_count === 0;
  return <div className="workforce-governance__hierarchy-setup">
    <section className="workforce-governance__hierarchy-card">
      <header>
        <div><span className="wr-eyebrow">KCAR 2025 · regulations 19–21</span><h3>Required AMO management</h3></div>
        <button type="button" className="wr-button wr-button--primary" disabled={!canManage || busy || complete} onClick={onInitialize}>
          {complete ? <BadgeCheck size={15} /> : <Landmark size={15} />}{complete ? "Roles ready" : busy ? "Applying…" : `Apply ${blueprint.required_role_count} roles`}
        </button>
      </header>
      <div className="workforce-governance__role-grid">
        {blueprint.regulatory_roles.map((role) => <article key={role.key} className="workforce-governance__role">
          <span className="workforce-governance__role-code">{role.code}</span>
          <div><strong>{role.title}</strong><small>{role.management_level === "EXECUTIVE" ? "Executive" : "Manager"} · no supervisor</small></div>
          <StatusPill value={role.status === "MATCH_AVAILABLE" ? "REVIEW" : role.status} />
        </article>)}
      </div>
    </section>
    <section className="workforce-governance__hierarchy-card">
      <header><div><span className="wr-eyebrow">Tenant-owned</span><h3>Support functions</h3></div><small>Not prescribed by KCAR</small></header>
      <div className="workforce-governance__tenant-functions">
        {blueprint.tenant_functions.map((item) => <article key={item.key}>
          <div><strong>{item.label}</strong><StatusPill value={item.status === "READY" ? "READY" : "PENDING"} /></div>
          <button type="button" disabled={!canManage} onClick={() => onConfigureTenant(item.key, item.suggested_code, item.suggested_title, item.position_id)}>
            {item.status === "READY" ? "Edit" : <><Plus size={14} /> Configure</>}
          </button>
        </article>)}
      </div>
    </section>
    <div className="workforce-governance__hierarchy-rule"><ShieldCheck size={16} /><span>Manager and executive roles cannot receive a supervisor. Reporting cycles are blocked by the server.</span></div>
  </div>;
}

function PersonnelMutations({ canManage, orgUnits, positions }: { canManage: boolean; orgUnits: HrOrgUnit[]; positions: HrPosition[] }) {
  const queryClient = useQueryClient();
  const initialFilters = useMemo(initialGovernanceFilters, []);
  const [filters, setFilters] = useState<HrPeopleFilters>(initialFilters);
  const [search, setSearch] = useState(initialFilters.search || "");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(50);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [mutation, setMutation] = useState<HrPersonnelMutationType>("ASSIGN_ORGANIZATION");
  const [effectiveOn, setEffectiveOn] = useState(isoDate(new Date()));
  const [orgUnitId, setOrgUnitId] = useState("");
  const [placementType, setPlacementType] = useState<"PRIMARY" | "SECONDARY" | "MATRIX">("PRIMARY");
  const [positionId, setPositionId] = useState("");
  const [preferredTitle, setPreferredTitle] = useState("");
  const [primaryBaseId, setPrimaryBaseId] = useState("");
  const [secondaryBaseId, setSecondaryBaseId] = useState("");
  const [supervisorSearch, setSupervisorSearch] = useState("");
  const [supervisorId, setSupervisorId] = useState("");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [groupMode, setGroupMode] = useState<"ADD" | "REMOVE" | "REPLACE">("ADD");
  const [contractStatus, setContractStatus] = useState("");
  const [contractType, setContractType] = useState("");
  const [contractEnd, setContractEnd] = useState("");
  const [weeklyHours, setWeeklyHours] = useState("");
  const [dailyHours, setDailyHours] = useState("");
  const [fte, setFte] = useState("");
  const [costCentre, setCostCentre] = useState("");
  const [overtimeEligible, setOvertimeEligible] = useState<"" | "true" | "false">("");
  const [nightEligible, setNightEligible] = useState<"" | "true" | "false">("");
  const [standbyEligible, setStandbyEligible] = useState<"" | "true" | "false">("");
  const [offboardingReason, setOffboardingReason] = useState("");
  const [revokeAccess, setRevokeAccess] = useState(true);
  const [endContracts, setEndContracts] = useState(true);
  const [removeGroups, setRemoveGroups] = useState(true);
  const [preview, setPreview] = useState<{ matched_count: number; selection_token: string } | null>(null);
  const [operation, setOperation] = useState<HrBulkOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((old) => ({ ...old, search: search.trim() || null }));
      setPage(1);
      setPreview(null);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const values: Record<string, string | null | undefined> = {
      gov_search: filters.search,
      gov_org: filters.org_unit_id,
      gov_descendants: filters.include_descendants === false ? "false" : null,
      gov_placement: filters.placement_type,
      gov_position: filters.position_id,
      gov_family: filters.job_family_id,
      gov_grade: filters.grade_id,
      gov_supervisor: filters.supervisor_user_id,
      gov_primary_base: filters.base_station_id,
      gov_secondary_base: filters.secondary_base_station_id,
      gov_contract_state: filters.contract_state,
      gov_lifecycle: filters.lifecycle_state,
      gov_contract_start_from: filters.contract_effective_from_on_or_after,
      gov_contract_start_to: filters.contract_effective_from_on_or_before,
      gov_contract_end_from: filters.contract_effective_to_on_or_after,
      gov_contract_end_to: filters.contract_effective_to_on_or_before,
      gov_sort: filters.sort_by,
      gov_direction: filters.sort_dir,
    };
    Object.entries(values).forEach(([name, value]) => value ? params.set(name, value) : params.delete(name));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    window.history.replaceState(null, "", `${window.location.pathname}${suffix}${window.location.hash}`);
  }, [filters]);

  const people = useQuery({
    queryKey: ["workforce", "governance", "people", page, pageSize, filters],
    queryFn: () => listWorkforceHrPeople({ ...filters, page, page_size: pageSize }),
    placeholderData: (old) => old,
  });
  const facets = useQuery({ queryKey: ["workforce", "hr", "people", "facets"], queryFn: getWorkforceHrPeopleFacets });
  const bases = useQuery({ queryKey: ["foundations", "base-stations", "active"], queryFn: () => listBaseStations({ include_inactive: false }) });
  const supervisors = useQuery({
    queryKey: ["workforce", "governance", "supervisors", supervisorSearch, orgUnitId],
    queryFn: () => listWorkforceHrSupervisors({ page: 1, page_size: 100, search: supervisorSearch || undefined, org_unit_id: orgUnitId || undefined }),
    enabled: mutation === "ASSIGN_SUPERVISOR",
  });

  const rows = people.data?.items || [];
  const total = people.data?.total || 0;
  const selection = useMemo<HrPeopleSelection>(() => allMatching
    ? { mode: "FILTERED", filters, exclude_user_ids: [...excluded] }
    : { mode: "EXPLICIT", user_ids: [...selected], exclude_user_ids: [], filters: {} },
  [allMatching, excluded, filters, selected]);
  const count = allMatching ? Math.max(0, total - excluded.size) : selected.size;
  const checked = (id: string) => allMatching ? !excluded.has(id) : selected.has(id);
  const pageChecked = rows.length > 0 && rows.every((row) => checked(row.user_id));
  const clearSelection = () => { setSelected(new Set()); setExcluded(new Set()); setAllMatching(false); setPreview(null); };
  const toggle = (id: string) => {
    setPreview(null);
    const setter = allMatching ? setExcluded : setSelected;
    setter((old) => { const next = new Set(old); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  const togglePage = () => {
    setPreview(null);
    const setter = allMatching ? setExcluded : setSelected;
    setter((old) => { const next = new Set(old); rows.forEach((row) => pageChecked ? next.delete(row.user_id) : next.add(row.user_id)); return next; });
  };

  useEffect(() => {
    if (!operation || TERMINAL.has(operation.status)) return;
    const timer = window.setInterval(() => void getWorkforceHrBulkOperation(operation.id).then((next) => {
      setOperation(next);
      if (TERMINAL.has(next.status)) void queryClient.invalidateQueries({ queryKey: ["workforce"] });
    }).catch((cause) => setError(errorMessage(cause))), 1500);
    return () => window.clearInterval(timer);
  }, [operation, queryClient]);

  const changeFilter = <K extends keyof HrPeopleFilters>(name: K, value: HrPeopleFilters[K]) => {
    clearSelection();
    setFilters((old) => ({ ...old, [name]: value ?? null }));
    setPage(1);
  };
  const clearFilters = () => {
    clearSelection();
    setSearch("");
    setFilters({ sort_by: "name", sort_dir: "asc", include_descendants: true });
    setPage(1);
  };
  const mutationReady = Boolean(effectiveOn) && (
    (mutation === "ASSIGN_ORGANIZATION" && orgUnitId)
    || (mutation === "ASSIGN_POSITION" && positionId)
    || (mutation === "ASSIGN_BASES" && primaryBaseId)
    || (mutation === "ASSIGN_SUPERVISOR" && supervisorId)
    || (mutation === "UPDATE_GROUPS" && groupIds.length)
    || (mutation === "UPDATE_CONTRACT_SETTINGS" && (contractStatus || contractType || contractEnd || weeklyHours || dailyHours || fte || costCentre || overtimeEligible || nightEligible || standbyEligible))
    || (mutation === "SCHEDULE_OFFBOARDING" && offboardingReason.trim().length >= 3)
  );
  const selectedPosition = positions.find((position) => position.id === positionId);
  const doPreview = async () => {
    setBusy(true); setError(null);
    try { setPreview(await previewWorkforceHrSelection(selection)); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const submit = async () => {
    if (!preview) return;
    setBusy(true); setError(null);
    const boolOrNull = (value: "" | "true" | "false") => value === "" ? null : value === "true";
    const payload: HrPersonnelMutationPayload = {
      selection,
      expected_match_count: preview.matched_count,
      expected_selection_token: preview.selection_token,
      mutation_type: mutation,
      effective_on: effectiveOn,
      org_unit_id: orgUnitId || null,
      placement_type: placementType,
      position_id: positionId || null,
      preferred_title: preferredTitle || null,
      primary_base_station_id: primaryBaseId || null,
      secondary_base_station_id: secondaryBaseId || null,
      supervisor_user_id: supervisorId || null,
      group_ids: groupIds,
      group_mode: groupMode,
      contract_settings: {
        contract_type: contractType || null,
        employment_status: contractStatus || null,
        effective_to: contractEnd || null,
        standard_weekly_minutes: weeklyHours ? Math.round(Number(weeklyHours) * 60) : null,
        standard_daily_minutes: dailyHours ? Math.round(Number(dailyHours) * 60) : null,
        fte_percentage: fte ? Number(fte) : null,
        cost_centre: costCentre || null,
        overtime_eligible: boolOrNull(overtimeEligible),
        night_shift_eligible: boolOrNull(nightEligible),
        standby_eligible: boolOrNull(standbyEligible),
      },
      offboarding_reason: offboardingReason || null,
      revoke_access: revokeAccess,
      end_contracts: endContracts,
      remove_groups: removeGroups,
    };
    try {
      const result = await submitWorkforceHrPersonnelMutation(payload, newKey());
      setOperation(result);
      clearSelection();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  if (people.isPending && !people.data) return <RosterLoading label="Loading governed personnel…" />;

  return <div className="workforce-governance__personnel">
    {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
    <div className="workforce-governance__filters">
      <Field label="Search"><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, staff, email or payroll" /></Field>
      <Field label="Organisation"><select value={filters.org_unit_id || ""} onChange={(e) => changeFilter("org_unit_id", e.target.value || null)}><option value="">All units</option>{orgUnits.map((x) => <option key={x.id} value={x.id}>{"—".repeat(x.depth)} {x.name}</option>)}</select></Field>
      <Check label="Include descendant units" checked={filters.include_descendants !== false} onChange={(value) => changeFilter("include_descendants", value)} />
      <Field label="Placement"><select value={filters.placement_type || ""} onChange={(e) => changeFilter("placement_type", (e.target.value || null) as HrPeopleFilters["placement_type"])}><option value="">Any placement</option><option value="PRIMARY">Primary</option><option value="SECONDARY">Secondary</option><option value="MATRIX">Matrix</option></select></Field>
      <Field label="Position"><select value={filters.position_id || ""} onChange={(e) => changeFilter("position_id", e.target.value || null)}><option value="">All positions</option>{positions.map((x) => <option key={x.id} value={x.id}>{x.canonical_title}</option>)}</select></Field>
      <Field label="Job family"><select value={filters.job_family_id || ""} onChange={(e) => changeFilter("job_family_id", e.target.value || null)}><option value="">All families</option>{facets.data?.job_families?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Grade"><select value={filters.grade_id || ""} onChange={(e) => changeFilter("grade_id", e.target.value || null)}><option value="">All grades</option>{facets.data?.grades?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Supervisor"><select value={filters.supervisor_user_id || ""} onChange={(e) => changeFilter("supervisor_user_id", e.target.value || null)}><option value="">All supervisors</option>{facets.data?.supervisors?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Primary base"><select value={filters.base_station_id || ""} onChange={(e) => changeFilter("base_station_id", e.target.value || null)}><option value="">All primary bases</option>{facets.data?.bases?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Secondary base"><select value={filters.secondary_base_station_id || ""} onChange={(e) => changeFilter("secondary_base_station_id", e.target.value || null)}><option value="">All secondary bases</option>{facets.data?.secondary_bases?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Contract record"><select value={filters.contract_state || ""} onChange={(e) => changeFilter("contract_state", (e.target.value || null) as HrPeopleFilters["contract_state"])}><option value="">Any record</option>{facets.data?.contract_states?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Lifecycle"><select value={filters.lifecycle_state || ""} onChange={(e) => changeFilter("lifecycle_state", (e.target.value || null) as HrPeopleFilters["lifecycle_state"])}><option value="">Any state</option>{facets.data?.lifecycle_states?.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></Field>
      <Field label="Contract start from"><input type="date" value={filters.contract_effective_from_on_or_after || ""} onChange={(e) => changeFilter("contract_effective_from_on_or_after", e.target.value || null)} /></Field>
      <Field label="Contract start to"><input type="date" value={filters.contract_effective_from_on_or_before || ""} onChange={(e) => changeFilter("contract_effective_from_on_or_before", e.target.value || null)} /></Field>
      <Field label="Contract end from"><input type="date" value={filters.contract_effective_to_on_or_after || ""} onChange={(e) => changeFilter("contract_effective_to_on_or_after", e.target.value || null)} /></Field>
      <Field label="Contract end to"><input type="date" value={filters.contract_effective_to_on_or_before || ""} onChange={(e) => changeFilter("contract_effective_to_on_or_before", e.target.value || null)} /></Field>
      <Field label="Sort"><select value={filters.sort_by || "name"} onChange={(e) => changeFilter("sort_by", e.target.value as HrPeopleFilters["sort_by"])}><option value="name">Name</option><option value="staff_code">Staff number</option><option value="org_unit">Organisation</option><option value="position">Position</option><option value="job_family">Job family</option><option value="grade">Grade</option><option value="supervisor">Supervisor</option><option value="contract_start">Contract start</option><option value="contract_end">Contract end</option><option value="primary_base">Primary base</option><option value="secondary_base">Secondary base</option><option value="employment_status">Lifecycle status</option></select></Field>
      <Field label="Direction"><select value={filters.sort_dir || "asc"} onChange={(e) => changeFilter("sort_dir", e.target.value as HrPeopleFilters["sort_dir"])}><option value="asc">Ascending</option><option value="desc">Descending</option></select></Field>
    </div>
    <div className="workforce-governance__selection">
      <strong>{count.toLocaleString()} selected</strong>
      <span>{allMatching ? `${total.toLocaleString()} matching minus ${excluded.size} exclusions` : `${rows.filter((row) => checked(row.user_id)).length} on this page`}</span>
      <button type="button" onClick={() => { setAllMatching(true); setSelected(new Set()); setExcluded(new Set()); setPreview(null); }} disabled={!total || total > 10000}>Select all {total.toLocaleString()} matching</button>
      <button type="button" onClick={clearSelection} disabled={!count}>Clear selection</button>
      <button type="button" onClick={clearFilters}>Clear filters</button>
    </div>
    {total > 10000 ? <div className="wr-inline-error">Narrow the filters to 10,000 or fewer personnel before selecting the full result set.</div> : null}
    <div className="workforce-governance__people-table"><table><thead><tr><th><input type="checkbox" checked={pageChecked} onChange={togglePage} aria-label="Select page" /></th><th>Staff</th><th>Person</th><th>Organisation</th><th>Position</th><th>Secondary / matrix</th><th>Supervisor</th><th>Bases</th><th>Contract</th><th>Lifecycle</th></tr></thead><tbody>{rows.map((row) => <tr key={row.user_id}><td><input type="checkbox" checked={checked(row.user_id)} onChange={() => toggle(row.user_id)} /></td><td>{row.staff_code}</td><td><strong>{row.full_name}</strong><small>{row.email}</small></td><td>{row.primary_org_path?.join(" / ") || row.department_name || "—"}</td><td>{row.preferred_title || row.canonical_position_title || row.position_title || "—"}<small>{[row.job_family_name, row.grade_name].filter(Boolean).join(" · ")}</small></td><td>{[...(row.secondary_org_units || []), ...(row.matrix_org_units || [])].map((x) => `${x.placement_type}: ${x.org_unit_name}`).join("; ") || "—"}</td><td>{row.supervisor_name || "—"}</td><td>{row.primary_base_code || "—"}<small>{row.secondary_base_code ? `Secondary: ${row.secondary_base_code}` : ""}</small></td><td>{row.contract_effective_from || "—"}<small>{row.contract_effective_to ? `to ${row.contract_effective_to}` : "Open ended"}</small></td><td><StatusPill value={row.lifecycle_state || row.employment_status || "ACTIVE"} /></td></tr>)}</tbody></table></div>
    <div className="workforce-governance__pager">
      <span>{people.data && total ? `${(people.data.page - 1) * people.data.page_size + 1}-${Math.min(people.data.page * people.data.page_size, total)} of ${total.toLocaleString()}` : "0 records"}</span>
      <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value) as typeof pageSize); setPage(1); }}>{PAGE_SIZES.map((value) => <option key={value} value={value}>{value} per page</option>)}</select>
      <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
      <span>Page {people.data?.page || page} of {Math.max(1, people.data?.pages || 0)}</span>
      <button type="button" disabled={!people.data?.pages || page >= people.data.pages} onClick={() => setPage(page + 1)}>Next</button>
    </div>
    <div className="workforce-governance__mutation-card">
      <h3><ShieldCheck size={17} /> Controlled change</h3>
      <div className="workforce-governance__mutation-grid">
        <Field label="Change type"><select value={mutation} onChange={(e) => { setMutation(e.target.value as HrPersonnelMutationType); setPreview(null); }}><option value="ASSIGN_ORGANIZATION">Assign organization</option><option value="ASSIGN_POSITION">Assign position</option><option value="ASSIGN_BASES">Assign bases</option><option value="ASSIGN_SUPERVISOR">Assign supervisor</option><option value="UPDATE_GROUPS">Update groups</option><option value="UPDATE_CONTRACT_SETTINGS">Update contract settings</option><option value="SCHEDULE_OFFBOARDING">Schedule offboarding</option></select></Field>
        <Field label="Effective date"><input type="date" value={effectiveOn} onChange={(e) => { setEffectiveOn(e.target.value); setPreview(null); }} /></Field>
        {mutation === "ASSIGN_ORGANIZATION" ? <><Field label="Organisation"><select value={orgUnitId} onChange={(e) => { setOrgUnitId(e.target.value); setPreview(null); }}><option value="">Select unit</option>{orgUnits.map((x) => <option key={x.id} value={x.id}>{"—".repeat(x.depth)} {x.name}</option>)}</select></Field><Field label="Placement"><select value={placementType} onChange={(e) => { setPlacementType(e.target.value as typeof placementType); setPreview(null); }}><option>PRIMARY</option><option>SECONDARY</option><option>MATRIX</option></select></Field></> : null}
        {mutation === "ASSIGN_POSITION" ? <><Field label="Canonical position"><select value={positionId} onChange={(e) => { setPositionId(e.target.value); setPreview(null); }}><option value="">Select position</option>{positions.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.canonical_title}</option>)}</select></Field><Field label="Preferred title"><input value={preferredTitle} onChange={(e) => { setPreferredTitle(e.target.value); setPreview(null); }} placeholder="Optional display title" /></Field>{selectedPosition && !selectedPosition.can_have_supervisor ? <div className="workforce-governance__rule"><ShieldCheck size={15} /><span>Management assignment: any existing supervisor link will be removed on the effective date.</span></div> : null}</> : null}
        {mutation === "ASSIGN_BASES" ? <><Field label="Primary base"><select value={primaryBaseId} onChange={(e) => { setPrimaryBaseId(e.target.value); setPreview(null); }}><option value="">Select base</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></Field><Field label="Secondary base"><select value={secondaryBaseId} onChange={(e) => { setSecondaryBaseId(e.target.value); setPreview(null); }}><option value="">None</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></Field></> : null}
        {mutation === "ASSIGN_SUPERVISOR" ? <><Field label="Find supervisor"><input value={supervisorSearch} onChange={(e) => setSupervisorSearch(e.target.value)} placeholder="Name, staff or position" /></Field><Field label="Supervisor"><select value={supervisorId} onChange={(e) => { setSupervisorId(e.target.value); setPreview(null); }}><option value="">Select governed supervisor</option>{supervisors.data?.items.map((x) => <option key={x.user_id} value={x.user_id}>{x.full_name} · {x.position_title || x.staff_code}{x.org_unit_name ? ` · ${x.org_unit_name}` : ""}{x.is_supervisory_position ? " · Supervisory" : ""}</option>)}</select></Field></> : null}
        {mutation === "UPDATE_GROUPS" ? <><Field label="Mode"><select value={groupMode} onChange={(e) => { setGroupMode(e.target.value as typeof groupMode); setPreview(null); }}><option>ADD</option><option>REMOVE</option><option>REPLACE</option></select></Field><Field label="Groups"><select multiple value={groupIds} onChange={(e) => { setGroupIds([...e.target.selectedOptions].map((x) => x.value)); setPreview(null); }}>{facets.data?.groups.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select></Field></> : null}
        {mutation === "UPDATE_CONTRACT_SETTINGS" ? <><Field label="Employment status"><select value={contractStatus} onChange={(e) => { setContractStatus(e.target.value); setPreview(null); }}><option value="">No change</option><option>ACTIVE</option><option>ONBOARDING</option><option>SUSPENDED</option><option>TERMINATED</option></select></Field><Field label="Contract type"><select value={contractType} onChange={(e) => { setContractType(e.target.value); setPreview(null); }}><option value="">No change</option><option>PERMANENT</option><option>FIXED_TERM</option><option>TEMPORARY</option><option>CONTRACTOR</option><option>INTERN</option></select></Field><Field label="Contract end"><input type="date" value={contractEnd} onChange={(e) => { setContractEnd(e.target.value); setPreview(null); }} /></Field><Field label="Weekly hours"><input type="number" min="0" max="168" value={weeklyHours} onChange={(e) => { setWeeklyHours(e.target.value); setPreview(null); }} placeholder="No change" /></Field><Field label="Daily hours"><input type="number" min="0" max="24" value={dailyHours} onChange={(e) => { setDailyHours(e.target.value); setPreview(null); }} placeholder="No change" /></Field><Field label="FTE %"><input type="number" min="1" max="100" value={fte} onChange={(e) => { setFte(e.target.value); setPreview(null); }} placeholder="No change" /></Field><Field label="Cost centre"><input value={costCentre} onChange={(e) => { setCostCentre(e.target.value); setPreview(null); }} placeholder="No change" /></Field><Field label="Overtime eligible"><select value={overtimeEligible} onChange={(e) => { setOvertimeEligible(e.target.value as typeof overtimeEligible); setPreview(null); }}><option value="">No change</option><option value="true">Yes</option><option value="false">No</option></select></Field><Field label="Night shift eligible"><select value={nightEligible} onChange={(e) => { setNightEligible(e.target.value as typeof nightEligible); setPreview(null); }}><option value="">No change</option><option value="true">Yes</option><option value="false">No</option></select></Field><Field label="Standby eligible"><select value={standbyEligible} onChange={(e) => { setStandbyEligible(e.target.value as typeof standbyEligible); setPreview(null); }}><option value="">No change</option><option value="true">Yes</option><option value="false">No</option></select></Field></> : null}
        {mutation === "SCHEDULE_OFFBOARDING" ? <><Field label="Reason"><textarea value={offboardingReason} onChange={(e) => { setOffboardingReason(e.target.value); setPreview(null); }} placeholder="Controlled offboarding reason" /></Field><Check label="Revoke portal access" checked={revokeAccess} onChange={(value) => { setRevokeAccess(value); setPreview(null); }} /><Check label="End employment contracts" checked={endContracts} onChange={(value) => { setEndContracts(value); setPreview(null); }} /><Check label="Remove group memberships" checked={removeGroups} onChange={(value) => { setRemoveGroups(value); setPreview(null); }} /></> : null}
      </div>
      <div className="workforce-governance__actions"><button type="button" disabled={!canManage || !count || busy || !mutationReady} onClick={() => void doPreview()}>Preview {count.toLocaleString()} selected</button>{preview ? <button type="button" className="wr-button wr-button--primary" disabled={busy || !mutationReady} onClick={() => void submit()}>Confirm {preview.matched_count.toLocaleString()} changes</button> : null}</div>
      {preview ? <p className="workforce-governance__confirmation">Selection verified at this exact population. Re-preview after any filter, selection or change-detail update.</p> : null}
      {operation ? <div className="workforce-governance__operation"><div><strong>{operation.operation_type.replaceAll("_", " ")}</strong><StatusPill value={operation.status} /></div><progress max="100" value={operation.progress_percent} /><span>{operation.processed_count}/{operation.total_count} processed · {operation.succeeded_count} succeeded · {operation.skipped_count} skipped · {operation.failed_count} failed</span>{operation.last_error ? <p>{operation.last_error}</p> : null}</div> : null}
    </div>
  </div>;
}

function CatalogueTable({ headers, rows }: { headers: string[]; rows: { id: string; cells: string[]; edit: () => void }[] }) {
  return <div className="workforce-governance__catalogue-table"><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}<th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>{row.cells.map((cell, index) => <td key={`${row.id}-${index}`}>{cell}</td>)}<td><button type="button" onClick={row.edit}>Edit</button></td></tr>)}</tbody></table></div>;
}
function Editor({ title, disabled, onSave, onReset, children }: { title: string; disabled: boolean; onSave: () => void; onReset: () => void; children: ReactNode }) {
  return <aside className="workforce-governance__editor"><h3>{title}</h3>{children}<div><button type="button" onClick={onReset}>Reset</button><button type="button" className="wr-button wr-button--primary" disabled={disabled} onClick={onSave}><Save size={14} /> Save</button></div></aside>;
}
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="workforce-governance__field"><span>{label}</span>{children}</label>; }
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label className="workforce-governance__check"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><span>{label}</span></label>; }

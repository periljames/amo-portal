import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BriefcaseBusiness,
  Building2,
  ChevronRight,
  FileCheck2,
  GraduationCap,
  Network,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserRoundCog,
  UsersRound,
  X,
} from "lucide-react";
import {
  createGroupPolicy,
  createOrganizationPosition,
  createOrganizationUnit,
  createPositionAssignment,
  createWorkforceEngagement,
  getOrganizationOverview,
  getOrganizationReferenceData,
  listGroupPolicies,
  listOrganizationPositions,
  listOrganizationUnits,
  listPositionAssignments,
  listWorkforceEngagements,
  type GroupPolicy,
  type OrganizationOverview,
  type OrganizationPosition,
  type OrganizationReferenceData,
  type OrganizationUnit,
  type PositionAssignment,
  type WorkforceEngagement,
} from "../../services/corporateStructure";
import "../../styles/admin-corporate-structure.css";

type WorkspaceTab = "overview" | "units" | "positions" | "assignments" | "engagements" | "policies" | "compliance";
type CreateMode = "unit" | "position" | "assignment" | "engagement" | "policy" | null;

const emptyOverview: OrganizationOverview = {
  units: 0,
  active_units: 0,
  positions: 0,
  approved_headcount: 0,
  active_assignments: 0,
  vacant_positions: 0,
  workforce_engagements: 0,
  contingent_workers: 0,
  missing_primary_assignment: 0,
  missing_engagement: 0,
  compliance_profiles_due: 0,
  expiring_credentials_90_days: 0,
};

const emptyReference: OrganizationReferenceData = { users: [], groups: [], departments: [] };
const today = new Date().toISOString().slice(0, 10);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The operation could not be completed.";
}

function statusTone(value: string): string {
  const normalised = value.toUpperCase();
  if (["ACTIVE", "CURRENT", "VALID", "APPROVED"].includes(normalised)) return "good";
  if (["EXPIRING", "DUE", "ACTING", "PENDING"].includes(normalised)) return "warn";
  if (["EXPIRED", "INACTIVE", "SUSPENDED", "REVOKED"].includes(normalised)) return "bad";
  return "neutral";
}

function Metric({ label, value, note, risk = false }: { label: string; value: number; note: string; risk?: boolean }) {
  return (
    <article className={`corp-metric${risk && value > 0 ? " corp-metric--risk" : ""}`}>
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
      <small>{note}</small>
    </article>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="corp-empty">
      <Network size={26} aria-hidden="true" />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

export default function CorporateStructurePage() {
  const [tab, setTab] = useState<WorkspaceTab>("overview");
  const [createMode, setCreateMode] = useState<CreateMode>(null);
  const [overview, setOverview] = useState<OrganizationOverview>(emptyOverview);
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [positions, setPositions] = useState<OrganizationPosition[]>([]);
  const [assignments, setAssignments] = useState<PositionAssignment[]>([]);
  const [engagements, setEngagements] = useState<WorkforceEngagement[]>([]);
  const [policies, setPolicies] = useState<GroupPolicy[]>([]);
  const [reference, setReference] = useState<OrganizationReferenceData>(emptyReference);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, unitData, positionData, assignmentData, engagementData, policyData, referenceData] = await Promise.all([
        getOrganizationOverview(),
        listOrganizationUnits(undefined, true),
        listOrganizationPositions(),
        listPositionAssignments(undefined, false),
        listWorkforceEngagements(undefined, false),
        listGroupPolicies(),
        getOrganizationReferenceData(),
      ]);
      setOverview(overviewData);
      setUnits(unitData);
      setPositions(positionData);
      setAssignments(assignmentData);
      setEngagements(engagementData);
      setPolicies(policyData);
      setReference(referenceData);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activeUsers = useMemo(() => reference.users.filter((user) => user.is_active), [reference.users]);
  const filteredUnits = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return units;
    return units.filter((unit) => [unit.code, unit.name, unit.unit_type, unit.manager_name ?? "", unit.parent_name ?? ""].some((value) => value.toLowerCase().includes(term)));
  }, [search, units]);
  const filteredPositions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return positions;
    return positions.filter((position) => [position.code, position.title, position.unit_name, position.job_family ?? "", position.grade ?? ""].some((value) => value.toLowerCase().includes(term)));
  }, [positions, search]);

  async function commit(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      setCreateMode(null);
      await load();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  const tabs: Array<{ id: WorkspaceTab; label: string; count?: number }> = [
    { id: "overview", label: "Overview" },
    { id: "units", label: "Org units", count: units.length },
    { id: "positions", label: "Positions", count: positions.length },
    { id: "assignments", label: "Assignments", count: assignments.length },
    { id: "engagements", label: "Engagements", count: engagements.length },
    { id: "policies", label: "Group policies", count: policies.length },
    { id: "compliance", label: "Compliance gaps" },
  ];

  return (
    <main className="corp-page">
      <header className="corp-page__header">
        <div>
          <span className="corp-eyebrow"><Network size={15} /> Organization governance</span>
          <h1>Corporate structure</h1>
          <p>Define reporting lines, approved positions, workforce terms and evidence ownership without treating a portal role as an appointment or aviation authorisation.</p>
        </div>
        <div className="corp-header-actions">
          <Link className="corp-button corp-button--quiet" to="/manager/team"><UsersRound size={16} /> Manager portal</Link>
          <button className="corp-icon-button" type="button" onClick={() => void load()} disabled={loading} aria-label="Refresh organization data"><RefreshCw size={17} /></button>
        </div>
      </header>

      {error ? <div className="corp-alert" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" onClick={() => setError(null)}><X size={15} /></button></div> : null}

      <section className="corp-control-strip" aria-label="Organization workspace controls">
        <nav className="corp-tabs">
          {tabs.map((item) => (
            <button key={item.id} type="button" className={tab === item.id ? "is-active" : ""} onClick={() => { setTab(item.id); setSearch(""); }}>
              {item.label}{typeof item.count === "number" ? <span>{item.count}</span> : null}
            </button>
          ))}
        </nav>
        <div className="corp-control-strip__right">
          {tab !== "overview" && tab !== "compliance" ? <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${tab}`} aria-label={`Search ${tab}`} /> : null}
          {tab === "units" ? <button className="corp-button" type="button" onClick={() => setCreateMode("unit")}><Plus size={16} /> New unit</button> : null}
          {tab === "positions" ? <button className="corp-button" type="button" onClick={() => setCreateMode("position")}><Plus size={16} /> New position</button> : null}
          {tab === "assignments" ? <button className="corp-button" type="button" onClick={() => setCreateMode("assignment")}><Plus size={16} /> Assign person</button> : null}
          {tab === "engagements" ? <button className="corp-button" type="button" onClick={() => setCreateMode("engagement")}><Plus size={16} /> New engagement</button> : null}
          {tab === "policies" ? <button className="corp-button" type="button" onClick={() => setCreateMode("policy")}><Plus size={16} /> New policy</button> : null}
        </div>
      </section>

      <div className={`corp-workspace${createMode ? " corp-workspace--split" : ""}`}>
        <section className="corp-workspace__main" aria-busy={loading}>
          {tab === "overview" ? (
            <>
              <div className="corp-metric-grid">
                <Metric label="Active units" value={overview.active_units} note={`${overview.units} total structure records`} />
                <Metric label="Approved positions" value={overview.approved_headcount} note={`${overview.positions} position definitions`} />
                <Metric label="Filled assignments" value={overview.active_assignments} note={`${overview.vacant_positions} vacancies remain`} />
                <Metric label="Contingent workforce" value={overview.contingent_workers} note={`${overview.workforce_engagements} active engagements`} />
                <Metric label="Missing assignment" value={overview.missing_primary_assignment} note="Active users without a primary position" risk />
                <Metric label="Missing engagement" value={overview.missing_engagement} note="Active users without governed terms" risk />
                <Metric label="Reviews due" value={overview.compliance_profiles_due} note="Personnel profiles needing review" risk />
                <Metric label="Credentials ≤ 90 days" value={overview.expiring_credentials_90_days} note="Valid evidence nearing expiry" risk />
              </div>
              <div className="corp-overview-grid">
                <article className="corp-panel">
                  <header><div><h2>Governance model</h2><p>Separate five concepts that are commonly mixed together.</p></div></header>
                  <div className="corp-governance-flow">
                    {[
                      [Building2, "Organization unit", "Where accountability sits"],
                      [BriefcaseBusiness, "Position", "Approved job and regulatory responsibility"],
                      [UserRoundCog, "Assignment", "Who occupies the position and reports to whom"],
                      [GraduationCap, "Engagement", "Employee, intern, contractor or secondment terms"],
                      [ShieldCheck, "Evidence", "Competence, training, licences and acknowledgements"],
                    ].map(([Icon, title, note], index) => {
                      const FlowIcon = Icon as typeof Building2;
                      return <div key={String(title)}><FlowIcon size={19} /><span><strong>{String(title)}</strong><small>{String(note)}</small></span>{index < 4 ? <ChevronRight size={15} /> : null}</div>;
                    })}
                  </div>
                </article>
                <article className="corp-panel">
                  <header><div><h2>Control priorities</h2><p>Items that should be closed before relying on access assignments.</p></div></header>
                  <ul className="corp-priority-list">
                    <li className={overview.missing_primary_assignment ? "is-risk" : "is-complete"}><span>{overview.missing_primary_assignment}</span><div><strong>Unplaced active users</strong><small>Create primary assignments and reporting managers.</small></div></li>
                    <li className={overview.missing_engagement ? "is-risk" : "is-complete"}><span>{overview.missing_engagement}</span><div><strong>Ungoverned employment terms</strong><small>Record permanent, fixed-term or contingent engagements.</small></div></li>
                    <li className={overview.compliance_profiles_due ? "is-risk" : "is-complete"}><span>{overview.compliance_profiles_due}</span><div><strong>Personnel reviews due</strong><small>Verify identity, competence, training and conduct records.</small></div></li>
                  </ul>
                </article>
              </div>
            </>
          ) : null}

          {tab === "units" ? (
            <div className="corp-table-shell"><table className="corp-table"><thead><tr><th>Unit</th><th>Type / parent</th><th>Management</th><th>Positions</th><th>Headcount</th><th>Status</th></tr></thead><tbody>
              {filteredUnits.map((unit) => <tr key={unit.id}><td><strong>{unit.name}</strong><small>{unit.code}{unit.cost_center ? ` · ${unit.cost_center}` : ""}</small></td><td><span className="corp-chip">{unit.unit_type}</span><small>{unit.parent_name ?? "Top level"}</small></td><td><strong>{unit.manager_name ?? "Manager not assigned"}</strong><small>{unit.deputy_manager_name ? `Deputy: ${unit.deputy_manager_name}` : "No deputy"}</small></td><td><strong>{unit.position_count}</strong><small>{unit.assignment_count} occupied</small></td><td>{unit.headcount_limit ?? "—"}</td><td><span className={`corp-status corp-status--${unit.is_active ? "good" : "bad"}`}>{unit.is_active ? "Active" : "Inactive"}</span></td></tr>)}
            </tbody></table>{!filteredUnits.length ? <EmptyState title="No organization units" detail="Create the top-level company or division, then add departments, sections and teams." /> : null}</div>
          ) : null}

          {tab === "positions" ? (
            <div className="corp-table-shell"><table className="corp-table"><thead><tr><th>Position</th><th>Unit</th><th>Reports to</th><th>Approved / filled</th><th>Governance</th><th>Vacancies</th></tr></thead><tbody>
              {filteredPositions.map((position) => <tr key={position.id}><td><strong>{position.title}</strong><small>{position.code}{position.grade ? ` · Grade ${position.grade}` : ""}</small></td><td><strong>{position.unit_name}</strong><small>{position.job_family ?? position.employment_category}</small></td><td>{position.reports_to_position_title ?? "Top position"}</td><td><strong>{position.occupied_count} / {position.headcount_limit}</strong><small>{position.is_supervisory ? "Supervisory" : "Individual contributor"}</small></td><td>{position.is_regulatory_post ? <span className="corp-chip corp-chip--accent">{position.regulatory_post_type ?? "Regulatory post"}</span> : <span className="corp-chip">Corporate</span>}<small>{position.authority_acceptance_required ? "Authority acceptance required" : position.succession_criticality}</small></td><td><span className={`corp-status corp-status--${position.vacancy_count > 0 ? "warn" : "good"}`}>{position.vacancy_count}</span></td></tr>)}
            </tbody></table>{!filteredPositions.length ? <EmptyState title="No approved positions" detail="Define positions under organization units before assigning personnel." /> : null}</div>
          ) : null}

          {tab === "assignments" ? (
            <div className="corp-table-shell"><table className="corp-table"><thead><tr><th>Person</th><th>Position / unit</th><th>Reports to</th><th>Assignment</th><th>Effective period</th><th>Evidence</th><th></th></tr></thead><tbody>
              {assignments.filter((item) => !search || [item.user_name, item.staff_code, item.position_title, item.unit_name].join(" ").toLowerCase().includes(search.toLowerCase())).map((item) => <tr key={item.id}><td><strong>{item.user_name}</strong><small>{item.staff_code}</small></td><td><strong>{item.position_title}</strong><small>{item.unit_name}</small></td><td>{item.reporting_manager_name ?? "Not assigned"}</td><td><span className={`corp-status corp-status--${statusTone(item.status)}`}>{item.status}</span><small>{item.assignment_type}{item.is_primary ? " · Primary" : ""}</small></td><td><strong>{item.effective_from}</strong><small>{item.effective_to ? `to ${item.effective_to}` : "Open ended"}</small></td><td><strong>{item.appointment_reference ?? "—"}</strong><small>{item.authority_acceptance_reference ? `Authority: ${item.authority_acceptance_reference}` : "No authority reference"}</small></td><td><Link className="corp-row-link" to={`/admin/users/${item.user_id}/governance`}>Profile <ChevronRight size={14} /></Link></td></tr>)}
            </tbody></table>{!assignments.length ? <EmptyState title="No position assignments" detail="Assign active personnel to approved positions and define their reporting manager." /> : null}</div>
          ) : null}

          {tab === "engagements" ? (
            <div className="corp-table-shell"><table className="corp-table"><thead><tr><th>Person</th><th>Engagement</th><th>Period</th><th>Sponsor</th><th>External party / programme</th><th>Access control</th><th></th></tr></thead><tbody>
              {engagements.filter((item) => !search || [item.user_name, item.staff_code, item.engagement_type, item.sponsor_name ?? ""].join(" ").toLowerCase().includes(search.toLowerCase())).map((item) => <tr key={item.id}><td><strong>{item.user_name}</strong><small>{item.staff_code}</small></td><td><span className={`corp-status corp-status--${statusTone(item.status)}`}>{item.engagement_type}</span><small>{item.contract_reference ?? item.status}</small></td><td><strong>{item.start_date}</strong><small>{item.end_date ? `to ${item.end_date}` : "Open ended"}</small></td><td>{item.sponsor_name ?? "Not required"}</td><td><strong>{item.institution_or_vendor ?? item.external_organisation ?? "—"}</strong><small>{item.programme_name ?? ""}</small></td><td><strong>{item.access_expiry_on ?? "No automatic expiry"}</strong><small>{item.offboarding_required ? "Offboarding required" : "No offboarding flag"}</small></td><td><Link className="corp-row-link" to={`/admin/users/${item.user_id}/governance`}>Profile <ChevronRight size={14} /></Link></td></tr>)}
            </tbody></table>{!engagements.length ? <EmptyState title="No workforce engagements" detail="Record employees, fixed-term staff, interns, trainees, contractors and secondments." /> : null}</div>
          ) : null}

          {tab === "policies" ? (
            <div className="corp-table-shell"><table className="corp-table"><thead><tr><th>Policy</th><th>Group / scope</th><th>Membership</th><th>Approvals</th><th>Segregation tags</th><th>Status</th></tr></thead><tbody>
              {policies.filter((item) => !search || [item.name, item.code, item.group_name, item.unit_name ?? ""].join(" ").toLowerCase().includes(search.toLowerCase())).map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.code}</small></td><td><strong>{item.group_name}</strong><small>{item.unit_name ?? "Tenant-wide"} · {item.inheritance_mode}</small></td><td>{item.membership_mode}<small>{item.default_account_role ?? "No access role implied"}</small></td><td><span className="corp-chip">Manager {item.requires_manager_approval ? "required" : "not required"}</span><small>Quality {item.requires_quality_approval ? "required" : "not required"}</small></td><td>{item.segregation_tags.length ? item.segregation_tags.join(", ") : "—"}</td><td><span className={`corp-status corp-status--${item.is_active ? "good" : "bad"}`}>{item.is_active ? "Active" : "Inactive"}</span></td></tr>)}
            </tbody></table>{!policies.length ? <EmptyState title="No group policies" detail="Bind groups to organization scope, approval rules and explicit permission templates." /> : null}</div>
          ) : null}

          {tab === "compliance" ? (
            <div className="corp-compliance-grid">
              <article className="corp-panel"><header><div><h2>Personnel readiness queue</h2><p>Prioritised data gaps that weaken assignment and access decisions.</p></div></header><div className="corp-gap-list">
                {[{label:"Active users without a primary position",value:overview.missing_primary_assignment,route:"/admin/users"},{label:"Active users without an engagement",value:overview.missing_engagement,route:"/admin/users"},{label:"Personnel compliance reviews due",value:overview.compliance_profiles_due,route:"/admin/users"},{label:"Credentials expiring within 90 days",value:overview.expiring_credentials_90_days,route:"/admin/users"}].map((item) => <Link key={item.label} to={item.route}><span className={item.value ? "is-risk" : "is-clear"}>{item.value}</span><strong>{item.label}</strong><ChevronRight size={16} /></Link>)}
              </div></article>
              <article className="corp-panel"><header><div><h2>Evidence boundaries</h2><p>What these records prove—and what they do not.</p></div></header><ul className="corp-evidence-list"><li><FileCheck2 size={18}/><span><strong>Appointment evidence</strong><small>Corporate position and authority acceptance references remain distinct from account permissions.</small></span></li><li><GraduationCap size={18}/><span><strong>Competence evidence</strong><small>Assessment status, training currency and credential scope are reviewed independently.</small></span></li><li><ShieldCheck size={18}/><span><strong>Access evidence</strong><small>Group policy grants must still pass approval, expiry and segregation-of-duties controls.</small></span></li></ul></article>
            </div>
          ) : null}
        </section>

        {createMode ? <CreatePanel mode={createMode} units={units} positions={positions} reference={reference} saving={saving} onClose={() => setCreateMode(null)} onCommit={commit} /> : null}
      </div>
    </main>
  );
}

function CreatePanel({ mode, units, positions, reference, saving, onClose, onCommit }: { mode: Exclude<CreateMode, null>; units: OrganizationUnit[]; positions: OrganizationPosition[]; reference: OrganizationReferenceData; saving: boolean; onClose: () => void; onCommit: (action: () => Promise<unknown>) => Promise<void> }) {
  const activeUsers = reference.users.filter((user) => user.is_active);
  const [values, setValues] = useState<Record<string, string | boolean>>({ effective_from: today, start_date: today, is_primary: true, is_active: true, requires_manager_approval: true, offboarding_required: true });
  const set = (key: string, value: string | boolean) => setValues((current) => ({ ...current, [key]: value }));
  const string = (key: string) => String(values[key] ?? "");
  const checked = (key: string) => Boolean(values[key]);
  const nullable = (key: string) => string(key).trim() || null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "unit") await onCommit(() => createOrganizationUnit({ code: string("code"), name: string("name"), unit_type: string("unit_type") || "DEPARTMENT", parent_id: nullable("parent_id"), department_id: nullable("department_id"), manager_user_id: nullable("manager_user_id"), deputy_manager_user_id: nullable("deputy_manager_user_id"), accountable_manager_user_id: nullable("accountable_manager_user_id"), quality_owner_user_id: nullable("quality_owner_user_id"), cost_center: nullable("cost_center"), purpose: nullable("purpose"), headcount_limit: string("headcount_limit") ? Number(string("headcount_limit")) : null, is_active: true }));
    if (mode === "position") await onCommit(() => createOrganizationPosition({ unit_id: string("unit_id"), code: string("code"), title: string("title"), reports_to_position_id: nullable("reports_to_position_id"), job_family: nullable("job_family"), grade: nullable("grade"), employment_category: string("employment_category") || "EMPLOYEE", headcount_limit: Number(string("headcount_limit") || 1), is_supervisory: checked("is_supervisory"), is_regulatory_post: checked("is_regulatory_post"), regulatory_post_type: nullable("regulatory_post_type"), authority_acceptance_required: checked("authority_acceptance_required"), minimum_competence_summary: nullable("minimum_competence_summary"), responsibilities: nullable("responsibilities"), succession_criticality: string("succession_criticality") || "STANDARD", is_active: true }));
    if (mode === "assignment") await onCommit(() => createPositionAssignment({ user_id: string("user_id"), position_id: string("position_id"), reporting_manager_user_id: nullable("reporting_manager_user_id"), assignment_type: string("assignment_type") || "SUBSTANTIVE", status: "ACTIVE", is_primary: checked("is_primary"), matrix_reporting: checked("matrix_reporting"), matrix_reason: nullable("matrix_reason"), fte_percent: Number(string("fte_percent") || 100), effective_from: string("effective_from") || today, effective_to: nullable("effective_to"), appointment_reference: nullable("appointment_reference"), authority_acceptance_reference: nullable("authority_acceptance_reference"), authority_accepted_on: nullable("authority_accepted_on"), delegation_limitations: nullable("delegation_limitations") }));
    if (mode === "engagement") await onCommit(() => createWorkforceEngagement({ user_id: string("user_id"), engagement_type: string("engagement_type") || "EMPLOYEE", status: "ACTIVE", contract_reference: nullable("contract_reference"), start_date: string("start_date") || today, end_date: nullable("end_date"), probation_months: string("probation_months") ? Number(string("probation_months")) : null, sponsor_user_id: nullable("sponsor_user_id"), external_organisation: nullable("external_organisation"), institution_or_vendor: nullable("institution_or_vendor"), programme_name: nullable("programme_name"), learning_objectives: nullable("learning_objectives"), work_permit_status: nullable("work_permit_status"), work_permit_reference: nullable("work_permit_reference"), work_permit_expires_on: nullable("work_permit_expires_on"), background_check_status: nullable("background_check_status"), access_expiry_on: nullable("access_expiry_on"), offboarding_required: checked("offboarding_required") }));
    if (mode === "policy") await onCommit(() => createGroupPolicy({ group_id: string("group_id"), unit_id: nullable("unit_id"), code: string("code"), name: string("name"), description: nullable("description"), inheritance_mode: string("inheritance_mode") || "UNIT_AND_DESCENDANTS", membership_mode: string("membership_mode") || "MANUAL", default_account_role: nullable("default_account_role"), permission_template: {}, segregation_tags: string("segregation_tags").split(",").map((item) => item.trim()).filter(Boolean), requires_manager_approval: checked("requires_manager_approval"), requires_quality_approval: checked("requires_quality_approval"), maximum_assignment_days: string("maximum_assignment_days") ? Number(string("maximum_assignment_days")) : null, is_active: true }));
  }

  const titles: Record<Exclude<CreateMode, null>, string> = { unit: "Create organization unit", position: "Create approved position", assignment: "Assign person to position", engagement: "Create workforce engagement", policy: "Create group policy" };
  return <aside className="corp-create-panel"><header><div><span>Controlled setup</span><h2>{titles[mode]}</h2></div><button type="button" onClick={onClose} aria-label="Close form"><X size={18}/></button></header><form onSubmit={(event) => void submit(event)}>
    {mode === "unit" ? <><Field label="Unit code"><input required value={string("code")} onChange={(e)=>set("code",e.target.value)} placeholder="QUALITY" /></Field><Field label="Unit name"><input required value={string("name")} onChange={(e)=>set("name",e.target.value)} placeholder="Quality and Compliance" /></Field><div className="corp-form-row"><Field label="Type"><select value={string("unit_type") || "DEPARTMENT"} onChange={(e)=>set("unit_type",e.target.value)}>{["COMPANY","DIVISION","DIRECTORATE","DEPARTMENT","SECTION","TEAM","STATION","BASE","PROJECT"].map((item)=><option key={item}>{item}</option>)}</select></Field><Field label="Parent"><select value={string("parent_id")} onChange={(e)=>set("parent_id",e.target.value)}><option value="">Top level</option>{units.filter((item)=>item.is_active).map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field></div><div className="corp-form-row"><UserSelect label="Manager" value={string("manager_user_id")} users={activeUsers} onChange={(value)=>set("manager_user_id",value)} /><UserSelect label="Deputy" value={string("deputy_manager_user_id")} users={activeUsers} onChange={(value)=>set("deputy_manager_user_id",value)} /></div><div className="corp-form-row"><UserSelect label="Accountable manager" value={string("accountable_manager_user_id")} users={activeUsers} onChange={(value)=>set("accountable_manager_user_id",value)} /><UserSelect label="Quality owner" value={string("quality_owner_user_id")} users={activeUsers} onChange={(value)=>set("quality_owner_user_id",value)} /></div><div className="corp-form-row"><Field label="Mapped department"><select value={string("department_id")} onChange={(e)=>set("department_id",e.target.value)}><option value="">None</option>{reference.departments.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Headcount ceiling"><input type="number" min="0" value={string("headcount_limit")} onChange={(e)=>set("headcount_limit",e.target.value)} /></Field></div><Field label="Purpose"><textarea rows={3} value={string("purpose")} onChange={(e)=>set("purpose",e.target.value)} /></Field></> : null}
    {mode === "position" ? <><Field label="Organization unit"><select required value={string("unit_id")} onChange={(e)=>set("unit_id",e.target.value)}><option value="">Select unit</option>{units.filter((item)=>item.is_active).map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><div className="corp-form-row"><Field label="Position code"><input required value={string("code")} onChange={(e)=>set("code",e.target.value)} /></Field><Field label="Position title"><input required value={string("title")} onChange={(e)=>set("title",e.target.value)} /></Field></div><Field label="Reports to position"><select value={string("reports_to_position_id")} onChange={(e)=>set("reports_to_position_id",e.target.value)}><option value="">Top position</option>{positions.map((item)=><option key={item.id} value={item.id}>{item.title} · {item.unit_name}</option>)}</select></Field><div className="corp-form-row"><Field label="Job family"><input value={string("job_family")} onChange={(e)=>set("job_family",e.target.value)} /></Field><Field label="Grade"><input value={string("grade")} onChange={(e)=>set("grade",e.target.value)} /></Field><Field label="Headcount"><input required type="number" min="1" value={string("headcount_limit") || "1"} onChange={(e)=>set("headcount_limit",e.target.value)} /></Field></div><Check label="Supervisory position" checked={checked("is_supervisory")} onChange={(value)=>set("is_supervisory",value)} /><Check label="Regulatory / nominated post" checked={checked("is_regulatory_post")} onChange={(value)=>set("is_regulatory_post",value)} />{checked("is_regulatory_post") ? <><Field label="Regulatory post type"><input required value={string("regulatory_post_type")} onChange={(e)=>set("regulatory_post_type",e.target.value)} placeholder="ACCOUNTABLE_MANAGER / QUALITY_MANAGER" /></Field><Check label="Authority acceptance evidence required" checked={checked("authority_acceptance_required")} onChange={(value)=>set("authority_acceptance_required",value)} /></> : null}<Field label="Minimum competence"><textarea rows={3} value={string("minimum_competence_summary")} onChange={(e)=>set("minimum_competence_summary",e.target.value)} /></Field><Field label="Responsibilities"><textarea rows={3} value={string("responsibilities")} onChange={(e)=>set("responsibilities",e.target.value)} /></Field></> : null}
    {mode === "assignment" ? <><UserSelect label="Person" required value={string("user_id")} users={activeUsers} onChange={(value)=>set("user_id",value)} /><Field label="Approved position"><select required value={string("position_id")} onChange={(e)=>set("position_id",e.target.value)}><option value="">Select position</option>{positions.filter((item)=>item.is_active && item.vacancy_count>0).map((item)=><option key={item.id} value={item.id}>{item.title} · {item.unit_name} ({item.vacancy_count} open)</option>)}</select></Field><UserSelect label="Reporting manager" value={string("reporting_manager_user_id")} users={activeUsers} onChange={(value)=>set("reporting_manager_user_id",value)} /><div className="corp-form-row"><Field label="Assignment type"><select value={string("assignment_type") || "SUBSTANTIVE"} onChange={(e)=>set("assignment_type",e.target.value)}>{["SUBSTANTIVE","ACTING","SECONDMENT","TEMPORARY","INTERIM","INTERNSHIP","APPRENTICESHIP","CONTRACT"].map((item)=><option key={item}>{item}</option>)}</select></Field><Field label="FTE %"><input type="number" min="1" max="100" value={string("fte_percent") || "100"} onChange={(e)=>set("fte_percent",e.target.value)} /></Field></div><div className="corp-form-row"><Field label="Effective from"><input required type="date" value={string("effective_from") || today} onChange={(e)=>set("effective_from",e.target.value)} /></Field><Field label="Effective to"><input type="date" value={string("effective_to")} onChange={(e)=>set("effective_to",e.target.value)} /></Field></div><Check label="Primary position" checked={checked("is_primary")} onChange={(value)=>set("is_primary",value)} /><Check label="Matrix reporting exception" checked={checked("matrix_reporting")} onChange={(value)=>set("matrix_reporting",value)} />{checked("matrix_reporting") ? <Field label="Matrix reporting reason"><textarea required rows={2} value={string("matrix_reason")} onChange={(e)=>set("matrix_reason",e.target.value)} /></Field> : null}<Field label="Appointment reference"><input value={string("appointment_reference")} onChange={(e)=>set("appointment_reference",e.target.value)} /></Field><Field label="Authority acceptance reference"><input value={string("authority_acceptance_reference")} onChange={(e)=>set("authority_acceptance_reference",e.target.value)} /></Field><Field label="Delegation limitations"><textarea rows={2} value={string("delegation_limitations")} onChange={(e)=>set("delegation_limitations",e.target.value)} /></Field></> : null}
    {mode === "engagement" ? <><UserSelect label="Person" required value={string("user_id")} users={activeUsers} onChange={(value)=>set("user_id",value)} /><Field label="Engagement type"><select value={string("engagement_type") || "EMPLOYEE"} onChange={(e)=>set("engagement_type",e.target.value)}>{["EMPLOYEE","FIXED_TERM","CONTRACTOR","CONSULTANT","INTERN","TRAINEE","APPRENTICE","VOLUNTEER","SECONDED","TEMPORARY"].map((item)=><option key={item}>{item}</option>)}</select></Field><div className="corp-form-row"><Field label="Start date"><input required type="date" value={string("start_date") || today} onChange={(e)=>set("start_date",e.target.value)} /></Field><Field label="End date"><input type="date" value={string("end_date")} onChange={(e)=>set("end_date",e.target.value)} /></Field></div><UserSelect label="Internal sponsor" value={string("sponsor_user_id")} users={activeUsers} onChange={(value)=>set("sponsor_user_id",value)} /><div className="corp-form-row"><Field label="Contract / agreement ref"><input value={string("contract_reference")} onChange={(e)=>set("contract_reference",e.target.value)} /></Field><Field label="Access expires"><input type="date" value={string("access_expiry_on")} onChange={(e)=>set("access_expiry_on",e.target.value)} /></Field></div><Field label="Institution, vendor or school"><input value={string("institution_or_vendor")} onChange={(e)=>set("institution_or_vendor",e.target.value)} /></Field><Field label="Programme"><input value={string("programme_name")} onChange={(e)=>set("programme_name",e.target.value)} /></Field><Field label="Learning objectives / scope"><textarea rows={3} value={string("learning_objectives")} onChange={(e)=>set("learning_objectives",e.target.value)} /></Field><div className="corp-form-row"><Field label="Work permit status"><select value={string("work_permit_status")} onChange={(e)=>set("work_permit_status",e.target.value)}><option value="">Not recorded</option><option>CURRENT</option><option>PENDING</option><option>NOT_REQUIRED</option><option>EXPIRED</option></select></Field><Field label="Background check"><select value={string("background_check_status")} onChange={(e)=>set("background_check_status",e.target.value)}><option value="">Not recorded</option><option>CLEAR</option><option>PENDING</option><option>NOT_REQUIRED</option><option>REVIEW</option></select></Field></div><Check label="Controlled offboarding required" checked={checked("offboarding_required")} onChange={(value)=>set("offboarding_required",value)} /></> : null}
    {mode === "policy" ? <><Field label="User group"><select required value={string("group_id")} onChange={(e)=>set("group_id",e.target.value)}><option value="">Select group</option>{reference.groups.map((item)=><option key={item.id} value={item.id}>{item.name} · {item.group_type}</option>)}</select></Field><div className="corp-form-row"><Field label="Policy code"><input required value={string("code")} onChange={(e)=>set("code",e.target.value)} /></Field><Field label="Policy name"><input required value={string("name")} onChange={(e)=>set("name",e.target.value)} /></Field></div><Field label="Organization scope"><select value={string("unit_id")} onChange={(e)=>set("unit_id",e.target.value)}><option value="">Tenant-wide</option>{units.filter((item)=>item.is_active).map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><div className="corp-form-row"><Field label="Inheritance"><select value={string("inheritance_mode") || "UNIT_AND_DESCENDANTS"} onChange={(e)=>set("inheritance_mode",e.target.value)}><option>UNIT_ONLY</option><option>UNIT_AND_DESCENDANTS</option><option>TENANT_WIDE</option></select></Field><Field label="Membership"><select value={string("membership_mode") || "MANUAL"} onChange={(e)=>set("membership_mode",e.target.value)}><option>MANUAL</option><option>POSITION_DRIVEN</option><option>UNIT_DRIVEN</option></select></Field></div><Field label="Segregation tags (comma separated)"><input value={string("segregation_tags")} onChange={(e)=>set("segregation_tags",e.target.value)} placeholder="CRS_SIGN, WORK_ORDER_APPROVE" /></Field><div className="corp-form-row"><Check label="Manager approval" checked={checked("requires_manager_approval")} onChange={(value)=>set("requires_manager_approval",value)} /><Check label="Quality approval" checked={checked("requires_quality_approval")} onChange={(value)=>set("requires_quality_approval",value)} /></div><Field label="Maximum assignment days"><input type="number" min="1" value={string("maximum_assignment_days")} onChange={(e)=>set("maximum_assignment_days",e.target.value)} /></Field><Field label="Policy description"><textarea rows={3} value={string("description")} onChange={(e)=>set("description",e.target.value)} /></Field></> : null}
    <footer><button className="corp-button corp-button--quiet" type="button" onClick={onClose}>Cancel</button><button className="corp-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save controlled record"}</button></footer>
  </form></aside>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="corp-field"><span>{label}</span>{children}</label>; }
function UserSelect({ label, value, users, onChange, required = false }: { label: string; value: string; users: OrganizationReferenceData["users"]; onChange: (value: string) => void; required?: boolean }) { return <Field label={label}><select required={required} value={value} onChange={(event)=>onChange(event.target.value)}><option value="">{required ? "Select person" : "Not assigned"}</option>{users.map((user)=><option key={user.id} value={user.id}>{user.full_name} · {user.staff_code}</option>)}</select></Field>; }
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label className="corp-check"><input type="checkbox" checked={checked} onChange={(event)=>onChange(event.target.checked)} /><span>{label}</span></label>; }

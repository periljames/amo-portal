import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  assessWorkPackage,
  createForecastScenario,
  createPackageRequirement,
  freezeWorkPackage,
  getReadinessDashboard,
  listForecastScenarios,
  listPackageAssessments,
  listPackageFreezes,
  listPackageRequirements,
  runForecastScenario,
  updatePackageRequirement,
  type ForecastScenario,
  type PackageFreeze,
  type ReadinessAssessment,
  type ReadinessDashboard,
  type ReadinessRequirement,
} from "../../services/forecastReadiness";
import { listWorkPackages, type WorkPackage } from "../../services/workPackages";
import { formatCapabilitiesForUi } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";
import "../../styles/forecast-readiness.css";

const emptyDashboard: ReadinessDashboard = {
  scenarios: 0,
  completed_scenarios: 0,
  packages_assessed: 0,
  ready_packages: 0,
  blocked_packages: 0,
  shortages: 0,
  active_freezes: 0,
};

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const className = normalized.includes("blocked") || normalized.includes("shortage") || normalized.includes("overdue")
    ? "badge badge--danger"
    : normalized.includes("attention") || normalized.includes("draft") || normalized.includes("scenario")
      ? "badge badge--warning"
      : normalized.includes("ready") || normalized.includes("complete") || normalized.includes("confirmed") || normalized.includes("active")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

export const PlanningForecastReadinessPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [dashboard, setDashboard] = useState<ReadinessDashboard>(emptyDashboard);
  const [scenarios, setScenarios] = useState<ForecastScenario[]>([]);
  const [packages, setPackages] = useState<WorkPackage[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [selectedPackageId, setSelectedPackageId] = useState<number | null>(null);
  const [requirements, setRequirements] = useState<ReadinessRequirement[]>([]);
  const [assessments, setAssessments] = useState<ReadinessAssessment[]>([]);
  const [freezes, setFreezes] = useState<PackageFreeze[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [scenarioDraft, setScenarioDraft] = useState({
    name: `Base forecast ${new Date().toISOString().slice(0, 10)}`,
    start_date: new Date().toISOString().slice(0, 10),
    horizon_days: 180,
    default_daily_hours: 5,
    default_daily_cycles: 3,
  });
  const [requirementDraft, setRequirementDraft] = useState({
    category: "MANPOWER" as ReadinessRequirement["category"],
    description: "",
    reference: "",
    quantity_required: 1,
    quantity_confirmed: 0,
  });

  const loadPackageDetail = useCallback(async (packageId: number | null) => {
    if (!packageId) {
      setRequirements([]); setAssessments([]); setFreezes([]); return;
    }
    const [requirementRows, assessmentRows, freezeRows] = await Promise.all([
      listPackageRequirements(packageId),
      listPackageAssessments(packageId),
      listPackageFreezes(packageId),
    ]);
    setRequirements(requirementRows);
    setAssessments(assessmentRows);
    setFreezes(freezeRows);
  }, []);

  const reload = useCallback(async () => {
    const [dashboardData, scenarioRows, packageRows] = await Promise.all([
      getReadinessDashboard(), listForecastScenarios(), listWorkPackages(),
    ]);
    setDashboard(dashboardData);
    setScenarios(scenarioRows);
    setPackages(packageRows);
    setSelectedScenarioId((current) => current || scenarioRows[0]?.id || "");
    setSelectedPackageId((current) => current ?? packageRows[0]?.id ?? null);
  }, []);

  useEffect(() => {
    void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Forecast readiness could not be loaded."));
  }, [reload]);

  useEffect(() => {
    void loadPackageDetail(selectedPackageId).catch((error) => setMessage(error instanceof Error ? error.message : "Package readiness could not be loaded."));
  }, [loadPackageDetail, selectedPackageId]);

  const selectedScenario = useMemo(() => scenarios.find((row) => row.id === selectedScenarioId) || scenarios[0] || null, [scenarios, selectedScenarioId]);
  const selectedPackage = useMemo(() => packages.find((row) => row.id === selectedPackageId) || packages[0] || null, [packages, selectedPackageId]);

  const execute = async (success: string, action: () => Promise<unknown>) => {
    setBusy(true); setMessage(null);
    try { await action(); setMessage(success); await reload(); await loadPackageDetail(selectedPackageId); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Planning operation failed."); }
    finally { setBusy(false); }
  };

  const createScenario = () => execute("Forecast scenario created.", async () => {
    const created = await createForecastScenario({ ...scenarioDraft, aircraft_assumptions_json: {} });
    setSelectedScenarioId(created.id);
  });

  const runScenario = () => execute("Forecast scenario recalculated.", async () => {
    if (!selectedScenario) throw new Error("Select a forecast scenario first.");
    await runForecastScenario(selectedScenario.id);
  });

  const addRequirement = () => execute("Readiness requirement added.", async () => {
    if (!selectedPackage) throw new Error("Select a work package first.");
    if (!requirementDraft.description.trim()) throw new Error("Requirement description is required.");
    await createPackageRequirement(selectedPackage.id, requirementDraft);
    setRequirementDraft((current) => ({ ...current, description: "", reference: "", quantity_confirmed: 0 }));
  });

  const confirmRequirement = (requirement: ReadinessRequirement) => execute("Requirement confirmation updated.", async () => {
    await updatePackageRequirement(requirement.id, { quantity_confirmed: requirement.quantity_required, status: "CONFIRMED" });
  });

  const assess = () => execute("Package readiness assessment completed.", async () => {
    if (!selectedPackage) throw new Error("Select a work package first.");
    await assessWorkPackage(selectedPackage.id);
  });

  const freeze = () => execute("Ready package manifest frozen.", async () => {
    if (!selectedPackage) throw new Error("Select a work package first.");
    const reason = window.prompt("Freeze reason", "Planning scope and readiness confirmed before Production release.");
    if (!reason?.trim()) throw new Error("Freeze reason is required.");
    await freezeWorkPackage(selectedPackage.id, reason.trim());
  });

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two forecast-readiness-page">
        <header className="page-header planning-phase-one__header">
          <div><p className="planning-phase-one__eyebrow">Maintenance Planning / Scenario & Readiness</p><h1>Forecast and Package Readiness</h1><p className="page-header__subtitle">Model utilization-driven due dates, confirm package resources, and freeze an immutable release manifest.</p><p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p></div>
          <div className="planning-phase-one__header-actions"><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/work-packages`}>Package builder</Link><button className="btn btn-primary" disabled={busy} onClick={() => void reload()}>Refresh</button></div>
        </header>

        <nav className="winair-subnav" aria-label="Work package views"><Link to={`/maintenance/${amoCode}/planning/work-packages`}>Package builder</Link><Link className="is-active" to={`/maintenance/${amoCode}/planning/work-packages?view=readiness`}>Forecast & readiness</Link></nav>
        {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}

        <section className="planning-metric-grid">{[
          ["Scenarios", dashboard.scenarios], ["Completed", dashboard.completed_scenarios], ["Assessed packages", dashboard.packages_assessed], ["Ready", dashboard.ready_packages], ["Blocked", dashboard.blocked_packages], ["Shortages", dashboard.shortages], ["Frozen", dashboard.active_freezes],
        ].map(([label, value]) => <article key={String(label)} className="planning-metric-card"><span className="planning-metric-card__label">{label}</span><strong>{value}</strong></article>)}</section>

        <section className="forecast-readiness-layout">
          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Forecast scenarios</h2><p>Convert remaining FH, FC and calendar limits into projected trigger dates.</p></div></div>
            <div className="forecast-form-grid">
              <label><span>Name</span><input className="input" value={scenarioDraft.name} onChange={(event) => setScenarioDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label><span>Start</span><input className="input" type="date" value={scenarioDraft.start_date} onChange={(event) => setScenarioDraft((current) => ({ ...current, start_date: event.target.value }))} /></label>
              <label><span>Horizon days</span><input className="input" type="number" min="1" value={scenarioDraft.horizon_days} onChange={(event) => setScenarioDraft((current) => ({ ...current, horizon_days: Number(event.target.value) }))} /></label>
              <label><span>FH/day</span><input className="input" type="number" min="0" step="0.1" value={scenarioDraft.default_daily_hours} onChange={(event) => setScenarioDraft((current) => ({ ...current, default_daily_hours: Number(event.target.value) }))} /></label>
              <label><span>FC/day</span><input className="input" type="number" min="0" step="0.1" value={scenarioDraft.default_daily_cycles} onChange={(event) => setScenarioDraft((current) => ({ ...current, default_daily_cycles: Number(event.target.value) }))} /></label>
            </div>
            <div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => void createScenario()}>Create scenario</button><button className="btn btn-primary" disabled={busy || !selectedScenario} onClick={() => void runScenario()}>Run selected</button></div>
            <div className="forecast-scenario-list">{scenarios.map((scenario) => <button key={scenario.id} className={selectedScenario?.id === scenario.id ? "is-selected" : ""} onClick={() => setSelectedScenarioId(scenario.id)}><span><strong>{scenario.name}</strong><small>{scenario.horizon_days} days · {scenario.default_daily_hours} FH/day · {scenario.default_daily_cycles} FC/day</small></span><StatusChip value={scenario.status} /></button>)}</div>
          </article>

          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Package resource gate</h2><p>Manpower, authorizations, materials, tools, facilities, documents, and hangar slots must be explicitly controlled.</p></div></div>
            <select className="input" value={selectedPackageId || ""} onChange={(event) => setSelectedPackageId(Number(event.target.value) || null)}><option value="">Select work package</option>{packages.map((row) => <option key={row.id} value={row.id}>{row.package_ref} · {row.aircraft_serial_number} · {row.title}</option>)}</select>
            <div className="forecast-form-grid readiness-requirement-form">
              <label><span>Category</span><select className="input" value={requirementDraft.category} onChange={(event) => setRequirementDraft((current) => ({ ...current, category: event.target.value as ReadinessRequirement["category"] }))}>{["MANPOWER", "AUTHORIZATION", "MATERIAL", "TOOL", "FACILITY", "DOCUMENT", "SLOT"].map((value) => <option key={value}>{value}</option>)}</select></label>
              <label><span>Reference</span><input className="input" value={requirementDraft.reference} onChange={(event) => setRequirementDraft((current) => ({ ...current, reference: event.target.value }))} /></label>
              <label className="is-wide"><span>Description</span><input className="input" value={requirementDraft.description} onChange={(event) => setRequirementDraft((current) => ({ ...current, description: event.target.value }))} /></label>
              <label><span>Required</span><input className="input" type="number" min="0" value={requirementDraft.quantity_required} onChange={(event) => setRequirementDraft((current) => ({ ...current, quantity_required: Number(event.target.value) }))} /></label>
              <label><span>Confirmed</span><input className="input" type="number" min="0" value={requirementDraft.quantity_confirmed} onChange={(event) => setRequirementDraft((current) => ({ ...current, quantity_confirmed: Number(event.target.value) }))} /></label>
            </div>
            <div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy || !selectedPackage} onClick={() => void addRequirement()}>Add requirement</button><button className="btn btn-primary" disabled={busy || !selectedPackage} onClick={() => void assess()}>Assess package</button><button className="btn btn-primary" disabled={busy || assessments[0]?.status !== "READY"} onClick={() => void freeze()}>Freeze manifest</button></div>
          </article>
        </section>

        {selectedScenario ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Projected due sequence</h2><p>{selectedScenario.summary_json.inside_horizon ? `${selectedScenario.summary_json.inside_horizon} item(s) fall inside the scenario horizon.` : "Run the scenario to generate projections."}</p></div><StatusChip value={selectedScenario.status} /></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Aircraft</th><th>Task</th><th>Projected due</th><th>Trigger</th><th>Days</th><th>Rate</th><th>Status</th></tr></thead><tbody>{selectedScenario.items.slice(0, 500).map((item) => <tr key={item.id}><td>{item.registration}</td><td><strong>{item.task_code || item.program_item_id}</strong><small>{item.task_title}</small></td><td>{formatDate(item.projected_due_date)}</td><td>{item.projected_trigger || "—"}</td><td>{item.projected_days == null ? "—" : Number(item.projected_days).toFixed(1)}</td><td>{item.daily_hours} FH · {item.daily_cycles} FC/day</td><td><StatusChip value={item.status} /></td></tr>)}</tbody></table></div></section> : null}

        {selectedPackage ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>{selectedPackage.package_ref} readiness register</h2><p>{selectedPackage.aircraft_serial_number} · {selectedPackage.title}</p></div><StatusChip value={assessments[0]?.status || selectedPackage.readiness_status} /></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Category</th><th>Description</th><th>Reference</th><th>Required</th><th>Confirmed</th><th>Status</th><th /></tr></thead><tbody>{requirements.map((row) => <tr key={row.id}><td>{humanize(row.category)}</td><td>{row.description}</td><td>{row.reference || "—"}</td><td>{row.quantity_required}</td><td>{row.quantity_confirmed}</td><td><StatusChip value={row.status} /></td><td>{row.status !== "CONFIRMED" && row.status !== "WAIVED" ? <button className="btn btn-secondary" disabled={busy} onClick={() => void confirmRequirement(row)}>Confirm full</button> : null}</td></tr>)}</tbody></table></div><div className="readiness-history"><div><h3>Assessment history</h3>{assessments.map((row) => <p key={row.id}><StatusChip value={row.status} /> Version {row.version} · {formatDate(row.assessed_at)} · {row.blockers_json.length} blocker(s)</p>)}</div><div><h3>Freeze history</h3>{freezes.map((row) => <p key={row.id}><StatusChip value={row.status} /> Version {row.version} · <code>{row.manifest_hash.slice(0, 16)}…</code></p>)}</div></div></section> : null}
      </div>
    </DepartmentLayout>
  );
};

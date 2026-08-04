import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  getFleetPlanningOverview,
  listProgramItems,
  type FleetDueItem,
  type FleetPlanningOverview,
} from "../../services/maintenanceProgram";
import {
  applyAmpRevision,
  approveAmpRevision,
  createAmpRevision,
  getAmpCoverage,
  listAmpRevisions,
  type AmpCoverage,
  type AmpRevision,
} from "../../services/maintenanceRevisions";
import {
  createWorkPackage,
  getWorkPackageReadiness,
  listWorkPackages,
  updateWorkPackageStatus,
  type WorkPackage,
  type WorkPackageStatus,
} from "../../services/workPackages";
import {
  canEditFeature,
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";

const tabs: Array<{ label: string; path: string; feature: ModuleFeature }> = [
  { label: "Dashboard", path: "dashboard", feature: "planning.dashboard" },
  { label: "Utilisation", path: "utilisation-monitoring", feature: "planning.utilisation-monitoring" },
  { label: "Forecast", path: "forecast-due-list", feature: "planning.forecast-due-list" },
  { label: "AMP", path: "amp", feature: "planning.amp" },
  { label: "Task Library", path: "task-library", feature: "planning.task-library" },
  { label: "AD/SB/EO", path: "ad-sb-eo-control", feature: "planning.ad-sb-eo-control" },
  { label: "Work Packages", path: "work-packages", feature: "planning.work-packages" },
  { label: "Work Orders", path: "work-orders", feature: "planning.work-orders" },
  { label: "Deferments", path: "deferments", feature: "planning.deferments" },
  { label: "NR Review", path: "non-routine-review", feature: "planning.non-routine-review" },
  { label: "Watchlists", path: "watchlists", feature: "planning.watchlists" },
  { label: "Publication Review", path: "publication-review", feature: "planning.publication-review" },
  { label: "Compliance", path: "compliance-actions", feature: "planning.compliance-actions" },
];

const emptyOverview: FleetPlanningOverview = {
  generated_at: "",
  horizon_days: 180,
  summary: {
    fleet_aircraft: 0,
    utilisation_current: 0,
    utilisation_stale: 0,
    utilisation_missing: 0,
    overdue: 0,
    due_soon: 0,
    planned: 0,
    unbaselined: 0,
    due_within_horizon: 0,
  },
  utilisation: [],
  due_items: [],
};

const emptyCoverage: AmpCoverage = {
  generated_at: "",
  summary: {
    fleet_aircraft: 0,
    active_baselines: 0,
    missing_baselines: 0,
    active_requirements: 0,
    unbaselined_requirements: 0,
  },
  rows: [],
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

function formatNumber(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dueText(item: FleetDueItem): string {
  return [
    item.next_due_date ? formatDate(item.next_due_date) : null,
    item.next_due_hours != null ? `${formatNumber(item.next_due_hours)} FH` : null,
    item.next_due_cycles != null ? `${formatNumber(item.next_due_cycles, 0)} FC` : null,
  ].filter(Boolean).join(" · ") || "No baseline";
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const tone = normalized.includes("overdue") || normalized.includes("blocked") || normalized.includes("missing")
    ? "badge badge--danger"
    : normalized.includes("attention") || normalized.includes("review") || normalized.includes("due")
      ? "badge badge--warning"
      : normalized.includes("ready") || normalized.includes("approved") || normalized.includes("active") || normalized.includes("closed")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={tone}>{humanize(value)}</span>;
};

const Shell: React.FC<{
  title: string;
  subtitle: string;
  feature: ModuleFeature;
  actions?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, subtitle, feature, actions, children }) => {
  const { amoCode } = useParams();
  const location = useLocation();
  const currentUser = getCachedUser();
  const context = getContext();
  const visibleTabs = tabs.filter((tab) => canViewFeature(currentUser, tab.feature, context.department));

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning</p>
            <h1>{title}</h1>
            <p className="page-header__subtitle">{subtitle}</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(currentUser, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          {actions ? <div className="planning-phase-one__header-actions">{actions}</div> : null}
        </header>
        <nav className="planning-phase-one__tabs" aria-label="Planning pages">
          {visibleTabs.map((tab) => {
            const target = `/maintenance/${amoCode}/planning/${tab.path}`;
            return <Link key={target} className={location.pathname === target ? "is-active" : ""} to={target}>{tab.label}</Link>;
          })}
        </nav>
        {canViewFeature(currentUser, feature, context.department) ? children : (
          <section className="card planning-panel"><h2>Role visibility</h2><p className="text-muted">This planning control is not available to the current role.</p></section>
        )}
      </div>
    </DepartmentLayout>
  );
};

const MetricGrid: React.FC<{ items: Array<{ label: string; value: number | string; tone?: string }> }> = ({ items }) => (
  <section className="planning-metric-grid">
    {items.map((item) => <article key={item.label} className={`planning-metric-card ${item.tone || ""}`}><span className="planning-metric-card__label">{item.label}</span><strong>{item.value}</strong></article>)}
  </section>
);

function nextPackageStatus(status: WorkPackageStatus): WorkPackageStatus | null {
  const transitions: Partial<Record<WorkPackageStatus, WorkPackageStatus>> = {
    DRAFT: "REVIEW",
    REVIEW: "READY",
    READY: "RELEASED",
    RELEASED: "IN_PROGRESS",
    IN_PROGRESS: "CLOSED",
  };
  return transitions[status] || null;
}

export const PlanningWorkPackagesPage: React.FC = () => {
  const currentUser = getCachedUser();
  const context = getContext();
  const canPlan = canPerformAction(currentUser, "planning.plan-package", context.department);
  const [packages, setPackages] = useState<WorkPackage[]>([]);
  const [overview, setOverview] = useState<FleetPlanningOverview>(emptyOverview);
  const [selectedAircraft, setSelectedAircraft] = useState("");
  const [selectedItems, setSelectedItems] = useState<number[]>([]);
  const [title, setTitle] = useState("");
  const [checkType, setCheckType] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [packageRows, planningOverview] = await Promise.all([
      listWorkPackages(),
      getFleetPlanningOverview({ horizonDays: 180, limit: 5000 }),
    ]);
    setPackages(packageRows);
    setOverview(planningOverview);
    if (!selectedAircraft && planningOverview.utilisation[0]) {
      setSelectedAircraft(planningOverview.utilisation[0].aircraft_serial_number);
    }
  }, [selectedAircraft]);

  useEffect(() => { void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Planning data could not be loaded.")); }, [reload]);

  const dueItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return overview.due_items.filter((item) => {
      if (item.aircraft_serial_number !== selectedAircraft) return false;
      if (!needle) return true;
      return `${item.task_code || ""} ${item.task_title} ${item.ata_chapter || ""}`.toLowerCase().includes(needle);
    });
  }, [overview.due_items, query, selectedAircraft]);

  const selectedDueItems = useMemo(
    () => overview.due_items.filter((item) => selectedItems.includes(item.program_item_id)),
    [overview.due_items, selectedItems],
  );

  const createPackage = async () => {
    if (!selectedAircraft || !title.trim() || selectedItems.length === 0) {
      setMessage("Select an aircraft, enter a package title, and choose at least one maintenance requirement.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const created = await createWorkPackage({
        aircraft_serial_number: selectedAircraft,
        title: title.trim(),
        check_type: checkType || undefined,
        due_date: dueDate || undefined,
        source_horizon_days: 180,
        program_item_ids: selectedItems,
        description: `${selectedItems.length} maintenance requirement(s) selected from the fleet forecast.`,
      });
      setMessage(`${created.package_ref} created with ${created.orders.reduce((total, order) => total + order.task_count, 0)} task(s).`);
      setSelectedItems([]);
      setTitle("");
      setCheckType("");
      setDueDate("");
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Work package could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const movePackage = async (workPackage: WorkPackage) => {
    const next = nextPackageStatus(workPackage.status);
    if (!next) return;
    setBusy(true);
    setMessage(null);
    try {
      await updateWorkPackageStatus(workPackage.id, next, `Moved from ${workPackage.status} to ${next} in planning control.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Package status could not be updated.");
    } finally {
      setBusy(false);
    }
  };

  const checkReadiness = async (workPackage: WorkPackage) => {
    setBusy(true);
    try {
      const result = await getWorkPackageReadiness(workPackage.id);
      setMessage(`${workPackage.package_ref}: ${result.readiness_status}. ${[...result.blockers, ...result.warnings].join(" ") || "No blockers or warnings."}`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Readiness could not be calculated.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Work Packages" subtitle="Bundle forecast requirements into controlled packages and release only when readiness checks pass." feature="planning.work-packages" actions={<button className="btn btn-secondary" onClick={() => void reload()} disabled={busy}>Refresh</button>}>
      {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}
      <MetricGrid items={[
        { label: "Open packages", value: packages.filter((row) => !["CLOSED", "CANCELLED"].includes(row.status)).length },
        { label: "Blocked", value: packages.filter((row) => row.readiness_status === "BLOCKED").length, tone: "is-danger" },
        { label: "Ready", value: packages.filter((row) => row.readiness_status === "READY").length },
        { label: "Selected requirements", value: selectedItems.length },
      ]} />

      <section className="planning-phase-two__split">
        <article className="card planning-panel planning-phase-two__builder">
          <div className="planning-panel__header"><div><h2>Build a package</h2><p>Select one aircraft and the exact forecast requirements to include.</p></div></div>
          <div className="planning-phase-two__form-grid">
            <label><span>Aircraft</span><select className="input" value={selectedAircraft} onChange={(event) => { setSelectedAircraft(event.target.value); setSelectedItems([]); }}>{overview.utilisation.map((aircraft) => <option key={aircraft.aircraft_serial_number} value={aircraft.aircraft_serial_number}>{aircraft.registration} · {aircraft.model || aircraft.aircraft_serial_number}</option>)}</select></label>
            <label><span>Package title</span><input className="input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="A-check or planned maintenance visit" /></label>
            <label><span>Check type</span><input className="input" value={checkType} onChange={(event) => setCheckType(event.target.value)} placeholder="A, C, 200FH, Line" /></label>
            <label><span>Target due date</span><input className="input" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
          </div>
          <div className="planning-toolbar planning-toolbar--filters planning-phase-two__selector-toolbar"><div><h3>Available requirements</h3><p>{dueItems.length} requirement(s) for the selected aircraft.</p></div><input className="input planning-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search task or ATA" /></div>
          <div className="planning-phase-two__selection-list">
            {dueItems.map((item) => {
              const checked = selectedItems.includes(item.program_item_id);
              return <label key={item.api_id} className={`planning-phase-two__selection ${checked ? "is-selected" : ""}`}><input type="checkbox" checked={checked} onChange={() => setSelectedItems((current) => checked ? current.filter((id) => id !== item.program_item_id) : [...current, item.program_item_id])} /><span><strong>{item.task_code || "Uncoded task"}</strong><small>{item.task_title} · ATA {item.ata_chapter || "—"}</small></span><span><StatusChip value={item.status} /><small>{dueText(item)}</small></span></label>;
            })}
            {!dueItems.length ? <div className="planning-empty-state"><strong>No matching requirements</strong><span>Adjust the aircraft or task search.</span></div> : null}
          </div>
          <div className="planning-phase-two__builder-footer"><span>{selectedDueItems.length} selected · nearest due {selectedDueItems.map((item) => item.next_due_date).filter(Boolean).sort()[0] ? formatDate(selectedDueItems.map((item) => item.next_due_date).filter(Boolean).sort()[0] as string) : "not set"}</span><button className="btn btn-primary" disabled={!canPlan || busy || selectedItems.length === 0} onClick={() => void createPackage()}>{busy ? "Working…" : "Create work package"}</button></div>
        </article>

        <article className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Package control</h2><p>Readiness, workload, and controlled lifecycle.</p></div></div>
          <div className="planning-phase-two__package-list">
            {packages.map((workPackage) => {
              const blockers = workPackage.readiness_json?.blockers || [];
              const warnings = workPackage.readiness_json?.warnings || [];
              const metrics = workPackage.readiness_json?.metrics || {};
              const next = nextPackageStatus(workPackage.status);
              return <section key={workPackage.id} className="planning-phase-two__package"><div className="planning-phase-two__package-head"><div><strong>{workPackage.package_ref}</strong><span>{workPackage.title}</span></div><div><StatusChip value={workPackage.status} /><StatusChip value={workPackage.readiness_status} /></div></div><dl><div><dt>Aircraft</dt><dd>{workPackage.aircraft_serial_number}</dd></div><div><dt>Due</dt><dd>{formatDate(workPackage.due_date)}</dd></div><div><dt>Orders</dt><dd>{workPackage.orders.length}</dd></div><div><dt>Tasks</dt><dd>{metrics.tasks ?? workPackage.orders.reduce((total, order) => total + order.task_count, 0)}</dd></div><div><dt>Man-hours</dt><dd>{formatNumber(metrics.estimated_manhours ?? workPackage.orders.reduce((total, order) => total + order.estimated_manhours, 0))}</dd></div></dl>{blockers.length || warnings.length ? <div className="planning-phase-two__readiness-notes">{blockers.map((item) => <span key={item} className="is-blocker">{item}</span>)}{warnings.map((item) => <span key={item}>{item}</span>)}</div> : null}<div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => void checkReadiness(workPackage)}>Check readiness</button>{next ? <button className="btn" disabled={!canPlan || busy} onClick={() => void movePackage(workPackage)}>{humanize(next)}</button> : null}</div></section>;
            })}
            {!packages.length ? <div className="planning-empty-state"><strong>No work packages</strong><span>Create the first package from forecast requirements.</span></div> : null}
          </div>
        </article>
      </section>
    </Shell>
  );
};

export const PlanningAmpPage: React.FC = () => {
  const currentUser = getCachedUser();
  const context = getContext();
  const canEdit = canEditFeature(currentUser, "planning.amp", context.department);
  const [revisions, setRevisions] = useState<AmpRevision[]>([]);
  const [coverage, setCoverage] = useState<AmpCoverage>(emptyCoverage);
  const [programItems, setProgramItems] = useState<any[]>([]);
  const [templateCode, setTemplateCode] = useState("");
  const [revisionCode, setRevisionCode] = useState("");
  const [revisionTitle, setRevisionTitle] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [applyAircraft, setApplyAircraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [revisionRows, coverageData, taskRows] = await Promise.all([
      listAmpRevisions(),
      getAmpCoverage(),
      listProgramItems(),
    ]);
    setRevisions(revisionRows);
    setCoverage(coverageData);
    setProgramItems(taskRows);
    if (!applyAircraft && coverageData.rows[0]) setApplyAircraft(coverageData.rows[0].aircraft_serial_number);
    if (!templateCode && taskRows[0]) setTemplateCode(taskRows[0].template_code);
  }, [applyAircraft, templateCode]);

  useEffect(() => { void reload().catch((error) => setMessage(error instanceof Error ? error.message : "AMP control data could not be loaded.")); }, [reload]);

  const templateOptions = useMemo(
    () => Array.from(new Set(programItems.map((item) => item.template_code).filter(Boolean))).sort(),
    [programItems],
  );

  const createRevision = async () => {
    if (!templateCode || !revisionCode.trim() || !revisionTitle.trim()) {
      setMessage("Template, revision code, and title are required.");
      return;
    }
    setBusy(true);
    try {
      await createAmpRevision({
        template_code: templateCode,
        revision_code: revisionCode.trim(),
        title: revisionTitle.trim(),
        effective_date: effectiveDate || undefined,
        source_reference: sourceReference || undefined,
      });
      setRevisionCode("");
      setRevisionTitle("");
      setEffectiveDate("");
      setSourceReference("");
      setMessage("Draft AMP revision created.");
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Revision could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (revision: AmpRevision) => {
    setBusy(true);
    try {
      await approveAmpRevision(revision.id, "Approved from AMP revision control.");
      setMessage(`${revision.template_code} ${revision.revision_code} approved.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Revision could not be approved.");
    } finally {
      setBusy(false);
    }
  };

  const apply = async (revision: AmpRevision) => {
    if (!applyAircraft) {
      setMessage("Select an aircraft before applying the revision.");
      return;
    }
    setBusy(true);
    try {
      const result = await applyAmpRevision(revision.id, applyAircraft, "Applied from fleet AMP coverage control.");
      setMessage(`${revision.revision_code} applied to ${applyAircraft}: ${result.requirements_created} requirement(s) created, ${result.requirements_existing} retained.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Revision could not be applied.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="AMP / Maintenance Programme" subtitle="Control programme revisions, approvals, aircraft baselines, and requirement coverage." feature="planning.amp" actions={<button className="btn btn-secondary" onClick={() => void reload()} disabled={busy}>Refresh</button>}>
      {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}
      <MetricGrid items={[
        { label: "Fleet aircraft", value: coverage.summary.fleet_aircraft },
        { label: "Active baselines", value: coverage.summary.active_baselines },
        { label: "Missing baselines", value: coverage.summary.missing_baselines, tone: coverage.summary.missing_baselines ? "is-danger" : "" },
        { label: "Active requirements", value: coverage.summary.active_requirements },
        { label: "Unbaselined requirements", value: coverage.summary.unbaselined_requirements, tone: coverage.summary.unbaselined_requirements ? "is-warning" : "" },
      ]} />

      <section className="planning-phase-two__split planning-phase-two__split--amp">
        <article className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Revision register</h2><p>Draft, approve, supersede, and deploy controlled programme revisions.</p></div></div>
          <div className="planning-phase-two__form-grid planning-phase-two__form-grid--revision">
            <label><span>Template</span><select className="input" value={templateCode} onChange={(event) => setTemplateCode(event.target.value)}><option value="">Select template</option>{templateOptions.map((code) => <option key={code} value={code}>{code}</option>)}</select></label>
            <label><span>Revision code</span><input className="input" value={revisionCode} onChange={(event) => setRevisionCode(event.target.value)} placeholder="Rev 12" /></label>
            <label><span>Title</span><input className="input" value={revisionTitle} onChange={(event) => setRevisionTitle(event.target.value)} placeholder="Approved Maintenance Programme Revision" /></label>
            <label><span>Effective date</span><input className="input" type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></label>
            <label className="planning-phase-two__wide-field"><span>Source reference</span><input className="input" value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} placeholder="Approval letter, MPD revision, or internal change reference" /></label>
          </div>
          <button className="btn btn-primary" disabled={!canEdit || busy} onClick={() => void createRevision()}>Create draft revision</button>
          <div className="table-wrapper planning-phase-two__table-spacer"><table className="table table-striped planning-table"><thead><tr><th>Template</th><th>Revision</th><th>Status</th><th>Effective</th><th>Tasks</th><th>Aircraft</th><th>Actions</th></tr></thead><tbody>{revisions.map((revision) => <tr key={revision.id}><td><strong>{revision.template_code}</strong><small>{revision.title}</small></td><td>{revision.revision_code}</td><td><StatusChip value={revision.status} /></td><td>{formatDate(revision.effective_date)}</td><td>{revision.task_count}</td><td>{revision.active_aircraft_count}</td><td><div className="planning-inline-actions">{revision.status === "DRAFT" ? <button className="btn btn-secondary" disabled={!canEdit || busy} onClick={() => void approve(revision)}>Approve</button> : null}{revision.status === "APPROVED" ? <button className="btn" disabled={!canEdit || busy || !applyAircraft} onClick={() => void apply(revision)}>Apply to aircraft</button> : null}</div></td></tr>)}</tbody></table></div>
        </article>

        <article className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Aircraft baseline coverage</h2><p>Select an aircraft before applying an approved revision.</p></div></div>
          <label className="planning-phase-two__aircraft-picker"><span>Target aircraft</span><select className="input" value={applyAircraft} onChange={(event) => setApplyAircraft(event.target.value)}>{coverage.rows.map((row) => <option key={row.aircraft_serial_number} value={row.aircraft_serial_number}>{row.registration} · {row.model || row.aircraft_serial_number}</option>)}</select></label>
          <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Aircraft</th><th>Template / Rev</th><th>Baseline</th><th>Requirements</th><th>Missing anchors</th><th>Applied</th></tr></thead><tbody>{coverage.rows.map((row) => <tr key={row.aircraft_serial_number}><td><strong>{row.registration}</strong><small>{row.model || row.aircraft_serial_number}</small></td><td>{row.template_code || "—"}<small>{row.revision_code || "No controlled revision"}</small></td><td><StatusChip value={row.baseline_status} /></td><td>{row.active_requirement_count}</td><td className={row.unbaselined_requirement_count ? "planning-danger-text" : ""}>{row.unbaselined_requirement_count}</td><td>{formatDate(row.applied_at)}</td></tr>)}</tbody></table></div>
        </article>
      </section>
    </Shell>
  );
};

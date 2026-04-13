import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";
import { createTask, inspectTask, inspectWorkOrder, listTasksForWorkOrder, listWorkOrders, updateTask, updateWorkOrder } from "../services/workOrders";
import { listExecutionEvidence, listReleaseGates, upsertReleaseGate, uploadExecutionEvidence } from "../services/productionExecution";
import { listDeferrals, listFleetAircraft, listAD, listSB } from "../services/production";
import { listInspections, listNonRoutines, listPartToolRequests } from "../services/maintenance";
import { getDueList, listProgramItems, recomputeDueList } from "../services/maintenanceProgram";
import {
  createComplianceAction,
  createWatchlist,
  decidePublicationReview,
  getPlanningDashboard,
  getProductionDashboard,
  listComplianceActions,
  listPublicationReview,
  listWatchlists,
  runWatchlist,
  updateComplianceActionStatus,
} from "../services/planningProduction";
import {
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../utils/roleAccess";

type Dept = "planning" | "production";

type ShellTab = {
  label: string;
  path: string;
  feature: ModuleFeature;
};

const planningTabs: ShellTab[] = [
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

const productionTabs: ShellTab[] = [
  { label: "Dashboard", path: "dashboard", feature: "production.dashboard" },
  { label: "Control Board", path: "control-board", feature: "production.control-board" },
  { label: "Execution", path: "work-order-execution", feature: "production.work-order-execution" },
  { label: "Findings", path: "findings", feature: "production.findings" },
  { label: "Materials", path: "materials", feature: "production.materials" },
  { label: "Review", path: "review-inspection", feature: "production.review-inspection" },
  { label: "Release Prep", path: "release-prep", feature: "production.release-prep" },
  { label: "Compliance", path: "compliance-items", feature: "production.compliance-items" },
  { label: "Technical Records", path: "records", feature: "production.records.dashboard" },
];

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const cls = normalized.includes("overdue") || normalized.includes("blocked") ? "badge badge--danger" : normalized.includes("due") || normalized.includes("await") ? "badge badge--warning" : "badge badge--info";
  return <span className={cls}>{value}</span>;
};

const EmptyState: React.FC<{ text: string }> = ({ text }) => <div className="card"><p className="text-muted">{text}</p></div>;

const ModuleShell: React.FC<{
  title: string;
  department: Dept;
  children: React.ReactNode;
  subtitle?: string;
  feature?: ModuleFeature;
}> = ({ title, department, subtitle, children, feature }) => {
  const { amoCode } = useParams();
  const location = useLocation();
  const currentUser = getCachedUser();
  const ctx = getContext();
  const tabs = (department === "planning" ? planningTabs : productionTabs).filter((tab) =>
    canViewFeature(currentUser, tab.feature, ctx.department)
  );

  if (feature && !canViewFeature(currentUser, feature, ctx.department)) {
    return (
      <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment={department}>
        <div className="page planning-production-page">
          <header className="page-header"><h1>{title}</h1></header>
          <div className="card">
            <strong>Role visibility</strong>
            <p className="text-muted" style={{ marginTop: 8 }}>
              {department === "planning"
                ? "This planning surface is limited to planning control roles, with selected read access for supervisors on package and order coordination."
                : "This production surface is limited to production supervisory, execution, certifying, and technical-records roles according to the page."}
            </p>
          </div>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment={department}>
      <div className="page planning-production-page">
        <header className="page-header">
          <h1>{title}</h1>
          {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
          <p className="text-muted">Active role scope: {formatCapabilitiesForUi(currentUser, ctx.department).join(" · ") || "Unassigned"}</p>
        </header>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {tabs.map((tab) => {
            const target = tab.path === "records"
              ? `/maintenance/${amoCode}/${department}/records`
              : `/maintenance/${amoCode}/${department}/${tab.path}`;
            return (
              <Link key={target} className={`btn ${location.pathname === target ? "btn-primary" : "btn-secondary"}`} to={target}>
                {tab.label}
              </Link>
            );
          })}
        </div>
        {children}
      </div>
    </DepartmentLayout>
  );
};

const PlanningDashboardPageInner: React.FC = () => {
  const { amoCode } = useParams();
  const [data, setData] = useState<any>({ summary: {}, priority_items: [] });
  const [actions, setActions] = useState<any[]>([]);
  const [review, setReview] = useState<any[]>([]);

  useEffect(() => {
    getPlanningDashboard().then(setData).catch(() => setData({ summary: {}, priority_items: [] }));
    listComplianceActions().then(setActions).catch(() => setActions([]));
    listPublicationReview().then(setReview).catch(() => setReview([]));
  }, []);

  const cards = useMemo(
    () => [
      { label: "Due within horizon", value: data?.summary?.due_soon ?? 0, route: "forecast-due-list" },
      { label: "Overdue tasks", value: data?.summary?.overdue ?? 0, route: "forecast-due-list?status=overdue" },
      { label: "Open AD/SB reviews", value: data?.summary?.open_watchlist_reviews ?? 0, route: "publication-review" },
      { label: "Applicable unplanned compliance", value: actions.filter((a) => ["Under Review", "Planned"].includes(a.status)).length, route: "compliance-actions" },
      { label: "Open deferments", value: data?.summary?.open_deferrals ?? 0, route: "deferments" },
      { label: "Review decisions (7d)", value: review.filter((r) => r.review_status !== "Matched").length, route: "publication-review" },
    ],
    [actions, data, review],
  );

  return (
    <ModuleShell title="Planning Dashboard" department="planning" feature="planning.dashboard" subtitle="Fleet maintenance planning, surveillance, and package readiness.">
      <section className="metric-grid">{cards.map((c) => <Link key={c.label} to={`/maintenance/${amoCode}/planning/${c.route}`} className="metric-card" style={{ textDecoration: "none", color: "inherit" }}><div className="metric-label metric-card__label">{c.label}</div><div className="metric-value metric-card__value">{c.value}</div></Link>)}</section>
      <section className="card"><h3>Priority issues</h3><table className="table table-striped"><thead><tr><th>Type</th><th>Reference</th><th>Status</th><th /></tr></thead><tbody>{(data?.priority_items || []).map((item: any, idx: number) => <tr key={`${item.ref}-${idx}`}><td>{item.type}</td><td>{item.ref}</td><td><StatusChip value={item.status} /></td><td><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/${item.type === "Deferral" ? "deferments" : "compliance-actions"}`}>Open</Link></td></tr>)}</tbody></table></section>
    </ModuleShell>
  );
};

const PlanningOpsPage: React.FC<{ title: string; mode: ShellTab["path"]; feature: ModuleFeature }> = ({ title, mode, feature }) => {
  const { amoCode } = useParams();
  const currentUser = getCachedUser();
  const ctx = getContext();
  const [fleet, setFleet] = useState<any[]>([]);
  const [deferrals, setDeferrals] = useState<any[]>([]);
  const [ads, setAds] = useState<any[]>([]);
  const [sbs, setSbs] = useState<any[]>([]);
  const [programItems, setProgramItems] = useState<any[]>([]);
  const [dueRows, setDueRows] = useState<any[]>([]);
  const [workOrders, setWorkOrders] = useState<any[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    listFleetAircraft().then(setFleet).catch(() => setFleet([]));
    listDeferrals().then(setDeferrals).catch(() => setDeferrals([]));
    listAD().then(setAds).catch(() => setAds([]));
    listSB().then(setSbs).catch(() => setSbs([]));
    listProgramItems().then(setProgramItems).catch(() => setProgramItems([]));
    listWorkOrders({ limit: 200 }).then(setWorkOrders).catch(() => setWorkOrders([]));
  }, []);

  useEffect(() => {
    if (!fleet.length) return;
    Promise.all(fleet.slice(0, 6).map((a) => getDueList(a.serial_number).catch(() => null))).then((lists) => {
      const merged = lists.filter(Boolean).flatMap((l: any) => l.items || []);
      setDueRows(merged);
    });
  }, [fleet]);

  const canRecompute = canPerformAction(currentUser, "planning.recompute-due", ctx.department);
  const canPlanPackage = canPerformAction(currentUser, "planning.plan-package", ctx.department);
  const filteredDue = useMemo(() => dueRows.filter((r) => JSON.stringify(r).toLowerCase().includes(q.toLowerCase())), [dueRows, q]);

  const content: Record<string, React.ReactNode> = {
    "utilisation-monitoring": <div className="card"><h3>Fleet utilisation and due recalculation</h3><p className="text-muted">Use recompute to refresh due logic after utilisation updates.</p><table className="table table-striped"><thead><tr><th>Aircraft</th><th>Action</th></tr></thead><tbody>{fleet.map((f) => <tr key={f.serial_number}><td>{f.registration} · {f.serial_number}</td><td><button className="btn btn-secondary" disabled={!canRecompute} onClick={() => recomputeDueList(f.serial_number)}>Recompute due</button></td></tr>)}</tbody></table></div>,
    "forecast-due-list": <div className="card"><h3>Forecast / Due List</h3><input className="input" placeholder="Search due items" value={q} onChange={(e) => setQ(e.target.value)} /><table className="table table-striped"><thead><tr><th>Aircraft</th><th>Task</th><th>Status</th><th>Remaining (FH/FC/D)</th><th /></tr></thead><tbody>{filteredDue.map((r) => <tr key={r.api_id}><td>{r.aircraft_serial_number}</td><td>{r.task_code || r.title}</td><td><StatusChip value={r.status} /></td><td>{r.remaining_hours ?? "-"}/{r.remaining_cycles ?? "-"}/{r.remaining_days ?? "-"}</td><td><Link className="btn" to={`/maintenance/${amoCode}/planning/work-packages`} aria-disabled={!canPlanPackage} onClick={(event) => !canPlanPackage && event.preventDefault()}>Plan package</Link></td></tr>)}</tbody></table></div>,
    amp: <div className="card"><h3>AMP / Maintenance Programme</h3><table className="table table-striped"><thead><tr><th>Template</th><th>Task</th><th>ATA</th><th>Interval</th><th>Status</th></tr></thead><tbody>{programItems.map((p) => <tr key={p.id}><td>{p.template_code}</td><td>{p.task_code || p.title}</td><td>{p.ata_chapter || "-"}</td><td>{p.interval_hours || "-"} FH / {p.interval_cycles || "-"} FC / {p.interval_days || "-"} D</td><td><StatusChip value={p.status} /></td></tr>)}</tbody></table></div>,
    "task-library": <div className="card"><h3>Task Library</h3><table className="table table-striped"><thead><tr><th>Task</th><th>Description</th><th>ATA</th></tr></thead><tbody>{programItems.map((p) => <tr key={p.id}><td>{p.task_code || p.task_number || p.id}</td><td>{p.title}</td><td>{p.ata_chapter || "-"}</td></tr>)}</tbody></table></div>,
    "ad-sb-eo-control": <div className="card"><h3>AD/SB/EO Control</h3><table className="table table-striped"><thead><tr><th>Type</th><th>Reference</th><th>Status</th><th>Due</th></tr></thead><tbody>{[...ads, ...sbs].map((a: any) => <tr key={`${a.item_type}-${a.id}`}><td>{a.item_type}</td><td>{a.reference}</td><td><StatusChip value={a.status || "Open"} /></td><td>{a.next_due_date || "-"}</td></tr>)}</tbody></table></div>,
    "work-packages": <div className="card"><h3>Work Packages</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Aircraft</th><th>Status</th><th>Type</th></tr></thead><tbody>{workOrders.filter((w: any) => !!w.work_package_ref).map((w: any) => <tr key={w.id}><td>{w.wo_number}</td><td>{w.aircraft_serial_number}</td><td><StatusChip value={w.status} /></td><td>{w.wo_type}</td></tr>)}</tbody></table></div>,
    "work-orders": <div className="card"><h3>Planning Work Orders</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Aircraft</th><th>Status</th><th>Due</th></tr></thead><tbody>{workOrders.map((w: any) => <tr key={w.id}><td>{w.wo_number}</td><td>{w.aircraft_serial_number}</td><td><StatusChip value={w.status} /></td><td>{w.due_date || "-"}</td></tr>)}</tbody></table></div>,
    deferments: <div className="card"><h3>Deferments</h3><table className="table table-striped"><thead><tr><th>Tail</th><th>Defect</th><th>Expiry</th><th>Status</th></tr></thead><tbody>{deferrals.map((d: any) => <tr key={d.id}><td>{d.tail_id}</td><td>{d.defect_ref}</td><td>{d.expiry_at || "-"}</td><td><StatusChip value={d.status || "Open"} /></td></tr>)}</tbody></table></div>,
    "non-routine-review": <div className="card"><h3>Non-Routine Review Queue</h3><table className="table table-striped"><thead><tr><th>Tail</th><th>WO</th><th>Description</th><th>Status</th></tr></thead><tbody>{listNonRoutines().map((nr) => <tr key={nr.id}><td>{nr.tail}</td><td>{nr.woId}</td><td>{nr.description}</td><td><StatusChip value={nr.status} /></td></tr>)}</tbody></table></div>,
  };

  return <ModuleShell title={title} department="planning" feature={feature}>{content[mode] || <EmptyState text="Nothing to show." />}</ModuleShell>;
};

const WatchlistsPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const ctx = getContext();
  const [rows, setRows] = useState<any[]>([]);
  const canManage = canPerformAction(currentUser, "planning.manage-watchlists", ctx.department);
  const reload = () => listWatchlists().then(setRows).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);
  return <ModuleShell title="Watchlists" department="planning" feature="planning.watchlists"><div className="card" style={{ display: "grid", gap: 8, marginBottom: 12 }}><button className="btn btn-primary" disabled={!canManage} onClick={async()=>{ await createWatchlist({ name: `WL-${Date.now()}`, source_type: "AD", query: "status:open" } as any); reload(); }}>Create watchlist</button></div><section className="card"><table className="table table-striped"><thead><tr><th>Name</th><th>Source</th><th>Last run</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.source_type}</td><td>{row.last_run_at || "Never"}</td><td><button className="btn" disabled={!canManage} onClick={async()=>{ await runWatchlist(row.id); reload(); }}>Run</button></td></tr>)}</tbody></table></section></ModuleShell>;
};

const PublicationReviewPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const ctx = getContext();
  const [rows, setRows] = useState<any[]>([]);
  const canDecide = canPerformAction(currentUser, "planning.decide-publication", ctx.department);
  const reload = () => listPublicationReview().then(setRows).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);
  return <ModuleShell title="Publication Review" department="planning" feature="planning.publication-review"><section className="card"><table className="table table-striped"><thead><tr><th>Ref</th><th>Status</th><th>Match</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.reference || row.id}</td><td>{row.review_status || "Pending"}</td><td>{row.match_status || "-"}</td><td><button className="btn" disabled={!canDecide} onClick={async()=>{ await decidePublicationReview(row.id,{ review_status: "Matched" } as any); reload(); }}>Mark matched</button></td></tr>)}</tbody></table></section></ModuleShell>;
};

const ComplianceActionsPageInner: React.FC = () => {
  const currentUser = getCachedUser();
  const ctx = getContext();
  const [rows, setRows] = useState<any[]>([]);
  const canManage = canPerformAction(currentUser, "planning.update-compliance", ctx.department);
  const reload = () => listComplianceActions().then(setRows).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);
  return <ModuleShell title="Compliance Actions" department="planning" feature="planning.compliance-actions"><div className="card" style={{ marginBottom: 12 }}><button className="btn btn-primary" disabled={!canManage} onClick={async()=>{ await createComplianceAction({ decision: "Evaluate", status: "Planned" } as any); reload(); }}>Create compliance action</button></div><section className="card"><table className="table table-striped"><thead><tr><th>ID</th><th>Decision</th><th>Status</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.id}</td><td>{row.decision}</td><td><StatusChip value={row.status} /></td><td><button className="btn" disabled={!canManage} onClick={async()=>{ await updateComplianceActionStatus(row.id,{ status: "In Work" } as any); reload(); }}>Set In Work</button></td></tr>)}</tbody></table></section></ModuleShell>;
};

const ProductionOpsPage: React.FC<{ title: string; mode: string; feature: ModuleFeature }> = ({ title, mode, feature }) => {
  const { amoCode } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = getCachedUser();
  const ctx = getContext();
  const [summary, setSummary] = useState<any>({ summary: {}, bottlenecks: [] });
  const [wos, setWos] = useState<any[]>([]);
  const [tasksByWo, setTasksByWo] = useState<Record<number, any[]>>({});
  const [inspections, setInspections] = useState<any[]>([]);
  const [parts, setParts] = useState<any[]>([]);
  const [nrs, setNrs] = useState<any[]>([]);
  const [actions, setActions] = useState<any[]>([]);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [releaseGates, setReleaseGates] = useState<any[]>([]);

  const reload = () => {
    getProductionDashboard().then(setSummary).catch(() => setSummary({ summary: {}, bottlenecks: [] }));
    listWorkOrders({ limit: 250 }).then(async (rows) => {
      setWos(rows);
      const pairs = await Promise.all(rows.slice(0, 30).map(async (w: any) => [w.id, await listTasksForWorkOrder(w.id).catch(() => [])] as const));
      setTasksByWo(Object.fromEntries(pairs));
    }).catch(() => setWos([]));
    setInspections(listInspections());
    setParts(listPartToolRequests());
    setNrs(listNonRoutines());
    listComplianceActions().then(setActions).catch(() => setActions([]));
    listExecutionEvidence().then(setEvidence).catch(() => setEvidence([]));
    listReleaseGates().then(setReleaseGates).catch(() => setReleaseGates([]));
  };

  useEffect(() => { reload(); }, [location.key]);

  const canManageBoard = canPerformAction(currentUser, "production.manage-board", ctx.department);
  const canExecute = canPerformAction(currentUser, "production.execute-work", ctx.department);
  const canRequestParts = canPerformAction(currentUser, "production.request-parts", ctx.department);
  const canPerformReview = canPerformAction(currentUser, "production.perform-review", ctx.department);
  const canPrepareRelease = canPerformAction(currentUser, "production.prepare-release", ctx.department);
  const gateByWo = useMemo(() => Object.fromEntries(releaseGates.map((g: any) => [g.work_order_id, g])), [releaseGates]);

  const dashboards = <><section className="metric-grid">{Object.entries(summary.summary || {}).map(([k, v]) => <div key={k} className="metric-card"><div className="metric-label">{k.replace(/_/g, " ")}</div><div className="metric-value">{String(v)}</div></div>)}</section><section className="card"><h3>Live bottlenecks</h3><table className="table table-striped"><thead><tr><th>Issue</th><th>Count</th><th /></tr></thead><tbody>{(summary.bottlenecks || []).map((b: any, i: number) => <tr key={i}><td>{b.name}</td><td>{b.count}</td><td><button className="btn" onClick={() => navigate(`/maintenance/${amoCode}/production/${b.route?.split("/").pop() || "dashboard"}`)}>Open</button></td></tr>)}</tbody></table></section></>;

  const sections: Record<string, React.ReactNode> = {
    dashboard: dashboards,
    "control-board": <section className="card"><h3>Production Control Board</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Aircraft</th><th>Status</th><th>Due</th><th>Blocked</th><th>Release gate</th></tr></thead><tbody>{wos.map((w) => <tr key={w.id}><td>{w.wo_number}</td><td>{w.aircraft_serial_number}</td><td><StatusChip value={w.status} /></td><td>{w.due_date || "-"}</td><td>{parts.some((p) => p.woId === w.id && p.status === "REQUESTED") ? <StatusChip value="Awaiting parts" /> : "No"}</td><td><StatusChip value={gateByWo[w.id]?.status || "Draft"} /></td></tr>)}</tbody></table>{!canManageBoard ? <p className="text-muted">Only supervisors can change board state and package flow.</p> : null}</section>,
    "work-order-execution": <section className="card"><h3>Work Order Execution (persisted)</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Task</th><th>Status</th><th>Actions</th><th>Evidence</th></tr></thead><tbody>{wos.map((w) => (tasksByWo[w.id] || []).slice(0, 6).map((t: any) => <tr key={`${w.id}-${t.id}`}><td>{w.wo_number}</td><td>{t.title}</td><td><StatusChip value={t.status || "PLANNED"} /></td><td><div style={{display:"flex",gap:6}}><button className="btn" disabled={!canExecute} onClick={async ()=>{await updateTask(t.id,{status:"IN_PROGRESS",last_known_updated_at:t.updated_at}); await updateWorkOrder(w.id,{status:"IN_PROGRESS"}); reload();}}>Start</button><button className="btn" disabled={!canExecute} onClick={async ()=>{await updateTask(t.id,{status:"COMPLETED",last_known_updated_at:t.updated_at}); reload();}}>Complete</button><button className="btn" disabled={!canPerformReview} onClick={async ()=>{await inspectTask(t.id,{signed_flag:true,notes:"Task reviewed"}); reload();}}>Inspect</button></div></td><td><label className="btn btn-secondary" aria-disabled={!canExecute}><input type="file" style={{display:"none"}} disabled={!canExecute} onChange={async (e)=>{const f=e.target.files?.[0]; if(!f) return; await uploadExecutionEvidence(w.id,f,t.id,"Task evidence"); reload();}}/>Upload</label></td></tr>))}</tbody></table></section>,
    findings: <section className="card"><h3>Findings / Non-routines (persisted)</h3><div style={{display:"flex",gap:8,marginBottom:8}}><button className="btn" disabled={!canExecute} onClick={async ()=>{const w=wos[0]; if(!w) return; await createTask(w.id,{title:"Raised non-routine finding",category:"DEFECT",origin_type:"NON_ROUTINE",priority:"HIGH"}); reload();}}>Raise non-routine task</button></div><table className="table table-striped"><thead><tr><th>ID</th><th>WO</th><th>Description</th><th>Status</th></tr></thead><tbody>{nrs.map((nr) => <tr key={nr.id}><td>{nr.id}</td><td>{nr.woId}</td><td>{nr.description}</td><td><StatusChip value={nr.status} /></td></tr>)}</tbody></table></section>,
    materials: <section className="card"><h3>Materials / Parts visibility</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Item</th><th>Qty</th><th>Status</th></tr></thead><tbody>{parts.map((p) => <tr key={p.id}><td>{p.woId}</td><td>{p.description}</td><td>{p.qty}</td><td><StatusChip value={p.status} /></td></tr>)}</tbody></table>{!canRequestParts ? <p className="text-muted">Only execution, certifying, supervisory, and stores roles can request or update parts.</p> : null}</section>,
    "review-inspection": <section className="card"><h3>Review and inspection</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Type</th><th>Status</th><th>Hold</th><th /></tr></thead><tbody>{inspections.map((i) => <tr key={i.id}><td>{i.woId}</td><td>{i.inspectionType}</td><td><StatusChip value={i.status} /></td><td>{i.holdFlag ? "Yes" : "No"}</td><td><button className="btn" disabled={!canPerformReview} onClick={async()=>{const wo=wos.find((x)=>x.id===i.woId); if(!wo) return; await inspectWorkOrder(wo.id,{signed_flag:true,notes:"Inspection complete"}); reload();}}>Sign inspection</button></td></tr>)}</tbody></table></section>,
    "release-prep": <section className="card"><h3>Release preparation gate (persisted)</h3><table className="table table-striped"><thead><tr><th>WO</th><th>Execution status</th><th>Evidence</th><th>Gate</th><th>Actions</th></tr></thead><tbody>{wos.map((w) => {const gate=gateByWo[w.id]; const evCount=evidence.filter((e)=>e.work_order_id===w.id).length; return <tr key={w.id}><td>{w.wo_number}</td><td><StatusChip value={w.status} /></td><td>{evCount}</td><td><StatusChip value={gate?.status || "Draft"} /></td><td><div style={{display:"flex",gap:6}}><button className="btn" disabled={!canPrepareRelease} onClick={async()=>{await upsertReleaseGate({work_order_id:w.id,status:"Ready",blockers_json:[],readiness_notes:"Ready for certification"}); reload();}}>Mark ready</button><button className="btn" disabled={!canPrepareRelease} onClick={async()=>{await upsertReleaseGate({work_order_id:w.id,status:"Awaiting Certification",sign_off:true}); reload();}}>Sign-off</button><button className="btn" disabled={!canPrepareRelease} onClick={async()=>{await upsertReleaseGate({work_order_id:w.id,status:"Handed to Records",handed_to_records:true,sign_off:true}); await updateWorkOrder(w.id,{status:"INSPECTED"}); reload();}}>Handoff records</button></div></td></tr>})}</tbody></table></section>,
    "compliance-items": <section className="card"><h3>Compliance-linked work items</h3><table className="table table-striped"><thead><tr><th>Action</th><th>Status</th><th>WO Ref</th><th>Package</th><th>Execution</th></tr></thead><tbody>{actions.map((a) => <tr key={a.id}><td>CA-{a.id} · {a.decision}</td><td><StatusChip value={a.status} /></td><td>{a.work_order_ref || "-"}</td><td>{a.package_ref || "-"}</td><td><button className="btn" disabled={!canManageBoard} onClick={async()=>{await updateComplianceActionStatus(a.id,{status:"In Work"}); reload();}}>Set In Work</button></td></tr>)}</tbody></table></section>,
  };

  return <ModuleShell title={title} department="production" feature={feature}>{sections[mode] || dashboards}</ModuleShell>;
};

export const PlanningDashboardPage = PlanningDashboardPageInner;
export const PlanningUtilisationPage = () => <PlanningOpsPage title="Utilisation Monitoring" mode="utilisation-monitoring" feature="planning.utilisation-monitoring" />;
export const PlanningForecastPage = () => <PlanningOpsPage title="Forecast / Due List" mode="forecast-due-list" feature="planning.forecast-due-list" />;
export const PlanningAmpPage = () => <PlanningOpsPage title="AMP / Maintenance Programme" mode="amp" feature="planning.amp" />;
export const PlanningTaskLibraryPage = () => <PlanningOpsPage title="Task Library" mode="task-library" feature="planning.task-library" />;
export const PlanningAdSbPage = () => <PlanningOpsPage title="AD / SB / EO Control" mode="ad-sb-eo-control" feature="planning.ad-sb-eo-control" />;
export const PlanningWorkPackagesPage = () => <PlanningOpsPage title="Work Packages" mode="work-packages" feature="planning.work-packages" />;
export const PlanningWorkOrdersPage = () => <PlanningOpsPage title="Planning Work Orders" mode="work-orders" feature="planning.work-orders" />;
export const PlanningDefermentsPage = () => <PlanningOpsPage title="Deferments" mode="deferments" feature="planning.deferments" />;
export const PlanningNonRoutinePage = () => <PlanningOpsPage title="Non-Routine Review" mode="non-routine-review" feature="planning.non-routine-review" />;
export const WatchlistsPage = WatchlistsPageInner;
export const PublicationReviewPage = PublicationReviewPageInner;
export const ComplianceActionsPage = ComplianceActionsPageInner;

export const ProductionDashboardPage = () => <ProductionOpsPage title="Production Dashboard" mode="dashboard" feature="production.dashboard" />;
export const ProductionControlBoardPage = () => <ProductionOpsPage title="Production Control Board" mode="control-board" feature="production.control-board" />;
export const ProductionExecutionPage = () => <ProductionOpsPage title="Work Order Execution" mode="work-order-execution" feature="production.work-order-execution" />;
export const ProductionFindingsPage = () => <ProductionOpsPage title="Findings / Non-Routines" mode="findings" feature="production.findings" />;
export const ProductionMaterialsPage = () => <ProductionOpsPage title="Materials / Parts" mode="materials" feature="production.materials" />;
export const ProductionReviewInspectionPage = () => <ProductionOpsPage title="Review and Inspection" mode="review-inspection" feature="production.review-inspection" />;
export const ProductionReleasePrepPage = () => <ProductionOpsPage title="Release Preparation" mode="release-prep" feature="production.release-prep" />;
export const ProductionComplianceItemsPage = () => <ProductionOpsPage title="Production Compliance Items" mode="compliance-items" feature="production.compliance-items" />;

export const PlanningProductionPage: React.FC = () => <PlanningDashboardPageInner />;

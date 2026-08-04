import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  createTask,
  inspectTask,
  inspectWorkOrder,
  listTasksForWorkOrder,
  listWorkOrders,
  updateTask,
  updateWorkOrder,
} from "../../services/workOrders";
import {
  listExecutionEvidence,
  listReleaseGates,
  upsertReleaseGate,
  uploadExecutionEvidence,
} from "../../services/productionExecution";
import { listInspections, listNonRoutines, listPartToolRequests } from "../../services/maintenance";
import {
  getProductionDashboard,
  listComplianceActions,
  updateComplianceActionStatus,
} from "../../services/planningProduction";
import {
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";

type ProductionTab = {
  label: string;
  path: string;
  feature: ModuleFeature;
};

const productionTabs: ProductionTab[] = [
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

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const cssClass = normalized.includes("overdue") || normalized.includes("blocked")
    ? "badge badge--danger"
    : normalized.includes("due") || normalized.includes("await")
      ? "badge badge--warning"
      : normalized.includes("ready") || normalized.includes("complete")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={cssClass}>{humanize(value)}</span>;
};

const EmptyState: React.FC<{ text: string }> = ({ text }) => (
  <div className="planning-empty-state"><strong>No records</strong><span>{text}</span></div>
);

const ProductionShell: React.FC<{
  title: string;
  children: React.ReactNode;
  subtitle?: string;
  feature?: ModuleFeature;
}> = ({ title, subtitle, children, feature }) => {
  const { amoCode } = useParams();
  const location = useLocation();
  const currentUser = getCachedUser();
  const context = getContext();
  const tabs = productionTabs.filter((tab) => canViewFeature(currentUser, tab.feature, context.department));

  if (feature && !canViewFeature(currentUser, feature, context.department)) {
    return (
      <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="production">
        <div className="page planning-production-page planning-phase-one">
          <header className="page-header"><h1>{title}</h1></header>
          <section className="card"><strong>Role visibility</strong><p className="text-muted planning-copy-spacer">This production surface is not available to the current role assignment.</p></section>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="production">
      <div className="page planning-production-page planning-phase-one">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Production Control</p>
            <h1>{title}</h1>
            {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(currentUser, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
        </header>

        <nav className="planning-phase-one__tabs" aria-label="Production pages">
          {tabs.map((tab) => {
            const target = tab.path === "records"
              ? `/maintenance/${amoCode}/production/records`
              : `/maintenance/${amoCode}/production/${tab.path}`;
            const active = location.pathname === target || location.pathname.startsWith(`${target}/`);
            return <Link key={target} className={active ? "is-active" : ""} to={target}>{tab.label}</Link>;
          })}
        </nav>
        {children}
      </div>
    </DepartmentLayout>
  );
};

const MetricGrid: React.FC<{ items: Array<{ label: string; value: number | string }> }> = ({ items }) => (
  <section className="planning-metric-grid">
    {items.map((item) => <article key={item.label} className="planning-metric-card"><span className="planning-metric-card__label">{item.label}</span><strong>{item.value}</strong></article>)}
  </section>
);

const SimpleTable: React.FC<{ title: string; subtitle?: string; headers: string[]; rows: React.ReactNode[][] }> = ({ title, subtitle, headers, rows }) => (
  <section className="card planning-panel">
    <div className="planning-panel__header"><div><h2>{title}</h2><p>{subtitle || `${rows.length.toLocaleString()} record(s)`}</p></div></div>
    {rows.length ? (
      <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>
    ) : <EmptyState text="No records are available yet." />}
  </section>
);

const ProductionOpsPage: React.FC<{ title: string; mode: string; feature: ModuleFeature }> = ({ title, mode, feature }) => {
  const { amoCode } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = getCachedUser();
  const context = getContext();
  const [summary, setSummary] = useState<any>({ summary: {}, bottlenecks: [] });
  const [workOrders, setWorkOrders] = useState<any[]>([]);
  const [tasksByWorkOrder, setTasksByWorkOrder] = useState<Record<number, any[]>>({});
  const [inspections, setInspections] = useState<any[]>([]);
  const [parts, setParts] = useState<any[]>([]);
  const [nonRoutines, setNonRoutines] = useState<any[]>([]);
  const [complianceActions, setComplianceActions] = useState<any[]>([]);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [releaseGates, setReleaseGates] = useState<any[]>([]);

  const reload = useCallback(() => {
    void getProductionDashboard().then(setSummary).catch(() => setSummary({ summary: {}, bottlenecks: [] }));
    void listWorkOrders({ limit: 250 }).then(async (rows) => {
      setWorkOrders(rows);
      const pairs = await Promise.all(rows.slice(0, 30).map(async (workOrder: any) => [workOrder.id, await listTasksForWorkOrder(workOrder.id).catch(() => [])] as const));
      setTasksByWorkOrder(Object.fromEntries(pairs));
    }).catch(() => setWorkOrders([]));
    setInspections(listInspections());
    setParts(listPartToolRequests());
    setNonRoutines(listNonRoutines());
    void listComplianceActions().then(setComplianceActions).catch(() => setComplianceActions([]));
    void listExecutionEvidence().then(setEvidence).catch(() => setEvidence([]));
    void listReleaseGates().then(setReleaseGates).catch(() => setReleaseGates([]));
  }, []);

  useEffect(() => { reload(); }, [location.key, reload]);

  const canManageBoard = canPerformAction(currentUser, "production.manage-board", context.department);
  const canExecute = canPerformAction(currentUser, "production.execute-work", context.department);
  const canRequestParts = canPerformAction(currentUser, "production.request-parts", context.department);
  const canPerformReview = canPerformAction(currentUser, "production.perform-review", context.department);
  const canPrepareRelease = canPerformAction(currentUser, "production.prepare-release", context.department);
  const gateByWorkOrder = useMemo(() => Object.fromEntries(releaseGates.map((gate: any) => [gate.work_order_id, gate])), [releaseGates]);

  const dashboard = (
    <>
      <MetricGrid items={Object.entries(summary.summary || {}).map(([key, value]) => ({ label: humanize(key), value: String(value) }))} />
      <SimpleTable title="Live bottlenecks" headers={["Issue", "Count", "Action"]} rows={(summary.bottlenecks || []).map((item: any) => [item.name, item.count, <button className="btn btn-secondary" onClick={() => navigate(`/maintenance/${amoCode}/production/${item.route?.split("/").pop() || "dashboard"}`)}>Open</button>])} />
    </>
  );

  const controlBoardRows = workOrders.map((workOrder) => [
    workOrder.wo_number,
    workOrder.aircraft_serial_number,
    <StatusChip value={workOrder.status} />,
    workOrder.due_date || "—",
    parts.some((part) => part.woId === workOrder.id && part.status === "REQUESTED") ? <StatusChip value="Awaiting parts" /> : "No",
    <StatusChip value={gateByWorkOrder[workOrder.id]?.status || "Draft"} />,
  ]);

  const sections: Record<string, React.ReactNode> = {
    dashboard,
    "control-board": <SimpleTable title="Production control board" subtitle="Work status, constraints, and release readiness." headers={["WO", "Aircraft", "Status", "Due", "Material block", "Release gate"]} rows={controlBoardRows} />,
    "work-order-execution": (
      <section className="card planning-panel">
        <div className="planning-panel__header"><div><h2>Work order execution</h2><p>Persisted task state, inspection, and evidence.</p></div></div>
        <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>WO</th><th>Task</th><th>Status</th><th>Actions</th><th>Evidence</th></tr></thead><tbody>{workOrders.flatMap((workOrder) => (tasksByWorkOrder[workOrder.id] || []).slice(0, 6).map((task: any) => <tr key={`${workOrder.id}-${task.id}`}><td>{workOrder.wo_number}</td><td>{task.title}</td><td><StatusChip value={task.status || "PLANNED"} /></td><td><div className="planning-inline-actions"><button className="btn" disabled={!canExecute} onClick={() => void updateTask(task.id, { status: "IN_PROGRESS", last_known_updated_at: task.updated_at }).then(() => updateWorkOrder(workOrder.id, { status: "IN_PROGRESS" })).then(reload)}>Start</button><button className="btn" disabled={!canExecute} onClick={() => void updateTask(task.id, { status: "COMPLETED", last_known_updated_at: task.updated_at }).then(reload)}>Complete</button><button className="btn" disabled={!canPerformReview} onClick={() => void inspectTask(task.id, { signed_flag: true, notes: "Task reviewed" }).then(reload)}>Inspect</button></div></td><td><label className="btn btn-secondary" aria-disabled={!canExecute}><input type="file" hidden disabled={!canExecute} onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; void uploadExecutionEvidence(workOrder.id, file, task.id, "Task evidence").then(reload); }} />Upload</label></td></tr>))}</tbody></table></div>
      </section>
    ),
    findings: (
      <section className="card planning-panel">
        <div className="planning-panel__header"><div><h2>Findings / non-routines</h2><p>Raised work outside the original package scope.</p></div><button className="btn btn-primary" disabled={!canExecute} onClick={() => { const workOrder = workOrders[0]; if (!workOrder) return; void createTask(workOrder.id, { title: "Raised non-routine finding", category: "DEFECT", origin_type: "NON_ROUTINE", priority: "HIGH" }).then(reload); }}>Raise non-routine</button></div>
        <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>ID</th><th>WO</th><th>Description</th><th>Status</th></tr></thead><tbody>{nonRoutines.map((item) => <tr key={item.id}><td>{item.id}</td><td>{item.woId}</td><td>{item.description}</td><td><StatusChip value={item.status} /></td></tr>)}</tbody></table></div>
      </section>
    ),
    materials: <><SimpleTable title="Materials / parts visibility" headers={["WO", "Item", "Qty", "Status"]} rows={parts.map((item) => [item.woId, item.description, item.qty, <StatusChip value={item.status} />])} />{!canRequestParts ? <p className="text-muted">The current role has read-only material visibility.</p> : null}</>,
    "review-inspection": <SimpleTable title="Review and inspection" headers={["WO", "Type", "Status", "Hold", "Action"]} rows={inspections.map((item) => [item.woId, item.inspectionType, <StatusChip value={item.status} />, item.holdFlag ? "Yes" : "No", <button className="btn btn-secondary" disabled={!canPerformReview} onClick={() => { const workOrder = workOrders.find((row) => row.id === item.woId); if (!workOrder) return; void inspectWorkOrder(workOrder.id, { signed_flag: true, notes: "Inspection complete" }).then(reload); }}>Sign inspection</button>])} />,
    "release-prep": (
      <section className="card planning-panel">
        <div className="planning-panel__header"><div><h2>Release preparation gate</h2><p>Evidence, readiness, certification, and records handover.</p></div></div>
        <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>WO</th><th>Execution status</th><th>Evidence</th><th>Gate</th><th>Actions</th></tr></thead><tbody>{workOrders.map((workOrder) => { const gate = gateByWorkOrder[workOrder.id]; const evidenceCount = evidence.filter((item) => item.work_order_id === workOrder.id).length; return <tr key={workOrder.id}><td>{workOrder.wo_number}</td><td><StatusChip value={workOrder.status} /></td><td>{evidenceCount}</td><td><StatusChip value={gate?.status || "Draft"} /></td><td><div className="planning-inline-actions"><button className="btn" disabled={!canPrepareRelease} onClick={() => void upsertReleaseGate({ work_order_id: workOrder.id, status: "Ready", blockers_json: [], readiness_notes: "Ready for certification" }).then(reload)}>Mark ready</button><button className="btn" disabled={!canPrepareRelease} onClick={() => void upsertReleaseGate({ work_order_id: workOrder.id, status: "Awaiting Certification", sign_off: true }).then(reload)}>Sign-off</button><button className="btn" disabled={!canPrepareRelease} onClick={() => void upsertReleaseGate({ work_order_id: workOrder.id, status: "Handed to Records", handed_to_records: true, sign_off: true }).then(() => updateWorkOrder(workOrder.id, { status: "INSPECTED" })).then(reload)}>Handoff</button></div></td></tr>; })}</tbody></table></div>
      </section>
    ),
    "compliance-items": <SimpleTable title="Compliance-linked work items" headers={["Action", "Status", "WO", "Package", "Action"]} rows={complianceActions.map((item) => [`CA-${item.id} · ${item.decision}`, <StatusChip value={item.status} />, item.work_order_ref || "—", item.package_ref || "—", <button className="btn btn-secondary" disabled={!canManageBoard} onClick={() => void updateComplianceActionStatus(item.id, { status: "In Work" }).then(reload)}>Set in work</button>])} />,
  };

  return <ProductionShell title={title} feature={feature} subtitle={mode === "dashboard" ? "Operational work, constraints, execution evidence, and release readiness." : undefined}>{sections[mode] || dashboard}</ProductionShell>;
};

export const ProductionDashboardPage = () => <ProductionOpsPage title="Production Dashboard" mode="dashboard" feature="production.dashboard" />;
export const ProductionControlBoardPage = () => <ProductionOpsPage title="Production Control Board" mode="control-board" feature="production.control-board" />;
export const ProductionExecutionPage = () => <ProductionOpsPage title="Work Order Execution" mode="work-order-execution" feature="production.work-order-execution" />;
export const ProductionFindingsPage = () => <ProductionOpsPage title="Findings / Non-Routines" mode="findings" feature="production.findings" />;
export const ProductionMaterialsPage = () => <ProductionOpsPage title="Materials / Parts" mode="materials" feature="production.materials" />;
export const ProductionReviewInspectionPage = () => <ProductionOpsPage title="Review and Inspection" mode="review-inspection" feature="production.review-inspection" />;
export const ProductionReleasePrepPage = () => <ProductionOpsPage title="Release Preparation" mode="release-prep" feature="production.release-prep" />;
export const ProductionComplianceItemsPage = () => <ProductionOpsPage title="Production Compliance Items" mode="compliance-items" feature="production.compliance-items" />;

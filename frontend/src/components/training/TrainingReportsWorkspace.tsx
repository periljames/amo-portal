import React, { useState } from "react";
import { Clock3, Download, FileBarChart, Plus, RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import Drawer from "../shared/Drawer";
import { listTrainingEvents } from "../../services/training";
import { createTrainingReportDefinition, downloadTrainingOperatingReport, downloadTrainingReportJob, listTrainingBudgets, listTrainingPlanSummaries, listTrainingReportDefinitions, listTrainingReportJobs, queueTrainingReportJob } from "../../services/trainingOperating";

type Props = { canManage: boolean; canExport: boolean };
const BUILTINS = [
  { code: "PEOPLE_COMPLIANCE", name: "People compliance register", description: "Complete current, due, overdue and missing population." },
  { code: "TRAINING_PLAN", name: "Training plan", description: "Approved revisions, obligations and source expiry manifest." },
  { code: "ATTENDANCE", name: "Attendance register", description: "Governed QMS/36 participant and certification evidence." },
  { code: "ASSESSMENTS", name: "Assessment and remediation", description: "Cases, criteria, decisions and corrective work." },
  { code: "AUTHORIZATIONS", name: "Authorization readiness", description: "Gates, committee decisions and issued privileges." },
  { code: "CERTIFICATES", name: "Certificate register", description: "Issue, revoke, supersede and public status history." },
  { code: "BUDGET", name: "Budget variance", description: "Planned, approved, committed and actual amounts with FX evidence." },
  { code: "AUDIT", name: "Training audit manifest", description: "Actor, transition, timestamp and controlled-source trail." },
] as const;

const TrainingReportsWorkspace: React.FC<Props> = ({ canManage, canExport }) => {
  const client = useQueryClient();
  const [definitionOpen, setDefinitionOpen] = useState(false);
  const [definition, setDefinition] = useState({ code: "", name: "", description: "", dataset: "PEOPLE_COMPLIANCE", allowed_formats: ["PDF", "XLSX"], retention_days: 365 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const definitions = useQuery({ queryKey: ["training", "report-definitions"], queryFn: listTrainingReportDefinitions });
  const jobs = useQuery({ queryKey: ["training", "report-jobs"], queryFn: () => listTrainingReportJobs() });
  const plans = useQuery({ queryKey: ["training", "plan-summaries"], queryFn: () => listTrainingPlanSummaries() });
  const budgets = useQuery({ queryKey: ["training", "budgets"], queryFn: listTrainingBudgets });
  const events = useQuery({ queryKey: ["training", "report-events"], queryFn: () => listTrainingEvents({ limit: 100 }) });

  const queue = async (code: string, format: "PDF" | "XLSX" | "CSV") => {
    setBusy(true); setError(null);
    try { await queueTrainingReportJob(code, format); await client.invalidateQueries({ queryKey: ["training", "report-jobs"] }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Report job could not be queued."); } finally { setBusy(false); }
  };
  const saveDefinition = async () => {
    setBusy(true); setError(null);
    try { await createTrainingReportDefinition({ ...definition, code: definition.code.toUpperCase(), default_filters: {}, schedule_json: {}, active: true }); setDefinitionOpen(false); await client.invalidateQueries({ queryKey: ["training", "report-definitions"] }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Report definition could not be saved."); } finally { setBusy(false); }
  };

  return <div className="tos-stack training-route-workspace">
    <section className="tos-card tos-route-commandbar"><div><p className="tos-kicker">Retained server exports</p><h2>Report catalogue and job history</h2><p>Every long-running export keeps its complete server scope, source cutoff, status, checksum and retention date.</p></div><button disabled={!canManage} onClick={() => setDefinitionOpen(true)}><Plus size={16} /> Report definition</button><button onClick={() => void jobs.refetch()}><RefreshCw size={16} /></button></section>
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    <section className="tos-report-catalogue">{[...BUILTINS, ...(definitions.data || []).filter((item) => !BUILTINS.some((builtin) => builtin.code === item.code))].map((report) => <article className="tos-card" key={report.code}><FileBarChart size={22} /><div><h3>{report.name}</h3><p>{report.description}</p></div><div className="tos-actions"><button disabled={!canExport || busy} onClick={() => void queue(report.code, "PDF")}>Queue PDF</button><button disabled={!canExport || busy} onClick={() => void queue(report.code, "XLSX")}>Queue XLSX</button></div></article>)}</section>
    <details className="tos-disclosure" open><summary><span><Clock3 size={18} /><strong>Export jobs</strong></span><small>{jobs.data?.total ?? "Unknown"} retained requests</small></summary><div className="tos-disclosure__body">{jobs.isError ? <div className="tos-empty"><strong>Job source unavailable</strong><span>Retry without losing completed exports.</span></div> : <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Requested</th><th>Report</th><th>Scope</th><th>Format</th><th>Status</th><th>Artifact</th></tr></thead><tbody>{(jobs.data?.items || []).map((job) => <tr key={job.id}><td>{new Date(job.created_at).toLocaleString()}</td><td>{job.report_code}</td><td>{String(job.scope_manifest.record_count ?? "Pending")} records<small>Cutoff {String(job.scope_manifest.source_cutoff_at || "pending")}</small></td><td>{job.output_format}</td><td><span className={`tos-pill ${job.status === "FAILED" ? "tos-pill--critical" : "tos-pill--ok"}`}>{job.status}</span>{job.error_text ? <small>{job.error_text}</small> : null}</td><td>{job.status === "COMPLETED" && job.artifact_checksum ? <button disabled={!canExport} onClick={() => void downloadTrainingReportJob(job).catch((reason) => setError(reason instanceof Error ? reason.message : "Report download failed."))}><Download size={15} /> Download</button> : "Awaiting worker"}</td></tr>)}</tbody></table></div>}</div></details>
    <details className="tos-disclosure"><summary><span><Download size={18} /><strong>Immediate governed artifacts</strong></span><small>Existing plan, budget and attendance artifacts</small></summary><div className="tos-disclosure__body"><div className="tos-list">{(plans.data || []).map((plan) => <div key={plan.id}><div><strong>{plan.plan_year} training plan · Rev {plan.revision_no}</strong><small>{plan.status} · {plan.participant_count} obligations</small></div><button disabled={!canExport} onClick={() => void downloadTrainingOperatingReport(`/reports/plans/${plan.id}.pdf`, `training-plan-${plan.plan_year}-rev-${plan.revision_no}.pdf`)}>PDF</button></div>)}{(budgets.data || []).map((budget) => <div key={budget.id}><div><strong>Training budget · Rev {budget.revision_no}</strong><small>{budget.status} · {budget.reporting_currency}</small></div><div className="tos-actions"><button disabled={!canExport} onClick={() => void downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.pdf`, `training-budget-rev-${budget.revision_no}.pdf`)}>PDF</button><button disabled={!canExport} onClick={() => void downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.xlsx`, `training-budget-rev-${budget.revision_no}.xlsx`)}>XLSX</button></div></div>)}{(events.data || []).map((event) => <div key={event.id}><div><strong>{event.title}</strong><small>{event.starts_on} · attendance register</small></div><button disabled={!canExport} onClick={() => void downloadTrainingOperatingReport(`/reports/attendance/${event.id}.pdf`, `attendance-register-${event.id}.pdf`)}>PDF</button></div>)}</div></div></details>
    <Drawer title="Create report definition" isOpen={definitionOpen} onClose={() => setDefinitionOpen(false)} panelClassName="training-form-drawer training-form-drawer--compact"><div className="tos-drawer-form"><label>Code<input value={definition.code} onChange={(e) => setDefinition({ ...definition, code: e.target.value.toUpperCase() })} /></label><label>Name<input value={definition.name} onChange={(e) => setDefinition({ ...definition, name: e.target.value })} /></label><label>Dataset<select value={definition.dataset} onChange={(e) => setDefinition({ ...definition, dataset: e.target.value })}>{BUILTINS.map((item) => <option key={item.code}>{item.code}</option>)}</select></label><label>Description<textarea value={definition.description} onChange={(e) => setDefinition({ ...definition, description: e.target.value })} /></label><label>Retention days<input type="number" min="1" max="3650" value={definition.retention_days} onChange={(e) => setDefinition({ ...definition, retention_days: Number(e.target.value) })} /></label><div className="tos-actions"><button onClick={() => setDefinitionOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !definition.code || !definition.name} onClick={() => void saveDefinition()}>Save definition</button></div></div></Drawer>
  </div>;
};

export default TrainingReportsWorkspace;

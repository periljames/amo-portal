import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { qmsListAudits } from "../../services/qms";
import { classifyQmsPath, qmsBasePath, qmsModulePath } from "./routes/qmsRouteRegistry";
const QualityAuditRegisterPage = lazy(() => import("../qualityAudits/QualityAuditRegisterPage"));
import "./qms-management-review.css";

type Insights = { year: number; total: number; open: number; unmapped: number | null;
  groups: { key: string; total: number; open: number }[];
  months: { month: string; raised: number; closed: number }[] };
const titles: Record<string, string> = { "by-severity": "Findings by severity", "by-process": "Findings by process", trends: "Finding trends", new: "Record a finding" };

export default function QmsFindingViewsPage() {
  const location = useLocation();
  const context = classifyQmsPath(location.pathname);
  const view = context.relativePath?.split("/")[1] || "register";
  if (view === "register" || view === "linked-cars") return <Suspense fallback={<p role="status">Opening finding register…</p>}><QualityAuditRegisterPage /></Suspense>;
  return <FindingInsightContent amoCode={context.amoCode || ""} view={view} />;
}

function FindingInsightContent({ amoCode, view }: { amoCode: string; view: string }) {
  const [params, setParams] = useSearchParams();
  const supplied = Number(params.get("period"));
  const year = Number.isInteger(supplied) && supplied >= 2000 && supplied <= 2199 ? supplied : new Date().getFullYear();
  const [revision, setRevision] = useState(0);
  const q = params.get("q") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const creating = view === "new";
  const data = useQuery({ queryKey: ["finding-insights", amoCode, view, year, revision], enabled: !creating,
    queryFn: ({ signal }) => apiRequest<Insights>(`${qmsPath(amoCode, "/findings/insights")}?${new URLSearchParams({ view, year: String(year) })}`, { signal, cacheTtlMs: 0 }) });
  const audits = useQuery({ queryKey: ["finding-source-audits", amoCode, q, offset], enabled: creating && hasQmsRolePermission("qms.audit.view"),
    queryFn: () => qmsListAudits({ domain: "AMO", q, limit: 25, offset, sort: "planned_start", direction: "desc" }, { amoCode }) });
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const register = (filters: Record<string, string>) => `${qmsModulePath(amoCode, "findings", "register")}?${new URLSearchParams({ period: String(year), ...filters })}`;
  if (!hasQmsRolePermission("qms.finding.view")) return <Navigate to={qmsBasePath(amoCode)} replace />;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><section className="qms-review" aria-label="Finding analysis and capture">
    <header className="qms-review__heading"><div><h1>{titles[view]}</h1><p>{creating ? "Create findings against the audit that supplies their scope, evidence and accountable audit team." : "Recorded findings, verified classifications and dated source events."}</p></div><div className="qms-review__buttons">
      <Link to={qmsModulePath(amoCode, "findings", "register")}>Finding register</Link>
      {!creating && <><form onSubmit={event => { event.preventDefault(); update("period", String(new FormData(event.currentTarget).get("period"))); }}><label>Finding year<input key={year} name="period" aria-label="Finding year" type="number" required min={2000} max={2199} defaultValue={year} /></label><button>Apply year</button></form><button disabled={data.isFetching} onClick={() => setRevision(value => value + 1)}>Refresh analysis</button></>}
    </div></header>
    <QmsSectionTabs amoCode={amoCode} />
    {creating ? <section className="qms-review__section"><h2>Select the source audit</h2><p>Open Fieldwork to record objective evidence, classify the finding and retain its audit link. Preparation and execution permissions remain enforced there.</p>
      {!hasQmsRolePermission("qms.finding.create") && <p>You can inspect findings. Recording a finding requires finding creation permission.</p>}
      <label>Find source audit<input type="search" value={q} onChange={event => update("q", event.target.value)} /></label>
      {!hasQmsRolePermission("qms.audit.view") && <p>Source audit access is required to open fieldwork.</p>}
      {audits.isPending && hasQmsRolePermission("qms.audit.view") && <p role="status">Loading source audits…</p>}{audits.isError && <p role="alert">{audits.error.message}<button onClick={() => void audits.refetch()}>Retry audits</button></p>}
      {audits.data && <>{!audits.data.items.length && <p>No source audits match. <Link to={qmsModulePath(amoCode, "audits", "plan")}>Open audit planning</Link></p>}
        <div className="qms-review__table"><table><thead><tr><th>Audit</th><th>Status</th><th>Source workflow</th></tr></thead><tbody>{audits.data.items.map(audit => <tr key={audit.id}><td>{audit.audit_ref}<br />{audit.title}</td><td>{audit.status.replaceAll("_", " ").toLowerCase()}</td><td><Link to={`${qmsBasePath(amoCode)}/audits/${audit.id}/live#findings`}>Open fieldwork</Link></td></tr>)}</tbody></table></div>
        <nav aria-label="Source audit pages"><button disabled={!offset} onClick={() => update("offset", String(Math.max(0, offset - 25)))}>Previous</button><span>{audits.data.total} source audits</span><button disabled={offset + 25 >= audits.data.total} onClick={() => update("offset", String(offset + 25))}>Next</button></nav></>}
    </section> : <>
      {data.isPending && <p role="status">Loading finding analysis…</p>}{data.isError && <p role="alert">{data.error.message}<button onClick={() => void data.refetch()}>Retry analysis</button></p>}
      {data.data && <><section className="qms-review__stats"><Link to={register({})}>Raised in {year}<strong>{data.data.total}</strong></Link><Link to={register({ status: "open" })}>Still open from this cohort<strong>{data.data.open}</strong></Link></section>
        <section className="qms-review__section"><h2>{view === "by-process" ? "Verified control process areas" : view === "by-severity" ? "Recorded severity" : "Monthly finding events"}</h2>
          {view === "by-process" && <><p>Only current verified finding links to approved active controls supply process areas. A finding can appear in several process areas; group counts are not additive.</p><p>{data.data.unmapped} finding(s) have no qualifying process mapping. <Link to={register({ processUnmapped: "1" })}>Inspect unmapped findings</Link> · <Link to={`${qmsBasePath(amoCode)}?hub=controls`}>Manage process controls</Link></p></>}
          {view === "trends" ? <><p>Raised counts use the finding creation date. Closed counts use the retained closure date, including findings raised in earlier years. These are monthly events, not historical backlog snapshots.</p><div className="qms-review__table"><table><thead><tr><th>Month</th><th>Raised</th><th>Closed</th></tr></thead><tbody>{data.data.months.map(month => <tr key={month.month}><th>{month.month}</th><td>{month.raised}</td><td>{month.closed}</td></tr>)}</tbody></table></div></>
            : <>{!data.data.groups.length && <p>No qualifying classifications were recorded for this cohort.</p>}<div className="qms-review__table"><table><thead><tr><th>{view === "by-process" ? "Process area" : "Severity"}</th><th>Findings</th><th>Open</th><th>Source records</th></tr></thead><tbody>{data.data.groups.map(group => <tr key={group.key}><th>{group.key}</th><td>{group.total}</td><td>{group.open}</td><td><Link to={register({ [view === "by-process" ? "process" : "severity"]: group.key })}>Inspect findings</Link></td></tr>)}</tbody></table></div></>}
        </section></>}
    </>}
  </section></DepartmentLayout>;
}

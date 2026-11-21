import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import QualityAuditsSectionLayout from "../qualityAudits/QualityAuditsSectionLayout";
import FindingAnalysis, { FindingAnalysisControls } from "./FindingAnalysis";
import type { FindingInsights } from "./findingAnalysisModel";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { qmsListAudits } from "../../services/qms";
import { classifyQmsPath, qmsBasePath, qmsModulePath } from "./routes/qmsRouteRegistry";
const QualityAuditRegisterPage = lazy(() => import("../qualityAudits/QualityAuditRegisterPage"));
import "./qms-management-review.css";

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
  const q = params.get("q") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const creating = view === "new";
  const data = useQuery({ queryKey: ["finding-insights", amoCode, view, year], enabled: !creating,
    queryFn: ({ signal }) => apiRequest<FindingInsights>(`${qmsPath(amoCode, "/findings/insights")}?${new URLSearchParams({ view, year: String(year) })}`, { signal, cacheTtlMs: 0 }) });
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
  const controls = <FindingAnalysisControls year={year} refreshing={data.isFetching} onFilter={update} onRefresh={() => void data.refetch()} />;
  if (!creating) return <QualityAuditsSectionLayout title={titles[view] || "Finding analysis"} subtitle="Finding analysis" toolbar={controls}>
    <QmsSectionTabs amoCode={amoCode} />
    <FindingAnalysis view={view} year={year} data={data.data} loading={data.isPending} refreshing={data.isFetching}
      error={data.error} openOnly={params.get("status") === "open"} search={params.get("processSearch") || ""}
      onFilter={update} onRefresh={() => void data.refetch()} register={register} />
  </QualityAuditsSectionLayout>;
  return <QualityAuditsSectionLayout title={titles.new} subtitle="Record a finding"><div className="qms-review">
    <QmsSectionTabs amoCode={amoCode} />
    <section className="qms-review__section"><h2>Select the source audit</h2><p>Open Fieldwork to record objective evidence, classify the finding and retain its audit link. Preparation and execution permissions remain enforced there.</p>
      {!hasQmsRolePermission("qms.finding.create") && <p>You can inspect findings. Recording a finding requires finding creation permission.</p>}
      <label>Find source audit<input type="search" value={q} onChange={event => update("q", event.target.value)} /></label>
      {!hasQmsRolePermission("qms.audit.view") && <p>Source audit access is required to open fieldwork.</p>}
      {audits.isPending && hasQmsRolePermission("qms.audit.view") && <p role="status">Loading source audits…</p>}{audits.isError && <p role="alert">{audits.error.message}<button onClick={() => void audits.refetch()}>Retry audits</button></p>}
      {audits.data && <>{!audits.data.items.length && <p>No source audits match. <Link to={qmsModulePath(amoCode, "audits", "plan")}>Open audit planning</Link></p>}
        <div className="qms-review__table"><table><thead><tr><th>Audit</th><th>Status</th><th>Source workflow</th></tr></thead><tbody>{audits.data.items.map(audit => <tr key={audit.id}><td>{audit.audit_ref}<br />{audit.title}</td><td>{audit.status.replaceAll("_", " ").toLowerCase()}</td><td><Link to={`${qmsBasePath(amoCode)}/audits/${audit.id}/live#findings`}>Open fieldwork</Link></td></tr>)}</tbody></table></div>
        <nav aria-label="Source audit pages"><button disabled={!offset} onClick={() => update("offset", String(Math.max(0, offset - 25)))}>Previous</button><span>{audits.data.total} source audits</span><button disabled={offset + 25 >= audits.data.total} onClick={() => update("offset", String(offset + 25))}>Next</button></nav></>}
    </section>
  </div></QualityAuditsSectionLayout>;
}

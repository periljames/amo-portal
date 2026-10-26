import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Download, FileText, RefreshCw } from "lucide-react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { apiBlob } from "../../services/typedApi";
import { saveDownloadedFile } from "../../utils/downloads";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { classifyQmsPath } from "./routes/qmsRouteRegistry";
import "./qms-reports.css";

const reports = [
  { id: "executive-dashboard", label: "Executive summary", description: "Audit and CAR status across the reporting period." },
  { id: "audit-performance", label: "Audit performance", description: "Audit plans, current status and completion dates." },
  { id: "car-performance", label: "CAR performance", description: "Corrective actions, priorities, due dates and closure." },
  { id: "finding-trends", label: "Finding trends", description: "Findings, severity, requirements and closure dates." },
  { id: "training-compliance", label: "Training record validity", description: "Completed training records, verification and current validity." },
];
type Snapshot = { summary?: { label: string; value: number }[]; kind: string; title: string; tenant: string; generated_at: string; start: string; end: string; population: string; columns: string[]; rows: string[][]; total: number };

export default function QmsReportsPage() {
  const location = useLocation();
  const { amoCode: routeAmoCode } = useParams();
  const amoCode = routeAmoCode || classifyQmsPath(location.pathname).amoCode || "";
  const view = location.pathname.split("/").filter(Boolean).at(-1) || "executive-dashboard";
  const kind = reports.some(report => report.id === view) ? view : "executive-dashboard";
  const catalogue = view === "exports";
  const [data, setData] = useState<Snapshot | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [request, setRequest] = useState<{ start: string; end: string; revision: number }>({ start: "", end: "", revision: 0 });
  const canView = hasQmsRolePermission("qms.reports.view");
  const canExport = hasQmsRolePermission("qms.reports.export");
  const invalid = Boolean(start && end && start > end);
  const stale = Boolean(data && (start !== data.start || end !== data.end));
  useEffect(() => {
    if (!canView) return;
    if (catalogue) { setError(""); return; }
    const controller = new AbortController();
    setLoading(true); setError(""); setData(null); setPage(0);
    const query = new URLSearchParams({ kind });
    if (request.start) query.set("start", request.start);
    if (request.end) query.set("end", request.end);
    apiRequest<Snapshot>(qmsPath(amoCode, `/reports/preview?${query}`), { signal: controller.signal, cacheTtlMs: 0, persistCache: false, staleWhileOfflineMs: 0, headers: { "X-AMO-Silent-Error": "1" } })
      .then(result => { if (!controller.signal.aborted) { setData(result); setStart(result.start); setEnd(result.end); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Report could not be loaded. Retry when connected."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [amoCode, kind, catalogue, request, canView]);
  async function download(output: "csv" | "html") {
    if (!data || stale || loading || busy || !canExport) return;
    setBusy(true); setError("");
    try {
      const query = new URLSearchParams({ kind, start: data.start, end: data.end, output });
      const result = await apiBlob(qmsPath(amoCode, `/reports/output?${query}`), { headers: { "X-AMO-Silent-Error": "1" } });
      saveDownloadedFile(result.blob, result.filename || `QMS-${kind}.${output}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Download failed. Your report remains available; retry the download."); }
    finally { setBusy(false); }
  }
  if (!canView) return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><p role="alert">Report viewing permission is required.</p></DepartmentLayout>;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="qms-reports">
    <header><div><h1>{catalogue ? "Report downloads" : data?.title || reports.find(report => report.id === kind)?.label}</h1><p>Tenant reports · {data?.tenant || amoCode}</p></div><FileText size={24} /></header>
    <QmsSectionTabs amoCode={amoCode} />
    {catalogue ? <div className="qms-reports__catalogue">{reports.map(report => <Link key={report.id} to={`/maintenance/${encodeURIComponent(amoCode)}/quality/reports/${report.id}`}><FileText size={22} /><h2>{report.label}</h2><p>{report.description}</p><span>View report & download <Download size={15} /></span></Link>)}</div> : <>
      <form className="qms-reports__filters" onSubmit={event => { event.preventDefault(); if (!invalid) setRequest({ start, end, revision: request.revision + 1 }); }}>
        <label>From<input type="date" aria-label="Report period start" value={start} max={end || undefined} onChange={event => setStart(event.target.value)} /></label>
        <label>Through<input type="date" aria-label="Report period end" value={end} min={start || undefined} onChange={event => setEnd(event.target.value)} /></label>
        <button type="submit" disabled={loading || invalid}><RefreshCw size={16} className={loading ? "qms-reports__spinner" : undefined} />{loading ? "Loading…" : "Apply / refresh"}</button>
        <div className="qms-reports__outputs"><button type="button" disabled={!data || stale || loading || busy || !canExport} onClick={() => void download("csv")}><Download size={16} />{busy ? "Preparing…" : "Download CSV"}</button><button type="button" disabled={!data || stale || loading || busy || !canExport} onClick={() => void download("html")}><FileText size={16} />Download printable report</button></div>
      </form>
      {invalid && <p role="status">The end date must be on or after the start date.</p>}
      {stale && <p role="status">Apply the changed period before downloading.</p>}
      {!canExport && <p>Report viewing is available. Downloading requires report export permission.</p>}
      {error && <div className="qms-reports__error" role="alert" data-portal-error-feedback>{error}<button type="button" onClick={() => setRequest(previous => ({ ...previous, revision: previous.revision + 1 }))}>Retry report</button></div>}
      {loading && <p role="status">Loading the complete report…</p>}
      {data && <section className="qms-reports__preview" data-report-kind={kind} aria-label="Report preview">
        <div className="qms-reports__metadata"><strong>{data.total} {kind === "executive-dashboard" ? "status groups" : "records"}</strong><span>Generated {new Date(data.generated_at).toLocaleString(undefined, { timeZoneName: "short" })}</span></div><p>{data.population}</p>
        {Boolean(data.summary?.length) && <div className="qms-reports__summary">{data.summary?.map(item => <span key={item.label}>{item.label.replaceAll("_", " ")} <strong>{item.value}</strong></span>)}</div>}
        {kind === "car-performance" && <Link to={`${location.pathname}?analysis=1`}>Open detailed CAR charts and analysis</Link>}
        <div className="qms-reports__table"><table><thead><tr>{data.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{data.rows.slice(page*25, (page+1)*25).map((row, index) => <tr key={index}>{row.map((cell, i) => <td key={i}>{cell || "—"}</td>)}</tr>)}</tbody></table></div>
        {!data.total && <p>No records match this period.</p>}
        {data.total > 25 && <nav aria-label="Report preview pages"><button type="button" disabled={!page} onClick={() => setPage(page-1)}>Previous</button><span>Page {page+1} of {Math.ceil(data.total/25)} · downloads include all {data.total} rows</span><button type="button" disabled={(page+1)*25 >= data.total} onClick={() => setPage(page+1)}>Next</button></nav>}
        <small>Printable reports open in your browser and can be printed or saved as PDF. Downloads retrieve a fresh server snapshot for the applied period.</small>
      </section>}
    </>}
  </main></DepartmentLayout>;
}

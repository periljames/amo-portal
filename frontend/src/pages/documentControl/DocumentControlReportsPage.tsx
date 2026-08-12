import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  BookCopy,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Download,
  FileClock,
  FileDiff,
  FileStack,
  History,
  Landmark,
  LibraryBig,
  Printer,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  exportReportsCsv,
  getReportsPortfolio,
  getReportsRegister,
  type ReportRegisterItem,
  type ReportRegisterView,
  type ReportsPortfolioResponse,
  type ReportsRegisterResponse,
} from "../../services/documentControlReportsPortfolio";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";
import "./dmsReports.css";

const SEARCH_DEBOUNCE_MS = 320;
type ReportsView = "master" | ReportRegisterView;

const REPORTS: Array<{ id: ReportsView; label: string; description: string; icon: typeof LibraryBig }> = [
  { id: "master", label: "Master Documents", description: "Controlled document master register", icon: LibraryBig },
  { id: "lep", label: "LEP", description: "Lists of Effective Pages", icon: FileStack },
  { id: "revisions", label: "Revisions", description: "Issue and revision evidence", icon: FileDiff },
  { id: "distribution", label: "Distribution", description: "Issued distribution campaigns", icon: Send },
  { id: "acknowledgements", label: "Acknowledgements", description: "Recipient acknowledgement evidence", icon: ClipboardCheck },
  { id: "controlled-copies", label: "Controlled Copies", description: "Numbered physical-copy custody", icon: BookCopy },
  { id: "external-sources", label: "External Sources", description: "External technical-data currency", icon: ShieldCheck },
  { id: "review-due", label: "Review Due", description: "Periodic review evidence", icon: FileClock },
  { id: "temporary-revisions", label: "Temporary Revisions", description: "TR lifecycle and expiry evidence", icon: FileDiff },
  { id: "authority", label: "Authority", description: "Regulatory submission evidence", icon: Landmark },
  { id: "archive", label: "Archive", description: "Superseded and archived revisions", icon: Archive },
  { id: "change-history", label: "Change History", description: "Controlled change-request history", icon: History },
  { id: "retention", label: "Retention / Disposition", description: "Retained generated-record evidence", icon: FileStack },
];

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  const safe = /^\s*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

function revisionLabel(revision: ReportsPortfolioResponse["items"][number]["latest_revision"]): string {
  if (!revision?.id) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number || "—"}`;
}

function downloadCsv(filename: string, headings: string[], rows: unknown[][]): void {
  const csv = [headings, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function downloadMasterCsv(data: ReportsPortfolioResponse): void {
  downloadCsv(
    `document-control-master-register-page-${data.pagination.page}.csv`,
    ["Code", "Title", "Type", "Class", "Owner", "Lifecycle", "Latest revision", "Effective revision", "Next review"],
    data.items.map((item) => [
      item.code,
      item.title,
      item.manual_type,
      item.document_class,
      item.owner_department,
      item.lifecycle_status,
      revisionLabel(item.latest_revision),
      revisionLabel(item.effective_revision),
      item.next_review_due || "",
    ]),
  );
}

function downloadRegisterCsv(data: ReportsRegisterResponse): void {
  downloadCsv(
    `document-control-${data.view}-page-${data.pagination.page}.csv`,
    ["Document code", "Document title", "Record", "Status", "Owner", "Date", "Due / expiry", "Context", "Record type"],
    data.items.map((item) => [
      item.document.code,
      item.document.title,
      item.record,
      item.status || "",
      item.owner || "",
      item.date || "",
      item.due_at || "",
      item.context || "",
      item.kind,
    ]),
  );
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function statusKind(value?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["ACTIVE", "CURRENT", "PUBLISHED", "ACKNOWLEDGED", "COMPLETED", "APPROVED", "RETURNED"].includes(status)) return "success";
  if (["OVERDUE", "FAILED", "REJECTED", "EXPIRED", "WITHDRAWN", "SUPERSEDED"].includes(status)) return "danger";
  if (["PENDING", "DRAFT", "SCHEDULED", "UNVERIFIED", "RECALLED"].includes(status)) return "warning";
  if (["IN_PROGRESS", "ISSUED", "SUBMITTED", "AUTHORITY_SUBMITTED"].includes(status)) return "info";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], value.length === 10 ? { dateStyle: "medium" } : { dateStyle: "medium", timeStyle: "short" });
}

export default function DocumentControlReportsPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const requestedView = params.get("view") as ReportsView | null;
  const view: ReportsView = REPORTS.some((report) => report.id === requestedView) ? requestedView as ReportsView : "master";
  const reportMeta = useMemo(() => REPORTS.find((report) => report.id === view) || REPORTS[0], [view]);
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [masterData, setMasterData] = useState<ReportsPortfolioResponse | null>(null);
  const [registerData, setRegisterData] = useState<ReportsRegisterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [exportError, setExportError] = useState("");
  const [exportMessage, setExportMessage] = useState("");
  const loadedRef = useRef(false);
  const page = Math.max(1, Number(params.get("page") || 1));
  const perPage = Math.min(100, Math.max(25, Number(params.get("per_page") || 50)));

  const load = useCallback(async () => {
    if (!tenant) return;
    const initial = !loadedRef.current;
    setLoading(initial);
    setRefreshing(!initial);
    setError("");
    try {
      if (view === "master") {
        const next = await getReportsPortfolio(tenant, {
          q: params.get("q") || undefined,
          documentClass: params.get("class") || undefined,
          lifecycleStatus: params.get("status") || undefined,
          page,
          perPage,
        });
        setMasterData(next);
        setRegisterData(null);
      } else {
        const next = await getReportsRegister(tenant, {
          view,
          q: params.get("q") || undefined,
          status: params.get("status") || undefined,
          dateFrom: params.get("date_from") || undefined,
          dateTo: params.get("date_to") || undefined,
          page,
          perPage,
        });
        setRegisterData(next);
        setMasterData(null);
      }
      loadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Reports could not be generated.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, params, perPage, tenant, view]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setSearchText(urlQuery); }, [urlQuery]);
  useEffect(() => {
    if (searchText === urlQuery) return;
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      const value = searchText.trim();
      if (value) next.set("q", value); else next.delete("q");
      next.set("page", "1");
      setParams(next, { replace: true });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [params, searchText, setParams, urlQuery]);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
    setExportError("");
    setExportMessage("");
  };

  const changeView = (nextView: ReportsView) => {
    const next = new URLSearchParams(params);
    if (nextView === "master") next.delete("view"); else next.set("view", nextView);
    next.delete("status");
    next.delete("class");
    next.delete("date_from");
    next.delete("date_to");
    next.set("page", "1");
    setParams(next);
    setExportError("");
    setExportMessage("");
  };

  const pagination = view === "master" ? masterData?.pagination : registerData?.pagination;
  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.per_page)) : 1;
  const hasRows = view === "master" ? Boolean(masterData?.items.length) : Boolean(registerData?.items.length);
  const hasFilteredRows = Boolean(pagination?.total);

  const exportCurrentPage = () => {
    if (view === "master" && masterData) downloadMasterCsv(masterData);
    else if (registerData) downloadRegisterCsv(registerData);
  };

  const exportFullRegister = async () => {
    if (!tenant || !hasFilteredRows) return;
    setExporting(true);
    setExportError("");
    setExportMessage("");
    try {
      const result = await exportReportsCsv(tenant, {
        view,
        q: params.get("q") || undefined,
        status: view === "master" ? undefined : params.get("status") || undefined,
        lifecycleStatus: view === "master" ? params.get("status") || undefined : undefined,
        documentClass: view === "master" ? params.get("class") || undefined : undefined,
        dateFrom: view === "master" ? undefined : params.get("date_from") || undefined,
        dateTo: view === "master" ? undefined : params.get("date_to") || undefined,
      });
      saveBlob(result.blob, result.filename);
      setExportMessage(result.rowCount === null ? "Full filtered register generated by the server." : `Full filtered register generated by the server · ${result.rowCount.toLocaleString()} row${result.rowCount === 1 ? "" : "s"}.`);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "The full filtered evidence register could not be generated.");
    } finally {
      setExporting(false);
    }
  };

  return <DocumentControlShell
    title="Reports"
    eyebrow="CONTROLLED EVIDENCE"
    subtitle="Authoritative Document Control registers remain bounded in the browser; full filtered CSV evidence is generated by the server with an explicit export ceiling."
    canControl
    actions={<>
      <button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>
      <button type="button" className="dc-button" disabled={!hasRows} onClick={() => window.print()}><Printer size={14} /> Print / PDF</button>
      <button type="button" className="dc-button" disabled={!hasRows} onClick={exportCurrentPage}><Download size={14} /> Export current page CSV</button>
      <button type="button" className="dc-button dc-button--primary" disabled={!hasFilteredRows || exporting} onClick={() => void exportFullRegister()}><Download size={14} /> {exporting ? "Generating full CSV…" : "Export full filtered CSV"}</button>
    </>}
  >
    <section className="dms-reports" data-testid="document-control-reports" aria-busy={refreshing || exporting}>
      <nav className="dms-reports__catalogue" aria-label="Controlled evidence registers">
        {REPORTS.map(({ id, label, description, icon: Icon }) => <button type="button" key={id} className={view === id ? "active" : ""} aria-current={view === id ? "page" : undefined} onClick={() => changeView(id)}>
          <Icon size={15} /><span><strong>{label}</strong><small>{description}</small></span>
        </button>)}
      </nav>

      <div className="dms-reports__workspace">
        <header className="dms-reports__report-head"><div><strong>{reportMeta.label}</strong><span>{reportMeta.description}</span></div>{pagination ? <small>{pagination.total.toLocaleString()} permitted record{pagination.total === 1 ? "" : "s"}</small> : null}</header>

        {view === "master" && masterData ? <div className="dc-metrics" aria-label="Document Control exception summary">
          {Object.entries(masterData.summary).map(([key, value]) => <div className={value ? "dc-metric dc-metric--danger" : "dc-metric"} key={key}><strong>{value}</strong><span>{key.replaceAll("_", " ")}</span></div>)}
        </div> : null}

        <div className="dc-toolbar dms-reports__filters">
          <label className="dc-search"><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={`Search ${reportMeta.label.toLowerCase()}`} /></label>
          {view === "master" ? <select aria-label="Report document class" value={params.get("class") || ""} onChange={(event) => update("class", event.target.value)}>
            <option value="">All document classes</option><option value="INTERNAL">Internal</option><option value="EXTERNAL">External</option><option value="RECORD">Record</option>
          </select> : null}
          <input aria-label="Report status" value={params.get("status") || ""} onChange={(event) => update("status", event.target.value.toUpperCase())} placeholder="Status filter" />
          {view !== "master" ? <><label><span>From</span><input aria-label="Report date from" type="date" value={params.get("date_from") || ""} onChange={(event) => update("date_from", event.target.value)} /></label><label><span>To</span><input aria-label="Report date to" type="date" value={params.get("date_to") || ""} onChange={(event) => update("date_to", event.target.value)} /></label></> : null}
          {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
        </div>

        {exportError ? <div className="dc-callout dc-callout--warning" role="alert"><AlertTriangle size={16} /><div><strong>Full export not generated.</strong><div>{exportError}</div></div></div> : null}
        {exportMessage ? <div className="dc-callout" role="status"><Download size={16} /><div><strong>Evidence export generated.</strong><div>{exportMessage}</div></div></div> : null}
        {pagination && pagination.total > 10_000 ? <div className="dc-callout dc-callout--warning"><AlertTriangle size={16} /><div><strong>Full direct export requires narrower filters.</strong><div>This view contains {pagination.total.toLocaleString()} records; the direct server export ceiling is 10,000 rows.</div></div></div> : null}

        {loading ? <DocumentControlLoading label={`Generating bounded ${reportMeta.label.toLowerCase()} evidence…`} /> : null}
        {error && !masterData && !registerData ? <DocumentControlError message={error} retry={() => void load()} /> : null}
        {error && (masterData || registerData) ? <div className="dc-callout dc-callout--warning" role="alert"><AlertTriangle size={16} /> The latest report refresh failed. The last permitted page remains visible.</div> : null}
        {!loading && !hasRows ? <DocumentControlEmpty title={`No ${reportMeta.label.toLowerCase()} entries match this view`} message="Change the report filters or search text." /> : null}

        {!loading && view === "master" && masterData?.items.length ? <div className="dc-table-wrap"><table className="dc-table">
          <thead><tr><th>Document</th><th>Type / class</th><th>Owner</th><th>Lifecycle</th><th>Latest</th><th>Effective</th><th>Next review</th></tr></thead>
          <tbody>{masterData.items.map((item) => <tr key={item.manual_id}>
            <td><button type="button" className="dms-reports__record-link" onClick={() => navigate(`${basePath}/library/${item.manual_id}`)}><strong>{item.code}</strong><small>{item.title}</small></button></td>
            <td><strong>{item.manual_type}</strong><small>{item.document_class}{item.regulated ? " · regulated" : ""}{item.restricted ? " · restricted" : ""}</small></td>
            <td>{item.owner_department}</td>
            <td><DocumentControlStatus status={item.lifecycle_status} kind={statusKind(item.lifecycle_status)} /></td>
            <td>{revisionLabel(item.latest_revision)}</td>
            <td>{revisionLabel(item.effective_revision)}</td>
            <td>{item.next_review_due || "Not scheduled"}</td>
          </tr>)}</tbody>
        </table></div> : null}

        {!loading && view !== "master" && registerData?.items.length ? <div className="dc-table-wrap"><table className="dc-table dms-reports__evidence-table">
          <thead><tr><th>Document</th><th>Evidence record</th><th>Status</th><th>Owner / holder</th><th>Date</th><th>Due / expiry</th><th>Context</th><th>Action</th></tr></thead>
          <tbody>{registerData.items.map((item: ReportRegisterItem) => <tr key={`${item.kind}:${item.id}`}>
            <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
            <td><strong>{item.record}</strong><small>{item.kind.replaceAll("_", " ")}</small></td>
            <td>{item.status ? <DocumentControlStatus status={item.status} kind={statusKind(item.status)} /> : "—"}</td>
            <td>{item.owner || "—"}</td>
            <td>{formatDate(item.date)}</td>
            <td>{formatDate(item.due_at)}</td>
            <td>{item.context || "—"}</td>
            <td><button type="button" className="dc-button" onClick={() => navigate(`${basePath}/${item.target_path}`)}>Open evidence</button></td>
          </tr>)}</tbody>
        </table></div> : null}

        {pagination ? <footer className="dlibrary__pagination">
          <span>{pagination.total ? `${(pagination.page - 1) * pagination.per_page + 1}–${Math.min(pagination.page * pagination.per_page, pagination.total)} of ${pagination.total}` : "0 records"}</span>
          <select aria-label="Report rows per page" value={pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
          <button type="button" disabled={pagination.page <= 1 || refreshing} onClick={() => update("page", String(pagination.page - 1))}><ChevronLeft size={14} /> Previous</button>
          <span>Page {pagination.page} of {totalPages}</span>
          <button type="button" disabled={pagination.page >= totalPages || refreshing} onClick={() => update("page", String(pagination.page + 1))}>Next <ChevronRight size={14} /></button>
        </footer> : null}
      </div>
    </section>
  </DocumentControlShell>;
}
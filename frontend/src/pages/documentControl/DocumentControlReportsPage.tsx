import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Download, RefreshCw, Search } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import {
  getReportsPortfolio,
  type ReportsPortfolioResponse,
} from "../../services/documentControlReportsPortfolio";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";

const SEARCH_DEBOUNCE_MS = 320;

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function revisionLabel(revision: ReportsPortfolioResponse["items"][number]["latest_revision"]): string {
  if (!revision?.id) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number || "—"}`;
}

function downloadCsv(data: ReportsPortfolioResponse): void {
  const headings = ["Code", "Title", "Type", "Class", "Owner", "Lifecycle", "Latest revision", "Effective revision", "Next review"];
  const rows = data.items.map((item) => [
    item.code,
    item.title,
    item.manual_type,
    item.document_class,
    item.owner_department,
    item.lifecycle_status,
    revisionLabel(item.latest_revision),
    revisionLabel(item.effective_revision),
    item.next_review_due || "",
  ]);
  const csv = [headings, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `document-control-master-register-page-${data.pagination.page}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function DocumentControlReportsPage() {
  const { tenant } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [data, setData] = useState<ReportsPortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
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
      const next = await getReportsPortfolio(tenant, {
        q: params.get("q") || undefined,
        documentClass: params.get("class") || undefined,
        lifecycleStatus: params.get("status") || undefined,
        page,
        perPage,
      });
      setData(next);
      loadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Reports could not be generated.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, params, perPage, tenant]);

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
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / data.pagination.per_page)) : 1;

  return <DocumentControlShell
    title="Reports"
    eyebrow="CONTROLLED EVIDENCE"
    subtitle="Bounded master-register evidence and exception summaries generated from the authoritative Document Control records."
    canControl
    actions={<>
      <button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>
      <button type="button" className="dc-button dc-button--primary" disabled={!data?.items.length} onClick={() => data && downloadCsv(data)}><Download size={14} /> Export current page CSV</button>
    </>}
  >
    <section data-testid="document-control-reports" aria-busy={refreshing}>
      {data ? <div className="dc-metrics" aria-label="Document Control exception summary">
        {Object.entries(data.summary).map(([key, value]) => <div className={value ? "dc-metric dc-metric--danger" : "dc-metric"} key={key}><strong>{value}</strong><span>{key.replaceAll("_", " ")}</span></div>)}
      </div> : null}

      <div className="dc-toolbar">
        <label className="dc-search"><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Find register entry by code, title or type" /></label>
        <select aria-label="Report document class" value={params.get("class") || ""} onChange={(event) => update("class", event.target.value)}>
          <option value="">All document classes</option><option value="INTERNAL">Internal</option><option value="EXTERNAL">External</option><option value="RECORD">Record</option>
        </select>
        <select aria-label="Report lifecycle status" value={params.get("status") || ""} onChange={(event) => update("status", event.target.value)}>
          <option value="">All lifecycle states</option><option value="ACTIVE">Active</option><option value="SUPERSEDED">Superseded</option><option value="ARCHIVED">Archived</option>
        </select>
        {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
      </div>

      {loading ? <DocumentControlLoading label="Generating bounded evidence register…" /> : null}
      {error && !data ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {error && data ? <div className="dc-callout dc-callout--warning" role="alert"><AlertTriangle size={16} /> The latest report refresh failed. The last permitted register page remains visible.</div> : null}
      {!loading && data && !data.items.length ? <DocumentControlEmpty title="No register entries match this view" message="Change the report filters or search text." /> : null}

      {!loading && data?.items.length ? <div className="dc-table-wrap"><table className="dc-table">
        <thead><tr><th>Document</th><th>Type / class</th><th>Owner</th><th>Lifecycle</th><th>Latest</th><th>Effective</th><th>Next review</th></tr></thead>
        <tbody>{data.items.map((item) => <tr key={item.manual_id}>
          <td><strong>{item.code}</strong><small>{item.title}</small></td>
          <td><strong>{item.manual_type}</strong><small>{item.document_class}{item.regulated ? " · regulated" : ""}{item.restricted ? " · restricted" : ""}</small></td>
          <td>{item.owner_department}</td>
          <td><DocumentControlStatus status={item.lifecycle_status} kind={item.lifecycle_status === "ACTIVE" ? "success" : "neutral"} /></td>
          <td>{revisionLabel(item.latest_revision)}</td>
          <td>{revisionLabel(item.effective_revision)}</td>
          <td>{item.next_review_due || "Not scheduled"}</td>
        </tr>)}</tbody>
      </table></div> : null}

      {data ? <footer className="dlibrary__pagination">
        <span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 documents"}</span>
        <select aria-label="Report rows per page" value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={data.pagination.page <= 1 || refreshing} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={14} /> Previous</button>
        <span>Page {data.pagination.page} of {totalPages}</span>
        <button type="button" disabled={data.pagination.page >= totalPages || refreshing} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={14} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}

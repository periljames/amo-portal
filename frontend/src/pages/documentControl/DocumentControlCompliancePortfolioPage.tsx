import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileWarning,
  Link2,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getCompliancePortfolio,
  type CompliancePortfolioItem,
  type CompliancePortfolioResponse,
  type CompliancePortfolioView,
} from "../../services/documentControlCompliancePortfolio";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./dmsCompliancePortfolio.css";

const SEARCH_DEBOUNCE_MS = 320;

const VIEWS: Array<{ id: CompliancePortfolioView; label: string; icon: typeof ShieldCheck }> = [
  { id: "reviews", label: "Periodic Reviews", icon: CalendarClock },
  { id: "external-sources", label: "External Technical Data", icon: ShieldCheck },
  { id: "relationships", label: "Relationship Review", icon: Link2 },
  { id: "applicability", label: "Applicability", icon: Target },
  { id: "superseded-references", label: "Superseded References", icon: FileWarning },
];

function statusKind(value?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["CURRENT", "COMPLETED", "CONFIRMED", "ACTIVE"].includes(status)) return "success";
  if (["OVERDUE", "SUPERSEDED_REFERENCE", "FAILED", "REJECTED", "EXPIRED"].includes(status)) return "danger";
  if (["DUE", "UNVERIFIED", "PENDING", "ASSESSMENT_REQUIRED", "UNRESOLVED", "PROPOSED"].includes(status)) return "warning";
  if (["IN_PROGRESS", "DETECTED"].includes(status)) return "info";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function documentCell(item: CompliancePortfolioItem) {
  return <><strong>{item.document.code}</strong><small>{item.document.title}</small></>;
}

function detailCells(item: CompliancePortfolioItem) {
  if (item.kind === "PERIODIC_REVIEW") return <>
    <td><strong>{item.owner || "Unassigned"}</strong><small>{item.outcome || "Outcome pending"}</small></td>
    <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /></td>
    <td>{formatDate(item.due_at)}</td>
  </>;
  if (item.kind === "EXTERNAL_SOURCE") return <>
    <td><strong>{item.provider}</strong><small>{item.authority || item.update_method || "External provider"}</small></td>
    <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.received_revision ? `Received ${item.received_revision}` : "No received revision recorded"}</small></td>
    <td><strong>{formatDate(item.next_check_due_at)}</strong><small>{item.last_checked_at ? `Last checked ${formatDate(item.last_checked_at)}` : "Not checked"}</small></td>
  </>;
  if (item.kind === "RELATIONSHIP") return <>
    <td><strong>{item.relationship_type?.replaceAll("_", " ")}</strong><small>{item.exact_token || item.target || "Linked entity"}{item.page_number ? ` · page ${item.page_number}` : ""}</small></td>
    <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.confidence_percent !== undefined ? `${item.confidence_percent}% detected confidence` : item.relationship_source}</small></td>
    <td>{item.section_label || "Document level"}</td>
  </>;
  if (item.kind === "APPLICABILITY") return <>
    <td><strong>{item.rule_type?.replaceAll("_", " ")}</strong><small>{item.target_type}: {item.target || "Criteria"}</small></td>
    <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.source || "Controlled rule"}</small></td>
    <td>{item.effective_from || "Any"} → {item.effective_to || "Open"}</td>
  </>;
  return <>
    <td><strong>{item.referenced_document?.code || "Referenced document"}</strong><small>{item.referenced_document?.title || item.exact_token || "Version-specific relationship"}</small></td>
    <td><DocumentControlStatus status={item.status} kind="danger" /><small>{item.relationship_type?.replaceAll("_", " ")}</small></td>
    <td>{item.page_number ? `Page ${item.page_number}` : item.section_label || "Document level"}</td>
  </>;
}

export default function DocumentControlCompliancePortfolioPage() {
  const navigate = useNavigate();
  const { tenant } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [data, setData] = useState<CompliancePortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const hasLoadedRef = useRef(false);
  const view = (params.get("view") as CompliancePortfolioView) || "reviews";
  const page = Math.max(1, Number(params.get("page") || 1));
  const perPage = Math.min(100, Math.max(25, Number(params.get("per_page") || 50)));

  const load = useCallback(async () => {
    if (!tenant) return;
    const initial = !hasLoadedRef.current;
    setLoading(initial);
    setRefreshing(!initial);
    setError("");
    try {
      const next = await getCompliancePortfolio(tenant, {
        view,
        q: params.get("q") || undefined,
        status: params.get("status") || undefined,
        page,
        perPage,
      });
      setData(next);
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The compliance workspace could not be loaded.");
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
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / data.pagination.per_page)) : 1;
  const viewMeta = useMemo(() => VIEWS.find((item) => item.id === view) || VIEWS[0], [view]);

  return <DocumentControlShell
    title="Compliance"
    eyebrow="DOCUMENT ASSURANCE"
    subtitle="Review due dates, external-source currentness, governed relationships, applicability and superseded references without inventing a compliance score."
    canControl
    actions={<button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>}
  >
    <section className="dms-compliance" data-testid="document-control-compliance" aria-busy={refreshing}>
      <nav className="dms-compliance__views" aria-label="Document assurance views">
        {VIEWS.map(({ id, label, icon: Icon }) => {
          const active = view === id;
          const count = Number(data?.facets?.[id] || 0);
          return <button type="button" key={id} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => update("view", id)}><Icon size={14} /><span>{label}</span>{count > 0 ? <small>{count}</small> : null}</button>;
        })}
      </nav>

      <div className="dms-compliance__toolbar">
        <label><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={`Search ${viewMeta.label.toLowerCase()}`} /></label>
        {view !== "superseded-references" ? <select aria-label="Filter assurance status" value={params.get("status") || ""} onChange={(event) => update("status", event.target.value)}>
          <option value="">Default actionable states</option>
          <option value="SCHEDULED">Scheduled</option><option value="IN_PROGRESS">In progress</option><option value="COMPLETED">Completed</option>
          <option value="ACTIVE">Active</option><option value="UNRESOLVED">Unresolved</option><option value="PROPOSED">Proposed</option><option value="CONFIRMED">Confirmed</option>
        </select> : null}
        {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
      </div>

      {loading ? <DocumentControlLoading label="Loading bounded document-assurance records…" /> : null}
      {error && !data ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {error && data ? <div className="dms-compliance__notice" role="alert"><AlertTriangle size={15} /><span>The latest assurance update could not be loaded. The last available results remain visible.</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}
      {!loading && data && !data.items.length ? <DocumentControlEmpty icon={CheckCircle2} title={`No ${viewMeta.label.toLowerCase()} items`} message="No authoritative record matches this assurance view and filter." /> : null}

      {!loading && data?.items.length ? <div className="dc-table-wrap dms-compliance__table-wrap"><table className="dc-table dms-compliance__table">
        <thead><tr><th>Document</th><th>{view === "reviews" ? "Owner / outcome" : view === "external-sources" ? "Source" : view === "applicability" ? "Rule / target" : view === "superseded-references" ? "Referenced document" : "Relationship"}</th><th>Status</th><th>{view === "reviews" ? "Due" : view === "external-sources" ? "Currency check" : view === "applicability" ? "Effectivity" : "Location"}</th><th>Action</th></tr></thead>
        <tbody>{data.items.map((item) => <tr key={`${item.kind}:${item.id}`}><td>{documentCell(item)}</td>{detailCells(item)}<td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}>Open context <ArrowRight size={14} /></button></td></tr>)}</tbody>
      </table></div> : null}

      {data ? <footer className="dms-compliance__pagination">
        <span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 records"}</span>
        <select aria-label="Assurance records per page" value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={data.pagination.page <= 1 || refreshing} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={14} /> Previous</button>
        <span>Page {data.pagination.page} of {totalPages}</span>
        <button type="button" disabled={data.pagination.page >= totalPages || refreshing} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={14} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}

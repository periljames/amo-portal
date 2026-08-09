import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileDiff,
  Landmark,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getChangesPortfolio,
  type ChangesPortfolioResponse,
  type ChangesPortfolioView,
} from "../../services/documentControlPortfolios";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./dmsChangesPortfolio.css";

const SEARCH_DEBOUNCE_MS = 320;

const VIEWS: Array<{ id: ChangesPortfolioView; label: string; icon: typeof FileDiff }> = [
  { id: "my-changes", label: "My Changes", icon: UserRound },
  { id: "requests", label: "Requests", icon: ClipboardList },
  { id: "draft", label: "Draft", icon: FileDiff },
  { id: "in-review", label: "In Review", icon: FileDiff },
  { id: "awaiting-quality", label: "Awaiting Quality", icon: ShieldCheck },
  { id: "awaiting-management", label: "Awaiting Management", icon: ShieldCheck },
  { id: "authority", label: "Authority", icon: Landmark },
  { id: "temporary-revisions", label: "Temporary Revisions", icon: AlertTriangle },
  { id: "ready-for-release", label: "Ready for Release", icon: CheckCircle2 },
  { id: "closed", label: "Closed", icon: CheckCircle2 },
];

function statusKind(value?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["PUBLISHED", "ARCHIVED", "APPROVED", "ACCEPTED", "READY", "CLOSED"].includes(status)) return "success";
  if (["BLOCKED", "OVERDUE", "REJECTED", "EXPIRED", "WITHDRAWN", "CORRECTIONS_REQUIRED"].includes(status)) return "danger";
  if (["DRAFT", "PENDING", "OPEN", "QUERY_RECEIVED"].includes(status)) return "warning";
  if (["ACTION", "TECHNICAL_REVIEW", "QUALITY_REVIEW", "ACCOUNTABLE_MANAGER_APPROVAL", "AUTHORITY_SUBMITTED", "SCHEDULED_FOR_EFFECTIVITY"].includes(status)) return "info";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function DocumentControlChangesPortfolioPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [data, setData] = useState<ChangesPortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const hasLoadedRef = useRef(false);

  const requestedView = params.get("view") as ChangesPortfolioView | null;
  const view: ChangesPortfolioView = VIEWS.some((candidate) => candidate.id === requestedView) ? requestedView as ChangesPortfolioView : "my-changes";
  const page = Math.max(1, Number(params.get("page") || 1));
  const perPage = Math.min(100, Math.max(25, Number(params.get("per_page") || 50)));

  const load = useCallback(async () => {
    if (!tenant) return;
    const initial = !hasLoadedRef.current;
    setLoading(initial);
    setRefreshing(!initial);
    setError("");
    try {
      const next = await getChangesPortfolio(tenant, {
        view,
        q: params.get("q") || undefined,
        status: params.get("status") || undefined,
        page,
        perPage,
      });
      setData(next);
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The changes portfolio could not be loaded.");
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
    if (key === "view") next.delete("status");
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / data.pagination.per_page)) : 1;
  const viewMeta = useMemo(() => VIEWS.find((item) => item.id === view) || VIEWS[0], [view]);

  return <DocumentControlShell
    title="Changes"
    eyebrow="DOCUMENT LIFECYCLE"
    subtitle="Change requests, revision workflows, temporary revisions and authority stages presented as one controlled lifecycle."
    canControl
    actions={<>
      <button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>
      <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library?action=raise-change`)}><ClipboardList size={14} /> Raise change request</button>
    </>}
  >
    <section className="dms-changes" data-testid="document-control-changes" aria-busy={refreshing}>
      <nav className="dms-changes__views" aria-label="Change lifecycle views">
        {VIEWS.map(({ id, label, icon: Icon }) => {
          const active = view === id;
          const count = Number(data?.facets?.[id] || 0);
          return <button type="button" key={id} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => update("view", id)}><Icon size={14} /><span>{label}</span>{count > 0 ? <small>{count}</small> : null}</button>;
        })}
      </nav>

      <div className="dms-changes__toolbar">
        <label><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={`Search ${viewMeta.label.toLowerCase()} by document or reference`} /></label>
        <select aria-label="Filter by exact status" value={params.get("status") || ""} onChange={(event) => update("status", event.target.value)}>
          <option value="">All statuses in this view</option>
          <option value="DRAFT">Draft</option>
          <option value="OPEN">Open</option>
          <option value="TECHNICAL_REVIEW">Technical review</option>
          <option value="QUALITY_REVIEW">Quality review</option>
          <option value="ACCOUNTABLE_MANAGER_APPROVAL">Management approval</option>
          <option value="AUTHORITY_SUBMITTED">Authority submitted</option>
          <option value="SCHEDULED_FOR_EFFECTIVITY">Scheduled for effectivity</option>
          <option value="PUBLISHED">Published</option>
        </select>
        {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
      </div>

      {loading ? <DocumentControlLoading label="Loading bounded change portfolio…" /> : null}
      {error && !data ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {error && data ? <div className="dms-changes__notice" role="alert"><AlertTriangle size={15} /><span>The latest portfolio update could not be loaded. The last available results remain visible.</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}
      {!loading && data && !data.items.length ? <DocumentControlEmpty icon={CheckCircle2} title={`No ${viewMeta.label.toLowerCase()} items`} message="No authoritative record matches this lifecycle view and filter." /> : null}

      {!loading && data?.items.length ? <div className="dc-table-wrap dms-changes__table-wrap"><table className="dc-table dms-changes__table">
        <thead><tr><th>Document</th><th>Change / revision</th><th>Stage</th><th>Impact</th><th>Due / effectivity</th><th>Action</th></tr></thead>
        <tbody>{data.items.map((item) => <tr key={`${item.kind}:${item.id}`}>
          <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
          <td><strong>{item.title}</strong><small>{item.subtitle || item.source}</small></td>
          <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.kind.replaceAll("_", " ")}</small></td>
          <td><div className="dms-changes__impact">{item.qms_blocking ? <DocumentControlStatus status="QMS blocking" kind="danger" /> : null}{item.training_impact_required ? <DocumentControlStatus status="Training impact" kind="warning" /> : null}{item.requires_authority ? <DocumentControlStatus status="Authority required" kind="info" /> : null}{!item.qms_blocking && !item.training_impact_required && !item.requires_authority ? <span>—</span> : null}</div></td>
          <td><strong>{formatDate(item.due_at)}</strong><small>Updated {formatDate(item.updated_at)}</small></td>
          <td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}>Open <ArrowRight size={14} /></button></td>
        </tr>)}</tbody>
      </table></div> : null}

      {data ? <footer className="dms-changes__pagination">
        <span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 items"}</span>
        <select aria-label="Items per page" value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={data.pagination.page <= 1 || refreshing} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={14} /> Previous</button>
        <span>Page {data.pagination.page} of {totalPages}</span>
        <button type="button" disabled={data.pagination.page >= totalPages || refreshing} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={14} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}

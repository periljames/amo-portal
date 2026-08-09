import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Copy,
  PackageCheck,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getDistributionPortfolio,
  type ControlledCopyPortfolioItem,
  type DistributionAcknowledgementPortfolioItem,
  type DistributionCampaignPortfolioItem,
  type DistributionPortfolioResponse,
  type DistributionPortfolioView,
} from "../../services/documentControlDistributionPortfolio";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./dmsDistributionPortfolio.css";

const SEARCH_DEBOUNCE_MS = 320;

const VIEWS: Array<{ id: DistributionPortfolioView; label: string; icon: typeof Send }> = [
  { id: "campaigns", label: "Current Distributions", icon: Send },
  { id: "pending-acknowledgements", label: "Pending Acknowledgements", icon: ClipboardCheck },
  { id: "overdue-acknowledgements", label: "Overdue Acknowledgements", icon: AlertTriangle },
  { id: "physical-copies", label: "Physical Copies", icon: Copy },
  { id: "recalls", label: "Recalls", icon: RotateCcw },
];

function statusKind(value?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["COMPLETED", "ACKNOWLEDGED", "RETURNED", "ON_SHELF"].includes(status)) return "success";
  if (["OVERDUE", "RECALLED", "WITHDRAWN", "DESTROYED"].includes(status)) return "danger";
  if (["DRAFT", "PENDING", "ISSUED"].includes(status)) return "warning";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function isCampaign(item: DistributionPortfolioResponse["items"][number]): item is DistributionCampaignPortfolioItem {
  return item.kind === "CAMPAIGN";
}

function isAcknowledgement(item: DistributionPortfolioResponse["items"][number]): item is DistributionAcknowledgementPortfolioItem {
  return item.kind === "ACKNOWLEDGEMENT";
}

function isCopy(item: DistributionPortfolioResponse["items"][number]): item is ControlledCopyPortfolioItem {
  return item.kind === "CONTROLLED_COPY";
}

export default function DocumentControlDistributionPortfolioPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [data, setData] = useState<DistributionPortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const hasLoadedRef = useRef(false);

  const view = (params.get("view") as DistributionPortfolioView) || "campaigns";
  const page = Math.max(1, Number(params.get("page") || 1));
  const perPage = Math.min(100, Math.max(25, Number(params.get("per_page") || 50)));

  const load = useCallback(async () => {
    if (!tenant) return;
    const initial = !hasLoadedRef.current;
    setLoading(initial);
    setRefreshing(!initial);
    setError("");
    try {
      const next = await getDistributionPortfolio(tenant, {
        view,
        q: params.get("q") || undefined,
        status: params.get("status") || undefined,
        page,
        perPage,
      });
      setData(next);
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The distribution workspace could not be loaded.");
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
    title="Distribution"
    eyebrow="CONTROLLED ISSUE & CUSTODY"
    subtitle="Digital issue, acknowledgement follow-up and numbered physical-copy custody in one operating workspace."
    canControl
    actions={<>
      <button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>
      <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/controlled-copies`)}><Copy size={14} /> Copy operations</button>
      <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library`)}><Send size={14} /> Choose document to distribute</button>
    </>}
  >
    <section className="dms-distribution" data-testid="document-control-distribution" aria-busy={refreshing}>
      <nav className="dms-distribution__views" aria-label="Distribution views">
        {VIEWS.map(({ id, label, icon: Icon }) => {
          const active = view === id;
          const count = Number(data?.facets?.[id] || 0);
          return <button type="button" key={id} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => update("view", id)}><Icon size={14} /><span>{label}</span>{count > 0 ? <small>{count}</small> : null}</button>;
        })}
      </nav>

      <div className="dms-distribution__toolbar">
        <label><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={`Search ${viewMeta.label.toLowerCase()} by document${view === "physical-copies" || view === "recalls" ? ", copy or location" : ""}`} /></label>
        {(view === "campaigns" || view === "physical-copies") ? <select aria-label="Filter distribution status" value={params.get("status") || ""} onChange={(event) => update("status", event.target.value)}>
          <option value="">All states</option>
          {view === "campaigns" ? <><option value="DRAFT">Draft</option><option value="ISSUED">Issued</option><option value="COMPLETED">Completed</option></> : <><option value="ISSUED">Issued / checked out</option><option value="RETURNED">Returned / on shelf</option><option value="RECALLED">Recalled</option><option value="WITHDRAWN">Withdrawn</option></>}
        </select> : null}
        {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
      </div>

      {loading ? <DocumentControlLoading label="Loading bounded distribution records…" /> : null}
      {error && !data ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {error && data ? <div className="dms-distribution__notice" role="alert"><AlertTriangle size={15} /><span>The latest distribution update could not be loaded. The last available records remain visible.</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}
      {!loading && data && !data.items.length ? <DocumentControlEmpty icon={CheckCircle2} title={`No ${viewMeta.label.toLowerCase()}`} message="No authoritative record matches this distribution view and filter." /> : null}

      {!loading && data?.items.length ? <div className="dc-table-wrap dms-distribution__table-wrap"><table className="dc-table dms-distribution__table">
        <thead><tr>{view === "campaigns" ? <><th>Document</th><th>Distribution</th><th>State</th><th>Recipients</th><th>Due</th><th>Action</th></> : view === "pending-acknowledgements" || view === "overdue-acknowledgements" ? <><th>Document</th><th>Recipient</th><th>Campaign</th><th>State</th><th>Due</th><th>Action</th></> : <><th>Document</th><th>Copy</th><th>Custody</th><th>Location</th><th>Due back</th><th>Action</th></>}</tr></thead>
        <tbody>{data.items.map((item) => {
          if (isCampaign(item)) return <tr key={item.id}>
            <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
            <td><strong>{item.title}</strong><small>{item.acknowledgement_required ? "Acknowledgement required" : "Delivery evidence only"}</small></td>
            <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.issued_at ? `Issued ${formatDate(item.issued_at)}` : "Not issued"}</small></td>
            <td><div className="dms-distribution__recipient-grid"><span><b>{item.recipients.total}</b> total</span><span><b>{item.recipients.acknowledged}</b> acknowledged</span><span><b>{item.recipients.pending}</b> pending</span>{item.recipients.overdue > 0 ? <span className="danger"><b>{item.recipients.overdue}</b> overdue</span> : null}</div></td>
            <td>{formatDate(item.due_at)}</td>
            <td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}>Open <ArrowRight size={14} /></button></td>
          </tr>;
          if (isAcknowledgement(item)) return <tr key={item.id}>
            <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
            <td><strong>{item.recipient.name}</strong><small>{item.notified_at ? `Issued ${formatDate(item.notified_at)}` : "Notified date unavailable"}</small></td>
            <td><strong>{item.title}</strong><small>{item.reminder_count} reminder{item.reminder_count === 1 ? "" : "s"}</small></td>
            <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /></td>
            <td>{formatDate(item.due_at)}</td>
            <td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}>Open campaign <ArrowRight size={14} /></button></td>
          </tr>;
          if (isCopy(item)) return <tr key={item.id}>
            <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
            <td><strong>{item.copy_number}</strong><small>{item.format.replaceAll("_", " ")}</small></td>
            <td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /><small>{item.holder || (item.custody_status === "RETURNED" ? "On shelf" : "No holder recorded")}</small></td>
            <td><strong>{item.location}</strong><small>{item.issued_at ? `Registered ${formatDate(item.issued_at)}` : ""}</small></td>
            <td>{formatDate(item.due_at)}</td>
            <td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}><PackageCheck size={14} /> Open custody</button></td>
          </tr>;
          return null;
        })}</tbody>
      </table></div> : null}

      {data ? <footer className="dms-distribution__pagination">
        <span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 records"}</span>
        <select aria-label="Distribution records per page" value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={data.pagination.page <= 1 || refreshing} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={14} /> Previous</button>
        <span>Page {data.pagination.page} of {totalPages}</span>
        <button type="button" disabled={data.pagination.page >= totalPages || refreshing} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={14} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}

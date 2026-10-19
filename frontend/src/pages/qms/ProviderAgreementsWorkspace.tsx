import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, ExternalLink, FileText, RefreshCw, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  getProviderAgreementRegister,
  type ProviderAgreementRegister,
  type ProviderAgreementRegisterItem,
} from "../../services/qmsProviders";

const STATUSES = ["ALL", "DRAFT", "ACTIVE", "SUSPENDED", "EXPIRED", "TERMINATED", "SUPERSEDED"] as const;
const PAGE_SIZE = 40;

function label(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function dateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}
function problem(row: ProviderAgreementRegisterItem): string {
  switch (row.attention) {
    case "EXECUTED_EVIDENCE_REQUIRED": return "Signed original and exact DMS link required";
    case "QUALITY_REVIEW_REQUIRED": return "Quality verification pending";
    case "EXPIRED": return "Expired — not valid for new work";
    case "SUSPENDED": return "Suspended — new work blocked";
    case "RENEWAL_DUE": return "Renewal / notice window due";
    default: return "No current renewal alert";
  }
}

/** Read-only QMS contract index. Decisions remain on the governed provider record. */
export default function ProviderAgreementsWorkspace({
  amoCode,
  onBack,
}: {
  amoCode: string;
  onBack: () => void;
}) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUSES)[number]>("ALL");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<ProviderAgreementRegister | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentRequest = useRef(0);
  const manager = hasQmsRolePermission("qms.supplier.manage");

  const reload = useCallback(() => setRevision((current) => current + 1), []);
  useEffect(() => {
    let active = true;
    const sequence = ++currentRequest.current;
    const handle = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void getProviderAgreementRegister(amoCode, {
        search, status: statusFilter, attentionOnly, days,
        limit: PAGE_SIZE, offset: page * PAGE_SIZE,
      }).then((next) => {
        if (active && sequence === currentRequest.current) setResult(next);
      }).catch((cause: unknown) => {
        if (active && sequence === currentRequest.current) {
          setError(cause instanceof Error ? cause.message : "Unable to load governed agreements");
          setResult(null);
        }
      }).finally(() => {
        if (active && sequence === currentRequest.current) setLoading(false);
      });
    }, search ? 250 : 0);
    return () => { active = false; ++currentRequest.current; window.clearTimeout(handle); };
  }, [amoCode, search, statusFilter, attentionOnly, days, page, revision]);

  const providerBase = `/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers`;
  return <main className="qms-provider-page qms-surface-root" aria-label="Agreements and renewals">
    <header className="qms-provider-page__header">
      <div>
        <p className="qms-provider-eyebrow">Quality governance · shared contractual records</p>
        <h1>Agreements & renewals</h1>
        <p>All providers share the QMS agreement register. Procurement references the same contract, DMS retains the controlled signed original, and external members receive only specifically granted revisions. A provider receipt is not a signature.</p>
      </div>
      <div className="qms-provider-page__actions">
        <button type="button" className="qms-provider-button is-secondary" onClick={onBack}><ArrowLeft size={16} />Providers</button>
        <button type="button" className="qms-provider-button is-secondary" onClick={reload} disabled={loading}><RefreshCw size={16} />Refresh</button>
      </div>
    </header>
    {!manager && <p role="note">Read-only access: contractual decisions require explicit Quality management authorization.</p>}
    <section className="qms-provider-register" aria-label="Governed agreement register">
      <div className="qms-provider-toolbar">
        <label className="qms-provider-search"><Search size={16} /><input type="search" aria-label="Search agreements" placeholder="Agreement number, title or provider" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
        <label>Agreement state
          <select aria-label="Agreement status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as (typeof STATUSES)[number]); setPage(0); }}>
            {STATUSES.map((status) => <option value={status} key={status}>{status === "ALL" ? "All statuses" : label(status)}</option>)}
          </select>
        </label>
        <label>Expiry horizon
          <select aria-label="Renewal window" value={days} onChange={(event) => { setDays(Number(event.target.value)); setPage(0); }}>
            {[0, 7, 30, 60, 90, 180, 365].map((value) => <option value={value} key={value}>{value} days</option>)}
          </select>
        </label>
        <label><input type="checkbox" checked={attentionOnly} onChange={(event) => { setAttentionOnly(event.target.checked); setPage(0); }} /> Attention only</label>
      </div>
      {loading && <p role="status" className="qms-provider-loading"><RefreshCw size={16} className="is-spinning" />Loading controlled agreements…</p>}
      {error && <div className="qms-provider-alert is-error" role="alert"><AlertTriangle size={16} />{error}<button type="button" onClick={reload}>Retry</button></div>}
      {!loading && !error && result && <>
        <p role="status" aria-live="polite">{result.total} agreement{result.total === 1 ? "" : "s"} match · QMS source as of {dateLabel(result.as_of)}.</p>
        <div className="qms-provider-table-wrap">
          <table className="qms-provider-table">
            <thead><tr><th>Provider</th><th>Agreement</th><th>Status</th><th>Effective / expires</th><th>Notice deadline</th><th>Controlled original</th><th>Quality action</th></tr></thead>
            <tbody>
              {result.items.map((row) => <tr key={row.id}>
                <td><strong>{row.legal_name}</strong><span>{row.supplier_code} · {label(row.provider_kind || "SUPPLIER")}</span></td>
                <td><strong>{row.contract_number}</strong><span>{row.title}</span>{row.supersedes_contract_id && <small>Amendment or renewal of {row.supersedes_contract_id}</small>}</td>
                <td><strong>{label(row.effective_status)}</strong><span>{label(row.provider_status)}</span></td>
                <td>{dateLabel(row.effective_on)} / {dateLabel(row.expires_on)}{row.days_until_expiry !== null && <small>{row.days_until_expiry} days until expiry</small>}</td>
                <td>{dateLabel(row.renewal_notice_on)}</td>
                <td><FileText size={15} aria-hidden="true" /> {row.controlled_original_linked ? "Records linked; Quality verification still required" : "Executed evidence incomplete"}</td>
                <td><div>{problem(row)}</div><Link to={`${providerBase}/${row.supplier_id}/contracts`} aria-label={`Open QMS agreement ${row.contract_number} for ${row.legal_name}`}>Open QMS record <ExternalLink size={14} aria-hidden="true" /></Link></td>
              </tr>)}
              {result.items.length === 0 && <tr><td colSpan={7}>No agreements match this tenant and filter. Change the filter or create a draft from an authorized provider record.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="qms-provider-page__actions">
          <button type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</button>
          <span>Page {page + 1} · {result.total} total</span>
          <button type="button" disabled={!result.has_more} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
      </>}
    </section>
  </main>;
}

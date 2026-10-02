import { useEffect, useMemo, useState } from "react";
import { Archive, BookOpen, Boxes, FileSearch, LibraryBig, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  searchTenantWarehouse,
  type WarehouseSearchResponse,
  type WarehouseSearchResult,
  type WarehouseSearchScope,
} from "../../services/documentLibrary";
import { prefetchPublicationReader } from "../../services/publications";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";

const SEARCH_DEBOUNCE_MS = 280;
const RECENT_SEARCHES_KEY = "amo.dms.search.recent.v1";
const SCOPES: Array<{ id: WarehouseSearchScope; label: string }> = [
  { id: "everything", label: "Everything" },
  { id: "repository", label: "Controlled information" },
  { id: "library", label: "Physical library" },
  { id: "records", label: "Records" },
  { id: "external", label: "External" },
];

function recentSearches(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(RECENT_SEARCHES_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string").slice(0, 6) : [];
  } catch {
    return [];
  }
}

function saveRecentSearch(query: string): void {
  if (typeof window === "undefined" || !query.trim()) return;
  const next = [query.trim(), ...recentSearches().filter((item) => item.toLowerCase() !== query.trim().toLowerCase())].slice(0, 6);
  window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
}

function highlight(text: string | null | undefined, query: string) {
  const source = String(text || "");
  const needle = query.trim();
  if (!needle) return source;
  const lower = source.toLowerCase();
  const index = lower.indexOf(needle.toLowerCase());
  if (index < 0) return source;
  return <>
    {source.slice(0, index)}
    <mark>{source.slice(index, index + needle.length)}</mark>
    {source.slice(index + needle.length)}
  </>;
}

function resultIdentity(item: WarehouseSearchResult): string {
  return item.code || item.record_number || item.series_code || item.catalogue_code || item.resource_type || item.kind.replaceAll("_", " ");
}

function ResultGroup({
  title,
  icon: Icon,
  items,
  query,
  tenant,
  onOpen,
}: {
  title: string;
  icon: typeof BookOpen;
  items: WarehouseSearchResult[];
  query: string;
  tenant: string;
  onOpen: (item: WarehouseSearchResult) => void;
}) {
  return <section className="dms-search-group">
    <header><span><Icon size={16} /><strong>{title}</strong></span><small>{items.length} result{items.length === 1 ? "" : "s"}</small></header>
    {items.map((item) => <button
      type="button"
      key={`${item.kind}:${item.id}:${item.heading || item.record_number || item.catalogue_code || ""}`}
      className="dms-search-result"
      disabled={!item.target_path}
      onMouseEnter={() => {
        if (item.kind === "CONTROLLED_DOCUMENT" && item.revision_id) prefetchPublicationReader(tenant, item.id, item.revision_id);
      }}
      onFocus={() => {
        if (item.kind === "CONTROLLED_DOCUMENT" && item.revision_id) prefetchPublicationReader(tenant, item.id, item.revision_id);
      }}
      onClick={() => onOpen(item)}
    >
      <span className="dms-search-result__identity"><small>{resultIdentity(item)}</small><strong>{highlight(item.title, query)}</strong></span>
      {item.heading ? <span className="dms-search-result__location">{highlight(item.heading, query)}{item.page_number ? ` · page ${item.page_number}` : ""}</span> : null}
      {item.snippet ? <p>{highlight(item.snippet, query)}</p> : null}
      {item.status || item.disposition_status ? <em>{String(item.status || item.disposition_status).replaceAll("_", " ")}</em> : null}
    </button>)}
    {!items.length ? <p className="dms-search-group__empty">No authorized matches in this scope.</p> : null}
  </section>;
}

export default function DocumentControlSearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { tenant } = useDocumentControlRoute();
  const query = params.get("q") || "";
  const rawScope = params.get("scope") as WarehouseSearchScope | null;
  const scope = SCOPES.some((item) => item.id === rawScope) ? rawScope as WarehouseSearchScope : "everything";
  const [input, setInput] = useState(query);
  const [result, setResult] = useState<WarehouseSearchResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(query.trim()));
  const [error, setError] = useState("");
  const [recent, setRecent] = useState<string[]>(() => recentSearches());

  useEffect(() => { setInput(query); }, [query]);

  useEffect(() => {
    if (input === query) return;
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      const value = input.trim();
      if (value) next.set("q", value); else next.delete("q");
      setParams(next, { replace: true });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [input, params, query, setParams]);

  useEffect(() => {
    if (!tenant || !query.trim()) {
      setResult(null);
      setLoading(false);
      setError("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    void searchTenantWarehouse(tenant, query.trim(), 20, scope)
      .then((response) => {
        if (cancelled) return;
        setResult(response);
        saveRecentSearch(query);
        setRecent(recentSearches());
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Search could not be completed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [query, scope, tenant]);

  const total = useMemo(() => result
    ? Object.values(result.counts).reduce((sum, value) => sum + Number(value || 0), 0)
    : 0, [result]);

  const chooseScope = (value: WarehouseSearchScope) => {
    const next = new URLSearchParams(params);
    if (value === "everything") next.delete("scope"); else next.set("scope", value);
    setParams(next);
  };

  const openResult = (item: WarehouseSearchResult) => {
    if (item.target_path) navigate(item.target_path);
  };

  return <DocumentControlShell
    title="Search company information"
    eyebrow="DISCOVERY"
    subtitle="Search authorized controlled documents, indexed content, retained records and physical-library materials from one permission-filtered surface."
    canControl={Boolean(result?.capabilities.control)}
  >
    <section className="dms-search" aria-busy={loading}>
      <label className="dms-search__box">
        <Search size={18} />
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Document code, title, filename, clause, record number, ISBN, author or indexed text"
          aria-label="Search company information"
          autoFocus
        />
      </label>

      <div className="dms-search__scopes" role="group" aria-label="Search scope">
        {SCOPES.map((item) => <button type="button" key={item.id} className={scope === item.id ? "active" : ""} onClick={() => chooseScope(item.id)}>{item.label}</button>)}
      </div>

      {!query.trim() && recent.length ? <section className="dms-search__recent">
        <strong>Recent searches</strong>
        <div>{recent.map((item) => <button type="button" key={item} onClick={() => { const next = new URLSearchParams(params); next.set("q", item); setParams(next); }}>{item}</button>)}</div>
      </section> : null}

      {loading ? <DocumentControlLoading label="Searching authorized company information…" /> : null}
      {error && !loading ? <DocumentControlError message={error} /> : null}
      {!loading && query.trim() && result && total === 0 ? <DocumentControlEmpty icon={FileSearch} title="No authorized matches" message="Try a broader term or another scope. Restricted content is not disclosed through result counts or suggestions." /> : null}

      {!loading && result && total > 0 ? <>
        <div className="dms-search__summary"><strong>{total} authorized result{total === 1 ? "" : "s"}</strong><span>Search scope: {SCOPES.find((item) => item.id === scope)?.label}</span></div>
        <div className="dms-search__groups">
          <ResultGroup title="Controlled information" icon={BookOpen} items={result.groups.controlled_documents} query={query} tenant={tenant} onOpen={openResult} />
          <ResultGroup title="Governed resources" icon={Boxes} items={result.groups.governed_resources} query={query} tenant={tenant} onOpen={openResult} />
          <ResultGroup title="Physical library" icon={LibraryBig} items={result.groups.library_items} query={query} tenant={tenant} onOpen={openResult} />
          <ResultGroup title="Retained records" icon={Archive} items={result.groups.retained_records} query={query} tenant={tenant} onOpen={openResult} />
        </div>
      </> : null}

      {result?.internet.enabled && scope === "external" ? <div className="dms-search__external">
        <strong>External search</strong>
        <p>{result.internet.privacy}</p>
        <div>{Object.entries(result.internet.links).map(([label, href]) => <a key={label} href={href} target="_blank" rel="noreferrer">{label.replaceAll("_", " ")}</a>)}</div>
      </div> : null}
    </section>
  </DocumentControlShell>;
}

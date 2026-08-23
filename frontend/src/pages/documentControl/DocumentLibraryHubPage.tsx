import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  BookMarked,
  BookOpen,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Copy,
  FileCheck2,
  FileText,
  FilterX,
  Heart,
  History,
  Link2,
  Search,
  ShieldCheck,
  UserRound,
  Workflow,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  discoverLibrary,
  listIntegratedLibrary,
  type IntegratedLibraryFilters,
  type IntegratedLibraryItem,
  type IntegratedLibraryResponse,
  type LibraryDiscoveryItem,
  type LibraryDiscoveryResponse,
  type LibraryDiscoveryView,
} from "../../services/documentLibrary";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import {
  documentControlJob,
  documentJobTarget,
  type DocumentControlJob,
} from "./documentControlJobs";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";

const CATEGORIES = [
  ["", "All", BookOpen],
  ["POLICY", "Policies", ShieldCheck],
  ["MANUAL", "Manuals", BookOpen],
  ["PROCEDURE", "Procedures", Workflow],
  ["WORK_INSTRUCTION", "Work instructions", ClipboardCheck],
  ["FORM", "Forms", FileText],
  ["CHECKLIST", "Checklists", FileCheck2],
  ["REGISTER", "Registers", Archive],
  ["EXTERNAL_DOCUMENT", "External data", Boxes],
] as const;

const PRESETS: Array<{ id: LibraryDiscoveryView | ""; label: string; icon: typeof BookOpen }> = [
  { id: "", label: "All Documents", icon: BookOpen },
  { id: "my-documents", label: "My Documents", icon: UserRound },
  { id: "favorites", label: "Favorites", icon: Heart },
  { id: "recently-opened", label: "Recently Opened", icon: Clock3 },
  { id: "recently-revised", label: "Recently Revised", icon: History },
  { id: "awaiting-my-review", label: "Awaiting My Review", icon: ClipboardCheck },
  { id: "external-technical-data", label: "External Technical Data", icon: Boxes },
  { id: "due-for-review", label: "Due for Review", icon: ShieldCheck },
  { id: "superseded", label: "Superseded", icon: BookMarked },
  { id: "archived", label: "Archived", icon: Archive },
];

const SEARCH_DEBOUNCE_MS = 320;

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "ACTIVE", "CURRENT", "RETURNED"].includes(value)) return "success";
  if (["SUPERSEDED", "ARCHIVED", "WITHDRAWN", "OVERDUE", "RECALLED"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "UNVERIFIED", "ISSUED"].includes(value)) return "warning";
  return "neutral";
}

function revisionText(item: IntegratedLibraryItem): string {
  const revision = item.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
}

function discoveryRevisionText(item: LibraryDiscoveryItem): string {
  const revision = item.current_revision || item.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
}

function physicalText(item: IntegratedLibraryItem): string {
  const physical = item.library.physical;
  if (!physical.total) return "No physical copy";
  const parts: string[] = [];
  if (physical.on_shelf) parts.push(`${physical.on_shelf} on shelf`);
  if (physical.checked_out) parts.push(`${physical.checked_out} with staff`);
  if (physical.recalled) parts.push(`${physical.recalled} recalled`);
  return parts.join(" · ") || `${physical.total} registered`;
}

function truthy(value: string | null): boolean {
  return value === "1" || value?.toLowerCase() === "true";
}

function queueLabel(params: URLSearchParams): string | null {
  if (truthy(params.get("unresolved_ownership"))) return "Ownership requiring confirmation";
  if (truthy(params.get("unresolved_relationships"))) return "Document relationships requiring review";
  if (params.get("indexing_status")) return `Indexing status: ${params.get("indexing_status")?.replaceAll("_", " ")}`;
  if (params.get("structure_status")) return `Structure status: ${params.get("structure_status")?.replaceAll("_", " ")}`;
  if (truthy(params.get("superseded_referenced"))) return "Superseded documents still referenced";
  if (params.get("owner_user_id")) return "Filtered by document owner";
  if (params.get("department_id")) return "Filtered by responsible department";
  return null;
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], value.length === 10 ? { dateStyle: "medium" } : { dateStyle: "medium", timeStyle: "short" });
}

function jobEligibility(item: IntegratedLibraryItem, job: DocumentControlJob): { allowed: boolean; reason?: string } {
  if (job.requiresPublished && item.read_target.kind !== "PUBLISHED") return { allowed: false, reason: "A published revision is required" };
  if (job.externalOnly && item.profile.document_class !== "EXTERNAL") return { allowed: false, reason: "External controlled documents only" };
  return { allowed: true };
}

export default function DocumentLibraryHubPage() {
  const navigate = useNavigate();
  const { tenant, basePath, readerBasePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") || "";
  const [searchText, setSearchText] = useState(urlQuery);
  const [data, setData] = useState<IntegratedLibraryResponse | null>(null);
  const [discoveryData, setDiscoveryData] = useState<LibraryDiscoveryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const hasLoadedRef = useRef(false);

  const filters = useMemo<IntegratedLibraryFilters>(() => ({
    q: params.get("q") || undefined,
    nodeType: params.get("type") || undefined,
    documentClass: params.get("class") || params.get("control_status") || undefined,
    status: params.get("status") || params.get("lifecycle_status") || undefined,
    ownerUserId: params.get("owner_user_id") || undefined,
    departmentId: params.get("department_id") || undefined,
    indexingStatus: params.get("indexing_status") || undefined,
    unresolvedOwnership: truthy(params.get("unresolved_ownership")),
    unresolvedRelationships: truthy(params.get("unresolved_relationships")),
    structureStatus: params.get("structure_status") || undefined,
    supersededReferenced: truthy(params.get("superseded_referenced")),
    sort: (params.get("sort") as IntegratedLibraryFilters["sort"]) || "code",
    direction: (params.get("direction") as IntegratedLibraryFilters["direction"]) || "asc",
    page: Math.max(1, Number(params.get("page") || 1)),
    perPage: Math.min(100, Math.max(25, Number(params.get("per_page") || 50))),
  }), [params]);

  const activeQueue = useMemo(() => queueLabel(params), [params]);
  const selectingChangeDocument = params.get("action") === "raise-change";
  const selectedJob = useMemo(() => documentControlJob(params.get("action")), [params]);
  const selectingDocumentForJob = Boolean(selectedJob);
  const requestedView = params.get("view") as LibraryDiscoveryView | null;
  const discoveryView: LibraryDiscoveryView = PRESETS.some((preset) => preset.id === requestedView) ? requestedView as LibraryDiscoveryView : "all";
  const hasIntegratedFilters = Boolean(filters.nodeType || filters.documentClass || filters.status || filters.ownerUserId || filters.departmentId || filters.indexingStatus || filters.unresolvedOwnership || filters.unresolvedRelationships || filters.structureStatus || filters.supersededReferenced);
  const discoveryMode = !selectingDocumentForJob && (Boolean(requestedView) || (Boolean(filters.q) && !hasIntegratedFilters));

  const load = useCallback(async () => {
    if (!tenant) return;
    const initialLoad = !hasLoadedRef.current;
    setLoading(initialLoad);
    setRefreshing(!initialLoad);
    setError("");
    try {
      if (discoveryMode) {
        const next = await discoverLibrary(tenant, { view: discoveryView, q: filters.q, page: filters.page, perPage: filters.perPage });
        setDiscoveryData(next);
        setData(null);
      } else {
        const next = await listIntegratedLibrary(tenant, filters);
        setData(next);
        setDiscoveryData(null);
      }
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled library could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [discoveryMode, discoveryView, filters, tenant]);

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
    if (key === "type" || key === "class" || key === "status") next.delete("view");
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };

  const selectPreset = (value: LibraryDiscoveryView | "") => {
    const next = new URLSearchParams(params);
    if (value) next.set("view", value); else next.delete("view");
    ["type", "class", "status", "lifecycle_status", "owner_user_id", "department_id", "indexing_status", "unresolved_ownership", "unresolved_relationships", "structure_status", "superseded_referenced"].forEach((key) => next.delete(key));
    next.set("page", "1");
    setParams(next);
  };

  const updateSort = (value: string) => {
    const [sort, direction] = value.split(":");
    const next = new URLSearchParams(params);
    next.delete("view");
    next.set("sort", sort || "code");
    next.set("direction", direction || "asc");
    next.set("page", "1");
    setParams(next);
  };

  const clearGovernanceQueue = () => {
    const next = new URLSearchParams(params);
    ["unresolved_ownership", "unresolved_relationships", "indexing_status", "structure_status", "superseded_referenced", "owner_user_id", "department_id"].forEach((key) => next.delete(key));
    next.set("page", "1");
    setParams(next);
  };

  const cancelJobSelection = () => {
    const next = new URLSearchParams(params);
    next.delete("action");
    setParams(next, { replace: true });
  };

  const pagination = discoveryMode ? discoveryData?.pagination : data?.pagination;
  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.per_page)) : 1;
  const canControl = Boolean((discoveryMode ? discoveryData?.capabilities.control : data?.capabilities.control));
  const hasRows = discoveryMode ? Boolean(discoveryData?.items.length) : Boolean(data?.items.length);

  const openReader = (item: IntegratedLibraryItem) => {
    const revisionId = item.read_target?.revision_id;
    if (!revisionId) return;
    navigate(`${readerBasePath}/${item.id}/rev/${revisionId}/read`);
  };

  const openDiscoveryReader = (item: LibraryDiscoveryItem) => {
    if (!item.read_target_revision_id) return;
    navigate(`${readerBasePath}/${item.id}/rev/${item.read_target_revision_id}/read`);
  };

  const selectForChange = (item: IntegratedLibraryItem) => {
    navigate(`${basePath}/library/${item.id}?tab=changes`);
  };

  const selectForJob = (item: IntegratedLibraryItem) => {
    if (!selectedJob) return;
    if (selectingChangeDocument) {
      selectForChange(item);
      return;
    }
    navigate(documentJobTarget(basePath, item.id, selectedJob));
  };

  return <DocumentControlShell
    title="Company document library"
    eyebrow={selectedJob ? "SELECT DOCUMENT / CONTROLLED WORK" : "CONTROLLED INFORMATION"}
    subtitle={selectedJob ? selectedJob.selectionPrompt : "Find the current controlled information you need, then read it or open its document workspace for lifecycle and evidence context."}
    canControl={canControl}
    actions={<>
      {canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/reports?view=retention`)}><Archive size={14} /> Retained records</button> : null}
    </>}
  >
    <section className="dlibrary" data-testid="integrated-document-library" aria-busy={refreshing}>
      {canControl && selectedJob ? <div className="dlibrary__queue-filter dlibrary__queue-filter--job" role="status"><span><ClipboardCheck size={15} /><strong>{selectingChangeDocument ? "Select a document for the change request" : selectedJob.label}.</strong> {selectedJob.selectionPrompt} Search or filter the library, then choose {selectedJob.selectLabel}.</span><button type="button" onClick={cancelJobSelection}><FilterX size={14} /> Cancel</button></div> : null}
      {activeQueue ? <div className="dlibrary__queue-filter" role="status"><span><ShieldCheck size={15} /><strong>Governance queue</strong> · {activeQueue}</span><button type="button" onClick={clearGovernanceQueue}><FilterX size={14} /> Clear queue filter</button></div> : null}
      {error && (data || discoveryData) ? <div className="dlibrary__queue-filter" role="alert"><span><strong>The latest library update could not be loaded.</strong> The last available results remain visible.</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}

      {!selectingDocumentForJob ? <div className="dlibrary__presets" aria-label="Library views">
        {PRESETS.map(({ id, label, icon: Icon }) => <button type="button" key={label} className={(requestedView || "") === id ? "active" : ""} onClick={() => selectPreset(id)}><Icon size={14} /> {label}</button>)}
      </div> : null}

      {!discoveryMode ? <div className="dlibrary__categories" aria-label="Document categories">
        {CATEGORIES.map(([value, label, Icon]) => {
          const active = (filters.nodeType || "") === value;
          const count = value ? Number(data?.facets.node_types[value] || 0) : Number(data?.facets.visible_documents || 0);
          return <button key={label} type="button" className={active ? "active" : ""} onClick={() => update("type", value)}><Icon size={16} /><span>{label}</span><small>{count}</small></button>;
        })}
      </div> : null}

      <div className="dlibrary__toolbar">
        <label className="dlibrary__search"><Search size={16} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Find code, title, alias, owner, revision, filename, hierarchy or indexed text" /></label>
        {!discoveryMode ? <>
          <select aria-label="Document control class" value={filters.documentClass || ""} onChange={(event) => update("class", event.target.value)}><option value="">Internal + external</option><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External controlled</option><option value="RECORD">Record documents</option></select>
          <select aria-label="Document lifecycle" value={filters.status || ""} onChange={(event) => update("status", event.target.value)}><option value="">All lifecycle states</option><option value="ACTIVE">Active</option><option value="SUPERSEDED">Superseded</option><option value="ARCHIVED">Archived</option></select>
          <select aria-label="Sort company library" value={`${filters.sort || "code"}:${filters.direction || "asc"}`} onChange={(event) => updateSort(event.target.value)}><option value="code:asc">Code A–Z</option><option value="code:desc">Code Z–A</option><option value="title:asc">Title A–Z</option><option value="title:desc">Title Z–A</option><option value="type:asc">Document type</option><option value="status:asc">Lifecycle status</option></select>
        </> : <span className="dlibrary__discovery-note">Permission-filtered discovery · server-bounded</span>}
        {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
      </div>

      {loading ? <DocumentControlLoading label={selectedJob ? "Loading eligible controlled documents…" : "Opening the company library…"} /> : null}
      {error && !data && !discoveryData ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !hasRows ? <DocumentControlEmpty icon={BookOpen} title="No document matches this view" message="Change the view, filters or search text. Access-controlled documents are shown only to permitted users." /> : null}

      {!loading && !discoveryMode && data?.items.length ? <div className="dlibrary__table-wrap"><table className="dc-table dlibrary__table">
        <thead><tr><th>Document</th><th>Current issue</th><th>Owner</th><th>Availability</th><th>Connected evidence</th><th>Source / currency</th><th>Action</th></tr></thead>
        <tbody>{data.items.map((item) => {
          const physical = item.library.physical;
          const integration = item.library.integrations;
          const external = item.library.external;
          const eligibility = selectedJob ? jobEligibility(item, selectedJob) : { allowed: true };
          return <tr key={item.id}>
            <td><strong>{item.code}</strong><span>{item.title}</span><small>{item.library.node_type.replaceAll("_", " ")}{item.library.structure_path ? ` · ${item.library.structure_path}` : ""}</small></td>
            <td><strong>{revisionText(item)}</strong><small>{item.latest_revision?.effective_date || "No effective date"}</small><DocumentControlStatus status={item.read_target.kind} kind={item.read_target.uncontrolled ? "warning" : "success"} /></td>
            <td>{item.library.owner?.assignee?.name ? <><strong>{item.library.owner.assignee.name}</strong><small>{item.library.responsible_department?.assignee?.name || item.profile.owner_department}</small></> : <><strong>{item.profile.owner_department || item.owner_role}</strong><small>Named owner not resolved</small></>}</td>
            <td><div className="dlibrary__availability"><span><BookOpen size={14} /> Digital {item.read_target.revision_id ? "available" : "unavailable"}</span><span className={physical.overdue ? "is-danger" : ""}><Copy size={14} /> {physicalText(item)}</span>{physical.overdue ? <small>{physical.overdue} overdue return{physical.overdue === 1 ? "" : "s"}</small> : null}</div></td>
            <td>{canControl ? <div className="dlibrary__connections"><span><Link2 size={14} /> {item.library.semantic_relationships || 0} document links</span><span><Workflow size={14} /> {integration?.count || 0} module links</span><span><Archive size={14} /> {item.library.generated_records || 0} generated records</span>{integration?.modules?.length ? <small>{integration.modules.join(" · ")}</small> : null}</div> : <small>Open the document to follow permitted links.</small>}</td>
            <td>{external ? <><strong>{external.provider}</strong><DocumentControlStatus status={external.currency_status} kind={statusKind(external.currency_status)} /><small>{external.revision_label || "Revision not received"}{external.authority ? ` · ${external.authority}` : ""}</small></> : <><DocumentControlStatus status={item.profile.document_class} kind={statusKind(item.profile.document_class)} /><small>Company-controlled source</small></>}</td>
            <td><div className="dlibrary__actions">{selectedJob && canControl ? <><button type="button" className="dc-button dc-button--primary" disabled={!eligibility.allowed} title={eligibility.reason} onClick={() => selectForJob(item)}>{selectingChangeDocument ? "Select for change" : selectedJob.selectLabel}</button>{!eligibility.allowed ? <small>{eligibility.reason}</small> : null}</> : <><button type="button" className="dc-button dc-button--primary" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}><BookOpen size={14} /> Read</button>{canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Open workspace</button> : null}</>}</div></td>
          </tr>;
        })}</tbody>
      </table></div> : null}

      {!loading && discoveryMode && discoveryData?.items.length ? <div className="dlibrary__table-wrap"><table className="dc-table dlibrary__table dlibrary__discovery-table">
        <thead><tr><th>Document</th><th>Current / latest</th><th>Owner</th><th>Hierarchy / source</th><th>Recent / review</th><th>State</th><th>Action</th></tr></thead>
        <tbody>{discoveryData.items.map((item) => <tr key={item.id}>
          <td><strong>{item.code}</strong><span>{item.title}</span><small>{item.manual_type.replaceAll("_", " ")}</small></td>
          <td><strong>{discoveryRevisionText(item)}</strong><small>{item.current_revision?.source_filename || item.latest_revision?.source_filename || "No source filename"}</small></td>
          <td><strong>{item.owner.name || item.owner.department || "Unassigned"}</strong><small>{item.owner.department || "No responsible department"}</small></td>
          <td><strong>{item.node.type.replaceAll("_", " ")}</strong><small>{item.node.path || "No hierarchy path"}</small></td>
          <td><strong>{item.last_opened_at ? `Opened ${formatDate(item.last_opened_at)}` : "Not recently opened"}</strong><small>{item.next_review_due ? `Review ${formatDate(item.next_review_due)}` : "No review due date"}{item.favorite ? " · Favorite" : ""}</small></td>
          <td><DocumentControlStatus status={item.lifecycle_status} kind={statusKind(item.lifecycle_status)} /><small>{item.document_class}</small></td>
          <td><div className="dlibrary__actions"><button type="button" className="dc-button dc-button--primary" disabled={!item.read_target_revision_id} onClick={() => openDiscoveryReader(item)}><BookOpen size={14} /> Read</button>{canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Open workspace</button> : null}</div></td>
        </tr>)}</tbody>
      </table></div> : null}

      {pagination ? <footer className="dlibrary__pagination">
        <span>{pagination.total ? `${(pagination.page - 1) * pagination.per_page + 1}–${Math.min(pagination.page * pagination.per_page, pagination.total)} of ${pagination.total}` : "0 documents"}</span>
        <select value={pagination.per_page} onChange={(event) => update("per_page", event.target.value)} aria-label="Documents per page"><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={pagination.page <= 1 || refreshing} onClick={() => update("page", String(pagination.page - 1))}><ChevronLeft size={15} /> Previous</button>
        <span>Page {pagination.page} of {totalPages}</span>
        <button type="button" disabled={pagination.page >= totalPages || refreshing} onClick={() => update("page", String(pagination.page + 1))}>Next <ChevronRight size={15} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}

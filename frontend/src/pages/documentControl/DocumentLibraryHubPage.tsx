import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import {
  Archive,
  BookMarked,
  BookOpen,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  FileCheck2,
  FileText,
  FilterX,
  Heart,
  History,
  LayoutGrid,
  List,
  Search,
  ShieldCheck,
  UserRound,
  UploadCloud,
  Workflow,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import ControlledDocumentUploadDialog from "../../components/documentControl/ControlledDocumentUploadDialog";
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
  ["REGULATION", "Regulations", BookMarked],
  ["PROCEDURE", "Procedures", Workflow],
  ["WORK_INSTRUCTION", "Work instructions", ClipboardCheck],
  ["FORM", "Forms", FileText],
  ["CHECKLIST", "Checklists", FileCheck2],
  ["REGISTER", "Registers", Archive],
  ["RECORD", "Records", Archive],
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
const PRESENTATION_STORAGE_KEY = "amo.dms.library.presentation.v1";
const DocumentLibraryRegisterGrid = lazy(() => import("./DocumentLibraryRegisterGrid"));

type LibraryPresentation = "shelf" | "register";

function categoryVisual(type?: string | null) {
  return CATEGORIES.find(([value]) => value === String(type || "").toUpperCase()) || CATEGORIES[0];
}

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "ACTIVE", "CURRENT", "RETURNED"].includes(value)) return "success";
  if (["SUPERSEDED", "ARCHIVED", "WITHDRAWN", "OVERDUE", "RECALLED"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "UNVERIFIED", "ISSUED"].includes(value)) return "warning";
  return "neutral";
}

function revisionText(item: IntegratedLibraryItem): string {
  const revision = item.current_revision || item.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
}

function controlStatus(item: IntegratedLibraryItem): string {
  const status = item.read_target.control_status || item.read_target.kind;
  return status === "CONTROLLED_DRAFT" || item.read_target.kind === "UNCONTROLLED" ? "DRAFT" : status;
}

function metadataText(item: IntegratedLibraryItem, key: string): string {
  const value = item.profile.metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function physicalText(item: IntegratedLibraryItem): string {
  const physical = item.library.physical;
  if (!physical.total) return "No controlled copies";
  return `${physical.on_shelf} on shelf · ${physical.checked_out} checked out${physical.overdue ? ` · ${physical.overdue} overdue` : ""}`;
}

function discoveryRevisionText(item: LibraryDiscoveryItem): string {
  const revision = item.current_revision || item.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
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
  const [uploadOpen, setUploadOpen] = useState(false);
  const [presentation, setPresentation] = useState<LibraryPresentation>(() => (
    typeof window !== "undefined" && window.localStorage.getItem(PRESENTATION_STORAGE_KEY) === "register"
      ? "register"
      : "shelf"
  ));
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
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PRESENTATION_STORAGE_KEY, presentation);
    }
  }, [presentation]);
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
  const offlineSnapshot = discoveryMode ? discoveryData?.offline_snapshot : data?.offline_snapshot;
  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.per_page)) : 1;
  const canControl = Boolean((discoveryMode ? discoveryData?.capabilities.control : data?.capabilities.control));
  const hasRows = discoveryMode ? Boolean(discoveryData?.items.length) : Boolean(data?.items.length);

  const openReader = useCallback((item: IntegratedLibraryItem) => {
    const revisionId = item.read_target?.revision_id;
    if (!revisionId) return;
    navigate(`${readerBasePath}/${item.id}/rev/${revisionId}/read`);
  }, [navigate, readerBasePath]);

  const openDiscoveryReader = useCallback((item: LibraryDiscoveryItem) => {
    if (!item.read_target_revision_id) return;
    navigate(`${readerBasePath}/${item.id}/rev/${item.read_target_revision_id}/read`);
  }, [navigate, readerBasePath]);

  const selectForChange = useCallback((item: IntegratedLibraryItem) => {
    navigate(`${basePath}/library/${item.id}?tab=changes`);
  }, [basePath, navigate]);

  const selectForJob = useCallback((item: IntegratedLibraryItem) => {
    if (!selectedJob) return;
    if (selectingChangeDocument) {
      selectForChange(item);
      return;
    }
    navigate(documentJobTarget(basePath, item.id, selectedJob));
  }, [basePath, navigate, selectForChange, selectedJob, selectingChangeDocument]);

  const integratedColumns = useMemo<ColDef<IntegratedLibraryItem>[]>(() => [
    {
      headerName: "Document",
      minWidth: 250,
      flex: 1.5,
      valueGetter: ({ data: item }) => item ? `${item.code} ${item.title}` : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-primary"><strong>{item.code}</strong><span>{item.title}</span></div> : null,
      tooltipValueGetter: ({ data: item }) => item ? `${item.code} · ${item.title}${metadataText(item, "description") ? ` · ${metadataText(item, "description")}` : ""}` : "",
    },
    {
      headerName: "Type / hierarchy",
      minWidth: 210,
      flex: 1.2,
      valueGetter: ({ data: item }) => item ? `${item.library.node_type} ${item.library.structure_path || ""}` : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.library.node_type.replaceAll("_", " ")}</strong><small>{item.library.structure_path || "Standard document group"}</small></div> : null,
    },
    {
      headerName: "Current revision",
      minWidth: 165,
      valueGetter: ({ data: item }) => item ? revisionText(item) : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{revisionText(item)}</strong><small>{item.current_revision?.effective_date ? `Effective ${formatDate(item.current_revision.effective_date)}` : item.latest_revision ? item.latest_revision.status.replaceAll("_", " ") : "No effective revision"}</small></div> : null,
    },
    {
      headerName: "Source / format",
      minWidth: 180,
      flex: 0.8,
      valueGetter: ({ data: item }) => {
        const revision = item?.current_revision || item?.latest_revision;
        return item ? `${metadataText(item, "source_issuer")} ${revision?.source_type || ""} ${revision?.source_filename || ""}` : "";
      },
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => {
        if (!item) return null;
        const revision = item.current_revision || item.latest_revision;
        return <div className="dlibrary__ag-stack"><strong>{metadataText(item, "source_issuer") || "Internal source"}</strong><small>{revision?.source_type || "—"}{revision?.source_filename ? ` · ${revision.source_filename}` : ""}</small></div>;
      },
    },
    {
      headerName: "Owner",
      minWidth: 175,
      flex: 1,
      valueGetter: ({ data: item }) => item ? item.library.owner?.assignee?.name || item.profile.owner_department || item.owner_role : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.library.owner?.assignee?.name || item.profile.owner_department || item.owner_role}</strong><small>{item.library.responsible_department?.assignee?.name || item.profile.owner_department || "Responsibility unresolved"}</small></div> : null,
    },
    {
      headerName: "Review due",
      minWidth: 135,
      valueGetter: ({ data: item }) => item?.profile.next_review_due || "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{formatDate(item.profile.next_review_due)}</strong><small>{item.profile.review_interval_months} month cycle</small></div> : null,
    },
    {
      headerName: "Control state",
      minWidth: 145,
      valueGetter: ({ data: item }) => item ? `${controlStatus(item)} ${item.profile.document_class}` : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><DocumentControlStatus status={controlStatus(item)} kind={item.read_target.uncontrolled ? "warning" : "success"} /><small>{item.profile.document_class}</small></div> : null,
    },
    {
      headerName: "Connected controls",
      minWidth: 205,
      valueGetter: ({ data: item }) => item ? `${item.library.semantic_relationships || 0} ${item.library.integrations?.count || 0} ${item.library.generated_records || 0} ${item.library.physical.total || 0}` : "",
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.library.semantic_relationships || 0} links · {item.library.integrations?.count || 0} modules · {item.library.generated_records || 0} records</strong><small>{physicalText(item)}</small></div> : null,
    },
    {
      headerName: "Actions",
      width: selectedJob && canControl ? 155 : canControl ? 205 : 90,
      minWidth: selectedJob && canControl ? 155 : canControl ? 205 : 90,
      pinned: "right",
      sortable: false,
      filter: false,
      cellRenderer: ({ data: item }: ICellRendererParams<IntegratedLibraryItem>) => {
        if (!item) return null;
        const eligibility = selectedJob ? jobEligibility(item, selectedJob) : { allowed: true };
        if (selectedJob && canControl) return <button type="button" className="dc-button dc-button--primary" disabled={!eligibility.allowed} title={eligibility.reason} onClick={() => selectForJob(item)}>{selectingChangeDocument ? "Select for change" : selectedJob.selectLabel}</button>;
        return <div className="dlibrary__ag-actions"><button type="button" className="dc-button dc-button--primary" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}>Read</button>{canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Workspace</button> : null}</div>;
      },
    },
  ], [basePath, canControl, navigate, openReader, selectForJob, selectedJob, selectingChangeDocument]);

  const discoveryColumns = useMemo<ColDef<LibraryDiscoveryItem>[]>(() => [
    { headerName: "Document", minWidth: 250, flex: 1.5, valueGetter: ({ data: item }) => item ? `${item.code} ${item.title}` : "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-primary"><strong>{item.code}</strong><span>{item.title}</span></div> : null },
    { headerName: "Type / hierarchy", minWidth: 210, flex: 1.2, valueGetter: ({ data: item }) => item ? `${item.node.type} ${item.node.path || ""}` : "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.node.type.replaceAll("_", " ")}</strong><small>{item.node.path || "Standard document group"}</small></div> : null },
    { headerName: "Current revision", minWidth: 170, valueGetter: ({ data: item }) => item ? discoveryRevisionText(item) : "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{discoveryRevisionText(item)}</strong><small>{item.current_revision?.effective_date ? `Effective ${formatDate(item.current_revision.effective_date)}` : item.latest_revision?.source_filename || "No effective revision"}</small></div> : null },
    { headerName: "Format", minWidth: 155, valueGetter: ({ data: item }) => item?.current_revision?.source_filename || item?.latest_revision?.source_filename || "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.current_revision?.source_filename?.split(".").pop()?.toUpperCase() || item.latest_revision?.source_filename?.split(".").pop()?.toUpperCase() || "—"}</strong><small>{item.current_revision?.source_filename || item.latest_revision?.source_filename || "No file"}</small></div> : null },
    { headerName: "Owner", minWidth: 170, flex: 1, valueGetter: ({ data: item }) => item ? item.owner.name || item.owner.department || "Unassigned" : "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{item.owner.name || "Unassigned"}</strong><small>{item.owner.department || "No department"}</small></div> : null },
    { headerName: "Review due", minWidth: 145, valueGetter: ({ data: item }) => item?.next_review_due || "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><strong>{formatDate(item.next_review_due)}</strong><small>{item.last_opened_at ? `Opened ${formatDate(item.last_opened_at)}` : "Not recently opened"}</small></div> : null },
    { headerName: "State", minWidth: 135, valueGetter: ({ data: item }) => item ? `${item.lifecycle_status} ${item.document_class}` : "", cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-stack"><DocumentControlStatus status={item.lifecycle_status} kind={statusKind(item.lifecycle_status)} /><small>{item.document_class}</small></div> : null },
    { headerName: "Actions", width: canControl ? 205 : 90, minWidth: canControl ? 205 : 90, pinned: "right", sortable: false, filter: false, cellRenderer: ({ data: item }: ICellRendererParams<LibraryDiscoveryItem>) => item ? <div className="dlibrary__ag-actions"><button type="button" className="dc-button dc-button--primary" disabled={!item.read_target_revision_id} onClick={() => openDiscoveryReader(item)}>Read</button>{canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Workspace</button> : null}</div> : null },
  ], [basePath, canControl, navigate, openDiscoveryReader]);

  const defaultColumn = useMemo<ColDef>(() => ({ sortable: true, filter: true, resizable: true, suppressHeaderMenuButton: false }), []);

  return <DocumentControlShell
    title="Company document library"
    eyebrow={selectedJob ? "SELECT DOCUMENT / CONTROLLED WORK" : "CONTROLLED INFORMATION"}
    subtitle={selectedJob ? selectedJob.selectionPrompt : "Find the current controlled information you need, then read it or open its document workspace for lifecycle and evidence context."}
    canControl={canControl}
    actions={<>
      {canControl && !selectedJob ? <button type="button" className="dc-button dc-button--primary" onClick={() => setUploadOpen(true)}><UploadCloud size={14} /> Register document</button> : null}
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
        {offlineSnapshot ? <span className="dlibrary__offline-state" role="status">Offline snapshot · {formatDate(new Date(offlineSnapshot.stored_at).toISOString())}</span> : null}
      </div>

      <div className="dlibrary__presentation" aria-label="Library presentation">
        <span>{presentation === "shelf" ? "Visual shelf" : "Controlled register"}</span>
        <div role="group" aria-label="Choose library view">
          <button type="button" className={presentation === "shelf" ? "active" : ""} aria-pressed={presentation === "shelf"} onClick={() => setPresentation("shelf")}><LayoutGrid size={15} /> Shelf</button>
          <button type="button" className={presentation === "register" ? "active" : ""} aria-pressed={presentation === "register"} onClick={() => setPresentation("register")}><List size={15} /> Register</button>
        </div>
      </div>

      {loading ? <DocumentControlLoading label={selectedJob ? "Loading eligible controlled documents…" : "Opening the company library…"} /> : null}
      {error && !data && !discoveryData ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !hasRows ? <DocumentControlEmpty icon={BookOpen} title="No document matches this view" message="Change the view, filters or search text. Access-controlled documents are shown only to permitted users." /> : null}

      {!loading && presentation === "shelf" && !discoveryMode && data?.items.length ? <div className="dlibrary__shelf" aria-label="Controlled document shelf">
        {data.items.map((item) => {
          const [, typeLabel, TypeIcon] = categoryVisual(item.library.node_type);
          const revision = item.current_revision || item.latest_revision;
          const eligibility = selectedJob ? jobEligibility(item, selectedJob) : { allowed: true };
          return <article key={`${item.id}:${revision?.id || "none"}`} className="dlibrary-card" data-document-type={item.library.node_type}>
            <header>
              <div className="dlibrary-card__cover" aria-hidden="true"><TypeIcon size={22} /><span>{typeLabel}</span></div>
              <div className="dlibrary-card__identity"><small>{item.code}</small><h2>{item.title}</h2><p>{metadataText(item, "description") || item.library.structure_path || "Controlled company information"}</p></div>
              <DocumentControlStatus status={controlStatus(item)} kind={item.read_target.uncontrolled ? "warning" : "success"} />
            </header>
            <dl>
              <div><dt>Revision</dt><dd>{revisionText(item)}</dd></div>
              <div><dt>Effective</dt><dd>{formatDate(revision?.effective_date)}</dd></div>
              <div><dt>Owner</dt><dd>{item.library.owner?.assignee?.name || item.profile.owner_department || item.owner_role}</dd></div>
              <div><dt>Review</dt><dd>{formatDate(item.profile.next_review_due)}</dd></div>
            </dl>
            <div className="dlibrary-card__context">
              <span>{item.library.structure_path || "Standard hierarchy"}</span>
              <span>{item.library.semantic_relationships || 0} links · {item.library.integrations?.count || 0} modules · {item.library.generated_records || 0} records</span>
            </div>
            <footer>
              {selectedJob && canControl ? <button type="button" className="dc-button dc-button--primary" disabled={!eligibility.allowed} title={eligibility.reason} onClick={() => selectForJob(item)}>{selectingChangeDocument ? "Select for change" : selectedJob.selectLabel}</button> : <>
                <button type="button" className="dc-button dc-button--primary" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}>Read current</button>
                {canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Workspace</button> : null}
              </>}
            </footer>
          </article>;
        })}
      </div> : null}

      {!loading && presentation === "shelf" && discoveryMode && discoveryData?.items.length ? <div className="dlibrary__shelf" aria-label="Document discovery shelf">
        {discoveryData.items.map((item) => {
          const [, typeLabel, TypeIcon] = categoryVisual(item.node.type);
          const revision = item.current_revision || item.latest_revision;
          return <article key={`${item.id}:${revision?.id || "none"}`} className="dlibrary-card" data-document-type={item.node.type}>
            <header>
              <div className="dlibrary-card__cover" aria-hidden="true"><TypeIcon size={22} /><span>{typeLabel}</span></div>
              <div className="dlibrary-card__identity"><small>{item.code}</small><h2>{item.title}</h2><p>{item.node.path || "Controlled company information"}</p></div>
              <DocumentControlStatus status={item.lifecycle_status} kind={statusKind(item.lifecycle_status)} />
            </header>
            <dl>
              <div><dt>Revision</dt><dd>{discoveryRevisionText(item)}</dd></div>
              <div><dt>Effective</dt><dd>{formatDate(revision?.effective_date)}</dd></div>
              <div><dt>Owner</dt><dd>{item.owner.name || item.owner.department || "Unassigned"}</dd></div>
              <div><dt>Review</dt><dd>{formatDate(item.next_review_due)}</dd></div>
            </dl>
            <div className="dlibrary-card__context"><span>{item.document_class} · {typeLabel}</span><span>{revision?.page_count ? `${revision.page_count} pages` : revision?.source_filename || "No source file"}</span></div>
            <footer>
              <button type="button" className="dc-button dc-button--primary" disabled={!item.read_target_revision_id} onClick={() => openDiscoveryReader(item)}>Read current</button>
              {canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Workspace</button> : null}
            </footer>
          </article>;
        })}
      </div> : null}

      {!loading && presentation === "register" && !discoveryMode && data?.items.length ? <Suspense fallback={<DocumentControlLoading label="Opening controlled register…" />}>
        <DocumentLibraryRegisterGrid
          mode="integrated"
          rowData={data.items}
          columnDefs={integratedColumns}
          defaultColDef={defaultColumn}
        />
      </Suspense> : null}

      {!loading && presentation === "register" && discoveryMode && discoveryData?.items.length ? <Suspense fallback={<DocumentControlLoading label="Opening discovery register…" />}>
        <DocumentLibraryRegisterGrid
          mode="discovery"
          rowData={discoveryData.items}
          columnDefs={discoveryColumns}
          defaultColDef={defaultColumn}
        />
      </Suspense> : null}

      {pagination ? <footer className="dlibrary__pagination">
        <span>{pagination.total ? `${(pagination.page - 1) * pagination.per_page + 1}–${Math.min(pagination.page * pagination.per_page, pagination.total)} of ${pagination.total}` : "0 documents"}</span>
        <select value={pagination.per_page} onChange={(event) => update("per_page", event.target.value)} aria-label="Documents per page"><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={pagination.page <= 1 || refreshing} onClick={() => update("page", String(pagination.page - 1))}><ChevronLeft size={15} /> Previous</button>
        <span>Page {pagination.page} of {totalPages}</span>
        <button type="button" disabled={pagination.page >= totalPages || refreshing} onClick={() => update("page", String(pagination.page + 1))}>Next <ChevronRight size={15} /></button>
      </footer> : null}
      <ControlledDocumentUploadDialog
        tenant={tenant}
        open={uploadOpen}
        allowApprovedIntake={canControl}
        onClose={() => setUploadOpen(false)}
        onUploaded={async (result) => { await load(); navigate(`${basePath}/library/${result.manual_id}?tab=workflow`); }}
      />
    </section>
  </DocumentControlShell>;
}

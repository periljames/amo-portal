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
  AlignJustify,
  LayoutGrid,
  LibraryBig,
  List,
  RefreshCcw,
  ScanLine,
  TableProperties,
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
  listLibraryCatalog,
  listSharedLibraryViews,
  publishSharedLibraryView,
  type IntegratedLibraryFilters,
  type IntegratedLibraryItem,
  type IntegratedLibraryResponse,
  type LibraryCatalogItem,
  type LibraryDiscoveryItem,
  type LibraryDiscoveryResponse,
  type LibraryDiscoveryView,
  type SharedLibraryView,
} from "../../services/documentLibrary";
import LibraryOperationsPanel from "./LibraryOperationsPanel";
import DocumentLibraryDetailsPane from "./DocumentLibraryDetailsPane";
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
  { id: "shared-with-me", label: "Shared With Me", icon: UserRound },
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
const PERSONAL_VIEWS_STORAGE_KEY = "amo.dms.library.personal-views.v1";
const SAVABLE_VIEW_KEYS = new Set(["q", "view", "type", "format", "owner", "department", "class", "status", "sort", "direction", "per_page", "indexing_status", "unresolved_ownership", "unresolved_relationships", "structure_status", "superseded_referenced"]);
const DocumentLibraryRegisterGrid = lazy(() => import("./DocumentLibraryRegisterGrid"));

type LibraryPresentation = "list" | "compact" | "cards" | "register";

type SelectedLibraryItem =
  | { mode: "integrated"; item: IntegratedLibraryItem }
  | { mode: "discovery"; item: LibraryDiscoveryItem };

type PersonalLibraryView = {
  id: string;
  name: string;
  params: Record<string, string>;
  presentation: LibraryPresentation;
};

function personalViewsKey(tenant: string): string {
  return `${PERSONAL_VIEWS_STORAGE_KEY}:${tenant.toLowerCase()}`;
}

function readPersonalViews(tenant: string): PersonalLibraryView[] {
  if (typeof window === "undefined" || !tenant) return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(personalViewsKey(tenant)) || "[]");
    return Array.isArray(value)
      ? value.filter((item): item is PersonalLibraryView => Boolean(
        item && typeof item.id === "string" && typeof item.name === "string"
        && ["list", "compact", "cards", "register"].includes(item.presentation),
      ))
      : [];
  } catch {
    return [];
  }
}

function currentViewParams(params: URLSearchParams): Record<string, string> {
  const result: Record<string, string> = {};
  params.forEach((value, key) => {
    if (SAVABLE_VIEW_KEYS.has(key) && value) result[key] = value;
  });
  return result;
}

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
  const [catalogItems, setCatalogItems] = useState<LibraryCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [libraryServicesOpen, setLibraryServicesOpen] = useState(false);
  const [libraryServicesMode, setLibraryServicesMode] = useState<"warehouse" | "catalog" | "scan" | "internet" | "account">("warehouse");
  const [presentation, setPresentation] = useState<LibraryPresentation>(() => {
    if (typeof window === "undefined") return "list";
    const stored = window.localStorage.getItem(PRESENTATION_STORAGE_KEY);
    if (stored === "shelf") return "cards";
    return stored === "compact" || stored === "cards" || stored === "register" ? stored : "list";
  });
  const [selectedItem, setSelectedItem] = useState<SelectedLibraryItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false);
  const [personalViews, setPersonalViews] = useState<PersonalLibraryView[]>([]);
  const [sharedViews, setSharedViews] = useState<SharedLibraryView[]>([]);
  const [savedViewName, setSavedViewName] = useState("");
  const [savedViewNotice, setSavedViewNotice] = useState("");
  const [savingSharedView, setSavingSharedView] = useState(false);
  const hasLoadedRef = useRef(false);

  const filters = useMemo<IntegratedLibraryFilters>(() => ({
    q: params.get("q") || undefined,
    nodeType: params.get("type") || undefined,
    sourceType: params.get("format") || undefined,
    documentClass: params.get("class") || params.get("control_status") || undefined,
    status: params.get("status") || params.get("lifecycle_status") || undefined,
    ownerName: params.get("owner") || undefined,
    departmentCode: params.get("department") || undefined,
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
  const hasIntegratedFilters = Boolean(filters.nodeType || filters.sourceType || filters.documentClass || filters.status || filters.ownerName || filters.departmentCode || filters.ownerUserId || filters.departmentId || filters.indexingStatus || filters.unresolvedOwnership || filters.unresolvedRelationships || filters.structureStatus || filters.supersededReferenced);
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
      if (!selectingDocumentForJob) {
        try {
          const catalogue = await listLibraryCatalog(tenant, {
            q: filters.q,
            page: 1,
            perPage: 12,
          });
          setCatalogItems(catalogue.items);
        } catch {
          // Controlled-document discovery must remain usable if a public/library
          // catalogue service is temporarily unavailable.
          setCatalogItems([]);
        }
      } else {
        setCatalogItems([]);
      }
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled library could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [discoveryMode, discoveryView, filters, selectingDocumentForJob, tenant]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!tenant) return;
    setPersonalViews(readPersonalViews(tenant));
    let cancelled = false;
    void listSharedLibraryViews(tenant)
      .then((response) => {
        if (!cancelled) setSharedViews(response.items);
      })
      .catch(() => {
        if (!cancelled) setSharedViews([]);
      });
    return () => { cancelled = true; };
  }, [tenant]);
  useEffect(() => { setSearchText(urlQuery); }, [urlQuery]);
  useEffect(() => {
    const requestedService = params.get("library_services");
    if (params.get("library_scan")) {
      setLibraryServicesMode("scan");
      setLibraryServicesOpen(true);
      return;
    }
    if (requestedService && ["warehouse", "catalog", "scan", "internet", "account"].includes(requestedService)) {
      setLibraryServicesMode(requestedService as "warehouse" | "catalog" | "scan" | "internet" | "account");
      setLibraryServicesOpen(true);
    }
  }, [params]);
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
    if (["type", "format", "class", "status", "owner", "department", "owner_user_id", "department_id", "indexing_status", "unresolved_ownership", "unresolved_relationships", "structure_status", "superseded_referenced"].includes(key)) next.delete("view");
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };

  const selectPreset = (value: LibraryDiscoveryView | "") => {
    const next = new URLSearchParams(params);
    if (value) next.set("view", value); else next.delete("view");
    ["type", "format", "class", "status", "lifecycle_status", "owner", "department", "owner_user_id", "department_id", "indexing_status", "unresolved_ownership", "unresolved_relationships", "structure_status", "superseded_referenced"].forEach((key) => next.delete(key));
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

  const applySavedView = (view: PersonalLibraryView | SharedLibraryView) => {
    const next = new URLSearchParams();
    Object.entries(view.params || {}).forEach(([key, value]) => {
      if (SAVABLE_VIEW_KEYS.has(key) && value) next.set(key, value);
    });
    next.set("page", "1");
    setParams(next);
    setPresentation(view.presentation);
    setSavedViewNotice(`View applied: ${view.name}`);
  };

  const savePersonalView = () => {
    const name = savedViewName.trim();
    if (!tenant || !name) {
      setSavedViewNotice("Enter a view name first.");
      return;
    }
    const view: PersonalLibraryView = {
      id: `personal-${Date.now()}`,
      name,
      params: currentViewParams(params),
      presentation,
    };
    const next = [...personalViews.filter((item) => item.name.toLowerCase() !== name.toLowerCase()), view].slice(-24);
    setPersonalViews(next);
    window.localStorage.setItem(personalViewsKey(tenant), JSON.stringify(next));
    setSavedViewName("");
    setSavedViewNotice(`Personal view saved: ${name}`);
  };

  const removePersonalView = (viewId: string) => {
    if (!tenant) return;
    const next = personalViews.filter((item) => item.id !== viewId);
    setPersonalViews(next);
    window.localStorage.setItem(personalViewsKey(tenant), JSON.stringify(next));
    setSavedViewNotice("Personal view removed.");
  };

  const publishCurrentView = async () => {
    const name = savedViewName.trim();
    if (!tenant || !name || !canControl) {
      setSavedViewNotice(name ? "Publishing this view requires Document Control authority." : "Enter a view name first.");
      return;
    }
    setSavingSharedView(true);
    setSavedViewNotice("");
    try {
      const published = await publishSharedLibraryView(tenant, {
        name,
        params: currentViewParams(params),
        presentation,
      });
      setSharedViews((items) => [...items.filter((item) => item.id !== published.id), published]);
      setSavedViewName("");
      setSavedViewNotice(`Shared view published: ${published.name}`);
    } catch (caught) {
      setSavedViewNotice(caught instanceof Error ? caught.message : "Shared view could not be published.");
    } finally {
      setSavingSharedView(false);
    }
  };

  const visibleItems = useMemo<Array<IntegratedLibraryItem | LibraryDiscoveryItem>>(
    () => discoveryMode ? (discoveryData?.items || []) : (data?.items || []),
    [data?.items, discoveryData?.items, discoveryMode],
  );
  const selectedLoadedItems = useMemo(
    () => visibleItems.filter((item) => selectedIds.has(item.id)),
    [selectedIds, visibleItems],
  );

  const toggleSelection = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  };

  const selectVisiblePage = (checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      visibleItems.forEach((item) => {
        if (checked) next.add(item.id); else next.delete(item.id);
      });
      return next;
    });
  };

  const exportSelectedMetadata = () => {
    if (!selectedLoadedItems.length) return;
    const payload = selectedLoadedItems.map((item) => {
      if ("library" in item) {
        const revision = item.current_revision || item.latest_revision;
        return {
          code: item.code,
          title: item.title,
          document_type: item.library.node_type,
          document_class: item.profile.document_class,
          lifecycle_status: item.status,
          revision: revision?.revision_number || null,
          issue: revision?.issue_number || null,
          effective_date: revision?.effective_date || null,
          owner: item.library.owner?.assignee?.name || item.profile.owner_department || null,
          department: item.library.responsible_department?.assignee?.name || item.profile.owner_department || null,
          hierarchy: item.library.structure_path || null,
          source_filename: revision?.source_filename || null,
        };
      }
      const revision = item.current_revision || item.latest_revision;
      return {
        code: item.code,
        title: item.title,
        document_type: item.node.type,
        document_class: item.document_class,
        lifecycle_status: item.lifecycle_status,
        revision: revision?.revision_number || null,
        issue: revision?.issue_number || null,
        effective_date: revision?.effective_date || null,
        owner: item.owner.name || null,
        department: item.owner.department || null,
        hierarchy: item.node.path || null,
        source_filename: revision?.source_filename || null,
      };
    });
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `dms-library-metadata-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  };

  const pagination = discoveryMode ? discoveryData?.pagination : data?.pagination;
  const offlineSnapshot = discoveryMode ? discoveryData?.offline_snapshot : data?.offline_snapshot;
  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.per_page)) : 1;
  const canControl = Boolean((discoveryMode ? discoveryData?.capabilities.control : data?.capabilities.control));
  const hasRows = (discoveryMode ? Boolean(discoveryData?.items.length) : Boolean(data?.items.length)) || Boolean(catalogItems.length);

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

  const selectIntegratedItem = useCallback((item: IntegratedLibraryItem) => {
    setSelectedItem({ mode: "integrated", item });
  }, []);

  const selectDiscoveryItem = useCallback((item: LibraryDiscoveryItem) => {
    setSelectedItem({ mode: "discovery", item });
  }, []);

  const readSelectedItem = useCallback(() => {
    if (!selectedItem) return;
    if (selectedItem.mode === "integrated") openReader(selectedItem.item);
    else openDiscoveryReader(selectedItem.item);
  }, [openDiscoveryReader, openReader, selectedItem]);

  const openSelectedWorkspace = useCallback(() => {
    if (!selectedItem) return;
    navigate(`${basePath}/library/${selectedItem.item.id}`);
  }, [basePath, navigate, selectedItem]);

  return <DocumentControlShell
    title="Company document library"
    eyebrow={selectedJob ? "SELECT DOCUMENT / CONTROLLED WORK" : "CONTROLLED INFORMATION"}
    subtitle={selectedJob ? selectedJob.selectionPrompt : "Find current company information, inspect its controlled context, then open the full workspace only when lifecycle work is required."}
    canControl={canControl}
  >
    <div className={`dlibrary-layout${selectedItem ? " has-details" : ""}`}>
      <section className="dlibrary" data-testid="integrated-document-library" aria-busy={refreshing}>
        <div className="dlibrary__commandbar" aria-label="Library commands">
          {canControl && !selectedJob ? <button type="button" className="dc-button dc-button--primary" onClick={() => setUploadOpen(true)}><UploadCloud size={14} /> New / Upload</button> : null}
          {!selectedJob ? <button type="button" className="dc-button" onClick={() => { setLibraryServicesMode("scan"); setLibraryServicesOpen(true); }}><ScanLine size={14} /> Scan</button> : null}
          {!selectedJob ? <button type="button" className="dc-button" onClick={() => { setLibraryServicesMode("catalog"); setLibraryServicesOpen(true); }}><LibraryBig size={14} /> Import / Library</button> : null}
          {!selectedJob ? <button type="button" className="dc-button" onClick={() => { setLibraryServicesMode("warehouse"); setLibraryServicesOpen(true); }}><Search size={14} /> Search everything</button> : null}
          <button type="button" className="dc-button" disabled={refreshing} onClick={() => void load()}><RefreshCcw size={14} /> Refresh</button>
        </div>

        {!selectingDocumentForJob && visibleItems.length ? <div className="dlibrary__selection-bar" aria-label="Library selection actions">
          <label><input type="checkbox" checked={visibleItems.length > 0 && visibleItems.every((item) => selectedIds.has(item.id))} onChange={(event) => selectVisiblePage(event.target.checked)} /><span>Select this page</span></label>
          {selectedIds.size ? <>
            <strong>{selectedIds.size} selected</strong>
            <button type="button" className="dc-button" disabled={!selectedLoadedItems.length} onClick={exportSelectedMetadata}>Export metadata</button>
            <button type="button" className="dc-button" onClick={() => setSelectedIds(new Set())}>Clear selection</button>
          </> : <span>Select items for bounded bulk actions.</span>}
        </div> : null}

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
            <select aria-label="Document owner" value={filters.ownerName || ""} onChange={(event) => update("owner", event.target.value)}><option value="">All owners</option>{(data?.facets.owners || []).map((owner) => <option key={owner.value} value={owner.value}>{owner.name} ({owner.count})</option>)}</select>
            <select aria-label="Responsible department" value={filters.departmentCode || ""} onChange={(event) => update("department", event.target.value)}><option value="">All departments</option>{(data?.facets.departments || []).map((department) => <option key={department.value} value={department.value}>{department.name} ({department.count})</option>)}</select>
            <select aria-label="Document control class" value={filters.documentClass || ""} onChange={(event) => update("class", event.target.value)}><option value="">Internal + external</option><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External controlled</option><option value="RECORD">Record documents</option></select>
            <select aria-label="Document format" value={filters.sourceType || ""} onChange={(event) => update("format", event.target.value)}><option value="">All formats</option><option value="PDF">PDF</option><option value="DOCX">DOCX</option><option value="DOC">DOC</option><option value="ODT">ODT</option><option value="RTF">RTF</option></select>
            <select aria-label="Document lifecycle" value={filters.status || ""} onChange={(event) => update("status", event.target.value)}><option value="">All lifecycle states</option><option value="ACTIVE">Active</option><option value="SUPERSEDED">Superseded</option><option value="ARCHIVED">Archived</option></select>
            <button type="button" className="dc-button" aria-expanded={advancedFiltersOpen} onClick={() => setAdvancedFiltersOpen((open) => !open)}>More filters</button>
            <select aria-label="Sort company library" value={`${filters.sort || "code"}:${filters.direction || "asc"}`} onChange={(event) => updateSort(event.target.value)}><option value="code:asc">Code A–Z</option><option value="code:desc">Code Z–A</option><option value="title:asc">Title A–Z</option><option value="title:desc">Title Z–A</option><option value="type:asc">Document type</option><option value="status:asc">Lifecycle status</option></select>
          </> : <span className="dlibrary__discovery-note">Permission-filtered discovery · server-bounded</span>}
          {refreshing ? <span role="status" aria-live="polite">Updating…</span> : null}
          {offlineSnapshot ? <span className="dlibrary__offline-state" role="status">Offline snapshot · {formatDate(new Date(offlineSnapshot.stored_at).toISOString())}</span> : null}
        </div>

        {advancedFiltersOpen && !discoveryMode ? <div className="dlibrary__advanced-filters" aria-label="Advanced library filters">
          <label><span>Indexing</span><select value={filters.indexingStatus || ""} onChange={(event) => update("indexing_status", event.target.value)}><option value="">Any indexing state</option><option value="PENDING">Pending</option><option value="RUNNING">Running</option><option value="COMPLETED">Completed</option><option value="FAILED">Failed</option></select></label>
          <label><span>Structure</span><select value={filters.structureStatus || ""} onChange={(event) => update("structure_status", event.target.value)}><option value="">Any structure state</option><option value="ORPHANED">Orphaned</option></select></label>
          <label className="is-check"><input type="checkbox" checked={Boolean(filters.unresolvedOwnership)} onChange={(event) => update("unresolved_ownership", event.target.checked ? "1" : "")} /><span>Ownership unresolved</span></label>
          <label className="is-check"><input type="checkbox" checked={Boolean(filters.unresolvedRelationships)} onChange={(event) => update("unresolved_relationships", event.target.checked ? "1" : "")} /><span>Relationships unresolved</span></label>
          <label className="is-check"><input type="checkbox" checked={Boolean(filters.supersededReferenced)} onChange={(event) => update("superseded_referenced", event.target.checked ? "1" : "")} /><span>Superseded still referenced</span></label>
          <button type="button" className="dc-button" onClick={() => {
            const next = new URLSearchParams(params);
            ["type", "format", "class", "status", "owner", "department", "owner_user_id", "department_id", "indexing_status", "unresolved_ownership", "unresolved_relationships", "structure_status", "superseded_referenced"].forEach((key) => next.delete(key));
            next.set("page", "1");
            setParams(next);
          }}>Reset filters</button>
        </div> : null}

        <div className="dlibrary__presentation" aria-label="Library presentation">
          <span>{presentation === "list" ? "List" : presentation === "compact" ? "Compact list" : presentation === "cards" ? "Cards" : "Controlled register"}</span>
          <div role="group" aria-label="Choose library presentation">
            <button type="button" className={presentation === "list" ? "active" : ""} aria-pressed={presentation === "list"} onClick={() => setPresentation("list")}><List size={15} /> List</button>
            <button type="button" className={presentation === "compact" ? "active" : ""} aria-pressed={presentation === "compact"} onClick={() => setPresentation("compact")}><AlignJustify size={15} /> Compact</button>
            <button type="button" className={presentation === "cards" ? "active" : ""} aria-pressed={presentation === "cards"} onClick={() => setPresentation("cards")}><LayoutGrid size={15} /> Cards</button>
            <button type="button" className={presentation === "register" ? "active" : ""} aria-pressed={presentation === "register"} onClick={() => setPresentation("register")}><TableProperties size={15} /> Register</button>
          </div>
        </div>

        {!selectingDocumentForJob ? <div className="dlibrary__saved-views" aria-label="Saved library views">
          <label>
            <span>Saved view</span>
            <select
              aria-label="Apply saved library view"
              defaultValue=""
              onChange={(event) => {
                const [scope, id] = event.target.value.split(":");
                const view = scope === "personal"
                  ? personalViews.find((item) => item.id === id)
                  : sharedViews.find((item) => item.id === id);
                if (view) applySavedView(view);
                event.currentTarget.value = "";
              }}
            >
              <option value="">Choose a saved view…</option>
              {personalViews.length ? <optgroup label="My views">{personalViews.map((view) => <option key={view.id} value={`personal:${view.id}`}>{view.name}</option>)}</optgroup> : null}
              {sharedViews.length ? <optgroup label="Shared views">{sharedViews.map((view) => <option key={view.id} value={`shared:${view.id}`}>{view.name}{view.is_default ? " · Default" : ""}</option>)}</optgroup> : null}
            </select>
          </label>
          <label className="dlibrary__saved-view-name"><span>Save current filters</span><input value={savedViewName} maxLength={80} onChange={(event) => setSavedViewName(event.target.value)} placeholder="View name" /></label>
          <button type="button" className="dc-button" onClick={savePersonalView}>Save personal</button>
          {canControl ? <button type="button" className="dc-button" disabled={savingSharedView} onClick={() => void publishCurrentView()}>{savingSharedView ? "Publishing…" : "Publish shared"}</button> : null}
          {personalViews.length ? <details>
            <summary>Manage my views</summary>
            <div>{personalViews.map((view) => <button type="button" key={view.id} onClick={() => removePersonalView(view.id)}>Remove {view.name}</button>)}</div>
          </details> : null}
          {savedViewNotice ? <span role="status">{savedViewNotice}</span> : null}
        </div> : null}

        {!loading && !selectingDocumentForJob && catalogItems.length ? <section className="dlibrary__materials" aria-label="Library books and physical materials">
          <header>
            <div><LibraryBig size={17} /><span><strong>Books & library materials</strong><small>Tenant catalogue · physical and reference holdings</small></span></div>
            <button type="button" className="dc-button" onClick={() => { setLibraryServicesMode("catalog"); setLibraryServicesOpen(true); }}>Open physical library</button>
          </header>
          <div className="dlibrary__materials-grid">
            {catalogItems.map((item) => <article key={item.id}>
              <div className="dlibrary__material-cover">{item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : <LibraryBig size={22} />}</div>
              <div className="dlibrary__material-body">
                <small>{item.catalogue_code} · {item.material_type.replaceAll("_", " ")}</small>
                <strong>{item.title}</strong>
                <span>{item.authors?.join(", ") || "Unknown author"}</span>
                <span>{item.publisher || "Publisher not recorded"}{item.publication_year ? ` · ${item.publication_year}` : ""}</span>
                <span>{item.holdings ? `${item.holdings.available} available · ${item.holdings.checked_out} out · ${item.holdings.on_hold} held` : "No physical copies"}</span>
              </div>
              <button type="button" className="dc-button" onClick={() => { setLibraryServicesMode(item.holdings?.available ? "scan" : "catalog"); setLibraryServicesOpen(true); }}>Library actions</button>
            </article>)}
          </div>
        </section> : null}

        {loading ? <DocumentControlLoading label={selectedJob ? "Loading eligible controlled documents…" : "Opening the company library…"} /> : null}
        {error && !data && !discoveryData ? <DocumentControlError message={error} retry={() => void load()} /> : null}
        {!loading && !hasRows ? <DocumentControlEmpty icon={BookOpen} title="No document matches this view" message="Change the view, filters or search text. Access-controlled documents are shown only to permitted users." /> : null}

        {!loading && (presentation === "list" || presentation === "compact") && !discoveryMode && data?.items.length ? <div className={`dlibrary__list-view${presentation === "compact" ? " is-compact" : ""}`} aria-label="Controlled document list">
          {data.items.map((item) => {
            const [, typeLabel, TypeIcon] = categoryVisual(item.library.node_type);
            const revision = item.current_revision || item.latest_revision;
            const eligibility = selectedJob ? jobEligibility(item, selectedJob) : { allowed: true };
            return <article key={item.id} className={selectedItem?.item.id === item.id ? "is-selected" : ""}>
              <label className="dlibrary-row__select" aria-label={`Select ${item.code}`}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={(event) => toggleSelection(item.id, event.target.checked)} /></label>
              <button type="button" className="dlibrary-row__main" onClick={() => selectIntegratedItem(item)}>
                <span className="dlibrary-row__icon"><TypeIcon size={18} /></span>
                <span className="dlibrary-row__identity"><small>{item.code}</small><strong>{item.title}</strong><em>{typeLabel} · {item.library.structure_path || "Controlled information"}</em></span>
                <span className="dlibrary-row__meta"><strong>{revisionText(item)}</strong><small>{revision?.effective_date ? `Effective ${formatDate(revision.effective_date)}` : "No effective date"}</small></span>
                <span className="dlibrary-row__owner"><strong>{item.library.owner?.assignee?.name || item.profile.owner_department || item.owner_role}</strong><small>{item.profile.owner_department}</small></span>
                <DocumentControlStatus status={controlStatus(item)} kind={item.read_target.uncontrolled ? "warning" : "success"} />
              </button>
              <div className="dlibrary-row__actions">
                {selectedJob && canControl
                  ? <button type="button" className="dc-button dc-button--primary" disabled={!eligibility.allowed} title={eligibility.reason} onClick={() => selectForJob(item)}>{selectingChangeDocument ? "Select for change" : selectedJob.selectLabel}</button>
                  : <button type="button" className="dc-button" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}>Read</button>}
              </div>
            </article>;
          })}
        </div> : null}

        {!loading && (presentation === "list" || presentation === "compact") && discoveryMode && discoveryData?.items.length ? <div className={`dlibrary__list-view${presentation === "compact" ? " is-compact" : ""}`} aria-label="Document discovery list">
          {discoveryData.items.map((item) => {
            const [, typeLabel, TypeIcon] = categoryVisual(item.node.type);
            const revision = item.current_revision || item.latest_revision;
            return <article key={item.id} className={selectedItem?.item.id === item.id ? "is-selected" : ""}>
              <label className="dlibrary-row__select" aria-label={`Select ${item.code}`}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={(event) => toggleSelection(item.id, event.target.checked)} /></label>
              <button type="button" className="dlibrary-row__main" onClick={() => selectDiscoveryItem(item)}>
                <span className="dlibrary-row__icon"><TypeIcon size={18} /></span>
                <span className="dlibrary-row__identity"><small>{item.code}</small><strong>{item.title}</strong><em>{typeLabel} · {item.node.path || "Controlled information"}</em></span>
                <span className="dlibrary-row__meta"><strong>{discoveryRevisionText(item)}</strong><small>{revision?.effective_date ? `Effective ${formatDate(revision.effective_date)}` : revision?.source_filename || "No effective revision"}</small></span>
                <span className="dlibrary-row__owner"><strong>{item.owner.name || "Unassigned"}</strong><small>{item.owner.department || "No department"}</small></span>
                <DocumentControlStatus status={item.lifecycle_status} kind={statusKind(item.lifecycle_status)} />
              </button>
              <div className="dlibrary-row__actions"><button type="button" className="dc-button" disabled={!item.read_target_revision_id} onClick={() => openDiscoveryReader(item)}>Read</button></div>
            </article>;
          })}
        </div> : null}

        {!loading && presentation === "cards" && !discoveryMode && data?.items.length ? <div className="dlibrary__shelf" aria-label="Controlled document cards">
          {data.items.map((item) => {
            const [, typeLabel, TypeIcon] = categoryVisual(item.library.node_type);
            const revision = item.current_revision || item.latest_revision;
            const eligibility = selectedJob ? jobEligibility(item, selectedJob) : { allowed: true };
            return <article key={`${item.id}:${revision?.id || "none"}`} className={`dlibrary-card${selectedItem?.item.id === item.id ? " is-selected" : ""}`} data-document-type={item.library.node_type}>
              <label className="dlibrary-card__select" aria-label={`Select ${item.code}`}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={(event) => toggleSelection(item.id, event.target.checked)} /></label>
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
              <div className="dlibrary-card__context"><span>{item.library.structure_path || "Standard hierarchy"}</span><span>{item.library.semantic_relationships || 0} links · {item.library.integrations?.count || 0} modules · {item.library.generated_records || 0} records</span></div>
              <footer>
                {selectedJob && canControl ? <button type="button" className="dc-button dc-button--primary" disabled={!eligibility.allowed} title={eligibility.reason} onClick={() => selectForJob(item)}>{selectingChangeDocument ? "Select for change" : selectedJob.selectLabel}</button> : <>
                  <button type="button" className="dc-button dc-button--primary" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}>Read</button>
                  <button type="button" className="dc-button" onClick={() => selectIntegratedItem(item)}>Details</button>
                </>}
              </footer>
            </article>;
          })}
        </div> : null}

        {!loading && presentation === "cards" && discoveryMode && discoveryData?.items.length ? <div className="dlibrary__shelf" aria-label="Document discovery cards">
          {discoveryData.items.map((item) => {
            const [, typeLabel, TypeIcon] = categoryVisual(item.node.type);
            const revision = item.current_revision || item.latest_revision;
            return <article key={`${item.id}:${revision?.id || "none"}`} className={`dlibrary-card${selectedItem?.item.id === item.id ? " is-selected" : ""}`} data-document-type={item.node.type}>
              <label className="dlibrary-card__select" aria-label={`Select ${item.code}`}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={(event) => toggleSelection(item.id, event.target.checked)} /></label>
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
                <button type="button" className="dc-button dc-button--primary" disabled={!item.read_target_revision_id} onClick={() => openDiscoveryReader(item)}>Read</button>
                <button type="button" className="dc-button" onClick={() => selectDiscoveryItem(item)}>Details</button>
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
            onRowClick={(item) => selectIntegratedItem(item as IntegratedLibraryItem)}
            onSelectionChange={(items) => setSelectedIds(new Set(items.map((item) => item.id)))}
          />
        </Suspense> : null}

        {!loading && presentation === "register" && discoveryMode && discoveryData?.items.length ? <Suspense fallback={<DocumentControlLoading label="Opening discovery register…" />}>
          <DocumentLibraryRegisterGrid
            mode="discovery"
            rowData={discoveryData.items}
            columnDefs={discoveryColumns}
            defaultColDef={defaultColumn}
            onRowClick={(item) => selectDiscoveryItem(item as LibraryDiscoveryItem)}
            onSelectionChange={(items) => setSelectedIds(new Set(items.map((item) => item.id)))}
          />
        </Suspense> : null}

        {pagination ? <footer className="dlibrary__pagination">
          <span>{pagination.total ? `${(pagination.page - 1) * pagination.per_page + 1}–${Math.min(pagination.page * pagination.per_page, pagination.total)} of ${pagination.total}` : "0 documents"}</span>
          <select value={pagination.per_page} onChange={(event) => update("per_page", event.target.value)} aria-label="Documents per page"><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
          <button type="button" disabled={pagination.page <= 1 || refreshing} onClick={() => update("page", String(pagination.page - 1))}><ChevronLeft size={15} /> Previous</button>
          <span>Page {pagination.page} of {totalPages}</span>
          <button type="button" disabled={pagination.page >= totalPages || refreshing} onClick={() => update("page", String(pagination.page + 1))}>Next <ChevronRight size={15} /></button>
        </footer> : null}

        {libraryServicesOpen ? <LibraryOperationsPanel
          tenant={tenant}
          canControl={canControl}
          initialMode={libraryServicesMode}
          initialScan={params.get("library_scan")}
          onClose={() => {
            setLibraryServicesOpen(false);
            if (params.get("library_scan") || params.get("library_services")) {
              const next = new URLSearchParams(params);
              next.delete("library_scan");
              next.delete("library_services");
              setParams(next, { replace: true });
            }
          }}
        /> : null}
        <ControlledDocumentUploadDialog
          tenant={tenant}
          open={uploadOpen}
          allowApprovedIntake={canControl}
          onClose={() => setUploadOpen(false)}
          onUploaded={async (result) => {
            await load();
            if (!result.batch_upload) navigate(`${basePath}/library/${result.manual_id}?tab=workflow`);
          }}
        />
      </section>

      {selectedItem ? <DocumentLibraryDetailsPane
        tenant={tenant}
        selected={selectedItem}
        canControl={canControl}
        onClose={() => setSelectedItem(null)}
        onRead={readSelectedItem}
        onOpenWorkspace={canControl ? openSelectedWorkspace : undefined}
      /> : null}
    </div>
  </DocumentControlShell>;
}

import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { ControlledCopy, DocumentLibraryItem } from "./documentControl";
import { readApiCache, writeApiCache } from "./offlinePersistence";

const LIBRARY_OFFLINE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export type LibraryOfflineSnapshot = {
  stored_at: number;
};

export type LibraryPhysicalSummary = {
  total: number;
  on_shelf: number;
  checked_out: number;
  recalled: number;
  overdue: number;
};

export type LibraryExternalSummary = {
  provider: string;
  authority?: string | null;
  status: string;
  next_check_due_at?: string | null;
  revision_label?: string | null;
  currency_status: string;
  applicability_status: string;
};

export type IntegratedLibraryItem = DocumentLibraryItem & {
  library: {
    node_type: string;
    structure_path?: string | null;
    physical: LibraryPhysicalSummary;
    external?: LibraryExternalSummary | null;
    semantic_relationships?: number | null;
    integrations?: { count: number; modules: string[]; blocking: number } | null;
    generated_records?: number | null;
    owner?: { assignee?: { id?: string; name?: string; code?: string }; confirmation_status?: string } | null;
    responsible_department?: { assignee?: { id?: string; name?: string; code?: string } } | null;
  };
};

export type IntegratedLibraryResponse = {
  items: IntegratedLibraryItem[];
  facets: { node_types: Record<string, number>; visible_documents: number };
  capabilities: { read: boolean; control: boolean };
  pagination: { page: number; per_page: number; total: number; returned: number };
  offline_snapshot?: LibraryOfflineSnapshot;
};

export type IntegratedLibraryFilters = {
  q?: string;
  nodeType?: string;
  documentClass?: string;
  status?: string;
  ownerUserId?: string;
  departmentId?: string;
  indexingStatus?: string;
  unresolvedOwnership?: boolean;
  unresolvedRelationships?: boolean;
  structureStatus?: string;
  supersededReferenced?: boolean;
  sort?: "code" | "title" | "type" | "status";
  direction?: "asc" | "desc";
  page?: number;
  perPage?: number;
};

export type LibraryDiscoveryView =
  | "all"
  | "my-documents"
  | "favorites"
  | "recently-opened"
  | "recently-revised"
  | "awaiting-my-review"
  | "external-technical-data"
  | "due-for-review"
  | "superseded"
  | "archived";

export type LibraryDiscoveryItem = {
  id: string;
  code: string;
  title: string;
  manual_type: string;
  lifecycle_status: string;
  document_class: string;
  owner: { id?: string | null; name?: string | null; department?: string | null };
  node: { type: string; path?: string | null };
  current_revision?: {
    id: string;
    issue_number?: string | null;
    revision_number: string;
    status?: string | null;
    effective_date?: string | null;
    created_at?: string | null;
    source_filename?: string | null;
    page_count?: number | null;
  } | null;
  latest_revision?: {
    id: string;
    issue_number?: string | null;
    revision_number: string;
    status?: string | null;
    effective_date?: string | null;
    created_at?: string | null;
    source_filename?: string | null;
    page_count?: number | null;
  } | null;
  read_target_revision_id?: string | null;
  next_review_due?: string | null;
  last_opened_at?: string | null;
  favorite: boolean;
};

export type LibraryDiscoveryResponse = {
  view: LibraryDiscoveryView;
  items: LibraryDiscoveryItem[];
  capabilities: { read: boolean; control: boolean };
  pagination: { page: number; per_page: number; total: number; returned: number };
  offline_snapshot?: LibraryOfflineSnapshot;
};

export type PhysicalCopyRegisterItem = ControlledCopy & {
  document: { id: string; code: string; title: string; manual_type: string };
  revision: { id: string; issue_number?: string | null; revision_number: string; status: string };
  home_location_text: string;
  holder_display?: string | null;
  overdue: boolean;
  scan_path: string;
  label_path: string;
};

export type PhysicalCopyRegisterResponse = {
  items: PhysicalCopyRegisterItem[];
  pagination: { page: number; per_page: number; total: number; returned: number };
  summary: { on_shelf: number; checked_out: number; overdue: number };
};

export type ControlledCopyScan = {
  copy: ControlledCopy & {
    home_location_text: string;
    holder_display?: string | null;
    holder_visible: boolean;
    overdue: boolean;
  };
  document: { id: string; code: string; title: string; manual_type: string; status: string };
  revision: { id: string; issue_number?: string | null; revision_number: string; status: string; effective_date?: string | null };
  events: Array<{
    id: string;
    event_type: string;
    actor_user_id?: string | null;
    from_holder_user_id?: string | null;
    to_holder_user_id?: string | null;
    from_location?: string | null;
    to_location?: string | null;
    reason?: string | null;
    evidence?: Array<Record<string, unknown>>;
    created_at?: string | null;
  }>;
  reader_path: string;
  capabilities: {
    control: boolean;
    check_out: boolean;
    check_in: boolean;
    verify_location: boolean;
    print_label: boolean;
  };
};

export type ControlledCopyCustodian = {
  id: string;
  name: string;
  email: string;
  staff_code?: string | null;
  department_id?: string | null;
};

export type ControlledCopyEventType = "TRANSFER" | "LOCATION_CHANGE" | "RECALL" | "RETURN" | "WITHDRAW" | "DESTROY";

function workspacePath(tenant: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant.toLowerCase())}${suffix}`;
}

function queryString(values: Record<string, string | number | boolean | undefined | null>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== false) params.set(key, String(value));
  });
  const value = params.toString();
  return value ? `?${value}` : "";
}

function serverUtcDate(value?: string | null): string | null | undefined {
  if (!value) return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().replace(/Z$/, "");
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = typeof detail === "string" ? detail : String(detail?.message || JSON.stringify(detail || payload));
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function cachedLibraryApi<T extends object>(path: string): Promise<T & { offline_snapshot?: LibraryOfflineSnapshot }> {
  const readCached = async () => {
    const cached = await readApiCache<T>(path).catch(() => null);
    return cached ? { ...cached.value, offline_snapshot: { stored_at: cached.storedAt } } : null;
  };
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    const cached = await readCached();
    if (cached) return cached;
    throw new Error("This library view has not been saved on this device. Reconnect and open it once before using it offline.");
  }
  try {
    const response = await api<T>(path);
    void writeApiCache(path, response, LIBRARY_OFFLINE_TTL_MS);
    return response;
  } catch (error) {
    const cached = await readCached();
    if (cached) return cached;
    throw error;
  }
}

export function listIntegratedLibrary(tenant: string, filters: IntegratedLibraryFilters = {}): Promise<IntegratedLibraryResponse> {
  return cachedLibraryApi(`${workspacePath(tenant, "/documents")}${queryString({
    q: filters.q,
    node_type: filters.nodeType,
    document_class: filters.documentClass,
    status: filters.status,
    owner_user_id: filters.ownerUserId,
    department_id: filters.departmentId,
    indexing_status: filters.indexingStatus,
    unresolved_ownership: filters.unresolvedOwnership,
    unresolved_relationships: filters.unresolvedRelationships,
    structure_status: filters.structureStatus,
    superseded_referenced: filters.supersededReferenced,
    sort: filters.sort || "code",
    direction: filters.direction || "asc",
    page: filters.page || 1,
    per_page: filters.perPage || 50,
  })}`);
}

export function discoverLibrary(tenant: string, filters: { view?: LibraryDiscoveryView; q?: string; page?: number; perPage?: number } = {}): Promise<LibraryDiscoveryResponse> {
  return cachedLibraryApi(`${workspacePath(tenant, "/library-discovery")}${queryString({
    view: filters.view || "all",
    q: filters.q,
    page: filters.page || 1,
    per_page: filters.perPage || 50,
  })}`);
}

export function listPhysicalCopies(
  tenant: string,
  filters: { q?: string; status?: string; custody?: string; overdue?: boolean; page?: number; perPage?: number } = {},
): Promise<PhysicalCopyRegisterResponse> {
  return api(`${workspacePath(tenant, "/physical-copies")}${queryString({
    q: filters.q,
    status: filters.status,
    custody: filters.custody,
    overdue: filters.overdue,
    page: filters.page || 1,
    per_page: filters.perPage || 50,
  })}`);
}

export function registerPhysicalCopy(
  tenant: string,
  payload: {
    manual_id: string;
    revision_id: string;
    copy_number: string;
    format?: "HARDCOPY" | "OFFLINE_MEDIA";
    holder_user_id?: string | null;
    location_text: string;
    due_back_at?: string | null;
    metadata?: Record<string, unknown>;
  },
): Promise<ControlledCopy> {
  return api(workspacePath(tenant, "/controlled-copies"), {
    method: "POST",
    body: JSON.stringify({ ...payload, due_back_at: serverUtcDate(payload.due_back_at) }),
  });
}

export function scanPhysicalCopy(tenant: string, copyId: string): Promise<ControlledCopyScan> {
  return api(workspacePath(tenant, `/controlled-copies/${encodeURIComponent(copyId)}/scan`));
}

export function circulatePhysicalCopy(
  tenant: string,
  copyId: string,
  payload: {
    action: "CHECK_OUT" | "CHECK_IN" | "VERIFY_LOCATION";
    due_back_at?: string | null;
    holder_user_id?: string | null;
    location_text?: string | null;
    acknowledgement?: boolean;
    comments?: string | null;
  },
): Promise<ControlledCopyScan> {
  return api(workspacePath(tenant, `/controlled-copies/${encodeURIComponent(copyId)}/circulation`), {
    method: "POST",
    body: JSON.stringify({ ...payload, due_back_at: serverUtcDate(payload.due_back_at) }),
  });
}

export function listControlledCopyCustodians(tenant: string, q?: string): Promise<ControlledCopyCustodian[]> {
  return api(`${workspacePath(tenant, "/controlled-copy-custodians")}${queryString({ q, limit: 75 })}`);
}

export async function recordPhysicalCopyEvent(
  tenant: string,
  copyId: string,
  payload: {
    event_type: ControlledCopyEventType;
    to_holder_user_id?: string | null;
    to_location?: string | null;
    reason?: string | null;
    evidence?: Array<Record<string, unknown>>;
  },
): Promise<ControlledCopyScan> {
  await api(workspacePath(tenant, `/controlled-copies/${encodeURIComponent(copyId)}/events`), {
    method: "POST",
    body: JSON.stringify({ ...payload, evidence: payload.evidence || [] }),
  });
  return scanPhysicalCopy(tenant, copyId);
}

export async function recordPhysicalCopyIncident(
  tenant: string,
  copyId: string,
  payload: { incident_type: "DAMAGE" | "LOSS"; reason: string; evidence: Array<Record<string, unknown>> },
): Promise<ControlledCopyScan> {
  await api(workspacePath(tenant, `/controlled-copies/${encodeURIComponent(copyId)}/incidents`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return scanPhysicalCopy(tenant, copyId);
}

export async function downloadPhysicalCopyLabel(tenant: string, copyId: string, filename: string): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${workspacePath(tenant, `/controlled-copies/${encodeURIComponent(copyId)}/label.pdf`)}`, {
    headers: authHeaders(),
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(`QR label could not be generated (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}


export type LibraryCatalogItem = {
  id: string;
  catalogue_code: string;
  material_type: "BOOK" | "JOURNAL" | "MAGAZINE" | "REFERENCE" | "MEDIA" | "MAP" | "ARCHIVE_OBJECT" | "OTHER";
  title: string;
  subtitle?: string | null;
  authors: string[];
  publisher?: string | null;
  publication_year?: number | null;
  edition?: string | null;
  language?: string | null;
  identifiers: Record<string, string>;
  subjects: string[];
  description?: string | null;
  source_provider: string;
  source_record_id?: string | null;
  source_url?: string | null;
  cover_url?: string | null;
  restricted: boolean;
  circulation_policy: {
    circulatable: boolean;
    self_checkout: boolean;
    loan_period_days: number;
    max_renewals: number;
    reference_only: boolean;
  };
  status: string;
  holdings?: { total: number; available: number; checked_out: number; on_hold: number; overdue: number };
};

export type LibraryHolding = {
  id: string;
  catalog_item_id: string;
  barcode: string;
  qr_token?: string | null;
  accession_number?: string | null;
  call_number?: string | null;
  format: string;
  home_location: string;
  current_location: string;
  status: string;
  holder_user_id?: string | null;
  checked_out_at?: string | null;
  due_at?: string | null;
  renewal_count?: number | null;
  last_inventory_at?: string | null;
  overdue: boolean;
  version: number;
};

export type ExternalCatalogResult = {
  provider: "GOOGLE_BOOKS" | "OPEN_LIBRARY";
  provider_id?: string | null;
  material_type: string;
  title: string;
  subtitle?: string | null;
  authors: string[];
  publisher?: string | null;
  published_date?: string | null;
  language?: string | null;
  identifiers: Record<string, string>;
  subjects: string[];
  description?: string | null;
  cover_url?: string | null;
  source_url?: string | null;
  existing_catalog_item_id?: string | null;
};

export type ExternalCatalogSearchResponse = {
  query: string;
  items: ExternalCatalogResult[];
  provider_errors: Array<{ provider: string; message: string }>;
  links: { google_search: string; google_books: string; open_library: string };
  privacy_notice: string;
};

export type LibraryCatalogResponse = {
  items: LibraryCatalogItem[];
  facets: { material_types: Record<string, number> };
  pagination: { page: number; per_page: number; total: number; returned: number };
  capabilities: { read: boolean; control: boolean };
};

export type LibraryHoldingScan = {
  item: LibraryCatalogItem;
  holding: LibraryHolding;
  events: Array<{
    id: string;
    event_type: string;
    patron_user_id?: string | null;
    from_status?: string | null;
    to_status?: string | null;
    from_location?: string | null;
    to_location?: string | null;
    due_at?: string | null;
    notes?: string | null;
    created_at?: string | null;
  }>;
  capabilities: {
    control: boolean;
    self_checkout: boolean;
    check_in: boolean;
    renew: boolean;
    place_hold: boolean;
  };
};

export type MyLibraryAccount = {
  loans: Array<{ item: LibraryCatalogItem; holding: LibraryHolding }>;
  holds: Array<{
    id: string;
    status: string;
    pickup_location?: string | null;
    expires_at?: string | null;
    item: LibraryCatalogItem;
  }>;
};

export function searchExternalCatalog(
  tenant: string,
  query: string,
  provider: "all" | "google" | "openlibrary" = "all",
  limit = 8,
): Promise<ExternalCatalogSearchResponse> {
  return api(`${workspacePath(tenant, "/catalog/external-search")}${queryString({ q: query, provider, limit })}`);
}

export function listLibraryCatalog(
  tenant: string,
  filters: { q?: string; materialType?: string; availability?: "any" | "available" | "checked_out"; page?: number; perPage?: number } = {},
): Promise<LibraryCatalogResponse> {
  return api(`${workspacePath(tenant, "/catalog/items")}${queryString({
    q: filters.q,
    material_type: filters.materialType,
    availability: filters.availability || "any",
    page: filters.page || 1,
    per_page: filters.perPage || 30,
  })}`);
}

export function createLibraryCatalogItem(
  tenant: string,
  payload: {
    catalogue_code: string;
    material_type?: string;
    title: string;
    subtitle?: string | null;
    authors?: string[];
    publisher?: string | null;
    publication_year?: number | null;
    edition?: string | null;
    language?: string | null;
    identifiers?: Record<string, string>;
    subjects?: string[];
    description?: string | null;
    source_provider?: string;
    source_record_id?: string | null;
    source_url?: string | null;
    cover_url?: string | null;
    restricted?: boolean;
    access_scope?: Record<string, unknown>;
    circulation_policy?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  },
): Promise<LibraryCatalogItem> {
  return api(workspacePath(tenant, "/catalog/items"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createLibraryHolding(
  tenant: string,
  itemId: string,
  payload: {
    barcode: string;
    accession_number?: string | null;
    call_number?: string | null;
    format?: string;
    home_location: string;
    acquired_on?: string | null;
    metadata?: Record<string, unknown>;
  },
): Promise<LibraryHolding> {
  return api(workspacePath(tenant, `/catalog/items/${encodeURIComponent(itemId)}/holdings`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function scanLibraryHolding(tenant: string, code: string): Promise<LibraryHoldingScan> {
  return api(workspacePath(tenant, `/catalog/scan/${encodeURIComponent(code.trim())}`));
}

export function circulateLibraryHolding(
  tenant: string,
  holdingId: string,
  payload: {
    action: "CHECK_OUT" | "CHECK_IN" | "RENEW" | "VERIFY_LOCATION";
    patron_user_id?: string | null;
    due_at?: string | null;
    location?: string | null;
    acknowledgement?: boolean;
    override_hold?: boolean;
    comments?: string | null;
  },
): Promise<{ item: LibraryCatalogItem; holding: LibraryHolding }> {
  return api(workspacePath(tenant, `/catalog/holdings/${encodeURIComponent(holdingId)}/circulation`), {
    method: "POST",
    body: JSON.stringify({ ...payload, due_at: serverUtcDate(payload.due_at) }),
  });
}

export function placeLibraryHold(
  tenant: string,
  itemId: string,
  payload: { pickup_location?: string | null; expires_at?: string | null } = {},
): Promise<{ id: string; status: string; already_exists: boolean }> {
  return api(workspacePath(tenant, `/catalog/items/${encodeURIComponent(itemId)}/holds`), {
    method: "POST",
    body: JSON.stringify({ ...payload, expires_at: serverUtcDate(payload.expires_at) }),
  });
}

export function cancelLibraryHold(tenant: string, holdId: string): Promise<{ id: string; status: string }> {
  return api(workspacePath(tenant, `/catalog/holds/${encodeURIComponent(holdId)}`), { method: "DELETE" });
}

export function getMyLibraryAccount(tenant: string): Promise<MyLibraryAccount> {
  return api(workspacePath(tenant, "/catalog/me"));
}

export async function downloadLibraryHoldingLabel(
  tenant: string,
  holdingId: string,
  filename: string,
): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}${workspacePath(tenant, `/catalog/holdings/${encodeURIComponent(holdingId)}/label.pdf`)}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) throw new Error(`Library label could not be generated (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}


export type LibraryHoldingRegisterResponse = {
  items: Array<{ item: LibraryCatalogItem; holding: LibraryHolding }>;
  pagination: { page: number; per_page: number; total: number; returned: number };
  summary: { available: number; checked_out: number; on_hold: number; overdue: number; exceptions: number };
};

export function listLibraryHoldings(
  tenant: string,
  filters: { q?: string; status?: string; overdue?: boolean; page?: number; perPage?: number } = {},
): Promise<LibraryHoldingRegisterResponse> {
  return api(`${workspacePath(tenant, "/catalog/holdings")}${queryString({
    q: filters.q,
    status: filters.status,
    overdue: filters.overdue,
    page: filters.page || 1,
    per_page: filters.perPage || 50,
  })}`);
}

export function controlLibraryHolding(
  tenant: string,
  holdingId: string,
  payload: {
    action: "MARK_LOST" | "MARK_DAMAGED" | "SEND_REPAIR" | "RETURN_TO_SHELF" | "WITHDRAW";
    location?: string | null;
    reason: string;
    evidence?: Array<Record<string, unknown>>;
  },
): Promise<{ item: LibraryCatalogItem; holding: LibraryHolding }> {
  return api(workspacePath(tenant, `/catalog/holdings/${encodeURIComponent(holdingId)}/control`), {
    method: "POST",
    body: JSON.stringify({ ...payload, evidence: payload.evidence || [] }),
  });
}


export type WarehouseSearchScope = "everything" | "repository" | "library" | "records" | "external";

export type WarehouseSearchResult = {
  kind: "GOVERNED_RESOURCE" | "CONTROLLED_DOCUMENT" | "LIBRARY_ITEM" | "RETAINED_RECORD";
  id: string;
  title: string;
  target_path?: string | null;
  code?: string | null;
  heading?: string | null;
  page_number?: number | null;
  snippet?: string | null;
  record_number?: string | null;
  series_code?: string | null;
  catalogue_code?: string | null;
  authors?: string[];
  status?: string | null;
  disposition_status?: string | null;
  resource_type?: string | null;
  classification?: string | null;
  source_entity_type?: string | null;
  copies?: { total: number; revision_required: number };
};

export type WarehouseSearchResponse = {
  query: string;
  scope: WarehouseSearchScope;
  groups: {
    governed_resources: WarehouseSearchResult[];
    controlled_documents: WarehouseSearchResult[];
    library_items: WarehouseSearchResult[];
    retained_records: WarehouseSearchResult[];
  };
  counts: {
    governed_resources: number;
    controlled_documents: number;
    library_items: number;
    retained_records: number;
  };
  internet: {
    enabled: boolean;
    privacy: string;
    links: Record<string, string>;
  };
  capabilities: { control: boolean };
};

export function searchTenantWarehouse(
  tenant: string,
  query: string,
  limit = 12,
  scope: WarehouseSearchScope = "everything",
): Promise<WarehouseSearchResponse> {
  return api(`${workspacePath(tenant, "/search")}${queryString({ q: query, scope, limit })}`);
}

export type WarehouseOverviewResponse = {
  resources: { total: number; by_type: Record<string, number> };
  versions: { total: number; by_status: Record<string, number> };
  physical_copies: { total: number; by_status: Record<string, number>; revision_required: number };
  relationships: { total: number; unverified: number };
  my_work: { active_loans: number; active_holds: number; acknowledgements_completed: number };
  capabilities: { control: boolean };
};

export function getWarehouseOverview(tenant: string): Promise<WarehouseOverviewResponse> {
  return api(workspacePath(tenant, "/warehouse/overview"));
}

export type WarehouseImpactResponse = {
  root_record_id: string;
  depth: number;
  nodes: Array<{
    id: string;
    resource_type: string;
    canonical_code: string;
    title: string;
    classification: string;
    lifecycle_status: string;
    target_path?: string | null;
    revision_required_copies: number;
  }>;
  edges: Array<{
    id: string;
    source_record_id: string;
    source_version_id?: string | null;
    relationship_type: string;
    target_record_id: string;
    target_version_id?: string | null;
    verified: boolean;
    verified_by_user_id?: string | null;
    effective_from?: string | null;
    effective_to?: string | null;
  }>;
  summary: {
    resources: number;
    relationships: number;
    unverified_relationships: number;
    revision_required_copies: number;
  };
};

export function getWarehouseImpact(tenant: string, recordId: string, depth = 2): Promise<WarehouseImpactResponse> {
  return api(`${workspacePath(tenant, `/warehouse/resources/${encodeURIComponent(recordId)}/impact`)}${queryString({ depth })}`);
}

export function verifyWarehouseRelationship(tenant: string, relationshipId: string): Promise<{ id: string; status: string; verified: boolean }> {
  return api(workspacePath(tenant, `/warehouse/relationships/${encodeURIComponent(relationshipId)}/verify`), { method: "POST" });
}

export type WarehouseReconcileResponse = {
  status: "RECONCILED";
  counts: {
    controlled_documents: number;
    controlled_versions: number;
    controlled_copies: number;
    library_items: number;
    library_holdings: number;
    retained_records: number;
    relationships?: number;
    acknowledgements?: number;
    external_references?: number;
    workflows?: number;
    patrons?: number;
    loans?: number;
    holds?: number;
    item_events?: number;
    retention_rules?: number;
    collections?: number;
  };
};

export function reconcileTenantWarehouse(tenant: string): Promise<WarehouseReconcileResponse> {
  return api(workspacePath(tenant, "/warehouse/reconcile"), { method: "POST" });
}

export type WarehouseRevisionException = {
  resource: {
    id: string;
    resource_type: string;
    canonical_code: string;
    title: string;
    classification: string;
    lifecycle_status: string;
    target_path?: string | null;
  };
  copy: {
    id: string;
    copy_number?: string | null;
    barcode: string;
    location?: string | null;
    installed_version?: string | null;
    required_version?: string | null;
    status: string;
  };
};

export function listWarehouseRevisionExceptions(
  tenant: string,
  page = 1,
  perPage = 100,
): Promise<{ items: WarehouseRevisionException[]; pagination: { page: number; per_page: number; total: number; returned: number } }> {
  return api(`${workspacePath(tenant, "/warehouse/revision-exceptions")}${queryString({ page, per_page: perPage })}`);
}


export type LibraryInventoryObservation = {
  id: string;
  holding_id: string;
  barcode: string;
  title: string;
  observed_location: string;
  expected_location: string;
  outcome: "MATCH" | "MISPLACED" | "EXCEPTION";
  observed_at?: string | null;
};

export type LibraryInventorySession = {
  id: string;
  location_prefix: string;
  status: "OPEN" | "CLOSED" | "CANCELLED";
  expected_count: number;
  observed_count: number;
  misplaced_count: number;
  missing_count: number;
  started_at?: string | null;
  closed_at?: string | null;
  observations?: LibraryInventoryObservation[];
};

export function createLibraryInventorySession(
  tenant: string,
  payload: { location_prefix: string; notes?: string | null },
): Promise<LibraryInventorySession> {
  return api(workspacePath(tenant, "/catalog/inventory-sessions"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getLibraryInventorySession(tenant: string, sessionId: string): Promise<LibraryInventorySession> {
  return api(workspacePath(tenant, `/catalog/inventory-sessions/${encodeURIComponent(sessionId)}`));
}

export function scanLibraryInventorySession(
  tenant: string,
  sessionId: string,
  payload: { code: string; observed_location: string },
): Promise<{ duplicate: boolean; barcode: string; title: string; outcome: string; expected_location: string; observed_location: string }> {
  return api(workspacePath(tenant, `/catalog/inventory-sessions/${encodeURIComponent(sessionId)}/scan`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function closeLibraryInventorySession(
  tenant: string,
  sessionId: string,
  notes?: string,
): Promise<LibraryInventorySession> {
  return api(workspacePath(tenant, `/catalog/inventory-sessions/${encodeURIComponent(sessionId)}/close`), {
    method: "POST",
    body: JSON.stringify({ notes: notes || null }),
  });
}


export type LibraryPatron = {
  id: string;
  name: string;
  email: string;
  staff_code?: string | null;
  role: string;
  department?: string | null;
};

export function searchLibraryPatrons(tenant: string, q?: string, limit = 30): Promise<{ items: LibraryPatron[] }> {
  return api(`${workspacePath(tenant, "/catalog/patrons")}${queryString({ q, limit })}`);
}


export type MarcXmlImportResponse = {
  dry_run: boolean;
  records_received: number;
  importable?: number;
  imported?: number;
  skipped: number;
  errors?: Array<{ catalogue_code: string; title: string; error: string }>;
  items: Array<Record<string, unknown>>;
};

export function importLibraryMarcXml(
  tenant: string,
  marcxml: string,
  options: {
    dryRun?: boolean;
    restricted?: boolean;
    accessScope?: Record<string, unknown>;
    circulationPolicy?: Record<string, unknown>;
  } = {},
): Promise<MarcXmlImportResponse> {
  return api(workspacePath(tenant, "/catalog/marcxml/import"), {
    method: "POST",
    body: JSON.stringify({
      marcxml,
      dry_run: Boolean(options.dryRun),
      restricted: Boolean(options.restricted),
      access_scope: options.accessScope || {},
      circulation_policy: options.circulationPolicy || {},
    }),
  });
}

export async function downloadLibraryMarcXml(
  tenant: string,
  filename = "library-marc21.xml",
): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}${workspacePath(tenant, "/catalog/marcxml/export")}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) throw new Error(`MARCXML export could not be generated (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

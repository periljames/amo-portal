import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { ControlledCopy, DocumentLibraryItem } from "./documentControl";

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
  // Existing Document Control date columns use UTC-naive service timestamps.
  // Preserve the actual instant while avoiding aware/naive comparison failures.
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

export function listIntegratedLibrary(
  tenant: string,
  filters: IntegratedLibraryFilters = {},
): Promise<IntegratedLibraryResponse> {
  return api(`${workspacePath(tenant, "/documents")}${queryString({
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

export function discoverLibrary(
  tenant: string,
  filters: { view?: LibraryDiscoveryView; q?: string; page?: number; perPage?: number } = {},
): Promise<LibraryDiscoveryResponse> {
  return api(`${workspacePath(tenant, "/library-discovery")}${queryString({
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

import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { trackProductWorkflow } from "./productAnalytics";

export type DocumentControlSettings = {
  tenant_id: string;
  default_retention_years: number;
  default_review_interval_months: number;
  regulated_workflow_enabled: boolean;
  default_ack_required: boolean;
  configured: boolean;
};

export type ArchiveRegister = {
  items: Array<{
    manual: { id: string; code: string; title: string };
    revision: Record<string, unknown>;
    superseded_by_revision_id?: string | null;
    archive_evidence?: Record<string, unknown> | null;
  }>;
  total: number;
};

export type ListOfEffectivePages = {
  manual: { id: string; code: string; title: string };
  revision: Record<string, unknown>;
  generated_at: string;
  rows: Array<{
    page_number: number;
    section_id?: string | null;
    section?: string | null;
    issue_number?: string | null;
    revision_number?: string | null;
    effective_date?: string | null;
    source: string;
  }>;
  complete_page_map: boolean;
  warning?: string | null;
};

function workspacePath(tenant: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant)}${suffix}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || JSON.stringify(payload?.detail || message);
    } catch {
      // Keep fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function getDocumentControlSettings(tenant: string): Promise<DocumentControlSettings> {
  return request(workspacePath(tenant, "/settings"));
}

export function updateDocumentControlSettings(
  tenant: string,
  payload: Omit<DocumentControlSettings, "tenant_id" | "configured">,
): Promise<DocumentControlSettings> {
  return trackProductWorkflow({
    module: "document-control",
    workflow: "document-control-settings-update",
    source: "document-control",
    operation: () => request(workspacePath(tenant, "/settings"), { method: "PUT", body: JSON.stringify(payload) }),
  });
}

export function updateDocumentMetadata(
  tenant: string,
  manualId: string,
  payload: { title?: string; code?: string; manual_type?: string; owner_role?: string },
): Promise<{ id: string; code: string; title: string; manual_type: string; owner_role: string }> {
  return trackProductWorkflow({
    module: "document-control",
    workflow: "document-metadata-update",
    source: "document-control",
    operation: () => request(workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}/metadata`), { method: "PATCH", body: JSON.stringify(payload) }),
  });
}

export function getArchiveRegister(tenant: string, manualId?: string): Promise<ArchiveRegister> {
  const query = manualId ? `?manual_id=${encodeURIComponent(manualId)}` : "";
  return request(`${workspacePath(tenant, "/archive")}${query}`);
}

export function getListOfEffectivePages(tenant: string, manualId: string, revisionId?: string): Promise<ListOfEffectivePages> {
  const query = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  return request(`${workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}/lep`)}${query}`);
}

export function getDocumentRegulationLinks(tenant: string, manualId: string, revisionId?: string): Promise<Array<Record<string, unknown>>> {
  const query = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  return request(`${workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}/regulation-links`)}${query}`);
}

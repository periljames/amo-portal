import { getApiBaseUrl } from "./config";
import { getToken, handleAuthFailure } from "./auth";

const API_BASE = getApiBaseUrl();

export type ManualSummary = {
  id: string;
  code: string;
  title: string;
  manual_type: string;
  status: string;
  current_published_rev_id: string | null;
};

export type ManualRevision = {
  id: string;
  manual_id: string;
  rev_number: string;
  issue_number?: string | null;
  status_enum: string;
  effective_date?: string | null;
  published_at?: string | null;
  immutable_locked: boolean;
};

export type ManualReadPayload = {
  revision_id: string;
  status: string;
  not_published: boolean;
  sections: Array<{ id: string; heading: string; anchor_slug: string; level: number }>;
  blocks: Array<{ section_id: string; html: string; text: string; change_hash: string }>;
};

export type ManualWorkflowPayload = {
  revision_id: string;
  status: string;
  requires_authority_approval: boolean;
  history: Array<{ action: string; at: string; actor_id?: string | null }>;
};

export type ManualDiffPayload = {
  revision_id: string;
  baseline_revision_id?: string | null;
  summary_json: Record<string, number>;
};

export type ManualExportPayload = {
  id: string;
  controlled: boolean;
  watermark_uncontrolled: boolean;
  generated_at: string;
  sha256: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json",
    },
  });
  if (!resp.ok) {
    if (resp.status === 401) handleAuthFailure();
    throw new Error(`Request failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listManuals(tenantSlug: string): Promise<ManualSummary[]> {
  return request<ManualSummary[]>(`/manuals/t/${tenantSlug}`);
}

export async function getManual(tenantSlug: string, manualId: string): Promise<ManualSummary> {
  return request<ManualSummary>(`/manuals/t/${tenantSlug}/${manualId}`);
}

export async function listRevisions(tenantSlug: string, manualId: string): Promise<ManualRevision[]> {
  return request<ManualRevision[]>(`/manuals/t/${tenantSlug}/${manualId}/revisions`);
}

export async function getMasterList(tenantSlug: string) {
  return request<any[]>(`/manuals/t/${tenantSlug}/master-list`);
}

export async function getRevisionRead(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualReadPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/read`);
}

export async function getRevisionDiff(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualDiffPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/diff`);
}

export async function getRevisionWorkflow(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualWorkflowPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/workflow`);
}

export async function transitionRevision(
  tenantSlug: string,
  manualId: string,
  revId: string,
  action: string,
  comment?: string,
) {
  return request<ManualWorkflowPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/workflow`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
}

export async function acknowledgeRevision(tenantSlug: string, manualId: string, revId: string, acknowledgementText: string) {
  return request<{ status: string }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ acknowledgement_text: acknowledgementText }),
  });
}

export async function listRevisionExports(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualExportPayload[]>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/exports`);
}

export async function createRevisionExport(
  tenantSlug: string,
  manualId: string,
  revId: string,
  payload: { controlled_bool: boolean; watermark_uncontrolled_bool: boolean; version_label?: string },
) {
  return request<{ id: string; sha256: string; storage_uri: string }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/exports`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

import { getApiBaseUrl } from "./config";
import { getToken, handleAuthFailure } from "./auth";

const API_BASE = getApiBaseUrl();

const MANUALS_UPDATED_EVENT = "amo:manuals-updated";
const MANUALS_UPDATED_STORAGE_KEY = "amo_manuals_updated";

type ManualsUpdatedDetail = {
  tenantSlug: string;
  reason: string;
  at: number;
};

export function emitManualsUpdated(tenantSlug: string, reason: string): void {
  if (typeof window === "undefined") return;
  const detail: ManualsUpdatedDetail = { tenantSlug, reason, at: Date.now() };
  window.dispatchEvent(new CustomEvent<ManualsUpdatedDetail>(MANUALS_UPDATED_EVENT, { detail }));
  try {
    window.localStorage.setItem(MANUALS_UPDATED_STORAGE_KEY, JSON.stringify(detail));
  } catch {
    // ignore storage write issues
  }
}

export function subscribeManualsUpdated(
  callback: (detail: { tenantSlug: string; reason: string; at: number }) => void,
): () => void {
  if (typeof window === "undefined") return () => {};

  const onCustom = (event: Event) => {
    const customEvent = event as CustomEvent<ManualsUpdatedDetail>;
    if (customEvent.detail) callback(customEvent.detail);
  };

  const onStorage = (event: StorageEvent) => {
    if (event.key !== MANUALS_UPDATED_STORAGE_KEY || !event.newValue) return;
    try {
      const parsed = JSON.parse(event.newValue) as ManualsUpdatedDetail;
      callback(parsed);
    } catch {
      // ignore parse errors
    }
  };

  window.addEventListener(MANUALS_UPDATED_EVENT, onCustom as EventListener);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(MANUALS_UPDATED_EVENT, onCustom as EventListener);
    window.removeEventListener("storage", onStorage);
  };
}


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
  const result = await request<ManualWorkflowPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/workflow`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
  emitManualsUpdated(tenantSlug, `workflow:${action}`);
  return result;
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


export type ManualProcessingStatus = {
  revision_id: string;
  stage: string;
  actor_id?: string | null;
  at?: string | null;
};

export async function getProcessingStatus(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualProcessingStatus>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/processing/status`);
}

export async function runProcessor(tenantSlug: string, manualId: string, revId: string) {
  return request<{ status: string; job_id: string }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/processing/run`, { method: "POST", body: JSON.stringify({ mode: "processor" }) });
}

export async function runOcr(tenantSlug: string, manualId: string, revId: string) {
  return request<{ status: string; job_id: string }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/ocr/run`, { method: "POST", body: JSON.stringify({ mode: "ocr" }) });
}

export async function generateOutline(tenantSlug: string, manualId: string, revId: string) {
  return request<{ status: string; generated: number }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/outline/generate`, { method: "POST", body: JSON.stringify({}) });
}


export async function uploadDocxRevision(
  tenantSlug: string,
  payload: {
    code: string;
    title: string;
    rev_number: string;
    issue_number: string;
    manual_type?: string;
    owner_role?: string;
    file: File;
  },
) {
  const token = getToken();
  const body = new FormData();
  body.append("code", payload.code);
  body.append("title", payload.title);
  body.append("rev_number", payload.rev_number);
  if (payload.issue_number) body.append("issue_number", payload.issue_number);
  if (payload.manual_type) body.append("manual_type", payload.manual_type);
  if (payload.owner_role) body.append("owner_role", payload.owner_role);
  body.append("file", payload.file);

  const resp = await fetch(`${API_BASE}/manuals/t/${tenantSlug}/upload-docx`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body,
  });
  if (!resp.ok) {
    if (resp.status === 401) handleAuthFailure();
    throw new Error(`Request failed: ${resp.status}`);
  }
  const result = (await resp.json()) as { manual_id: string; revision_id: string; status: string; paragraphs: number };
  emitManualsUpdated(tenantSlug, "upload-docx");
  return result;
}


export async function previewDocxUpload(tenantSlug: string, file: File) {
  const token = getToken();
  const body = new FormData();
  body.append("file", file);

  const resp = await fetch(`${API_BASE}/manuals/t/${tenantSlug}/upload-docx/preview`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body,
  });
  if (!resp.ok) {
    if (resp.status === 401) handleAuthFailure();
    throw new Error(`Preview request failed: ${resp.status}`);
  }
  return (await resp.json()) as {
    filename: string;
    heading: string;
    paragraph_count: number;
    sample: string[];
  };
}

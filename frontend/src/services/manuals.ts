import { getToken, authHeaders } from "./auth";
import { apiDelete, apiGet, apiPost, apiPostForm } from "./crs";


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
  manual?: { id: string; code: string; title: string; manual_type: string };
  sections: Array<{ id: string; heading: string; anchor_slug: string; level: number }>;
  blocks: Array<{ section_id: string; html: string; text: string; change_hash: string }>;
};

export type ManualFeaturedEntry = {
  manual_id: string;
  code: string;
  title: string;
  manual_type: string;
  current_revision: string | null;
  open_count: number;
};

export type ManualDocxPreview = {
  filename: string;
  heading: string;
  paragraph_count: number;
  sample: string[];
  outline: string[];
  metadata: {
    part_number?: string | null;
    manual_type?: string | null;
    title?: string | null;
    revision_number?: string | null;
    issue_number?: string | null;
    effective_date?: string | null;
  };
  excerpt: string;
};

export type ManualOCRVerifyPayload = {
  revision_id: string;
  detected_ref?: string | null;
  detected_date?: string | null;
  typed_ref?: string | null;
  typed_date?: string | null;
  ref_match: boolean;
  date_match: boolean;
  verified: boolean;
  text_excerpt: string;
};

export type ManualWorkflowPayload = {
  revision_id: string;
  status: string;
  requires_authority_approval: boolean;
  allowed_actions?: string[];
  process_rail?: Array<{ key: string; label: string; state: string; at?: string | null }>;
  current_stage?: string;
  authority_approval_ref?: string | null;
  quick_review?: {
    changed_sections?: number;
    changed_blocks?: number;
    added?: number;
    removed?: number;
    changed_pages?: string[];
    change_highlights?: string[];
  };
  history: Array<{ action: string; at: string; actor_id?: string | null }>;
};

export type ManualLifecycleTransitionPayload = ManualWorkflowPayload & {
  previous_state?: string;
  state?: string;
};

export type ManualDiffPayload = {
  revision_id: string;
  baseline_revision_id?: string | null;
  summary_json: Record<string, number>;
};

export type ManualComparisonPayload = {
  baseline_revision_id?: string | null;
  current_lines: Array<{ line: string; kind: "added" | "removed" | "same" }>;
  baseline_lines: Array<{ line: string; kind: "added" | "removed" | "same" }>;
};

export type ManualExportPayload = {
  id: string;
  controlled: boolean;
  watermark_uncontrolled: boolean;
  generated_at: string;
  sha256: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const body = init?.body;
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (method === "GET") {
    return apiGet<T>(path, { ...init, headers });
  }
  if (method === "DELETE") {
    return apiDelete<T>(path, undefined, { ...init, headers });
  }
  if (method === "POST") {
    if (body instanceof FormData) {
      return apiPostForm<T>(path, body, { ...init, headers });
    }
    return apiPost<T>(path, body as BodyInit | undefined, { ...init, headers });
  }
  throw new Error(`Unsupported request method for manuals API: ${method}`);
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

export async function listFeaturedManuals(tenantSlug: string) {
  return request<ManualFeaturedEntry[]>(`/manuals/t/${tenantSlug}/featured`);
}

export async function getRevisionRead(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualReadPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/read`);
}

export async function getRevisionDiff(tenantSlug: string, manualId: string, revId: string) {
  return request<ManualDiffPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/diff`);
}

export async function getRevisionComparison(tenantSlug: string, manualId: string, revId: string) {
  try {
    return await request<ManualComparisonPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/compare`);
  } catch {
    const diff = await getRevisionDiff(tenantSlug, manualId, revId).catch(() => null);
    return {
      baseline_revision_id: diff?.baseline_revision_id || null,
      current_lines: [],
      baseline_lines: [],
    } satisfies ManualComparisonPayload;
  }
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

export async function transitionManualLifecycle(
  tenantSlug: string,
  manualId: string,
  revId: string,
  action: string,
  comment?: string,
): Promise<ManualLifecycleTransitionPayload> {
  const response = await transitionRevision(tenantSlug, manualId, revId, action, comment);
  return {
    ...response,
    previous_state: response.status,
    state: response.status,
  };
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
    effective_date?: string;
    manual_type?: string;
    owner_role?: string;
    change_log?: string;
    file: File;
  },
) {
  const body = new FormData();
  body.append("code", payload.code);
  body.append("title", payload.title);
  body.append("rev_number", payload.rev_number);
  if (payload.issue_number) body.append("issue_number", payload.issue_number);
  if (payload.effective_date) body.append("effective_date", payload.effective_date);
  if (payload.manual_type) body.append("manual_type", payload.manual_type);
  if (payload.owner_role) body.append("owner_role", payload.owner_role);
  if (payload.change_log) body.append("change_log", payload.change_log);
  body.append("file", payload.file);

  const result = await apiPostForm<{ manual_id: string; revision_id: string; status: string; paragraphs: number }>(
    `/manuals/t/${tenantSlug}/upload-docx`,
    body,
    { headers: authHeaders() },
  );
  emitManualsUpdated(tenantSlug, "upload-docx");
  return result;
}


export async function previewDocxUpload(tenantSlug: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return apiPostForm<ManualDocxPreview>(`/manuals/t/${tenantSlug}/upload-docx/preview`, body, { headers: authHeaders() });
}

export async function verifyOcrLetter(
  tenantSlug: string,
  manualId: string,
  revId: string,
  payload: { file: File; typed_ref?: string; typed_date?: string },
) {
  const body = new FormData();
  body.append("file", payload.file);
  if (payload.typed_ref) body.append("typed_ref", payload.typed_ref);
  if (payload.typed_date) body.append("typed_date", payload.typed_date);
  return apiPostForm<ManualOCRVerifyPayload>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/ocr/verify`, body, { headers: authHeaders() });
}

export async function createStampedOverlay(
  tenantSlug: string,
  manualId: string,
  revId: string,
  payload: { signer_name: string; signer_role: string; stamp_label: string; controlled_bool?: boolean },
) {
  return request<{ revision_id: string; export_id: string; storage_uri: string; sha256: string }>(`/manuals/t/${tenantSlug}/${manualId}/rev/${revId}/stamp-overlay`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

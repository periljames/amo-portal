import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type ReaderRevisionOption = {
  id: string;
  revision_number: string;
  issue_number?: string | null;
  status: string;
  effective_date?: string | null;
  source_sha256?: string | null;
};

export type ReaderManifest = {
  manual_id: string;
  revision_id: string;
  source_type?: string | null;
  mime_type?: string | null;
  source_sha256?: string | null;
  page_count?: number | null;
  semantic_section_count: number;
  semantic_block_count: number;
  renderer: string;
  location_adapter: string;
  selection_support: string;
  revision_options: ReaderRevisionOption[];
  capabilities: {
    layout: boolean;
    semantic_text: boolean;
    annotations: boolean;
    compare: boolean;
    evidence: boolean;
    ocr_metadata_present: boolean;
    control: boolean;
  };
};

export type ReaderLocation = {
  id: string;
  location_key: string;
  location_type: string;
  page_number?: number | null;
  normalized_rects: Array<Record<string, number>>;
  exact_quote?: string | null;
  prefix_context?: string | null;
  suffix_context?: string | null;
  section_id?: string | null;
  block_id?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  adapter_name: string;
  adapter_version: string;
  source_sha256: string;
};

export type ReaderAnnotation = {
  id: string;
  manual_id: string;
  revision_id: string;
  annotation_type: string;
  color: string;
  visibility: string;
  note_text?: string | null;
  tags: string[];
  linked_entity_type?: string | null;
  linked_entity_id?: string | null;
  status: string;
  created_by_user_id: string;
  created_at?: string | null;
  updated_at?: string | null;
  location?: ReaderLocation | null;
  reader_url: string;
};

export type ReaderEvidence = {
  schema_version: number;
  captured_at: string;
  document: { id: string; code: string; title: string; type: string; status: string };
  revision: {
    id: string;
    revision_number: string;
    issue_number?: string | null;
    status: string;
    effective_date?: string | null;
    published_at?: string | null;
    immutable_locked: boolean;
    source_sha256?: string | null;
    source_filename?: string | null;
    source_mime_type?: string | null;
    source_page_count?: number | null;
  };
  control_profile: Record<string, unknown>;
  responsibilities: Array<Record<string, unknown>>;
  relationship_summary: Record<string, number>;
  reference_health: Record<string, number>;
  index?: Record<string, unknown> | null;
  annotations: { count: number; by_type: Record<string, number> };
  workflow?: { id: string; state: string; version: number } | null;
  audit_history: Array<{ id: string; action: string; entity_type: string; entity_id: string; actor_id?: string | null; at?: string | null }>;
  manifest: ReaderManifest;
  capabilities: { control: boolean; snapshot: boolean };
};

export type ReaderComparison = {
  source_revision_id: string;
  target_revision_id: string;
  summary: Record<string, number>;
  sections: Array<{
    source_section_id?: string | null;
    source_anchor_slug?: string | null;
    source_heading?: string | null;
    target_section_id?: string | null;
    target_anchor_slug?: string | null;
    target_heading?: string | null;
    status: "UNCHANGED" | "CHANGED" | "REMOVED" | "ADDED";
    strategy: string;
    source_block_count: number;
    target_block_count: number;
  }>;
  annotation_proposals: Array<{ annotation: ReaderAnnotation; proposal: { strategy: string; confidence_percent: number; location: Record<string, unknown>; reason: string } }>;
  capabilities: { control: boolean; prepare_migrations: boolean };
};

export type AnnotationMigration = {
  id: string;
  source_annotation_id: string;
  source_revision_id: string;
  target_revision_id: string;
  strategy: string;
  confidence_percent: number;
  status: string;
  reason?: string | null;
  proposed_location: Record<string, unknown>;
  target_annotation_id?: string | null;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
};

function base(tenant: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant)}/reader`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `Reader governance request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || JSON.stringify(payload?.detail || payload);
    } catch {
      // Keep HTTP fallback.
    }
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

function revisionPath(tenant: string, manualId: string, revisionId: string, suffix: string): string {
  return `${base(tenant)}/documents/${encodeURIComponent(manualId)}/revisions/${encodeURIComponent(revisionId)}${suffix}`;
}

export function getReaderManifest(tenant: string, manualId: string, revisionId: string): Promise<ReaderManifest> {
  return request(revisionPath(tenant, manualId, revisionId, "/manifest"));
}

export function listReaderAnnotations(tenant: string, manualId: string, revisionId: string, status = "ACTIVE"): Promise<{ items: ReaderAnnotation[]; capabilities: { control: boolean; create: boolean } }> {
  return request(`${revisionPath(tenant, manualId, revisionId, "/annotations")}?status=${encodeURIComponent(status)}`);
}

export function createReaderAnnotation(tenant: string, manualId: string, revisionId: string, payload: Record<string, unknown>): Promise<ReaderAnnotation> {
  return request(revisionPath(tenant, manualId, revisionId, "/annotations"), { method: "POST", body: JSON.stringify(payload) });
}

export function updateReaderAnnotation(tenant: string, manualId: string, revisionId: string, annotationId: string, payload: Record<string, unknown>): Promise<ReaderAnnotation> {
  return request(revisionPath(tenant, manualId, revisionId, `/annotations/${encodeURIComponent(annotationId)}`), { method: "PATCH", body: JSON.stringify(payload) });
}

export function getReaderEvidence(tenant: string, manualId: string, revisionId: string): Promise<ReaderEvidence> {
  return request(revisionPath(tenant, manualId, revisionId, "/evidence"));
}

export function listEvidenceSnapshots(tenant: string, manualId: string, revisionId: string): Promise<Array<Record<string, unknown>>> {
  return request(revisionPath(tenant, manualId, revisionId, "/evidence/snapshots"));
}

export function createEvidenceSnapshot(tenant: string, manualId: string, revisionId: string): Promise<Record<string, unknown>> {
  return request(revisionPath(tenant, manualId, revisionId, "/evidence/snapshots"), { method: "POST" });
}

export function getEvidenceSnapshot(tenant: string, manualId: string, revisionId: string, snapshotId: string): Promise<Record<string, unknown>> {
  return request(revisionPath(tenant, manualId, revisionId, `/evidence/snapshots/${encodeURIComponent(snapshotId)}`));
}

export function compareReaderRevisions(tenant: string, manualId: string, sourceRevisionId: string, targetRevisionId: string): Promise<ReaderComparison> {
  const params = new URLSearchParams({ source_revision_id: sourceRevisionId, target_revision_id: targetRevisionId });
  return request(`${base(tenant)}/documents/${encodeURIComponent(manualId)}/compare?${params.toString()}`);
}

export function prepareAnnotationMigrations(tenant: string, manualId: string, sourceRevisionId: string, targetRevisionId: string): Promise<Record<string, unknown>> {
  return request(`${base(tenant)}/documents/${encodeURIComponent(manualId)}/annotation-migrations/prepare`, {
    method: "POST",
    body: JSON.stringify({ source_revision_id: sourceRevisionId, target_revision_id: targetRevisionId }),
  });
}

export function listAnnotationMigrations(tenant: string, manualId: string, targetRevisionId?: string, status?: string): Promise<AnnotationMigration[]> {
  const params = new URLSearchParams();
  if (targetRevisionId) params.set("target_revision_id", targetRevisionId);
  if (status) params.set("status", status);
  const query = params.toString();
  return request(`${base(tenant)}/documents/${encodeURIComponent(manualId)}/annotation-migrations${query ? `?${query}` : ""}`);
}

export function decideAnnotationMigration(tenant: string, manualId: string, migrationId: string, decision: "ACCEPT" | "REJECT", comments: string): Promise<Record<string, unknown>> {
  return request(`${base(tenant)}/documents/${encodeURIComponent(manualId)}/annotation-migrations/${encodeURIComponent(migrationId)}`, {
    method: "PATCH",
    body: JSON.stringify({ decision, comments }),
  });
}

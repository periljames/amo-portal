import { getToken, handleAuthFailure } from "./auth";
import { portalFetch } from "./offlineHttp";

export interface ContentPack {
  id: string;
  code: string;
  manufacturer: string;
  family: string;
  series: string | null;
  description: string;
  status: string;
  created_at: string;
}

export interface ContentRevision {
  id: string;
  pack_id: string;
  revision_code: string;
  status: string;
  content_hash: string | null;
  change_summary: string | null;
  created_at: string;
  published_at: string | null;
}

export interface ContentSource {
  id: string;
  source_type: string;
  reference: string;
  source_revision: string;
  effective_date: string | null;
  checksum_sha256: string;
  authority: string;
  provenance_json: Record<string, unknown>;
  publication_revision_id: string | null;
  temporary_revision_id: string | null;
  source_page_ref: string | null;
  document_locator: string | null;
}

export interface ContentTask {
  id: string;
  task_code: string;
  title: string;
  description: string | null;
  ata_chapter: string | null;
  programme_section: string | null;
  task_type: string | null;
  intervals_json: Record<string, unknown>;
  raw_interval_text: string | null;
  effectivity_expression_json: Record<string, unknown>;
  raw_effectivity_text: string | null;
  source_requirements_json: Array<Record<string, unknown>>;
  task_card_number: string | null;
  task_card_configuration: string | null;
  amm_reference: string | null;
  zones_json: string[];
  panels_json: string[];
  general_references_json: string[];
  skill_code: string | null;
  labour_hours: string | null;
  number_of_persons: number | null;
  program_notes_json: string[];
  packaging_json: Record<string, unknown>;
  source_page_ref: string | null;
  source_reference: string;
  source_revision: string;
  source_checksum_sha256: string;
  metadata_json: Record<string, unknown>;
}

export interface ContentResource {
  id: string;
  resource_kind: string;
  resource_code: string;
  title: string;
  payload_json: Record<string, unknown>;
  source_reference: string;
  source_revision: string;
  source_checksum_sha256: string;
  source_page_ref: string | null;
  metadata_json: Record<string, unknown>;
}

export interface ContentRevisionDetail extends ContentRevision {
  sources: ContentSource[];
  tasks: ContentTask[];
  resources: ContentResource[];
}

export interface OemPublication {
  id: string;
  code: string;
  manufacturer: string;
  family: string;
  series: string | null;
  publication_code: string;
  title: string;
  publication_kind: string;
  status: string;
  created_at: string;
}

export interface OemPublicationRevision {
  id: string;
  publication_id: string;
  revision_code: string;
  status: string;
  issue_date: string | null;
  effective_date: string | null;
  checksum_sha256: string;
  source_filename: string | null;
  storage_locator: string | null;
  source_url: string | null;
  change_summary: string | null;
  supersedes_revision_id: string | null;
  submitted_by_amo_id: string | null;
  verified_at: string | null;
  created_at: string;
}

export interface OemTemporaryRevision {
  id: string;
  publication_revision_id: string;
  temporary_revision_code: string;
  status: string;
  issue_date: string | null;
  effective_date: string | null;
  checksum_sha256: string;
  source_filename: string | null;
  storage_locator: string | null;
  source_url: string | null;
  replaces_temporary_revision_code: string | null;
  filing_instructions: string | null;
  change_summary: string | null;
  submitted_by_amo_id: string | null;
  verified_at: string | null;
  created_at: string;
}

export interface OemSourceWatch {
  id: string;
  publication_id: string;
  channel_type: string;
  reference: string;
  is_active: boolean;
  last_checked_at: string | null;
  last_seen_marker: string | null;
  last_result: string | null;
  created_at: string;
}

export interface OemCurrentness {
  publication: OemPublication;
  current_revision: OemPublicationRevision | null;
  newest_candidate: OemPublicationRevision | null;
  active_temporary_revisions: OemTemporaryRevision[];
  watches: OemSourceWatch[];
  currentness_status:
    | "NO_CURRENT_REVISION"
    | "CURRENT"
    | "CANDIDATE_REVIEW_REQUIRED"
    | "TEMPORARY_REVISION_ACTIVE"
    | "SOURCE_CHECK_REQUIRED";
}

export interface WorkbookSheetPreview {
  name: string;
  state: string;
  row_count: number;
  column_count: number;
  sample_rows: unknown[][];
}

export interface OemWorkbookPreview {
  filename: string;
  extension: string;
  size_bytes: number;
  checksum_sha256: string;
  detected_profile: string;
  profile_confidence: string;
  workbook_kind: string;
  sheets: WorkbookSheetPreview[];
  warnings: string[];
  recommended_pack_code: string | null;
  source_manifest: Record<string, unknown>;
}

function authHeaders(json = true): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (json) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function parseError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (typeof payload?.detail === "string") return new Error(payload.detail);
  return new Error(`OEM maintenance-data API ${response.status}: ${response.statusText}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await portalFetch(path, {
    ...init,
    headers: init?.headers ?? authHeaders(true),
    credentials: "include",
    offline: { cache: !init?.method || init.method === "GET", queueMutation: false },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseError(response);
  return await response.json() as T;
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export function listContentPacks(filters: { family?: string; series?: string } = {}): Promise<ContentPack[]> {
  return request(`/architecture/content-packs${query(filters)}`);
}

export function listContentRevisions(packId: string): Promise<ContentRevision[]> {
  return request(`/architecture/content-packs/${encodeURIComponent(packId)}/revisions`);
}

export function getContentRevision(revisionId: string): Promise<ContentRevisionDetail> {
  return request(`/architecture/content-packs/revisions/${encodeURIComponent(revisionId)}`);
}

export function listOemCurrentness(filters: { family?: string; series?: string } = {}): Promise<OemCurrentness[]> {
  return request(`/architecture/content-packs/oem-currentness${query(filters)}`);
}

export function listOemPublications(filters: { family?: string; series?: string } = {}): Promise<OemPublication[]> {
  return request(`/architecture/content-packs/oem-publications${query(filters)}`);
}

export async function previewOemWorkbook(file: File): Promise<OemWorkbookPreview> {
  const form = new FormData();
  form.append("file", file);
  return request("/architecture/content-packs/oem-import/preview", {
    method: "POST",
    headers: authHeaders(false),
    body: form,
  });
}

export function createOemPublication(payload: {
  code: string;
  manufacturer: string;
  family: string;
  series?: string | null;
  publication_code: string;
  title: string;
  publication_kind: string;
}): Promise<OemPublication> {
  return request("/architecture/content-packs/oem-publications", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitOemPublicationRevision(
  publicationId: string,
  payload: {
    revision_code: string;
    issue_date?: string | null;
    effective_date?: string | null;
    checksum_sha256: string;
    source_filename?: string | null;
    storage_locator?: string | null;
    source_url?: string | null;
    change_summary?: string | null;
    supersedes_revision_id?: string | null;
    metadata_json?: Record<string, unknown>;
  },
): Promise<OemPublicationRevision> {
  return request(`/architecture/content-packs/oem-publications/${encodeURIComponent(publicationId)}/revisions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function decideOemPublicationRevision(
  revisionId: string,
  action: "VERIFY" | "MAKE_CURRENT" | "REJECT" | "WITHDRAW",
  decisionNote: string,
): Promise<OemPublicationRevision> {
  return request(`/architecture/content-packs/oem-publication-revisions/${encodeURIComponent(revisionId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, decision_note: decisionNote }),
  });
}

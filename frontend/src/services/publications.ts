import { authHeaders, getCachedUser } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiPostForm } from "./crs";
import type { ManualReadPayload } from "./manuals";
import { getPdfReaderPerformanceProfile } from "./pdfPerformance";

export type PublicationUploadPreview = {
  filename: string;
  heading: string;
  paragraph_count: number;
  sample: string[];
  outline: string[];
  excerpt: string;
  source_type: "DOCX" | "PDF";
  page_count?: number | null;
  metadata: {
    part_number?: string | null;
    manual_type?: string | null;
    title?: string | null;
    revision_number?: string | null;
    issue_number?: string | null;
    effective_date?: string | null;
  };
};

export type PublicationUploadPayload = {
  code: string;
  title: string;
  rev_number: string;
  issue_number: string;
  effective_date?: string;
  manual_type?: string;
  owner_role?: string;
  change_log?: string;
  file: File;
};

export type PublicationUploadResult = {
  manual_id: string;
  revision_id: string;
  status: string;
  source_type: "DOCX" | "PDF";
  paragraphs?: number;
  page_count?: number;
};

export type PublicationReaderMetadata = {
  manual_id: string;
  revision_id: string;
  title: string;
  code: string;
  manual_type: string;
  owner_role?: string | null;
  date?: string | null;
  language: string;
  issue_number?: string | null;
  revision_number?: string | null;
  status: string;
  is_published: boolean;
  control_label: string;
  source_type?: string | null;
  source_filename?: string | null;
  source_size_bytes: number;
  source_page_count?: number | null;
  source_url?: string | null;
  rendered_pdf_url: string;
  rendered_pdf_size_bytes: number;
  download_filename: string;
  reader_mode: "html" | "pdf";
  image_only: boolean;
  text_char_count: number;
  citation_current: number;
  citation_total: number;
  subsidiary_count: number;
  cache_key?: string;
  source_exact?: boolean;
  form_policy?: "READ_ONLY_PRESERVED" | string;
  section_count?: number;
};

export type PublicationAcknowledgement = {
  required: boolean;
  pending: boolean;
  status?: string | null;
  due_at?: string | null;
  acknowledged_at?: string | null;
  acknowledgement_text?: string | null;
};

export type PublicationReaderBootstrap = {
  cache_key: string;
  metadata: PublicationReaderMetadata;
  read: ManualReadPayload & {
    revision?: {
      id: string;
      rev_number?: string | null;
      issue_number?: string | null;
      effective_date?: string | null;
      published_at?: string | null;
      source_filename?: string | null;
      source_type?: string | null;
      source_mime_type?: string | null;
      source_page_count?: number | null;
      source_available?: boolean;
      source_url?: string | null;
    };
    progress?: {
      last_section_id?: string | null;
      last_anchor_slug?: string | null;
      last_page_number?: number | null;
      scroll_percent?: number;
      zoom_percent?: number;
      last_opened_at?: string | null;
    };
    sections: Array<ManualReadPayload["sections"][number] & { page_start?: number | null; page_end?: number | null }>;
  };
  acknowledgement: PublicationAcknowledgement;
};

export type PublicationReaderContent = {
  sections: Array<{ id: string; heading: string; anchor_slug: string; level: number }>;
  blocks: ManualReadPayload["blocks"];
  start: number;
  limit: number;
  returned_sections: number;
};

export type PublicationSearchResult = {
  section_id: string;
  anchor_slug: string;
  heading: string;
  level: number;
  page_start?: number | null;
  snippet: string;
};

export type ApprovedPublicationIntakePayload = {
  authority_name: string;
  approval_reference: string;
  approval_date: string;
  effective_date?: string | null;
  comments: string;
  acknowledgement_required: boolean;
  notify_eligible_users: boolean;
};

const READER_CACHE_PREFIX = "amo-publication-bootstrap:v2";
const READER_CACHE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function extensionOf(file: File): "docx" | "pdf" {
  const name = file.name.toLowerCase();
  if (name.endsWith(".docx")) return "docx";
  if (name.endsWith(".pdf")) return "pdf";
  throw new Error("Only searchable DOCX and PDF publications are supported.");
}

function readerCacheKey(tenantSlug: string, manualId: string, revisionId: string): string {
  const userId = getCachedUser()?.id || "anonymous";
  return `${READER_CACHE_PREFIX}:${userId}:${tenantSlug}:${manualId}:${revisionId}`;
}

export function readCachedPublicationBootstrap(tenantSlug: string, manualId: string, revisionId: string): PublicationReaderBootstrap | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(readerCacheKey(tenantSlug, manualId, revisionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { cached_at: number; payload: PublicationReaderBootstrap };
    if (!parsed?.payload || Date.now() - Number(parsed.cached_at || 0) > READER_CACHE_MAX_AGE_MS) {
      window.localStorage.removeItem(readerCacheKey(tenantSlug, manualId, revisionId));
      return null;
    }
    return parsed.payload;
  } catch {
    return null;
  }
}

export function cachePublicationBootstrap(tenantSlug: string, manualId: string, revisionId: string, payload: PublicationReaderBootstrap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(readerCacheKey(tenantSlug, manualId, revisionId), JSON.stringify({ cached_at: Date.now(), payload }));
  } catch {
    // Storage may be unavailable or full. HTTP caching still remains active.
  }
}

export async function previewPublicationUpload(tenantSlug: string, file: File): Promise<PublicationUploadPreview> {
  const extension = extensionOf(file);
  const body = new FormData();
  body.append("file", file);
  return apiPostForm<PublicationUploadPreview>(`/manuals/t/${encodeURIComponent(tenantSlug)}/upload-${extension}/preview`, body, { headers: authHeaders() });
}

export async function uploadPublicationRevision(tenantSlug: string, payload: PublicationUploadPayload): Promise<PublicationUploadResult> {
  const extension = extensionOf(payload.file);
  const body = new FormData();
  body.append("code", payload.code);
  body.append("title", payload.title);
  body.append("rev_number", payload.rev_number);
  body.append("issue_number", payload.issue_number);
  if (payload.effective_date) body.append("effective_date", payload.effective_date);
  if (payload.manual_type) body.append("manual_type", payload.manual_type);
  if (payload.owner_role) body.append("owner_role", payload.owner_role);
  if (payload.change_log) body.append("change_log", payload.change_log);
  body.append("file", payload.file);
  return apiPostForm<PublicationUploadResult>(`/manuals/t/${encodeURIComponent(tenantSlug)}/upload-${extension}`, body, { headers: authHeaders() });
}

async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(authHeaders());
  if (init.body !== undefined && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const raw = payload?.detail;
      detail = typeof raw === "string" ? raw : String(raw?.message || JSON.stringify(raw || detail));
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response;
}

export async function getPublicationReaderBootstrap(tenantSlug: string, manualId: string, revisionId: string): Promise<PublicationReaderBootstrap> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-bootstrap`;
  const response = await authenticatedFetch(path);
  const payload = await response.json() as PublicationReaderBootstrap;
  cachePublicationBootstrap(tenantSlug, manualId, revisionId, payload);
  return payload;
}

export function prefetchPublicationReader(tenantSlug: string, manualId: string, revisionId: string): void {
  if (readCachedPublicationBootstrap(tenantSlug, manualId, revisionId)) return;
  void getPublicationReaderBootstrap(tenantSlug, manualId, revisionId).catch(() => undefined);
}

export async function getPublicationReaderContent(tenantSlug: string, manualId: string, revisionId: string, sectionIds: string[]): Promise<PublicationReaderContent> {
  const query = new URLSearchParams();
  for (const sectionId of [...new Set(sectionIds.filter(Boolean))]) query.append("section_id", sectionId);
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-content?${query.toString()}`;
  const response = await authenticatedFetch(path);
  return response.json() as Promise<PublicationReaderContent>;
}

export async function searchPublicationReader(tenantSlug: string, manualId: string, revisionId: string, query: string): Promise<PublicationSearchResult[]> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-search?q=${encodeURIComponent(query)}`;
  const response = await authenticatedFetch(path);
  const payload = await response.json() as { items: PublicationSearchResult[] };
  return payload.items || [];
}

export function updatePublicationReaderPosition(tenantSlug: string, manualId: string, revisionId: string, payload: { page_number?: number | null; anchor_slug?: string | null; section_id?: string | null; scroll_percent?: number; zoom_percent?: number }): Promise<void> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-position`;
  return authenticatedFetch(path, { method: "POST", body: JSON.stringify(payload), keepalive: true }).then(() => undefined);
}

export function publicationPdfSource(path: string): {
  url: string;
  httpHeaders: Record<string, string>;
  withCredentials: boolean;
  rangeChunkSize: number;
  disableAutoFetch: boolean;
  disableRange: boolean;
  disableStream: boolean;
} {
  const performance = getPdfReaderPerformanceProfile();
  if (/^(?:blob:|data:)/i.test(path)) {
    return {
      url: path,
      httpHeaders: {},
      withCredentials: false,
      rangeChunkSize: performance.rangeChunkSize,
      disableAutoFetch: false,
      disableRange: false,
      disableStream: false,
    };
  }

  const headers = new Headers(authHeaders());
  const userId = getCachedUser()?.id;
  const separator = path.includes("?") ? "&" : "?";
  const partitionedPath = userId ? `${path}${separator}reader_user=${encodeURIComponent(userId)}` : path;
  const url = /^https?:\/\//i.test(partitionedPath)
    ? partitionedPath
    : `${getApiBaseUrl()}${partitionedPath}`;
  return {
    url,
    httpHeaders: Object.fromEntries(headers),
    withCredentials: true,
    rangeChunkSize: performance.rangeChunkSize,
    disableAutoFetch: false,
    disableRange: false,
    disableStream: false,
  };
}

export async function approvePublicationIntake(tenantSlug: string, manualId: string, revisionId: string, payload: ApprovedPublicationIntakePayload): Promise<{ status: string; campaign_id?: string | null; notifications_issued?: boolean }> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/approved-intake`;
  const response = await authenticatedFetch(path, { method: "POST", body: JSON.stringify(payload) });
  return response.json();
}

export async function getPublicationReaderMetadata(tenantSlug: string, manualId: string, revisionId: string): Promise<PublicationReaderMetadata> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-metadata`;
  const response = await authenticatedFetch(path);
  return response.json() as Promise<PublicationReaderMetadata>;
}

export async function getPublicationAcknowledgement(tenantSlug: string, manualId: string, revisionId: string): Promise<PublicationAcknowledgement> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/acknowledgement`;
  const response = await authenticatedFetch(path);
  return response.json() as Promise<PublicationAcknowledgement>;
}

export async function fetchPublicationBlob(path: string): Promise<{ blob: Blob; size: number; filename?: string }> {
  const response = await authenticatedFetch(path);
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : plain;
  return { blob, size: blob.size, filename };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function formatFileSize(bytes?: number | null): string {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "size unavailable";
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB"];
  let current = value / 1024;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) { current /= 1024; index += 1; }
  const digits = current >= 10 ? 1 : 2;
  return `${current.toFixed(digits)} ${units[index]}`;
}

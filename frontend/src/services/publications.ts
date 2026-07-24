import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiPostForm } from "./crs";

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
};

function extensionOf(file: File): "docx" | "pdf" {
  const name = file.name.toLowerCase();
  if (name.endsWith(".docx")) return "docx";
  if (name.endsWith(".pdf")) return "pdf";
  throw new Error("Only searchable DOCX and PDF publications are supported.");
}

export async function previewPublicationUpload(tenantSlug: string, file: File): Promise<PublicationUploadPreview> {
  const extension = extensionOf(file);
  const body = new FormData();
  body.append("file", file);
  return apiPostForm<PublicationUploadPreview>(
    `/manuals/t/${encodeURIComponent(tenantSlug)}/upload-${extension}/preview`,
    body,
    { headers: authHeaders() },
  );
}

export async function uploadPublicationRevision(
  tenantSlug: string,
  payload: PublicationUploadPayload,
): Promise<PublicationUploadResult> {
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
  return apiPostForm<PublicationUploadResult>(
    `/manuals/t/${encodeURIComponent(tenantSlug)}/upload-${extension}`,
    body,
    { headers: authHeaders() },
  );
}

async function authenticatedFetch(path: string): Promise<Response> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: authHeaders(),
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = String(payload?.detail || detail);
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response;
}

export async function getPublicationReaderMetadata(
  tenantSlug: string,
  manualId: string,
  revisionId: string,
): Promise<PublicationReaderMetadata> {
  const path = `/manuals/t/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/reader-metadata`;
  const response = await authenticatedFetch(path);
  return response.json() as Promise<PublicationReaderMetadata>;
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
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  const digits = current >= 10 ? 1 : 2;
  return `${current.toFixed(digits)} ${units[index]}`;
}

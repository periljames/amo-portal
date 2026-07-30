import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { DocumentationExecutionProfile, DocumentationRecord } from "./documentation";

export type PdfReaderCapabilities = {
  execution?: DocumentationExecutionProfile | null;
  renderer: "PDF.js" | string;
  processor: "PDFium" | string;
  processor_version: string;
  source_sha256: string;
  page_count: number;
  has_acroform: boolean;
  has_javascript: boolean;
  is_dynamic_xfa: boolean;
  encrypted: boolean;
  unsupported_reason?: string | null;
  can_fill: boolean;
  can_save_draft: boolean;
  can_download_original: boolean;
  can_download_working: boolean;
  can_flatten: boolean;
  can_submit: boolean;
};

export type FlattenedPdfResult = {
  blob: Blob;
  filename: string;
  sourceSha256?: string | null;
  outputSha256?: string | null;
  pageCount?: number | null;
  flattenedPages?: number | null;
};

function revisionPath(tenant: string, manualId: string, revisionId: string): string {
  return `/manuals/t/${encodeURIComponent(tenant.toLowerCase())}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}`;
}

async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(authHeaders());
  if (init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `PDF reader request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = typeof detail === "string" ? detail : String(detail?.message || message);
    } catch {
      // Retain the status fallback for non-JSON proxy or storage errors.
    }
    throw new Error(message);
  }
  return response;
}

function contentDispositionFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("Content-Disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded); } catch { return fallback; }
  }
  return plain || fallback;
}

export async function getPdfReaderCapabilities(
  tenant: string,
  manualId: string,
  revisionId: string,
): Promise<PdfReaderCapabilities> {
  const response = await authenticatedFetch(`${revisionPath(tenant, manualId, revisionId)}/pdf-capabilities`);
  return response.json() as Promise<PdfReaderCapabilities>;
}

export async function flattenPdfWorkingCopy(
  tenant: string,
  manualId: string,
  revisionId: string,
  file: File,
): Promise<FlattenedPdfResult> {
  const body = new FormData();
  body.append("artifact", file);
  const response = await authenticatedFetch(`${revisionPath(tenant, manualId, revisionId)}/flatten.pdf`, {
    method: "POST",
    body,
  });
  const blob = await response.blob();
  return {
    blob,
    filename: contentDispositionFilename(response, file.name.replace(/\.pdf$/i, "_FLATTENED.pdf")),
    sourceSha256: response.headers.get("X-PDF-Source-SHA256"),
    outputSha256: response.headers.get("X-PDF-Output-SHA256"),
    pageCount: Number(response.headers.get("X-PDF-Page-Count") || 0) || null,
    flattenedPages: Number(response.headers.get("X-PDF-Flattened-Pages") || 0) || null,
  };
}

export async function submitPdfWorkingCopy(
  tenant: string,
  manualId: string,
  revisionId: string,
  file: File,
  payload: Record<string, unknown> = {},
): Promise<DocumentationRecord> {
  const body = new FormData();
  body.append("artifact", file);
  body.append("payload_json", JSON.stringify(payload));
  const response = await authenticatedFetch(`${revisionPath(tenant, manualId, revisionId)}/submit-record`, {
    method: "POST",
    body,
  });
  return response.json() as Promise<DocumentationRecord>;
}

import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { DocumentationExecutionProfile, DocumentationRecord } from "./documentation";
import { registerAuthoritativePdfSource } from "./pdfWorkingCopyAuthority";

export type PdfStaticOverlaySchemaField = {
  id?: string;
  name?: string;
  label?: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  font_size?: number;
  multiline?: boolean;
  align?: "left" | "center" | "right";
  default_value?: string;
};

export type PdfStaticOverlaySchema = {
  fields?: PdfStaticOverlaySchemaField[];
  instructions?: string;
};

export type PdfStaticOverlayItem = {
  id: string;
  name?: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  font_size?: number;
  multiline?: boolean;
  align?: "left" | "center" | "right";
};

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
  automatic_form_execution?: boolean;
  form_download_mode?: "CHANGED_FORM_PAGES" | string | null;
  can_overlay_fill?: boolean;
  can_configure_overlay?: boolean;
  overlay_schema?: PdfStaticOverlaySchema | null;
  overlay_download_mode?: "COMPLETED_PAGES" | string | null;
  overlay_reason?: string | null;
};

export type FlattenedPdfResult = {
  blob: Blob;
  filename: string;
  sourceSha256?: string | null;
  workingSha256?: string | null;
  outputSha256?: string | null;
  pageCount?: number | null;
  flattenedPages?: number | null;
  selectedPages?: number[];
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

function selectedPageHeader(value: string | null): number[] {
  if (!value) return [];
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0);
}

export async function getPdfReaderCapabilities(
  tenant: string,
  manualId: string,
  revisionId: string,
): Promise<PdfReaderCapabilities> {
  // A revisit or failed refresh must not inherit a checksum registered by an
  // earlier reader session. Draft admission resumes only after this request
  // returns the current immutable source checksum.
  registerAuthoritativePdfSource(tenant, manualId, revisionId, null);
  const response = await authenticatedFetch(
    `${revisionPath(tenant, manualId, revisionId)}/pdf-capabilities`,
    { cache: "no-store" },
  );
  const capabilities = await response.json() as PdfReaderCapabilities;
  registerAuthoritativePdfSource(tenant, manualId, revisionId, capabilities.source_sha256);
  return capabilities;
}

export async function flattenPdfWorkingCopy(
  tenant: string,
  manualId: string,
  revisionId: string,
  file: File,
  completedPageNumbers: number[] = [],
): Promise<FlattenedPdfResult> {
  const body = new FormData();
  body.append("artifact", file);
  body.append("page_numbers_json", JSON.stringify(
    [...new Set(completedPageNumbers)]
      .filter((page) => Number.isInteger(page) && page > 0)
      .sort((left, right) => left - right),
  ));
  const response = await authenticatedFetch(`${revisionPath(tenant, manualId, revisionId)}/flatten.pdf`, {
    method: "POST",
    body,
  });
  const blob = await response.blob();
  return {
    blob,
    filename: contentDispositionFilename(response, file.name.replace(/\.pdf$/i, "_COMPLETED_PAGES.pdf")),
    sourceSha256: response.headers.get("X-PDF-Template-SHA256"),
    workingSha256: response.headers.get("X-PDF-Working-SHA256"),
    outputSha256: response.headers.get("X-PDF-Output-SHA256"),
    pageCount: Number(response.headers.get("X-PDF-Page-Count") || 0) || null,
    flattenedPages: Number(response.headers.get("X-PDF-Flattened-Pages") || 0) || null,
    selectedPages: selectedPageHeader(response.headers.get("X-PDF-Selected-Pages")),
  };
}

export async function createPdfStaticOverlay(
  tenant: string,
  manualId: string,
  revisionId: string,
  items: PdfStaticOverlayItem[],
  completedOnly = true,
): Promise<FlattenedPdfResult> {
  const body = new FormData();
  body.append("overlay_json", JSON.stringify({ items, completed_only: completedOnly }));
  const response = await authenticatedFetch(`${revisionPath(tenant, manualId, revisionId)}/static-overlay.pdf`, {
    method: "POST",
    body,
  });
  const blob = await response.blob();
  return {
    blob,
    filename: contentDispositionFilename(response, completedOnly ? "FILLED_PAGES.pdf" : "FILLED_COPY.pdf"),
    sourceSha256: response.headers.get("X-PDF-Template-SHA256"),
    outputSha256: response.headers.get("X-PDF-Output-SHA256"),
    pageCount: Number(response.headers.get("X-PDF-Page-Count") || 0) || null,
    selectedPages: selectedPageHeader(response.headers.get("X-PDF-Selected-Pages")),
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

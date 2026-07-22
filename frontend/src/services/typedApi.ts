import { authHeaders } from "./auth";
import { portalFetch, type PortalFetchInit } from "./offlineHttp";

export type StructuredApiError = Error & {
  status: number;
  errorCode: string;
  fieldErrors: Record<string, string | string[]>;
  conflicts: Array<Record<string, unknown>>;
  retryable: boolean;
  raw?: unknown;
};

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(authHeaders());
  if (extra) {
    new Headers(extra).forEach((value, key) => headers.set(key, value));
  }
  return headers;
}

async function parseError(response: Response): Promise<StructuredApiError> {
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    raw = await response.text().catch(() => "");
  }
  const wrapped = raw && typeof raw === "object" && "detail" in raw ? (raw as { detail?: unknown }).detail : raw;
  const payload = wrapped && typeof wrapped === "object" ? wrapped as Record<string, unknown> : {};
  const message = typeof payload.detail === "string"
    ? payload.detail
    : typeof raw === "string" && raw.trim()
      ? raw
      : `${response.status} ${response.statusText}`;
  const error = new Error(message) as StructuredApiError;
  error.status = response.status;
  error.errorCode = typeof payload.error_code === "string" ? payload.error_code : "API_REQUEST_FAILED";
  error.fieldErrors = payload.field_errors && typeof payload.field_errors === "object"
    ? payload.field_errors as Record<string, string | string[]>
    : {};
  error.conflicts = Array.isArray(payload.conflicts)
    ? payload.conflicts.filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    : [];
  error.retryable = payload.retryable === true;
  error.raw = raw;
  return error;
}

export async function apiJson<T>(
  path: string,
  init: PortalFetchInit = {},
): Promise<T> {
  const headers = buildHeaders(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await portalFetch(path, {
    credentials: "include",
    ...init,
    headers,
  });
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function apiBlob(
  path: string,
  init: PortalFetchInit = {},
): Promise<{ blob: Blob; filename?: string }> {
  const response = await portalFetch(path, {
    credentials: "include",
    ...init,
    offline: { ...init.offline, cache: false, queueMutation: false },
    headers: buildHeaders(init.headers),
  });
  if (!response.ok) throw await parseError(response);
  const disposition = response.headers.get("content-disposition") || "";
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return {
    blob: await response.blob(),
    filename: decodeURIComponent(utf8 || plain || "") || undefined,
  };
}

export function jsonBody(payload: unknown): string {
  return JSON.stringify(payload);
}

export function queryString(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

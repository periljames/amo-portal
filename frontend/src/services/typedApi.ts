import { authHeaders } from "./auth";
import { portalFetch, type PortalFetchInit } from "./offlineHttp";

export type StructuredApiError = Error & {
  status: number;
  errorCode: string;
  fieldErrors: Record<string, string | string[]>;
  conflicts: Array<Record<string, unknown>>;
  retryable: boolean;
  metadata: Record<string, unknown>;
  raw?: unknown;
};

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(authHeaders());
  if (extra) {
    new Headers(extra).forEach((value, key) => headers.set(key, value));
  }
  return headers;
}

async function responseBody(response: Response): Promise<{ raw: unknown; text: string }> {
  const text = await response.text().catch(() => "");
  if (!text.trim()) return { raw: "", text: "" };
  try {
    return { raw: JSON.parse(text) as unknown, text };
  } catch {
    return { raw: text, text };
  }
}

function structuredError(
  message: string,
  options: {
    status: number;
    errorCode: string;
    retryable?: boolean;
    raw?: unknown;
    fieldErrors?: Record<string, string | string[]>;
    conflicts?: Array<Record<string, unknown>>;
    metadata?: Record<string, unknown>;
  },
): StructuredApiError {
  const error = new Error(message) as StructuredApiError;
  error.status = options.status;
  error.errorCode = options.errorCode;
  error.fieldErrors = options.fieldErrors || {};
  error.conflicts = options.conflicts || [];
  error.retryable = options.retryable === true;
  error.metadata = options.metadata || {};
  error.raw = options.raw;
  return error;
}

async function parseError(response: Response): Promise<StructuredApiError> {
  const { raw } = await responseBody(response);
  const rawObject = raw && typeof raw === "object"
    ? raw as Record<string, unknown>
    : null;
  const nestedDetail = rawObject?.detail;
  // FastAPI domain errors commonly wrap an object inside `detail`, while
  // infrastructure errors (DB circuit/pool, proxy readiness) use a top-level
  // object whose `detail` is the human-readable string. Only unwrap the former.
  const wrapped = nestedDetail && typeof nestedDetail === "object"
    ? nestedDetail
    : raw;
  const payload = wrapped && typeof wrapped === "object"
    ? wrapped as Record<string, unknown>
    : {};
  const message = typeof payload.detail === "string"
    ? payload.detail
    : typeof payload.message === "string"
      ? payload.message
      : typeof raw === "string" && raw.trim()
        ? raw
        : `${response.status} ${response.statusText}`;
  const details = payload.details && typeof payload.details === "object"
    ? payload.details as Record<string, unknown>
    : {};
  const metadata = payload.metadata && typeof payload.metadata === "object"
    ? payload.metadata as Record<string, unknown>
    : details;

  return structuredError(message, {
    status: response.status,
    errorCode: typeof payload.error_code === "string"
      ? payload.error_code
      : typeof payload.code === "string"
        ? payload.code
        : "API_REQUEST_FAILED",
    fieldErrors: payload.field_errors && typeof payload.field_errors === "object"
      ? payload.field_errors as Record<string, string | string[]>
      : {},
    conflicts: Array.isArray(payload.conflicts)
      ? payload.conflicts.filter(
          (item): item is Record<string, unknown> => !!item && typeof item === "object",
        )
      : [],
    retryable: payload.retryable === true,
    metadata,
    raw,
  });
}

async function parseJson<T>(path: string, response: Response): Promise<T> {
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  const { raw, text } = await responseBody(response);
  const preview = text.replace(/\s+/g, " ").trim().slice(0, 180);
  const looksLikeHtml = /^(?:<!doctype|<html|<head|<body)/i.test(preview);

  if (looksLikeHtml) {
    throw structuredError(
      `API route ${path} returned the portal HTML document instead of JSON. The reverse proxy is not forwarding this API route to the backend.`,
      {
        status: 502,
        errorCode: "API_ROUTE_RETURNED_HTML",
        retryable: true,
        raw: preview,
      },
    );
  }

  if (!contentType.includes("application/json") && !contentType.includes("+json")) {
    throw structuredError(
      `API route ${path} returned ${contentType || "an unknown content type"} instead of JSON.`,
      {
        status: 502,
        errorCode: "API_RESPONSE_NOT_JSON",
        retryable: true,
        raw: preview,
      },
    );
  }

  if (typeof raw === "string") {
    throw structuredError(`API route ${path} returned invalid JSON.`, {
      status: 502,
      errorCode: "API_RESPONSE_INVALID_JSON",
      retryable: true,
      raw: preview,
    });
  }

  return raw as T;
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
  return await parseJson<T>(path, response);
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

import { reportPortalError, reportUploadError, type PortalErrorTarget } from "./portalError";

const INSTALL_FLAG = "__amoPortalFetchErrorBridgeInstalled";
const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const ACTION_CONTEXT_MS = 30_000;
const SILENT_BACKGROUND_MUTATION_PATHS = new Set([
  "/api/realtime/presence",
]);

type GuardedWindow = Window & {
  __amoPortalFetchErrorBridgeInstalled?: boolean;
};

type ActionContext = {
  form: HTMLFormElement;
  at: number;
};

let recentAction: ActionContext | null = null;

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  if (typeof Request !== "undefined" && input instanceof Request) return input.method.toUpperCase();
  return "GET";
}

function requestHeaders(input: RequestInfo | URL, init?: RequestInit): Headers {
  if (init?.headers) return new Headers(init.headers);
  if (typeof Request !== "undefined" && input instanceof Request) return new Headers(input.headers);
  return new Headers();
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function isSilentBackgroundMutation(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    return SILENT_BACKGROUND_MUTATION_PATHS.has(parsed.pathname);
  } catch {
    return false;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function isUpload(init: RequestInit | undefined, headers: Headers): boolean {
  if (typeof FormData !== "undefined" && init?.body instanceof FormData) {
    for (const value of init.body.values()) {
      if (typeof File !== "undefined" && value instanceof File) return true;
    }
  }
  return (headers.get("Content-Type") || "").toLowerCase().includes("multipart/form-data");
}

function currentActionForm(): HTMLFormElement | null {
  if (!recentAction || Date.now() - recentAction.at > ACTION_CONTEXT_MS) {
    recentAction = null;
    return null;
  }
  return recentAction.form.isConnected ? recentAction.form : null;
}

function errorTarget(upload: boolean): PortalErrorTarget {
  const form = currentActionForm();
  if (!form) return null;
  if (upload) {
    const populatedFile = [...form.querySelectorAll<HTMLInputElement>('input[type="file"]')]
      .find((input) => Boolean(input.files?.length));
    if (populatedFile) return populatedFile;
    const firstFile = form.querySelector<HTMLInputElement>('input[type="file"]');
    if (firstFile) return firstFile;
  }
  return form.querySelector<HTMLElement>('[aria-invalid="true"], [data-error="true"], [data-error-anchor]')
    || form.querySelector<HTMLElement>('button[type="submit"], input[type="submit"]')
    || form;
}

async function responseMessage(response: Response): Promise<string> {
  const fallback = response.statusText || `Request failed with status ${response.status}`;
  try {
    const clone = response.clone();
    const contentType = clone.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const body = await clone.json() as { detail?: unknown; message?: unknown; error?: unknown } | null;
      const detail = body?.detail ?? body?.message ?? body?.error;
      if (typeof detail === "string" && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        const messages = detail.map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            const record = item as Record<string, unknown>;
            return String(record.msg ?? record.message ?? record.detail ?? "");
          }
          return "";
        }).filter(Boolean);
        if (messages.length) return messages.join("; ");
      }
    }
    const text = await clone.text();
    if (text.trim()) return text.trim().slice(0, 700);
  } catch {
    // The caller still receives the untouched original response.
  }
  return fallback;
}

function recordSubmittedForm(event: SubmitEvent): void {
  if (event.target instanceof HTMLFormElement) recentAction = { form: event.target, at: Date.now() };
}

export function installPortalFetchErrorBridge(): () => void {
  if (typeof window === "undefined" || typeof window.fetch !== "function") return () => undefined;
  const guardedWindow = window as GuardedWindow;
  if (guardedWindow[INSTALL_FLAG]) return () => undefined;

  const originalFetch = window.fetch.bind(window);
  const bridgedFetch: typeof window.fetch = async (input, init) => {
    const method = requestMethod(input, init);
    const headers = requestHeaders(input, init);
    const mutation = MUTATION_METHODS.has(method);
    const upload = isUpload(init, headers);
    const url = requestUrl(input);
    const silent = headers.get("X-AMO-Silent-Error") === "1" || isSilentBackgroundMutation(url);

    try {
      const response = await originalFetch(input, init);
      if (mutation && !silent && !response.ok) {
        const message = await responseMessage(response);
        const target = errorTarget(upload);
        const options = {
          message,
          target,
          code: String(response.status),
          actionLabel: target ? (upload ? "Show upload field" : "Show form") : undefined,
          dedupeKey: `fetch:${method}:${url}:${response.status}:${message}`,
        };
        if (upload) reportUploadError(message, options);
        else reportPortalError(message, { ...options, source: "api", title: "Action failed" });
      }
      return response;
    } catch (error) {
      if (mutation && !silent && !isAbort(error)) {
        const target = errorTarget(upload);
        const options = {
          target,
          actionLabel: target ? (upload ? "Show upload field" : "Show form") : undefined,
          fallbackMessage: upload
            ? "The file upload was interrupted. Check the connection and try again."
            : "The server could not be reached. Check the connection and try again.",
          dedupeKey: `fetch-network:${method}:${url}`,
        };
        if (upload) reportUploadError(error, options);
        else reportPortalError(error, { ...options, source: "api", title: "Action failed" });
      }
      throw error;
    }
  };

  document.addEventListener("submit", recordSubmittedForm, true);
  window.fetch = bridgedFetch;
  guardedWindow[INSTALL_FLAG] = true;

  return () => {
    document.removeEventListener("submit", recordSubmittedForm, true);
    if (window.fetch === bridgedFetch) window.fetch = originalFetch;
    guardedWindow[INSTALL_FLAG] = false;
  };
}

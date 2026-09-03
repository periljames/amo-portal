import { reportPortalError, reportUploadError, type PortalErrorTarget } from "./portalError";
import {
  ensureAuthenticatedRequestAllowed,
  getToken,
  getTokenSecondsRemaining,
  hasRecoverableSession,
  handleAuthFailure,
  recoverSessionAfterUnauthorized,
} from "./auth";
import {
  markPortalSessionExpired,
  notePortalNetworkFailure,
  notePortalResponse,
} from "./portalConnectivity";
import { getApiBaseUrl } from "./config";

const INSTALL_FLAG = "__amoPortalFetchErrorBridgeInstalled";
const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const ACTION_CONTEXT_MS = 30_000;
const SILENT_BACKGROUND_MUTATION_PATHS = new Set([
  "/api/realtime/presence",
  "/api/realtime/token",
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

function isAuthRecoveryUrl(url: string): boolean {
  try {
    return new URL(url, window.location.origin).pathname.replace(/\/+$/, "") === "/auth/refresh";
  } catch {
    return false;
  }
}

function isPublicAuthUrl(url: string): boolean {
  try {
    const path = new URL(url, window.location.origin).pathname.replace(/\/+$/, "");
    return path === "/auth/login"
      || path === "/auth/login-context"
      || path === "/auth/logout-session"
      || path.startsWith("/auth/password-reset/")
      || path === "/auth/dev-seed-login";
  } catch {
    return false;
  }
}

function isPublicHealthUrl(url: string): boolean {
  try {
    const path = new URL(url, window.location.origin).pathname.replace(/\/+$/, "") || "/";
    return path === "/" || ["/livez", "/readyz", "/healthz", "/health", "/time"].includes(path);
  } catch {
    return false;
  }
}

/**
 * Platform Operations is a separate gateway (proxied under same-origin /ops).
 * Its 401s mean ops auth/config failed — not that the portal access token is
 * invalid. Treating them as session death logs Superadmin users out while
 * /auth/me would still succeed.
 */
export function isPlatformOpsUrl(url: string): boolean {
  try {
    const base = typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "http://127.0.0.1";
    const path = new URL(url, base).pathname;
    return path === "/ops" || path.startsWith("/ops/");
  } catch {
    return false;
  }
}

function isPortalApiUrl(url: string): boolean {
  try {
    const requestUrl = new URL(url, window.location.origin);
    const apiBase = new URL(getApiBaseUrl() || "/", window.location.origin);
    if (requestUrl.origin !== apiBase.origin) return false;
    const basePath = apiBase.pathname.replace(/\/+$/, "");
    return !basePath || basePath === "/" || requestUrl.pathname.startsWith(`${basePath}/`);
  } catch {
    return false;
  }
}

function withCurrentAccessToken(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  fallbackRequest?: Request | null,
): [RequestInfo | URL, RequestInit | undefined] {
  const token = getToken();
  const headers = requestHeaders(fallbackRequest || input, init);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (fallbackRequest) return [new Request(fallbackRequest, { headers }), undefined];
  return [input, { ...init, headers }];
}

function recoveryPendingResponse(): Response {
  return new Response(JSON.stringify({
    detail: "The saved session is waiting for the server to recover.",
    error_code: "SESSION_RECOVERY_PENDING",
    retryable: true,
    request_accepted: false,
  }), {
    status: 503,
    headers: { "Content-Type": "application/json", "Retry-After": "5" },
  });
}

function isSilentBackgroundMutation(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    const path = parsed.pathname.replace(/\/+$/, "");
    if (SILENT_BACKGROUND_MUTATION_PATHS.has(path)) return true;
    // Live audit collaboration heartbeats are background beacons; failures must
    // not surface as user-facing Action failed toasts during fieldwork.
    return /\/audits\/[^/]+\/presence\/heartbeat$/i.test(path)
      || path.endsWith("/quality/audit-access/presence/heartbeat");
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
    const authRecoveryRequest = isAuthRecoveryUrl(url);
    const publicAuthRequest = isPublicAuthUrl(url);
    const publicHealthRequest = isPublicHealthUrl(url);
    const platformOpsRequest = isPlatformOpsUrl(url);
    const silent = headers.get("X-AMO-Silent-Error") === "1" || isSilentBackgroundMutation(url);
    const portalRequest = isPortalApiUrl(url) && !platformOpsRequest;
    const authenticatedRequest = portalRequest
      && !authRecoveryRequest
      && !publicAuthRequest
      && !publicHealthRequest
      && (
      (headers.get("Authorization") || "").startsWith("Bearer ")
      || hasRecoverableSession()
    );
    const retryRequest = typeof Request !== "undefined" && input instanceof Request ? input.clone() : null;

    // Logout/presence are lifecycle beacons and are deliberately silent. They
    // must not recursively trigger the idle guard that dispatched them.
    if (authenticatedRequest && !silent && !ensureAuthenticatedRequestAllowed()) {
      throw new DOMException("Session ended", "AbortError");
    }

    let activeInput = input;
    let activeInit = init;
    if (
      authenticatedRequest
      && (!getToken() || (getTokenSecondsRemaining() ?? 1) <= 0)
    ) {
      const recovered = await recoverSessionAfterUnauthorized("access-expired-preflight");
      if (!recovered) return recoveryPendingResponse();
      [activeInput, activeInit] = withCurrentAccessToken(input, init, retryRequest);
    }

    try {
      let response = await originalFetch(activeInput, activeInit);
      if (response.status === 401 && authenticatedRequest) {
        const recovered = await recoverSessionAfterUnauthorized("unauthorized-response");
        if (recovered) {
          const [retryInput, retryInit] = withCurrentAccessToken(input, init, retryRequest);
          response = await originalFetch(retryInput, retryInit);
        }
        if (response.status === 401) {
          markPortalSessionExpired("unauthorized-response");
          handleAuthFailure("unauthorized-response");
        }
      }
      if (portalRequest) notePortalResponse(response);
      if (mutation && !silent && !response.ok && response.status !== 401) {
        // Expected confirmation prompts (e.g. weekend policy) are handled in-page —
        // do not toast them as Action failed.
        let suppressToast = false;
        try {
          const probe = await response.clone().json() as { detail?: { code?: string } } | null;
          suppressToast =
            probe?.detail?.code === "WEEKEND_CONFIRMATION_REQUIRED"
            || probe?.detail?.code === "SCHEDULE_START_IN_PAST";
        } catch {
          suppressToast = false;
        }
        if (!suppressToast) {
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
      }
      return response;
    } catch (error) {
      if (portalRequest && !isAbort(error)) {
        notePortalNetworkFailure(error instanceof Error ? error.message : "network-unreachable");
      }
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

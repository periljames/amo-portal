import {
  authHeaders,
  cacheCurrentUser,
  handleAuthFailure,
  type PortalUser,
} from "./auth";
import { getApiBaseUrl } from "./config";

const PLATFORM_ACCESS_VERIFY_TIMEOUT_MS = 10_000;

export class PlatformAccessVerificationError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "PlatformAccessVerificationError";
    this.status = status;
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

async function readVerificationError(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  if (!text) return response.statusText || `HTTP ${response.status}`;
  try {
    const payload = JSON.parse(text) as { detail?: unknown; message?: unknown; error?: unknown };
    const detail = payload.detail ?? payload.message ?? payload.error;
    if (typeof detail === "string") return detail;
    if (detail != null) return JSON.stringify(detail);
  } catch {
    // Fall through to the plain response text.
  }
  return text.trim() || response.statusText || `HTTP ${response.status}`;
}

export async function verifyCurrentPlatformUser(): Promise<PortalUser> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => {
    controller.abort(new DOMException("Platform access verification timed out", "AbortError"));
  }, PLATFORM_ACCESS_VERIFY_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/auth/me`, {
      method: "GET",
      credentials: "include",
      headers: authHeaders({ Accept: "application/json" }),
      signal: controller.signal,
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw new PlatformAccessVerificationError(
        0,
        `Platform access verification timed out after ${PLATFORM_ACCESS_VERIFY_TIMEOUT_MS / 1000} seconds.`,
      );
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }

  if (!response.ok) {
    const message = await readVerificationError(response);
    if (response.status >= 400 && response.status < 500) {
      handleAuthFailure(`platform-access-rejected:${response.status}`);
    }
    throw new PlatformAccessVerificationError(response.status, message);
  }

  const user = (await response.json()) as PortalUser;
  cacheCurrentUser(user);
  return user;
}

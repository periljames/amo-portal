import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  OfflineQueuedError,
  isPortalCacheablePath,
  isReplaySafeMutation,
  portalFetch,
} from "./offlineHttp";
import { notePortalResponse } from "./portalConnectivity";
import { installOfflineBrowser, offlineTestBody } from "../test/offlineBrowser";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  installOfflineBrowser();
  notePortalResponse(new Response(null, { status: 200 }));
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("portal offline cache policy", () => {
  it("allows operational JSON endpoints", () => {
    expect(isPortalCacheablePath("/rostering/periods?from=2026-07-20&to=2026-07-26")).toBe(true);
    expect(isPortalCacheablePath("/workforce/people?active_only=true")).toBe(true);
    expect(isPortalCacheablePath("/qms/audits?page=1")).toBe(true);
  });

  it("excludes credentials, billing and downloadable artefacts", () => {
    expect(isPortalCacheablePath("/auth/me")).toBe(false);
    expect(isPortalCacheablePath("/accounts/admin/billing/invoices")).toBe(false);
    expect(isPortalCacheablePath("/rostering/reports/export?format=pdf")).toBe(false);
    expect(isPortalCacheablePath("/training/certificate.pdf")).toBe(false);
  });
});

describe("portal offline mutation policy", () => {
  it.each([
    ["/rostering/versions/id/assignments", "POST"],
    ["/rostering/assignments/id", "PATCH"],
    ["/work-orders/tasks/1", "PUT"],
    ["/workforce/attendance-events", "POST"],
  ])("retains the original %s command key after an ambiguous timeout", async (path, method) => {
    let sentKey: string | null = null;
    globalThis.fetch = vi.fn((_input, init) => {
      if (init?.method === "GET") return Promise.resolve(new Response('{"ready":true}', { status: 200 }));
      sentKey = new Headers(init?.headers).get("Idempotency-Key");
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Timed out", "AbortError")));
      });
    });
    const body = offlineTestBody(path);
    const failure = await portalFetch(path, { method, body, timeoutMs: 10, offline: { queueMutation: true } }).catch((error) => error);
    expect(failure).toBeInstanceOf(OfflineQueuedError);
    expect(failure.operation.idempotencyKey).toBe(sentKey);
    expect(failure.operation.body).toBe(body);
  });
  it("keeps authoritative and destructive operations live-only", () => {
    expect(isReplaySafeMutation("/rostering/assignments/ID-1", "DELETE")).toBe(false);
    expect(isReplaySafeMutation("/workforce/leave-requests/ID-1/approve", "POST")).toBe(false);
    expect(isReplaySafeMutation("/payroll/runs/ID-1/post", "POST")).toBe(false);
    expect(isReplaySafeMutation("/rostering/versions/ID-1/assignments", "POST")).toBe(true);
  });

  it("does not queue a mutation when the server returns an error", async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ detail: "worker failed" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;

    const response = await portalFetch("/rostering/versions/ID-1/assignments", {
      method: "POST",
      body: JSON.stringify({ user_id: "ID-U1" }),
      offline: { queueMutation: true },
    });

    expect(response.status).toBe(500);
  });

  it("does not queue an aborted mutation", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new DOMException("Session ended", "AbortError");
    }) as typeof fetch;

    await expect(portalFetch("/rostering/versions/ID-1/assignments", {
      method: "POST",
      body: JSON.stringify({ user_id: "ID-U1", source_reference_id: "offline-test-503" }),
      offline: { queueMutation: true },
    })).rejects.not.toBeInstanceOf(OfflineQueuedError);
  });

  it("queues only when a 503 explicitly confirms that the request was not accepted", async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      detail: "Database unavailable",
      error_code: "DB_TEMPORARILY_UNAVAILABLE",
      request_accepted: false,
      retryable: true,
    }), {
      status: 503,
      headers: { "Content-Type": "application/json", "X-Portal-Readiness": "offline" },
    })) as typeof fetch;

    await expect(portalFetch("/rostering/versions/ID-1/assignments", {
      method: "POST",
      body: JSON.stringify({ user_id: "ID-U1", source_reference_id: "offline-test-transport" }),
      offline: { queueMutation: true },
    })).rejects.toBeInstanceOf(OfflineQueuedError);
  });

  it("queues a mutation after a genuine transport failure", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    await expect(portalFetch("/rostering/versions/ID-1/assignments", {
      method: "POST",
      body: JSON.stringify({ user_id: "ID-U1", source_reference_id: "offline-test-transport" }),
      offline: { queueMutation: true, entityType: "roster-assignment" },
    })).rejects.toBeInstanceOf(OfflineQueuedError);
  });
});

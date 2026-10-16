import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  OfflineQueuedError,
  isPortalCacheablePath,
  isReplaySafeMutation,
  portalFetch,
} from "./offlineHttp";
import { notePortalResponse } from "./portalConnectivity";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  notePortalResponse(new Response(null, { status: 200 }));
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
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

  it("durably queues an exact idempotent checklist command when its API request times out", async () => {
    globalThis.fetch = vi.fn((_url, init) => new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!(signal instanceof AbortSignal)) {
        reject(new Error("The fieldwork request must include an abort signal"));
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    })) as typeof fetch;

    const clientMutationId = "test-fieldwork-timeout-12345";
    const command = JSON.stringify({
      client_mutation_id: clientMutationId,
      device_id: "test-device-12345",
      device_sequence: 1,
      client_timestamp: "2026-10-16T07:00:00.000Z",
      base_version: 1,
      operation: "CHECKLIST_UPDATE",
      reason: "Offline continuity",
      canonical_response_status: "COMPLIANT",
    });
    await expect(portalFetch("/api/maintenance/tenant-a/quality/audits/audit-1/checklist-items/item-1/fieldwork-mutations", {
      method: "POST",
      body: command,
      timeoutMs: 10,
      offline: {
        queueMutation: true,
        requireDurable: true,
        entityType: "qms-audit-checklist-item",
        entityId: "item-1",
        idempotencyKey: clientMutationId,
      },
    })).rejects.toBeInstanceOf(OfflineQueuedError);
  });

  it("recognizes the API client timeout signal but never queues a user cancellation", async () => {
    globalThis.fetch = vi.fn((_url, init) => new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      if (!(signal instanceof AbortSignal)) {
        reject(new Error("Expected abortable fieldwork fetch"));
        return;
      }
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    })) as typeof fetch;

    const payload = JSON.stringify({
      client_mutation_id: "test-fieldwork-caller-timeout-12345",
      device_id: "test-device-12345", device_sequence: 2,
      client_timestamp: "2026-10-16T08:00:00.000Z", base_version: 1,
      operation: "CHECKLIST_UPDATE", reason: "Continue fieldwork after timeout",
      canonical_response_status: "COMPLIANT",
    });
    const caller = new AbortController();
    const timeout = setTimeout(() => caller.abort(new DOMException("Request timed out after 1 seconds", "AbortError")), 10);
    try {
      await expect(portalFetch("/api/maintenance/tenant-a/quality/audits/audit-1/checklist-items/item-1/fieldwork-mutations", {
        method: "POST", body: payload, signal: caller.signal, timeoutMs: 10_000,
        offline: { queueMutation: true, requireDurable: true,
          entityType: "qms-audit-checklist-item", entityId: "item-1",
          idempotencyKey: "test-fieldwork-caller-timeout-12345",
        },
      })).rejects.toBeInstanceOf(OfflineQueuedError);
    } finally {
      clearTimeout(timeout);
    }
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

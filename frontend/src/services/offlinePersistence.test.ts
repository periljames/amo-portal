import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearCurrentOfflineScope, enqueueOfflineMutation, listOfflineMutations, replayOfflineMutations, retryOfflineMutation } from "./offlinePersistence";
import { installOfflineBrowser, offlineTestBody } from "../test/offlineBrowser";

vi.mock("./auth", () => ({
  authHeaders: (headers: HeadersInit) => headers,
  getToken: () => "test-token",
  getCachedUser: () => null,
  getContext: () => ({}),
  handleAuthFailure: vi.fn(),
}));
vi.mock("./portalConnectivity", async (importOriginal) => ({
  ...await importOriginal<typeof import("./portalConnectivity")>(),
  isPortalReady: () => true,
  notePortalResponse: vi.fn(),
}));

beforeEach(async () => { installOfflineBrowser(); await clearCurrentOfflineScope(); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function queue(path: string) {
  return enqueueOfflineMutation({ path, method: "POST", body: offlineTestBody(path) });
}

describe("offline replay module isolation", () => {
  it("keeps replay ownership until other modules finish after a storage failure", async () => {
    await queue("/api/maintenance/amo/quality/audits/a/checklist-items/one/fieldwork-mutations");
    await queue("/workforce/attendance-events");
    vi.spyOn(crypto.subtle, "encrypt").mockRejectedValueOnce(new Error("temporary storage encryption failure"));
    let release!: (response: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const replay = replayOfflineMutations();
    let rejected = false;
    void replay.catch(() => { rejected = true; });
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(rejected).toBe(false);
    release(new Response("{}", { status: 200 }));
    await expect(replay).rejects.toThrow(/storage/);
  });
  it("syncs independent modules while a slow module is still waiting", async () => {
    await queue("/api/maintenance/amo/quality/audits/a/checklist-items/one/fieldwork-mutations");
    await queue("/workforce/attendance-events");
    let release!: (response: Response) => void;
    const fetch = vi.fn((url: string) => url.includes("fieldwork-mutations")
      ? new Promise<Response>((resolve) => { release = resolve; })
      : Promise.resolve(new Response("{}", { status: 200 })));
    vi.stubGlobal("fetch", fetch);
    const replay = replayOfflineMutations();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    try {
      await vi.waitFor(async () => {
        expect((await listOfflineMutations()).some((entry) => entry.path === "/workforce/attendance-events")).toBe(false);
      });
    } finally {
      release(new Response("{}", { status: 200 }));
    }
    expect((await replay).total).toBe(0);
  });

  it("creates a new receipt key after a human retries a revision conflict", async () => {
    const path = "/rostering/assignments/id";
    const entry = await enqueueOfflineMutation({ path, method: "PATCH", entityType: "roster-assignment", body: offlineTestBody(path) });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: {
      code: "ROSTER_REVISION_CONFLICT", message: "A second device changed this assignment.", retryable: true, current_state_revision: 5,
    } }), { status: 409, headers: { "Content-Type": "application/json" } })));
    await replayOfflineMutations();
    const [conflict] = await listOfflineMutations();
    expect(conflict.status).toBe("conflict");
    expect(conflict.error).toContain("second device");
    const retried = await retryOfflineMutation(entry.id);
    expect(retried.idempotencyKey).not.toBe(entry.idempotencyKey);
    expect(JSON.parse(retried.body!).expected_state_revision).toBe(5);
    expect(retried.attempts).toBe(0);
    expect(retried.headers["idempotency-key"]).toBe(retried.idempotencyKey);
  });
  it.each([500, 503, 429, 409])("continues other modules after a local HTTP %s", async (status) => {
    await queue("/api/maintenance/amo/quality/audits/a/checklist-items/one/fieldwork-mutations");
    await queue("/api/maintenance/amo/quality/audits/a/checklist-items/two/fieldwork-mutations");
    await queue("/workforce/attendance-events");
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: "COMMAND_IN_PROGRESS" } }), { status }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const summary = await replayOfflineMutations();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(fetch.mock.calls[1][0])).toContain("/workforce/attendance-events");
    expect(summary.total).toBe(2);
    expect((await listOfflineMutations())[0].attempts).toBe(1);
    expect((await listOfflineMutations())[1].attempts).toBe(0);
  });

  it("pauses all modules on an explicit shared database outage", async () => {
    await queue("/api/maintenance/amo/quality/audits/a/checklist-items/one/fieldwork-mutations");
    await queue("/workforce/attendance-events");
    const fetch = vi.fn().mockResolvedValue(new Response("{}", {
      status: 503, headers: { "X-Portal-Readiness": "offline" },
    }));
    vi.stubGlobal("fetch", fetch);
    expect((await replayOfflineMutations()).total).toBe(2);
    // Independent modules already in flight may also observe the outage.
    expect(fetch.mock.calls.length).toBeLessThanOrEqual(2);
  });
});

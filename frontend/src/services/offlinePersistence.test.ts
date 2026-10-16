import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearCurrentOfflineScope, enqueueOfflineMutation, listOfflineMutations, replayOfflineMutations } from "./offlinePersistence";

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

beforeEach(async () => { await clearCurrentOfflineScope(); });
afterEach(() => { vi.unstubAllGlobals(); });

async function queue(path: string) {
  return enqueueOfflineMutation({ path, method: "POST", body: "{}" });
}

describe("offline replay module isolation", () => {
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
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";
import { startPortalOfflineSync } from "./portalOfflineSync";

const state = vi.hoisted(() => ({
  scope: "one", remaining: 600, change: () => {},
  replay: vi.fn(), entries: vi.fn(), evidence: vi.fn(), upload: vi.fn(),
}));
vi.mock("./auth", () => ({ getToken: () => "token", getTokenSecondsRemaining: () => state.remaining }));
vi.mock("./offlinePersistence", () => ({
  currentOfflineScope: () => state.scope, replayOfflineMutations: state.replay, listOfflineMutations: state.entries,
  onOfflineStateChanged: (listener: () => void) => { state.change = listener; return () => {}; },
}));
vi.mock("./portalConnectivity", () => ({ isPortalReady: () => true, onPortalConnectivityChange: () => () => {} }));
vi.mock("./qmsOfflineAuditEvidence", () => ({
  listPendingAuditEvidenceGroups: state.evidence, synchronizeOfflineAuditEvidence: state.upload,
  onOfflineAuditEvidenceChanged: () => () => {},
}));
let stop: () => void;
beforeEach(() => {
  vi.useFakeTimers(); installOfflineBrowser();
  vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "visible" }));
  state.scope = "one"; state.remaining = 600;
  state.replay.mockReset().mockResolvedValue({ total: 0 });
  state.entries.mockReset().mockResolvedValue([]);
  state.evidence.mockReset().mockResolvedValue([]);
  state.upload.mockReset().mockResolvedValue(undefined);
});
afterEach(() => { stop?.(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("portal background sync scheduling", () => {
  it("runs a follow-up promptly when edits arrive during replay", async () => {
    let release!: () => void;
    state.replay.mockImplementationOnce(() => new Promise<void>((resolve) => { release = resolve; }));
    stop = startPortalOfflineSync();
    await vi.advanceTimersByTimeAsync(300);
    expect(state.replay).toHaveBeenCalledTimes(1);
    state.change(); state.change();
    release();
    await vi.advanceTimersByTimeAsync(301);
    expect(state.replay).toHaveBeenCalledTimes(2);
  });
  it("retries at the command deadline rather than waiting 30 seconds", async () => {
    state.entries.mockImplementation(async () => [{ status: "queued", nextAttemptAt: Date.now() + 2000 }]);
    stop = startPortalOfflineSync();
    await vi.advanceTimersByTimeAsync(300);
    await vi.advanceTimersByTimeAsync(1999);
    expect(state.replay).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2);
    expect(state.replay).toHaveBeenCalledTimes(2);
  });
  it("does not upload old-tenant evidence after switching scope", async () => {
    state.replay.mockImplementationOnce(async () => { state.scope = "two"; });
    stop = startPortalOfflineSync();
    await vi.advanceTimersByTimeAsync(300);
    expect(state.evidence).not.toHaveBeenCalled();
    expect(state.upload).not.toHaveBeenCalled();
  });
  it("does not attempt replay with expired credentials", async () => {
    state.remaining = -1;
    stop = startPortalOfflineSync();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(state.replay).not.toHaveBeenCalled();
  });
});

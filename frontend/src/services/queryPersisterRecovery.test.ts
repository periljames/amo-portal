import { afterEach, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";
vi.mock("./offlinePersistence", () => ({ currentOfflineScope: () => "test-user:test-tenant", encryptDeviceValue: vi.fn(), decryptDeviceValue: vi.fn() }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it("releases query-provider hydration when IndexedDB never opens", async () => {
 installOfflineBrowser(); vi.useFakeTimers();
 vi.stubGlobal("window", { indexedDB: { open: () => ({}) } });
 const { createPortalQueryPersister } = await import("./queryPersister");
 const restore = createPortalQueryPersister().restoreClient();
 await vi.advanceTimersByTimeAsync(800);
 expect(await restore).toBeUndefined();
});

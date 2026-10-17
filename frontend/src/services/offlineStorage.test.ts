import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installOfflineBrowser, offlineTestBody } from "../test/offlineBrowser";
import * as storage from "./offlinePersistence";

vi.mock("./auth", () => ({
  getCachedUser: () => ({ id: "user-one", amo_id: "amo-one" }),
  getContext: () => ({}), getToken: () => "token", authHeaders: () => ({}), handleAuthFailure: vi.fn(),
}));

beforeEach(async () => { installOfflineBrowser(); await storage.clearCurrentOfflineScope(); });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function rawOutbox() {
  const db = await new Promise<IDBDatabase>((resolve) => {
    const request = indexedDB.open("amo-portal-offline", 3);
    request.onsuccess = () => resolve(request.result);
  });
  return { db, rows: await new Promise<Record<string, unknown>[]>((resolve) => {
    const request = db.transaction("outbox").objectStore("outbox").getAll();
    request.onsuccess = () => resolve(request.result);
  }) };
}

describe("durable encrypted offline storage", () => {
  it("persists encrypted changes across a module reload", async () => {
    const body = offlineTestBody("/workforce/attendance-events", { note: "private attendance data" });
    const entry = await storage.enqueueOfflineMutation({ path: "/workforce/attendance-events", method: "POST", body });
    const { db, rows } = await rawOutbox();
    expect(rows[0].body).toBeUndefined();
    expect(JSON.stringify(rows[0])).not.toContain("private attendance data");
    expect(rows[0].encryptedBody).toBeDefined();
    db.close();
    vi.resetModules();
    const reopened = await import("./offlinePersistence");
    const [restored] = await reopened.listOfflineMutations();
    expect(restored.id).toBe(entry.id);
    expect(restored.body).toBe(body);
  });

  it("does not claim a durable save when browser storage is absent", async () => {
    Object.assign(window, { indexedDB: undefined });
    await expect(storage.enqueueOfflineMutation({ path: "/workforce/attendance-events", method: "POST", body: offlineTestBody("/workforce/attendance-events") }))
      .rejects.toThrow(/not queued/i);
  });

  it("keeps unreadable changes visible and retains encrypted bytes", async () => {
    const entry = await storage.enqueueOfflineMutation({ path: "/workforce/attendance-events", method: "POST", body: offlineTestBody("/workforce/attendance-events") });
    const { db, rows } = await rawOutbox();
    const tx = db.transaction("outbox", "readwrite");
    tx.objectStore("outbox").put({ ...rows[0], encryptedBody: { v: 1, iv: "bad", data: "bad" } });
    await new Promise<void>((resolve) => { tx.oncomplete = () => resolve(); });
    const [unreadable] = await storage.listOfflineMutations();
    expect(unreadable.id).toBe(entry.id);
    expect(unreadable.errorCode).toBe("OFFLINE_STORAGE_UNREADABLE");
    expect((await storage.getOfflineOutboxSummary()).failed).toBe(1);
    const raw = await rawOutbox();
    expect(raw.rows).toHaveLength(1);
    raw.db.close();
    await storage.discardOfflineMutation(entry.id);
    expect((await storage.listOfflineMutations()).length).toBe(0);
    db.close();
  });

  it("uses one encryption key when independent tabs initialize without Web Locks", async () => {
    const { db } = await rawOutbox();
    const transaction = db.transaction("device_keys", "readwrite");
    transaction.objectStore("device_keys").clear();
    await new Promise<void>((resolve) => { transaction.oncomplete = () => resolve(); });
    db.close();
    vi.resetModules();
    const first = await import("./offlinePersistence");
    vi.resetModules();
    const second = await import("./offlinePersistence");
    const [one, two] = await Promise.all([first.encryptDeviceValue("first tab"), second.encryptDeviceValue("second tab")]);
    expect(one).not.toBeNull();
    expect(two).not.toBeNull();
    expect(await second.decryptDeviceValue(one!)).toBe("first tab");
    expect(await first.decryptDeviceValue(two!)).toBe("second tab");
  });
});

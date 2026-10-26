import { afterEach, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";
import { getOrCreateDeviceStorageKey } from "./deviceStorageKey";

afterEach(() => vi.unstubAllGlobals());

it("concurrent tabs all retain the same non-extractable encryption key", async () => {
  installOfflineBrowser();
  const name = `key-race-${crypto.randomUUID()}`;
  const connect = () => new Promise<IDBDatabase>((resolve) => {
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("keys", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
  });
  const tabs = await Promise.all(Array.from({ length: 12 }, connect));
  try {
    const keys = await Promise.all(tabs.map((db) => getOrCreateDeviceStorageKey(db, "keys", "device-key")));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const bytes = new TextEncoder().encode("QMS evidence and controlled document bytes");
    const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, keys[0], bytes);
    for (const key of keys) {
      expect(key.extractable).toBe(false);
      const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, encrypted);
      expect(new TextDecoder().decode(decrypted)).toBe(new TextDecoder().decode(bytes));
    }
  } finally { tabs.forEach((db) => db.close()); }
});

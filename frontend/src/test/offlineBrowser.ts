import { indexedDB, IDBKeyRange } from "fake-indexeddb";
import { vi } from "vitest";

/** In-memory IndexedDB transactions plus runtime WebCrypto and browser event stubs. */
export function installOfflineBrowser() {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
    clear: () => values.clear(),
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size; },
  };
  const browser = Object.assign(new EventTarget(), {
    indexedDB, localStorage: storage, sessionStorage: storage,
    location: { origin: "http://localhost:5173", hostname: "localhost", port: "5173" },
    setTimeout, clearTimeout, setInterval, clearInterval,
  });
  vi.stubGlobal("window", browser);
  vi.stubGlobal("localStorage", storage);
  vi.stubGlobal("sessionStorage", storage);
  vi.stubGlobal("IDBKeyRange", IDBKeyRange);
  vi.stubGlobal("indexedDB", indexedDB);
  vi.stubGlobal("BroadcastChannel", undefined);
  return browser;
}

export function offlineTestBody(path: string, extra: Record<string, unknown> = {}): string {
  if (path.includes("fieldwork-")) return JSON.stringify({
    client_mutation_id: `fieldwork-${crypto.randomUUID()}`, device_id: "test-device-123456",
    device_sequence: 1, base_version: 0, client_timestamp: new Date().toISOString(),
    operation: "CHECKLIST_UPDATE", canonical_response_status: "COMPLIANT", reason: "Test fieldwork", ...extra,
  });
  if (path.startsWith("/rostering/")) return JSON.stringify({ source_reference_id: "test-reference", expected_state_revision: 1, ...extra });
  if (path.startsWith("/work-orders/")) return JSON.stringify({ last_known_updated_at: "2026-10-16T12:00:00Z", ...extra });
  return JSON.stringify({ idempotency_key: `attendance-${crypto.randomUUID()}`, ...extra });
}

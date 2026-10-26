import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";
import { readFieldworkJournal, saveFieldworkJournal } from "./qmsFieldworkJournal";

const identity = vi.hoisted(() => ({ id: "auditor-a" }));
vi.mock("./auth", () => ({
  getCachedUser: () => ({ id: identity.id, amo_id: "amo-a" }), getContext: () => ({ amoCode: "amo-a" }),
  getToken: () => "test", authHeaders: (value: unknown) => value, handleAuthFailure: vi.fn(),
}));
beforeEach(() => { installOfflineBrowser(); identity.id = "auditor-a"; });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("restores encrypted remarks and a completion request after more than a day offline", async () => {
  const audit = crypto.randomUUID();
  const value = {
    notes: { question: "Inspected traceability records" },
    parkedFindings: { question: { level: "LEVEL_4", statement: "Retained observation draft" } },
    acceptedRows: { question: { checklist_item_id: "question", audit_id: audit, response_value: "YES", entity_version: 4 } },
    completion: { requestedAt: new Date().toISOString() },
  };
  await saveFieldworkJournal("amo-a", audit, value);
  const db = await new Promise<IDBDatabase>((resolve) => { const request = indexedDB.open("amo-qms-fieldwork-journal", 1); request.onsuccess = () => resolve(request.result); });
  const rows = await new Promise<unknown[]>((resolve) => { const request = db.transaction("entries").objectStore("entries").getAll(); request.onsuccess = () => resolve(request.result); });
  db.close();
  expect(JSON.stringify(rows)).not.toContain("Inspected traceability records");
  expect(JSON.stringify(rows)).not.toContain("Retained observation draft");
  const later = Date.now() + 3 * 24 * 60 * 60 * 1000;
  vi.spyOn(Date, "now").mockReturnValue(later);
  expect(await readFieldworkJournal("amo-a", audit)).toEqual(value);
  identity.id = "auditor-b";
  expect(await readFieldworkJournal("amo-a", audit)).toBeNull();
  identity.id = "auditor-a";
  expect(await readFieldworkJournal("amo-b", audit)).toBeNull();
});

it("reports storage failure and preserves the last committed work", async () => {
  const audit = crypto.randomUUID();
  await saveFieldworkJournal("amo-a", audit, { notes: "Retain this" });
  vi.spyOn(crypto.subtle, "encrypt").mockRejectedValueOnce(new Error("Device full"));
  await expect(saveFieldworkJournal("amo-a", audit, { notes: "New work" })).rejects.toThrow("Device full");
  expect(await readFieldworkJournal("amo-a", audit)).toEqual({ notes: "Retain this" });
});

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";
import { readRetainedAuditEvidence, retainDownloadedAuditEvidence, retainedAuditEvidenceIds } from "./qmsOfflineAuditEvidence";
import type { AuditEvidenceArtifact } from "./qmsAuditEvidence";

const identity = vi.hoisted(() => ({ scope: "auditor-a:amo-a" }));
vi.mock("./offlinePersistence", () => ({ currentOfflineScope: () => identity.scope, listOfflineMutations: vi.fn(async () => []) }));
vi.mock("./qmsChecklistExecutionGovernance", () => ({ listChecklistExecutionGovernance: vi.fn() }));
vi.mock("./qmsAuditEvidence", () => ({ uploadInternalAuditEvidence: vi.fn() }));
beforeEach(() => { installOfflineBrowser(); identity.scope = "auditor-a:amo-a"; });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function sample() {
  const blob = new Blob(["Retained synthetic audit evidence"], { type: "text/plain" });
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  const sha256 = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
  const artifact = { id: crypto.randomUUID(), filename: "test.txt", content_type: "text/plain", sha256, created_at: new Date().toISOString() } as AuditEvidenceArtifact;
  return { blob, artifact, audit: crypto.randomUUID() };
}

it("keeps encrypted, hash-verified reading copies isolated by user, tenant and audit", async () => {
  const { blob, artifact, audit } = await sample();
  expect(await retainDownloadedAuditEvidence("amo-a", audit, artifact, blob)).toBe(true);
  expect(await retainedAuditEvidenceIds("amo-a", audit)).toEqual([artifact.id]);
  expect(await (await readRetainedAuditEvidence("amo-a", audit, artifact))?.text()).toBe(await blob.text());
  expect(await readRetainedAuditEvidence("amo-b", audit, artifact)).toBeNull();
  expect(await readRetainedAuditEvidence("amo-a", "other-audit", artifact)).toBeNull();
  identity.scope = "auditor-b:amo-a";
  expect(await readRetainedAuditEvidence("amo-a", audit, artifact)).toBeNull();
  identity.scope = "auditor-a:amo-a";
  const db = await new Promise<IDBDatabase>(resolve => { const request = indexedDB.open("amo-qms-offline-evidence", 2); request.onsuccess = () => resolve(request.result); });
  const rows = await new Promise<unknown[]>(resolve => { const request = db.transaction("retained").objectStore("retained").getAll(); request.onsuccess = () => resolve(request.result); });
  db.close();
  expect(JSON.stringify(rows)).not.toContain(await blob.text());
  expect(await readRetainedAuditEvidence("amo-a", audit, { ...artifact, sha256: "0".repeat(64) })).toBeNull();
});

it("rejects changed download bytes before retaining them", async () => {
  const { artifact, audit } = await sample();
  await expect(retainDownloadedAuditEvidence("amo-a", audit, artifact, new Blob(["Changed bytes"]))).rejects.toThrow("checksum");
  expect(await retainedAuditEvidenceIds("amo-a", audit)).toEqual([]);
});

it("does not block an online download when local retention fails", async () => {
  const { blob, artifact, audit } = await sample();
  vi.spyOn(crypto.subtle, "encrypt").mockRejectedValueOnce(new Error("Device storage unavailable"));
  expect(await retainDownloadedAuditEvidence("amo-a", audit, artifact, blob)).toBe(false);
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { optionalStorageRead } from "./storageReadDeadline";
afterEach(() => vi.useRealTimers());
describe("optional device hydration", () => {
 it("does not strand online startup behind a blocked database", async () => {
  vi.useFakeTimers(); const pending = optionalStorageRead(() => new Promise<never>(() => {}), undefined);
  await vi.advanceTimersByTimeAsync(800); expect(await pending).toBeUndefined();
 });
 it("returns a ready snapshot unchanged", async () => { expect(await optionalStorageRead(async () => ({ data: 1 }), undefined)).toEqual({ data: 1 }); });
 it("treats cache errors as an optional miss", async () => { expect(await optionalStorageRead(async () => { throw Error("blocked"); }, undefined)).toBeUndefined(); });
});

import { describe, expect, it } from "vitest";
import { readCompleteRegister } from "./qmsCompleteRegister";

describe("complete register analysis", () => {
  it("includes records beyond the first hundred", async () => {
    const rows = Array.from({ length: 237 }, (_, index) => ({ id: String(index), value: index }));
    const offsets: number[] = [];
    const result = await readCompleteRegister(async offset => {
      offsets.push(offset);
      return { items: rows.slice(offset, offset + 100), offset, limit: 100, total: rows.length, has_more: offset + 100 < rows.length };
    }, new AbortController().signal);
    expect(result).toEqual(rows);
    expect(offsets).toEqual([0, 100, 200]);
  });
  it("rejects a partial population rather than fabricating totals", async () => {
    await expect(readCompleteRegister(async () => ({ items: [{ id: "one" }], total: 2, offset: 0, limit: 100, has_more: false }), new AbortController().signal)).rejects.toThrow("incomplete");
  });
  it("stops a server that repeats a page", async () => {
    await expect(readCompleteRegister(async offset => ({ items: [{ id: "one" }], total: 3, offset, limit: 1, has_more: true }), new AbortController().signal)).rejects.toThrow("repeated");
  });
  it("rejects population changes during pagination", async () => {
    await expect(readCompleteRegister(async offset => ({ items: [{ id: String(offset) }], total: offset ? 3 : 2, offset, limit: 1, has_more: true }), new AbortController().signal)).rejects.toThrow("Records changed");
  });
  it("does not fetch another page after the caller leaves", async () => {
    const controller = new AbortController();
    let calls = 0;
    await expect(readCompleteRegister(async offset => { calls++; controller.abort(); return { items: [{ id: "one" }], total: 2, offset, limit: 1, has_more: true }; }, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(calls).toBe(1);
  });
});

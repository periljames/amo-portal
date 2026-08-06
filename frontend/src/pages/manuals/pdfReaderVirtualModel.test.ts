import { describe, expect, it } from "vitest";

import {
  nextHotPageIndexes,
  selectPhysicalVirtualPage,
} from "./pdfReaderVirtualModel";

describe("virtual PDF reader model", () => {
  it("publishes the physical page crossing the reader anchor", () => {
    expect(selectPhysicalVirtualPage([
      { index: 18, start: 0, end: 980 },
      { index: 19, start: 998, end: 1978 },
    ], 1010, 14)).toBe(20);
  });

  it("does not publish a requested page before it reaches the viewport", () => {
    expect(selectPhysicalVirtualPage([
      { index: 4, start: 0, end: 950 },
      { index: 5, start: 968, end: 1918 },
    ], 20, 14)).toBe(5);
  });

  it("retains a bounded current-page neighbourhood", () => {
    expect(nextHotPageIndexes([2, 3, 4, 70], 20, 111, 5)).toEqual([18, 19, 20, 2, 3]);
  });

  it("clips retained pages to document boundaries", () => {
    expect(nextHotPageIndexes([], 1, 3, 10)).toEqual([0, 1]);
    expect(nextHotPageIndexes([], 3, 3, 10)).toEqual([1, 2]);
  });
});

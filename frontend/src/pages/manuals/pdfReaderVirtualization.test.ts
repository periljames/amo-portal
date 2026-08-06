import { describe, expect, it } from "vitest";

import {
  prioritizePdfRenderIndexes,
  selectPdfVirtualPage,
  updatePdfRetainedPages,
} from "./pdfReaderVirtualization";

describe("virtualized controlled PDF reader", () => {
  it("publishes the page physically crossing the viewport anchor", () => {
    const page = selectPdfVirtualPage([
      { index: 18, start: 0, end: 980, size: 980 },
      { index: 19, start: 1000, end: 1980, size: 980 },
      { index: 20, start: 2000, end: 2980, size: 980 },
    ], 1010, 760, 24);

    expect(page).toBe(20);
  });

  it("does not publish a requested page until the virtual viewport reaches it", () => {
    const page = selectPdfVirtualPage([
      { index: 19, start: 19000, end: 19980, size: 980 },
      { index: 20, start: 20000, end: 20980, size: 980 },
    ], 19020, 760, 24);

    expect(page).toBe(20);
    expect(page).not.toBe(5);
  });

  it("prioritizes the explicit destination before nearby and retained pages", () => {
    const indexes = prioritizePdfRenderIndexes(
      [18, 19, 20, 21],
      [1, 2, 17, 18],
      27,
      20,
      111,
      8,
    );

    expect(indexes[0]).toBe(26);
    expect(indexes).toContain(19);
    expect(indexes.length).toBeLessThanOrEqual(8);
  });

  it("keeps a bounded least-recently-used completed-page set", () => {
    let retained: number[] = [];
    for (let page = 1; page <= 18; page += 1) {
      retained = updatePdfRetainedPages(retained, page, 10);
    }

    expect(retained).toEqual([9, 10, 11, 12, 13, 14, 15, 16, 17, 18]);
    expect(updatePdfRetainedPages(retained, 12, 10).at(-1)).toBe(12);
  });
});

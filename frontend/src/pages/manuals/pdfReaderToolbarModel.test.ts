import { describe, expect, it } from "vitest";

import {
  clampPdfZoom,
  parsePdfScaleValue,
  pdfPageWidth,
  pdfScaleLabel,
} from "./pdfReaderToolbarModel";

describe("pdfReaderToolbarModel", () => {
  it("keeps explicit percentage zoom within the reader contract", () => {
    expect(clampPdfZoom(25)).toBe(50);
    expect(clampPdfZoom(125)).toBe(125);
    expect(clampPdfZoom(900)).toBe(400);
    expect(parsePdfScaleValue("300")).toEqual({ mode: "CUSTOM", zoom: 300 });
  });

  it("supports the De Havilland-style named scale choices", () => {
    expect(parsePdfScaleValue("AUTO")).toEqual({ mode: "AUTO" });
    expect(parsePdfScaleValue("ACTUAL")).toEqual({ mode: "ACTUAL" });
    expect(parsePdfScaleValue("PAGE")).toEqual({ mode: "PAGE" });
    expect(parsePdfScaleValue("WIDTH")).toEqual({ mode: "WIDTH" });
    expect(pdfScaleLabel("AUTO", 100)).toBe("Automatic Zoom");
    expect(pdfScaleLabel("CUSTOM", 150)).toBe("150%");
  });

  it("computes page, width, actual, and percentage sizes independently", () => {
    const base = {
      zoom: 100,
      availableWidth: 1000,
      availableHeight: 700,
      pageRatio: 1.4,
      actualWidth: 600,
    };
    expect(pdfPageWidth({ ...base, mode: "PAGE" })).toBe(500);
    expect(pdfPageWidth({ ...base, mode: "WIDTH" })).toBe(1000);
    expect(pdfPageWidth({ ...base, mode: "ACTUAL" })).toBe(600);
    expect(pdfPageWidth({ ...base, mode: "CUSTOM", zoom: 200 })).toBe(1200);
    expect(pdfPageWidth({ ...base, mode: "AUTO" })).toBe(600);
  });
});

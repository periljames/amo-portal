import { describe, expect, it } from "vitest";

import {
  highlightPdfText,
  outputPdfFilename,
  pdfReaderShortcut,
  searchPdfDocument,
} from "./pdfReaderEngine";
import { pdfWorkingCopyKey } from "./pdfWorkingCopyStore";

function fakeDocument(pages: string[]) {
  return {
    numPages: pages.length,
    getPage: async (pageNumber: number) => ({
      getTextContent: async () => ({
        items: pages[pageNumber - 1].split(" ").map((str) => ({ str })),
      }),
    }),
  };
}

describe("controlled PDF reader engine", () => {
  it("searches every page in page order with bounded asynchronous workers", async () => {
    const controller = new AbortController();
    const progress: number[] = [];
    const results = await searchPdfDocument(
      fakeDocument(["engine inspection", "aircraft engine record", "no match", "ENGINE case"]),
      "engine",
      { caseSensitive: false, wholeWord: true },
      controller.signal,
      (completed) => progress.push(completed),
    );

    expect(results.map((result) => result.page)).toEqual([1, 2, 4]);
    expect(results.every((result) => result.snippet.toLowerCase().includes("engine"))).toBe(true);
    expect(progress.at(-1)).toBe(4);
  });

  it("cancels stale searches before returning results", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(searchPdfDocument(fakeDocument(["engine"]), "engine", {}, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("does not match partial words in whole-word mode", async () => {
    const results = await searchPdfDocument(
      fakeDocument(["engine engineering re-engine"]),
      "engine",
      { wholeWord: true },
      new AbortController().signal,
    );
    expect(results).toHaveLength(2);
  });

  it("escapes text before adding search highlights", () => {
    const html = highlightPdfText("<engine & frame>", "engine", {}, true);
    expect(html).toContain("&lt;");
    expect(html).toContain("&amp;");
    expect(html).toContain("pdf-engine-search-mark is-active");
    expect(html).not.toContain("<engine");
  });

  it("maps browser-standard keyboard commands without intercepting ordinary keys", () => {
    const base = { metaKey: false, altKey: false, shiftKey: false, target: null };
    expect(pdfReaderShortcut({ ...base, ctrlKey: true, key: "f" })).toBe("SEARCH");
    expect(pdfReaderShortcut({ ...base, ctrlKey: true, key: "+" })).toBe("ZOOM_IN");
    expect(pdfReaderShortcut({ ...base, ctrlKey: true, key: "-" })).toBe("ZOOM_OUT");
    expect(pdfReaderShortcut({ ...base, ctrlKey: true, key: "0" })).toBe("RESET_ZOOM");
    expect(pdfReaderShortcut({ ...base, ctrlKey: false, key: "PageDown" })).toBe("NEXT_PAGE");
    expect(pdfReaderShortcut({ ...base, ctrlKey: false, key: "x" })).toBeNull();
  });

  it("partitions local drafts by user, tenant, document, and revision", () => {
    const first = pdfWorkingCopyKey({ userId: "user-1", tenant: "KQ", manualId: "manual-1", revisionId: "rev-1" });
    const otherUser = pdfWorkingCopyKey({ userId: "user-2", tenant: "KQ", manualId: "manual-1", revisionId: "rev-1" });
    const otherTenant = pdfWorkingCopyKey({ userId: "user-1", tenant: "Jambo", manualId: "manual-1", revisionId: "rev-1" });
    const otherRevision = pdfWorkingCopyKey({ userId: "user-1", tenant: "KQ", manualId: "manual-1", revisionId: "rev-2" });

    expect(new Set([first, otherUser, otherTenant, otherRevision]).size).toBe(4);
    expect(first).toContain("pdf-working-copy:v1");
  });

  it("labels editable and flattened outputs distinctly", () => {
    expect(outputPdfFilename("QAM-51.pdf", "WORKING_COPY")).toBe("QAM-51_WORKING_COPY.pdf");
    expect(outputPdfFilename("QAM-51.pdf", "FLATTENED")).toBe("QAM-51_FLATTENED.pdf");
  });
});

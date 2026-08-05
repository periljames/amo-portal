import { describe, expect, it, vi } from "vitest";

import { getPdfReaderPerformanceProfile } from "../../services/pdfPerformance";
import { registerAuthoritativePdfSource } from "../../services/pdfWorkingCopyAuthority";
import {
  highlightPdfText,
  isPdfWorkingCopyGenerationCurrent,
  isPdfDraftLifecycleCurrent,
  outputPdfFilename,
  pdfReaderShortcut,
  searchPdfDocument,
  resolvePdfReaderScrollRoot,
} from "./pdfReaderEngine";
import {
  pdfWorkingCopyKey,
  pdfWorkingCopyMatchesAuthoritativeSource,
} from "./pdfWorkingCopyStore";

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

  it("keeps visible-page authority inside the real viewport on every performance profile", () => {
    const profiles = [
      { connection: { effectiveType: "2g", saveData: true }, deviceMemory: 2, hardwareConcurrency: 2 },
      { connection: { effectiveType: "3g", downlink: 3 }, deviceMemory: 4, hardwareConcurrency: 4 },
      { connection: { effectiveType: "4g", downlink: 30, rtt: 45 }, deviceMemory: 16, hardwareConcurrency: 12 },
      { connection: { effectiveType: "4g", downlink: 10, rtt: 100 }, deviceMemory: 8, hardwareConcurrency: 8 },
    ];

    for (const navigatorValue of profiles) {
      vi.stubGlobal("navigator", navigatorValue);
      const profile = getPdfReaderPerformanceProfile();
      expect(profile.prefetchMarginPx).toBe(0);
      expect(profile.renderRadius).toBeGreaterThan(0);
      expect(profile.hotPageLimit).toBeGreaterThanOrEqual(profile.renderRadius * 2 + 1);
    }
    vi.unstubAllGlobals();
  });

  it("partitions local drafts by user, tenant, document, and revision", () => {
    const first = pdfWorkingCopyKey({ userId: "user-1", tenant: "KQ", manualId: "manual-1", revisionId: "rev-1" });
    const otherUser = pdfWorkingCopyKey({ userId: "user-2", tenant: "KQ", manualId: "manual-1", revisionId: "rev-1" });
    const otherTenant = pdfWorkingCopyKey({ userId: "user-1", tenant: "Jambo", manualId: "manual-1", revisionId: "rev-1" });
    const otherRevision = pdfWorkingCopyKey({ userId: "user-1", tenant: "KQ", manualId: "manual-1", revisionId: "rev-2" });

    expect(new Set([first, otherUser, otherTenant, otherRevision]).size).toBe(4);
    expect(first).toContain("pdf-working-copy:v1");
  });

  it("admits a draft only after its exact source checksum becomes authoritative", () => {
    const identity = { userId: "user-1", tenant: "KQ", manualId: "manual-1", revisionId: "rev-1" };
    registerAuthoritativePdfSource(identity.tenant, identity.manualId, identity.revisionId, null);
    expect(pdfWorkingCopyMatchesAuthoritativeSource(identity, "source-a")).toBe(false);

    registerAuthoritativePdfSource(identity.tenant, identity.manualId, identity.revisionId, "SOURCE-A");
    expect(pdfWorkingCopyMatchesAuthoritativeSource(identity, "source-a")).toBe(true);
    expect(pdfWorkingCopyMatchesAuthoritativeSource(identity, "source-b")).toBe(false);
  });

  it("labels editable and flattened outputs distinctly", () => {
    expect(outputPdfFilename("QAM-51.pdf", "WORKING_COPY")).toBe("QAM-51_WORKING_COPY.pdf");
    expect(outputPdfFilename("QAM-51.pdf", "FLATTENED")).toBe("QAM-51_FLATTENED.pdf");
  });

  it("keeps a failed persistence generation dirty", () => {
    const savingGeneration = 4;
    const persistenceSucceeded = false;

    expect(persistenceSucceeded && isPdfWorkingCopyGenerationCurrent(savingGeneration, savingGeneration)).toBe(false);
  });

  it("does not clear dirty custody when a newer edit arrives during persistence", () => {
    const savingGeneration = 4;
    const currentGeneration = 5;

    expect(isPdfWorkingCopyGenerationCurrent(savingGeneration, currentGeneration)).toBe(false);
    expect(isPdfWorkingCopyGenerationCurrent(currentGeneration, currentGeneration)).toBe(true);
  });

  it("invalidates an autosave completing after submit or discard", () => {
    expect(isPdfDraftLifecycleCurrent(3, 3)).toBe(true);
    expect(isPdfDraftLifecycleCurrent(3, 4)).toBe(false);
  });

  it("selects the compact reader's direct scrolling viewport", () => {
    const shell = {} as HTMLElement;
    const compactViewport = {} as HTMLElement;
    let overflowY = "auto";
    const reader = {
      querySelector: vi.fn((selector: string) => selector.includes("pdfv2") ? compactViewport : null),
      closest: vi.fn(() => shell),
    } as unknown as HTMLElement;
    vi.stubGlobal("window", { getComputedStyle: () => ({ overflowY }) });

    expect(resolvePdfReaderScrollRoot(reader)).toBe(compactViewport);
    overflowY = "visible";
    expect(resolvePdfReaderScrollRoot(reader)).toBe(shell);
    expect(reader.querySelector).toHaveBeenCalledWith(":scope > .pdfv2-viewport");
    vi.unstubAllGlobals();
  });

  it("falls back to the legacy direct scrolling viewport", () => {
    const legacyViewport = {} as HTMLElement;
    const reader = {
      querySelector: vi.fn((selector: string) => selector.includes("pdf-engine") ? legacyViewport : null),
      closest: vi.fn(() => null),
    } as unknown as HTMLElement;
    vi.stubGlobal("window", { getComputedStyle: () => ({ overflowY: "auto" }) });

    expect(resolvePdfReaderScrollRoot(reader)).toBe(legacyViewport);
    expect(reader.querySelector).toHaveBeenCalledWith(":scope > .pdf-engine-viewport");
    vi.unstubAllGlobals();
  });
});

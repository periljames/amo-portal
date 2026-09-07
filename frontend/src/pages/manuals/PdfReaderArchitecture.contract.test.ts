import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const bridge = readFileSync(new URL("./PdfReaderCore.tsx", import.meta.url), "utf-8");
const reader = readFileSync(new URL("./PdfReaderCoreV4.tsx", import.meta.url), "utf-8");
const sourceCache = readFileSync(new URL("./pdfSourceCache.ts", import.meta.url), "utf-8");
const publications = readFileSync(new URL("../../services/publications.ts", import.meta.url), "utf-8");
const publicationPage = readFileSync(new URL("./PublicationsReaderPage.tsx", import.meta.url), "utf-8");
const navigator = readFileSync(new URL("./PdfReaderCoreV5.tsx", import.meta.url), "utf-8");
const layoutViewer = readFileSync(new URL("./PublicationPdfLayoutViewer.tsx", import.meta.url), "utf-8");
const navigatorStyles = readFileSync(new URL("./pdfReaderNavigatorV5.css", import.meta.url), "utf-8");
const serviceWorker = readFileSync(new URL("../../../public/portal-sw.js", import.meta.url), "utf-8");
const legacyV2 = readFileSync(new URL("./PdfReaderCoreV2.tsx", import.meta.url), "utf-8");
const legacyV3 = readFileSync(new URL("./PdfReaderCoreV3.tsx", import.meta.url), "utf-8");

describe("controlled PDF reader architecture", () => {
  it("measures the real viewport before rendering pages and sizes mixed pages independently", () => {
    expect(reader).toContain("useLayoutEffect");
    expect(reader).toContain("useState({ width: 0, height: 0 })");
    expect(reader).not.toContain("width: 960, height: 720");
    expect(reader).toContain("entry?.contentRect.width || viewport.clientWidth");
    expect(reader).toContain("viewportReady ? orderedVirtualItems.map");
    expect(reader).toContain("pageWidthFor(page)");
    expect(reader).toContain('"--pdfv3-page-ratio": String(ratio)');
    expect(layoutViewer).toContain("window.visualViewport");
    expect(layoutViewer).toContain('root.getBoundingClientRect().top');
    expect(layoutViewer).toContain('root.style.setProperty("--publication-reader-available-height"');
    expect(navigatorStyles).toContain("height: var(--publication-reader-available-height");
    expect(navigatorStyles).not.toContain("100dvh - var(--tenant-topbar-height");
  });

  it("keeps the hot render window bounded by the selected performance profile", () => {
    expect(reader).toContain("profile.renderRadius");
    expect(reader).toContain("profile.hotPageLimit");
    expect(reader).toContain("profile.maxCanvasPixels");
    expect(reader).not.toContain("...current.map((index) => index + 1)");
  });

  it("never starts a competing whole-document cache download automatically", () => {
    expect(bridge).not.toContain("warmPdfSourceCache");
    expect(bridge).not.toContain("Promise.race");
    expect(bridge).toContain("savePdfSourceOffline");
    expect(bridge).toContain("readLatestCachedPdfSource");
    expect(bridge).toContain("offline-recovery");
    expect(bridge).toContain("network-recovery");
    expect(reader).toContain("onSourceLoadError?.(error)");
    expect(bridge).toContain("resolved.reader_source_sha256 || resolved.source_sha256");
    expect(bridge).toContain("navigator.onLine === false");
  });

  it("retains exact controlled bytes only in authenticated encrypted chunks", () => {
    expect(sourceCache).toContain('DB_NAME = "amo-controlled-pdf-offline"');
    expect(sourceCache).toContain('name: "AES-GCM"');
    expect(sourceCache).toContain('crypto.subtle.digest("SHA-256"');
    expect(sourceCache).toContain("sourceSha256.toLowerCase()");
    expect(sourceCache).toContain("CHUNK_BYTES");
    expect(sourceCache).toContain('createIndex("byIdentity"');
    expect(sourceCache).toContain("navigator.storage.persist()");
    expect(sourceCache).toContain("removeLegacyPlaintextCache");
    expect(serviceWorker).toContain("Controlled document responses remain network-only in this worker");
    expect(serviceWorker).toContain('VERSION = "v7"');
    expect(publications).toContain("readPersistedPublicationBootstrap");
    expect(publications).toContain("writeApiCache(key, payload, READER_CACHE_MAX_AGE_MS)");
    expect(publications).not.toContain("window.localStorage.setItem(readerCacheKey");
    expect(publicationPage).toContain("navigator.onLine !== false");
    expect(publicationPage).toContain("has not been saved for offline use on this device");
    expect(navigator).toContain("readPersistedPublicationBootstrap");
    expect(navigator).toContain("navigator.onLine !== false");
  });

  it("routes legacy reader imports to the single active renderer", () => {
    expect(legacyV2).toContain('from "./PdfReaderCoreV4"');
    expect(legacyV3).toContain('from "./PdfReaderCoreV4"');
    expect(legacyV2.split("\n").length).toBeLessThan(20);
    expect(legacyV3.split("\n").length).toBeLessThan(20);
  });
});

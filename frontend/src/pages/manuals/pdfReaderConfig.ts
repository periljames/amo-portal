import { getPdfReaderPerformanceProfile, pdfDevicePixelRatio } from "../../services/pdfPerformance";

declare const __PDFJS_ASSET_VERSION__: string;

const applicationBase = String(import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
const pdfJsAssetRoot = `${applicationBase}pdfjs/${encodeURIComponent(__PDFJS_ASSET_VERSION__)}/`;

/**
 * React-PDF compares the options object by identity. Keep one immutable object
 * for the lifetime of the application so reader state changes never recreate
 * the PDFDocumentLoadingTask.
 *
 * PDF.js 5 requires its decoder/font resources to be published separately.
 * The Vite build copies the exact installed pdfjs-dist resources under the
 * versioned same-origin path used below. This prevents the broken
 * `nullopenjpeg_nowasm_fallback.js` import and supports JPX/JPEG 2000 scans,
 * packed CMaps and standard PDF fonts without weakening script controls.
 */
export const PDF_DOCUMENT_OPTIONS = Object.freeze({
  isEvalSupported: false,
  enableScripting: false,
  enableXfa: false,
  useWasm: true,
  wasmUrl: `${pdfJsAssetRoot}wasm/`,
  cMapUrl: `${pdfJsAssetRoot}cmaps/`,
  cMapPacked: true,
  standardFontDataUrl: `${pdfJsAssetRoot}standard_fonts/`,
});

export { getPdfReaderPerformanceProfile, pdfDevicePixelRatio };

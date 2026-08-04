/**
 * React-PDF compares the options object by identity. Keep one immutable object
 * for the lifetime of the application so reader state updates never recreate
 * the underlying PDFDocumentLoadingTask.
 *
 * PDF.js 5 prefers WebAssembly for JPEG 2000 (JPX) decoding. The portal does
 * not publish PDF.js decoder binaries or relax its content-security policy for
 * runtime WASM compilation, so the default path leaves JPX image XObjects blank.
 * PDF.js includes a JavaScript OpenJPEG fallback; selecting it explicitly keeps
 * controlled manuals complete without weakening the portal CSP. Bounded page
 * rendering limits the additional decode cost to the active page window.
 *
 * Scripting is disabled independently of rendering. AcroForm widgets remain
 * interactive, while field JavaScript is removed from the server-side reader
 * derivative and cannot execute in PDF.js.
 */
export const PDF_DOCUMENT_OPTIONS = Object.freeze({
  isEvalSupported: false,
  enableScripting: false,
  enableXfa: true,
  useWasm: false,
});

/**
 * Keep text and forms sharp without forcing every continuously rendered page
 * to allocate a full device-resolution canvas on high-DPI displays.
 */
export function pdfDevicePixelRatio(maximum = 1.4): number {
  if (typeof window === "undefined") return 1;
  return Math.min(window.devicePixelRatio || 1, maximum);
}

/**
 * React-PDF compares the options object by identity. Keep one immutable object
 * for the lifetime of the application so reader state updates never recreate
 * the underlying PDFDocumentLoadingTask.
 */
export const PDF_DOCUMENT_OPTIONS = Object.freeze({
  isEvalSupported: false,
  enableXfa: true,
});

/**
 * Keep text and forms sharp without forcing every continuously rendered page
 * to allocate a full device-resolution canvas on high-DPI displays.
 */
export function pdfDevicePixelRatio(maximum = 1.4): number {
  if (typeof window === "undefined") return 1;
  return Math.min(window.devicePixelRatio || 1, maximum);
}

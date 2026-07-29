import type { DocumentInitParameters } from "pdfjs-dist/types/src/display/api";

/**
 * React-PDF compares the options object by identity. Keep one immutable object
 * for the lifetime of the application so reader state updates never cause the
 * underlying PDFDocumentLoadingTask to be destroyed and recreated.
 */
export const PDF_DOCUMENT_OPTIONS: Readonly<DocumentInitParameters> = Object.freeze({
  isEvalSupported: false,
  enableXfa: true,
});

export function pdfDevicePixelRatio(maximum = 1.6): number {
  if (typeof window === "undefined") return 1;
  return Math.min(window.devicePixelRatio || 1, maximum);
}

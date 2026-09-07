/**
 * Compatibility entry point. The portal has one PDF rendering authority;
 * legacy imports are deliberately routed to the active engine.
 */
export { default } from "./PdfReaderCoreV4";
export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOfflineControl,
  PdfReaderOutlineItem,
} from "./PdfReaderCoreV4";

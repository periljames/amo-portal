import PdfReaderCoreV4 from "./PdfReaderCoreV4";

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOfflineControl,
  PdfReaderOutlineItem,
} from "./PdfReaderCoreV4";

/**
 * Compatibility bridge retained for older imports and source contracts.
 * PDF loading/rendering is owned by the V4 engine; this layer adds no viewer.
 */
export default PdfReaderCoreV4;

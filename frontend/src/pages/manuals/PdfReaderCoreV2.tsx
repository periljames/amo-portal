import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type FC,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { useVirtualizer, type VirtualItem } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FilePenLine,
  LoaderCircle,
  Minus,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import type { DocumentationRecord } from "../../services/documentation";
import {
  flattenPdfWorkingCopy,
  getPdfReaderCapabilities,
  submitPdfWorkingCopy,
  type PdfReaderCapabilities,
} from "../../services/pdfReader";
import { downloadBlob, fetchPublicationBlob, publicationPdfSource } from "../../services/publications";
import { PDF_DOCUMENT_OPTIONS, getPdfReaderPerformanceProfile, pdfDevicePixelRatio } from "./pdfReaderConfig";
import {
  clampPdfValue,
  copyPdfBytes,
  highlightPdfText,
  isPdfDraftLifecycleCurrent,
  isPdfWorkingCopyGenerationCurrent,
  outputPdfFilename,
  safePdfFilename,
  searchPdfDocument,
  type PdfSearchOptions,
  type PdfSearchResult,
} from "./pdfReaderEngine";
import {
  prioritizePdfRenderIndexes,
  selectPdfVirtualPage,
  updatePdfRetainedPages,
} from "./pdfReaderVirtualization";
import {
  deletePdfWorkingCopy,
  readPdfWorkingCopy,
  savePdfWorkingCopy,
  type PdfWorkingCopyIdentity,
  type StoredPdfWorkingCopy,
} from "./pdfWorkingCopyStore";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./pdfReaderEngineV2.css";
import "./pdfReaderVirtualized.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfDocument = Document as unknown as FC<any>;
const PdfPage = Page as unknown as FC<any>;
const PAGE_GAP = 20;
const NAVIGATION_TIMEOUT_MS = 8000;
const DEFAULT_PAGE_RATIO = 1.414;

type PdfDocumentHandle = {
  numPages: number;
  getOutline?: () => Promise<any[] | null>;
  getDestination?: (name: string) => Promise<any[] | null>;
  getPageIndex?: (value: unknown) => Promise<number>;
  getFieldObjects?: () => Promise<Record<string, Array<Record<string, unknown>>> | null>;
  hasJSActions?: () => Promise<boolean>;
  saveDocument?: () => Promise<Uint8Array>;
  annotationStorage?: { onSetModified?: () => void; onResetModified?: () => void };
};

type PdfItemClickTarget = {
  dest?: string | unknown[] | null;
  pageIndex?: number | null;
  pageNumber?: number | null;
};

type VirtualPdfPageProps = {
  pageNumber: number;
  width: number;
  item: VirtualItem;
  documentKey: string;
  safeForm: boolean;
  devicePixelRatio: number;
  uncontrolled: boolean;
  current: boolean;
  query: string;
  searchOptions: PdfSearchOptions;
  activeSearchResult?: PdfSearchResult;
  renderPageOverlay?: (pageNumber: number) => ReactNode;
  onElement: (page: number, element: HTMLDivElement | null) => void;
  onMeasure: (element: Element | null) => void;
  onRatio: (page: number, ratio: number) => void;
  onReady: (page: number) => void;
  onFailure: (page: number, message: string) => void;
  onAnnotations: (page: number, annotations: any[]) => void;
  onTextReady: (page: number) => void;
};

export type PdfReaderOutlineItem = { id: string; title: string; page: number; level: number };
export type PdfReaderNavigationRequest = { page: number; token: number };
export type PdfReaderCoreProps = {
  fileUrl: string;
  originalDownloadUrl?: string;
  title: string;
  filename?: string | null;
  identity: PdfWorkingCopyIdentity;
  uncontrolled?: boolean;
  initialPage?: number;
  initialZoom?: number;
  navigationRequest?: PdfReaderNavigationRequest | null;
  capabilities?: PdfReaderCapabilities | null;
  compact?: boolean;
  renderPageOverlay?: (pageNumber: number) => ReactNode;
  onPageChange?: (pageNumber: number) => void;
  onZoomChange?: (zoomPercent: number) => void;
  onAcroFormDetected?: (hasAcroForm: boolean) => void;
  onOutlineReady?: (items: PdfReaderOutlineItem[]) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onSubmitWorkingCopy?: (file: File) => Promise<DocumentationRecord>;
  onRecordCreated?: (record: DocumentationRecord) => void;
};

const READ_ONLY: PdfReaderCapabilities = {
  renderer: "PDF.js",
  processor: "PDFium",
  processor_version: "checking",
  source_sha256: "",
  page_count: 0,
  has_acroform: false,
  has_javascript: false,
  is_dynamic_xfa: false,
  encrypted: false,
  unsupported_reason: null,
  can_fill: false,
  can_save_draft: false,
  can_download_original: true,
  can_download_working: false,
  can_flatten: false,
  can_submit: false,
};

const uniquePages = (values: Iterable<number>) => [...new Set(values)]
  .filter((value) => Number.isInteger(value) && value > 0)
  .sort((left, right) => left - right);

async function outlineItems(pdf: PdfDocumentHandle): Promise<PdfReaderOutlineItem[]> {
  const source = await pdf.getOutline?.().catch(() => null);
  if (!Array.isArray(source)) return [];
  const rows: PdfReaderOutlineItem[] = [];
  const visit = async (items: any[], level: number, prefix: string) => {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      let destination = item?.dest;
      if (typeof destination === "string") destination = await pdf.getDestination?.(destination).catch(() => null);
      const reference = Array.isArray(destination) ? destination[0] : null;
      let page = typeof reference === "number" ? reference + 1 : 0;
      if (!page && reference && pdf.getPageIndex) page = (await pdf.getPageIndex(reference).catch(() => -1)) + 1;
      const id = `${prefix}-${index}`;
      if (page > 0) rows.push({ id, title: String(item?.title || `Page ${page}`), page, level });
      if (item?.items?.length) await visit(item.items, level + 1, id);
    }
  };
  await visit(source, 1, "outline");
  return rows.sort((left, right) => left.page - right.page || left.level - right.level);
}

function detectedFormPages(fields: Record<string, Array<Record<string, unknown>>> | null, pageCount: number): number[] {
  const pages = new Set<number>();
  Object.values(fields || {}).flat().forEach((field) => {
    const raw = Number(field.page ?? field.pageIndex ?? field.page_number);
    if (!Number.isFinite(raw)) return;
    const page = raw >= 0 && raw < pageCount ? raw + 1 : raw;
    if (page >= 1 && page <= pageCount) pages.add(page);
  });
  return uniquePages(pages);
}

function VirtualPdfPage({
  pageNumber,
  width,
  item,
  documentKey,
  safeForm,
  devicePixelRatio,
  uncontrolled,
  current,
  query,
  searchOptions,
  activeSearchResult,
  renderPageOverlay,
  onElement,
  onMeasure,
  onRatio,
  onReady,
  onFailure,
  onAnnotations,
  onTextReady,
}: VirtualPdfPageProps) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    setReady(false);
    setFailed("");
  }, [documentKey, pageNumber, width]);

  const style = {
    transform: `translateY(${item.start}px)`,
    width: `${width}px`,
    minHeight: `${Math.max(1, item.size - PAGE_GAP)}px`,
  } as CSSProperties;

  return <div
    ref={(element) => {
      onElement(pageNumber, element);
      onMeasure(element);
    }}
    className={`pdfv2-virtual-item${current ? " is-current" : ""}`}
    data-index={item.index}
    data-page-number={pageNumber}
    style={style}
    aria-label={`Page ${pageNumber}`}
  >
    <div className={`pdfv2-page pdfv2-page-shell${ready ? " is-ready" : " is-rendering"}${current ? " is-current" : ""}`}>
      {uncontrolled ? <span className="pdfv2-watermark">UNCONTROLLED DRAFT</span> : null}
      <PdfPage
        pageNumber={pageNumber}
        width={width}
        renderMode="canvas"
        renderTextLayer
        renderAnnotationLayer
        renderForms={safeForm}
        devicePixelRatio={devicePixelRatio}
        customTextRenderer={({ str }: { str: string }) => highlightPdfText(str, query, searchOptions, false)}
        loading={null}
        error={null}
        onGetAnnotationsSuccess={(annotations: any[]) => onAnnotations(pageNumber, annotations)}
        onLoadSuccess={(loaded: any) => {
          const originalWidth = Number(loaded?.originalWidth || loaded?.view?.[2] || 1);
          const originalHeight = Number(loaded?.originalHeight || loaded?.view?.[3] || originalWidth * DEFAULT_PAGE_RATIO);
          onRatio(pageNumber, originalHeight / originalWidth);
        }}
        onRenderSuccess={() => {
          setReady(true);
          setFailed("");
          onReady(pageNumber);
        }}
        onRenderError={(error: unknown) => {
          const message = error instanceof Error ? error.message : `Page ${pageNumber} could not be rendered`;
          setFailed(message);
          onFailure(pageNumber, message);
        }}
        onRenderTextLayerSuccess={() => onTextReady(pageNumber)}
      />
      {!ready ? <div className={`pdfv2-render-cover${failed ? " is-error" : ""}`} role={failed ? "alert" : "status"}>
        {failed ? <><AlertTriangle size={17} />{failed}</> : <><LoaderCircle className="is-spinning" size={17} />Rendering page {pageNumber}…</>}
      </div> : null}
      {activeSearchResult?.page === pageNumber ? <span className="sr-only">Current search result on page {pageNumber}</span> : null}
      {renderPageOverlay?.(pageNumber)}
    </div>
  </div>;
}

export default function PdfReaderCoreV2(props: PdfReaderCoreProps) {
  const {
    fileUrl,
    originalDownloadUrl,
    title,
    filename,
    identity,
    uncontrolled = false,
    initialPage = 1,
    initialZoom = 100,
    navigationRequest,
    capabilities: suppliedCapabilities,
    compact = false,
    renderPageOverlay,
    onPageChange,
    onZoomChange,
    onAcroFormDetected,
    onOutlineReady,
    onDirtyChange,
    onSubmitWorkingCopy,
    onRecordCreated,
  } = props;

  const hostRef = useRef<HTMLElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const pdfRef = useRef<PdfDocumentHandle | null>(null);
  const serializing = useRef<Promise<Uint8Array> | null>(null);
  const autosaveTimer = useRef<number | null>(null);
  const autosaveInFlightRef = useRef<Promise<void> | null>(null);
  const autosaveQueuedRef = useRef(false);
  const editGenerationRef = useRef(0);
  const lifecycleGenerationRef = useRef(0);
  const persistDraftRef = useRef<() => Promise<void>>(async () => undefined);
  const editedRef = useRef(new Set<number>());
  const dirtyRef = useRef(false);
  const currentPageRef = useRef(Math.max(1, initialPage));
  const retainedOrderRef = useRef<number[]>([]);
  const readyPagesRef = useRef(new Set<number>());
  const navigationTargetRef = useRef<number | null>(null);
  const navigationTimerRef = useRef<number | null>(null);
  const initialPositionedRef = useRef(false);
  const searchInput = useRef<HTMLInputElement | null>(null);
  const searchController = useRef<AbortController | null>(null);
  const scrollFrameRef = useRef(0);

  const [capabilities, setCapabilities] = useState<PdfReaderCapabilities>(suppliedCapabilities || READ_ONLY);
  const [capabilityError, setCapabilityError] = useState("");
  const [draft, setDraft] = useState<StoredPdfWorkingCopy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [pageInput, setPageInput] = useState(String(Math.max(1, initialPage)));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [retainedPages, setRetainedPages] = useState<number[]>([]);
  const [hostSize, setHostSize] = useState({ width: 960, height: 720 });
  const [zoom, setZoom] = useState(clampPdfValue(initialZoom, 50, 250));
  const [fitMode, setFitMode] = useState<"WIDTH" | "PAGE" | "CUSTOM">("WIDTH");
  const [fieldCount, setFieldCount] = useState(0);
  const [formPages, setFormPages] = useState<number[]>([]);
  const [editedPages, setEditedPages] = useState<number[]>([]);
  const [dirty, setDirty] = useState(false);
  const [draftState, setDraftState] = useState<"" | "SAVING" | "SAVED" | "ERROR">("");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState<"" | "ORIGINAL" | "WORKING" | "FLATTEN" | "SUBMIT">("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOptions, setSearchOptions] = useState<PdfSearchOptions>({ caseSensitive: false, wholeWord: false });
  const [searchResults, setSearchResults] = useState<PdfSearchResult[]>([]);
  const [searchIndex, setSearchIndex] = useState(-1);
  const [searchBusy, setSearchBusy] = useState(false);
  const [navigationPending, setNavigationPending] = useState<number | null>(null);

  const performanceProfile = useMemo(() => getPdfReaderPerformanceProfile(), []);
  const source = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const readerFile = useMemo(() => draft ? { data: new Uint8Array(draft.bytes.slice(0)) } : source, [draft, source]);
  const documentKey = useMemo(
    () => `${identity.tenant}:${identity.manualId}:${identity.revisionId}:${fileUrl}:${draft?.savedAt || "source"}`,
    [draft?.savedAt, fileUrl, identity.manualId, identity.revisionId, identity.tenant],
  );
  const outputName = safePdfFilename(filename || "", `${title}.pdf`);
  const formDetected = Boolean(capabilities.has_acroform || fieldCount > 0);
  const safeForm = Boolean(
    capabilities.can_fill
    && formDetected
    && !capabilities.has_javascript
    && !capabilities.is_dynamic_xfa
    && !capabilities.encrypted,
  );
  const availableWidth = Math.max(260, Math.min(1800, hostSize.width - (compact ? 16 : 34)));
  const ratio = pageRatios[currentPage] || DEFAULT_PAGE_RATIO;
  const pageWidth = Math.round(
    fitMode === "PAGE"
      ? Math.max(230, Math.min(availableWidth, Math.max(320, hostSize.height - 34) / ratio))
      : fitMode === "CUSTOM"
        ? availableWidth * (zoom / 100)
        : availableWidth,
  );

  const virtualizer = useVirtualizer({
    count: pageCount,
    getScrollElement: () => viewportRef.current,
    estimateSize: (index) => Math.round(pageWidth * (pageRatios[index + 1] || DEFAULT_PAGE_RATIO) + PAGE_GAP),
    overscan: performanceProfile.renderRadius,
    getItemKey: (index) => index + 1,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const renderIndexes = prioritizePdfRenderIndexes(
    virtualItems.map((item) => item.index),
    retainedPages,
    navigationPending,
    currentPage,
    pageCount,
    performanceProfile.hotPageLimit,
  );
  const measurements = virtualizer.getMeasurements();
  const renderItems = renderIndexes
    .map((index) => measurements[index])
    .filter((item): item is VirtualItem => Boolean(item));

  const setDirtyState = useCallback((value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
    onDirtyChange?.(value);
  }, [onDirtyChange]);

  const setEdited = useCallback((values: Iterable<number>) => {
    const pages = uniquePages(values);
    editedRef.current = new Set(pages);
    setEditedPages(pages);
  }, []);

  const clearAutosaveTimer = useCallback(() => {
    if (autosaveTimer.current !== null) {
      window.clearTimeout(autosaveTimer.current);
      autosaveTimer.current = null;
    }
  }, []);

  const clearNavigationTimer = useCallback(() => {
    if (navigationTimerRef.current !== null) {
      window.clearTimeout(navigationTimerRef.current);
      navigationTimerRef.current = null;
    }
  }, []);

  const invalidateDraftLifecycle = useCallback(() => {
    lifecycleGenerationRef.current += 1;
    autosaveQueuedRef.current = false;
    clearAutosaveTimer();
  }, [clearAutosaveTimer]);

  const publishPhysicalPage = useCallback((page: number) => {
    const normalized = clampPdfValue(page, 1, Math.max(1, pageCount));
    if (normalized === currentPageRef.current) return;
    currentPageRef.current = normalized;
    setCurrentPage(normalized);
    setPageInput(String(normalized));
    onPageChange?.(normalized);
  }, [onPageChange, pageCount]);

  const synchronizePhysicalPage = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !pageCount) return;
    const page = selectPdfVirtualPage(
      virtualizer.getVirtualItems(),
      viewport.scrollTop,
      viewport.clientHeight,
      24,
    );
    if (!page) return;
    publishPhysicalPage(page);
    const target = navigationTargetRef.current;
    if (target === page && readyPagesRef.current.has(page)) {
      navigationTargetRef.current = null;
      setNavigationPending(null);
      clearNavigationTimer();
    }
  }, [clearNavigationTimer, pageCount, publishPhysicalPage, virtualizer]);

  const requestPhysicalSync = useCallback(() => {
    if (scrollFrameRef.current) return;
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = 0;
      synchronizePhysicalPage();
    });
  }, [synchronizePhysicalPage]);

  const retainReadyPage = useCallback((page: number) => {
    readyPagesRef.current.add(page);
    retainedOrderRef.current = updatePdfRetainedPages(
      retainedOrderRef.current,
      page,
      performanceProfile.hotPageLimit,
    );
    const retained = retainedOrderRef.current.filter((value) => value >= 1 && value <= pageCount);
    setRetainedPages((current) => current.length === retained.length && current.every((value, index) => value === retained[index])
      ? current
      : retained);
  }, [pageCount, performanceProfile.hotPageLimit]);

  const jump = useCallback((requested: number, behavior: ScrollBehavior = "auto") => {
    if (!pageCount) return;
    const page = clampPdfValue(requested, 1, pageCount);
    navigationTargetRef.current = page;
    setNavigationPending(page);
    setActionError("");
    setPageInput(String(page));
    clearNavigationTimer();
    retainedOrderRef.current = updatePdfRetainedPages(
      retainedOrderRef.current,
      page,
      performanceProfile.hotPageLimit,
    );
    setRetainedPages(retainedOrderRef.current);

    virtualizer.scrollToIndex(page - 1, { align: "start", behavior });
    window.requestAnimationFrame(() => {
      virtualizer.measure();
      virtualizer.scrollToIndex(page - 1, { align: "start", behavior: "auto" });
      requestPhysicalSync();
    });

    navigationTimerRef.current = window.setTimeout(() => {
      if (navigationTargetRef.current !== page) return;
      navigationTargetRef.current = null;
      setNavigationPending(null);
      setActionError(`Page ${page} could not be positioned in the reader. Retry the navigation action.`);
    }, NAVIGATION_TIMEOUT_MS);
  }, [clearNavigationTimer, pageCount, performanceProfile.hotPageLimit, requestPhysicalSync, virtualizer]);

  const followPdfItem = useCallback(async (target: PdfItemClickTarget) => {
    try {
      let page = Number(target.pageNumber || 0);
      if (!page && target.pageIndex !== null && target.pageIndex !== undefined) {
        const pageIndex = Number(target.pageIndex);
        if (Number.isInteger(pageIndex) && pageIndex >= 0) page = pageIndex + 1;
      }
      let destination = target.dest;
      const pdf = pdfRef.current;
      if (!page && typeof destination === "string" && pdf?.getDestination) {
        destination = await pdf.getDestination(destination).catch(() => null);
      }
      if (!page && Array.isArray(destination)) {
        const reference = destination[0];
        if (typeof reference === "number") page = reference + 1;
        else if (reference && pdf?.getPageIndex) page = (await pdf.getPageIndex(reference).catch(() => -1)) + 1;
      }
      if (page > 0) {
        jump(page, "auto");
        return;
      }
      setActionError("The selected PDF link does not contain a resolvable page destination.");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The selected PDF link could not be opened.");
    }
  }, [jump]);

  useEffect(() => {
    if (suppliedCapabilities) {
      setCapabilities(suppliedCapabilities);
      setCapabilityError("");
      return;
    }
    let active = true;
    getPdfReaderCapabilities(identity.tenant, identity.manualId, identity.revisionId)
      .then((value) => {
        if (!active) return;
        setCapabilities(value);
        setCapabilityError("");
      })
      .catch((error) => {
        if (!active) return;
        setCapabilities(READ_ONLY);
        setCapabilityError(error instanceof Error ? error.message : "PDF processing is unavailable");
      });
    return () => { active = false; };
  }, [identity.manualId, identity.revisionId, identity.tenant, suppliedCapabilities]);

  useEffect(() => {
    onAcroFormDetected?.(formDetected);
  }, [formDetected, onAcroFormDetected]);

  useEffect(() => {
    lifecycleGenerationRef.current += 1;
    editGenerationRef.current = 0;
    autosaveQueuedRef.current = false;
    clearAutosaveTimer();
  }, [capabilities.source_sha256, clearAutosaveTimer, identity.manualId, identity.revisionId, identity.tenant]);

  useEffect(() => {
    if (!capabilities.source_sha256) return;
    let active = true;
    readPdfWorkingCopy(identity)
      .then((value) => {
        if (!active || !value) return;
        setDraft(value);
        setEdited(value.editedPages || []);
        setDirtyState(true);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [capabilities.source_sha256, identity.manualId, identity.revisionId, identity.tenant, identity.userId, setDirtyState, setEdited]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const update = () => {
      setHostSize({
        width: Math.max(300, viewport.clientWidth),
        height: Math.max(360, viewport.clientHeight),
      });
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(viewport);
    window.addEventListener("resize", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  useEffect(() => {
    virtualizer.measure();
    readyPagesRef.current.clear();
    retainedOrderRef.current = updatePdfRetainedPages([], currentPageRef.current, performanceProfile.hotPageLimit);
    setRetainedPages(retainedOrderRef.current);
    window.requestAnimationFrame(() => {
      virtualizer.scrollToIndex(Math.max(0, currentPageRef.current - 1), { align: "start", behavior: "auto" });
      requestPhysicalSync();
    });
  }, [pageWidth, performanceProfile.hotPageLimit, requestPhysicalSync, virtualizer]);

  useEffect(() => {
    onZoomChange?.(fitMode === "CUSTOM" ? zoom : Math.round(pageWidth / availableWidth * 100));
  }, [availableWidth, fitMode, onZoomChange, pageWidth, zoom]);

  useEffect(() => {
    if (!navigationRequest?.page || !pageCount) return;
    jump(navigationRequest.page);
  }, [jump, navigationRequest?.page, navigationRequest?.token, pageCount]);

  useEffect(() => {
    if (!pageCount || initialPositionedRef.current) return;
    initialPositionedRef.current = true;
    const restored = clampPdfValue(initialPage, 1, pageCount);
    window.requestAnimationFrame(() => jump(restored));
  }, [initialPage, jump, pageCount]);

  const serialize = useCallback(async () => {
    if (!pdfRef.current?.saveDocument) throw new Error("This PDF cannot be saved as a working copy");
    if (!serializing.current) {
      serializing.current = pdfRef.current.saveDocument().finally(() => { serializing.current = null; });
    }
    return serializing.current;
  }, []);

  const persistDraft = useCallback(async () => {
    if (!capabilities.can_save_draft || !dirtyRef.current) return;
    if (autosaveInFlightRef.current) {
      autosaveQueuedRef.current = true;
      await autosaveInFlightRef.current;
      return;
    }

    const savingGeneration = editGenerationRef.current;
    const savingLifecycle = lifecycleGenerationRef.current;
    const savingPages = [...editedRef.current];
    setDraftState("SAVING");

    const saveTask = (async () => {
      try {
        const bytes = await serialize();
        if (!isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)) return;
        await savePdfWorkingCopy(
          identity,
          outputPdfFilename(outputName, "WORKING_COPY"),
          copyPdfBytes(bytes),
          capabilities.source_sha256,
          savingPages,
        );
        if (!isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)) {
          await deletePdfWorkingCopy(identity).catch(() => undefined);
          return;
        }
        if (isPdfWorkingCopyGenerationCurrent(savingGeneration, editGenerationRef.current)) {
          setDirtyState(false);
          setDraftState("SAVED");
        } else {
          setDirtyState(true);
          setDraftState("");
          autosaveQueuedRef.current = true;
        }
      } catch {
        if (isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)) setDraftState("ERROR");
      } finally {
        autosaveInFlightRef.current = null;
        const shouldFollowUp = autosaveQueuedRef.current
          && isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)
          && dirtyRef.current;
        autosaveQueuedRef.current = false;
        if (shouldFollowUp) window.setTimeout(() => void persistDraftRef.current(), 0);
      }
    })();

    autosaveInFlightRef.current = saveTask;
    await saveTask;
  }, [capabilities.can_save_draft, capabilities.source_sha256, identity, outputName, serialize, setDirtyState]);

  useEffect(() => {
    persistDraftRef.current = persistDraft;
  }, [persistDraft]);

  const markEdited = useCallback((page: number) => {
    editGenerationRef.current += 1;
    setEdited(new Set([...editedRef.current, Math.max(1, page)]));
    setDirtyState(true);
    setDraftState("");
    clearAutosaveTimer();
    if (capabilities.can_save_draft) {
      autosaveTimer.current = window.setTimeout(() => {
        autosaveTimer.current = null;
        void persistDraftRef.current();
      }, 800);
    }
  }, [capabilities.can_save_draft, clearAutosaveTimer, setDirtyState, setEdited]);

  useEffect(() => {
    const warnOnUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnOnUnload);
    return () => window.removeEventListener("beforeunload", warnOnUnload);
  }, []);

  useEffect(() => () => {
    invalidateDraftLifecycle();
    clearNavigationTimer();
    searchController.current?.abort();
    if (scrollFrameRef.current) window.cancelAnimationFrame(scrollFrameRef.current);
  }, [clearNavigationTimer, invalidateDraftLifecycle]);

  const loadDocument = useCallback((pdf: PdfDocumentHandle) => {
    pdfRef.current = pdf;
    const count = Math.max(1, Number(pdf.numPages || 1));
    const restored = clampPdfValue(initialPage, 1, count);
    initialPositionedRef.current = false;
    currentPageRef.current = restored;
    setPageCount(count);
    setCurrentPage(restored);
    setPageInput(String(restored));
    setPageRatios({});
    setRetainedPages([restored]);
    retainedOrderRef.current = [restored];
    readyPagesRef.current.clear();
    setLoadError("");
    if (pdf.annotationStorage) pdf.annotationStorage.onSetModified = () => markEdited(currentPageRef.current);

    Promise.all([
      pdf.getFieldObjects?.().catch(() => null) || null,
      pdf.hasJSActions?.().catch(() => false) || false,
      outlineItems(pdf),
    ]).then(([fields, scripts, outline]) => {
      const countFields = Object.values(fields || {}).flat().length;
      const pages = detectedFormPages(fields, count);
      setFieldCount(countFields);
      setFormPages(pages);
      onAcroFormDetected?.(Boolean(capabilities.has_acroform || countFields > 0));
      onOutlineReady?.(outline);
      if (scripts && (capabilities.has_acroform || countFields)) {
        setActionError("Scripted PDF actions are disabled; the standard form fields remain available.");
      }
    }).catch(() => undefined);
  }, [capabilities.has_acroform, initialPage, markEdited, onAcroFormDetected, onOutlineReady]);

  const onPageRatio = useCallback((page: number, nextRatio: number) => {
    if (!Number.isFinite(nextRatio) || nextRatio <= 0) return;
    setPageRatios((current) => Math.abs((current[page] || 0) - nextRatio) < 0.0001
      ? current
      : { ...current, [page]: nextRatio });
    window.requestAnimationFrame(() => {
      virtualizer.measure();
      if (navigationTargetRef.current === page) {
        virtualizer.scrollToIndex(page - 1, { align: "start", behavior: "auto" });
      }
      requestPhysicalSync();
    });
  }, [requestPhysicalSync, virtualizer]);

  const onPageReady = useCallback((page: number) => {
    retainReadyPage(page);
    if (navigationTargetRef.current === page) {
      window.requestAnimationFrame(() => {
        virtualizer.measure();
        virtualizer.scrollToIndex(page - 1, { align: "start", behavior: "auto" });
        requestPhysicalSync();
      });
    } else {
      requestPhysicalSync();
    }
  }, [requestPhysicalSync, retainReadyPage, virtualizer]);

  const onPageAnnotations = useCallback((page: number, annotations: any[]) => {
    if (!annotations.some((item) => item?.subtype === "Widget" || item?.fieldType)) return;
    setFieldCount((value) => Math.max(1, value));
    setFormPages((values) => uniquePages([...values, page]));
    onAcroFormDetected?.(true);
  }, [onAcroFormDetected]);

  const workingFile = useCallback(async () => new File(
    [copyPdfBytes(await serialize())],
    outputPdfFilename(outputName, "WORKING_COPY"),
    { type: "application/pdf" },
  ), [outputName, serialize]);

  const perform = async (kind: typeof busy, action: () => Promise<void>) => {
    setBusy(kind);
    setActionError("");
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The PDF action failed");
    } finally {
      setBusy("");
    }
  };

  const downloadOriginal = () => perform("ORIGINAL", async () => {
    const result = await fetchPublicationBlob(originalDownloadUrl || fileUrl);
    downloadBlob(result.blob, result.filename || outputName);
  });

  const downloadWorking = () => perform("WORKING", async () => {
    const file = await workingFile();
    downloadBlob(file, file.name);
  });

  const downloadCompleted = () => perform("FLATTEN", async () => {
    const file = await workingFile();
    const result = await flattenPdfWorkingCopy(
      identity.tenant,
      identity.manualId,
      identity.revisionId,
      file,
      editedPages.length ? editedPages : formPages,
    );
    downloadBlob(result.blob, result.filename);
  });

  const submit = () => perform("SUBMIT", async () => {
    if (!window.confirm("Submit this completed PDF as an immutable controlled record?")) return;
    const file = await workingFile();
    const created = onSubmitWorkingCopy
      ? await onSubmitWorkingCopy(file)
      : await submitPdfWorkingCopy(identity.tenant, identity.manualId, identity.revisionId, file, {
        completed_page_numbers: editedPages.length ? editedPages : formPages,
      });
    invalidateDraftLifecycle();
    editGenerationRef.current = 0;
    setRecord(created);
    setDirtyState(false);
    setEdited([]);
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setDraft(null);
    onRecordCreated?.(created);
  });

  const discard = async () => {
    if (dirty && !window.confirm("Discard the working copy?")) return;
    invalidateDraftLifecycle();
    editGenerationRef.current = 0;
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setDraft(null);
    setDirtyState(false);
    setEdited([]);
    setDraftState("");
  };

  const revealSearchResult = useCallback((result?: PdfSearchResult, attempt = 0) => {
    if (!result) return;
    const page = pageRefs.current.get(result.page);
    if (!page) {
      if (attempt < 20) window.setTimeout(() => revealSearchResult(result, attempt + 1), 40);
      return;
    }
    const marks = [...page.querySelectorAll<HTMLElement>(".pdf-engine-search-mark")];
    marks.forEach((mark) => mark.classList.remove("is-active"));
    const target = marks[Math.max(0, result.ordinal - 1)] || marks[0];
    if (!target) {
      if (attempt < 20) window.setTimeout(() => revealSearchResult(result, attempt + 1), 40);
      return;
    }
    target.classList.add("is-active");
    target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  }, []);

  const runSearch = async () => {
    if (!pdfRef.current || query.trim().length < 2) return;
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setSearchBusy(true);
    try {
      const rows = await searchPdfDocument(pdfRef.current as any, query.trim(), searchOptions, controller.signal);
      if (controller.signal.aborted) return;
      setSearchResults(rows);
      setSearchIndex(rows.length ? 0 : -1);
      if (rows[0]) jump(rows[0].page);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setActionError(error instanceof Error ? error.message : "PDF search failed");
      }
    } finally {
      if (searchController.current === controller) searchController.current = null;
      if (!controller.signal.aborted) setSearchBusy(false);
    }
  };

  const moveSearch = (step: number) => {
    if (!searchResults.length) return;
    const index = (searchIndex + step + searchResults.length) % searchResults.length;
    const result = searchResults[index];
    setSearchIndex(index);
    jump(result.page);
  };

  const activeResult = searchResults[searchIndex];

  useEffect(() => {
    if (!activeResult || !readyPagesRef.current.has(activeResult.page)) return;
    window.requestAnimationFrame(() => revealSearchResult(activeResult));
  }, [activeResult, query, revealSearchResult]);

  return <section
    ref={hostRef}
    className={`pdfv2-reader pdfv2-reader--virtualized ${compact ? "is-compact" : ""} ${uncontrolled ? "is-uncontrolled" : ""} ${safeForm ? "is-form-active" : ""}`}
    data-pdf-navigation-pending={navigationPending || undefined}
    onKeyDown={(event: ReactKeyboardEvent<HTMLElement>) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
        window.requestAnimationFrame(() => searchInput.current?.focus());
      }
    }}
  >
    <header className="pdfv2-toolbar">
      <div className="pdfv2-pages">
        <button type="button" aria-label="Previous page" onClick={() => jump(currentPage - 1)} disabled={currentPage <= 1}><ChevronLeft size={17} /></button>
        <input
          value={pageInput}
          aria-label="Page number"
          inputMode="numeric"
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event: ChangeEvent<HTMLInputElement>) => setPageInput(event.target.value.replace(/\D+/g, ""))}
          onBlur={() => jump(Number(pageInput || currentPage))}
          onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
            if (event.key === "Enter") {
              event.preventDefault();
              jump(Number(pageInput || currentPage));
              event.currentTarget.blur();
            }
          }}
        />
        <span>/ {pageCount || "—"}</span>
        <button type="button" aria-label="Next page" onClick={() => jump(currentPage + 1)} disabled={!pageCount || currentPage >= pageCount}><ChevronRight size={17} /></button>
        {navigationPending ? <span className="pdfv2-navigation-state" role="status"><LoaderCircle className="is-spinning" size={13} />Opening {navigationPending}</span> : null}
      </div>
      <div className="pdfv2-zoom">
        <button type="button" aria-label="Zoom out" onClick={() => { setFitMode("CUSTOM"); setZoom((value) => clampPdfValue(value - 10, 50, 250)); }}><Minus size={17} /></button>
        <button type="button" onClick={() => {
          if (fitMode === "WIDTH") setFitMode("PAGE");
          else if (fitMode === "PAGE") { setFitMode("CUSTOM"); setZoom(100); }
          else setFitMode("WIDTH");
        }}>{fitMode === "WIDTH" ? "Fit width" : fitMode === "PAGE" ? "Fit page" : `${zoom}%`}</button>
        <button type="button" aria-label="Zoom in" onClick={() => { setFitMode("CUSTOM"); setZoom((value) => clampPdfValue(value + 10, 50, 250)); }}><Plus size={17} /></button>
      </div>
      <div className="pdfv2-actions">
        <button type="button" className={searchOpen ? "active" : ""} onClick={() => { setSearchOpen((value) => !value); window.requestAnimationFrame(() => searchInput.current?.focus()); }}><Search size={16} /><span>Search</span></button>
        {safeForm ? <span className="pdfv2-form-state"><FilePenLine size={15} /> Form active{editedPages.length ? ` · ${editedPages.length} changed` : ""}</span> : null}
        <details className="pdfv2-menu">
          <summary><Download size={16} /><span>Download</span></summary>
          <div>
            <button type="button" disabled={Boolean(busy) || !capabilities.can_download_original} onClick={() => void downloadOriginal()}>Original PDF</button>
            <button type="button" disabled={Boolean(busy) || !capabilities.can_download_working || !pdfRef.current?.saveDocument} onClick={() => void downloadWorking()}>Editable PDF</button>
            <button type="button" disabled={Boolean(busy) || !capabilities.can_flatten || !safeForm || !pdfRef.current?.saveDocument} onClick={() => void downloadCompleted()}>Completed form pages{editedPages.length ? ` (${editedPages.length})` : ""}</button>
          </div>
        </details>
        <details className="pdfv2-menu">
          <summary aria-label="More PDF actions"><MoreHorizontal size={18} /></summary>
          <div>
            {capabilities.can_submit ? <button type="button" disabled={Boolean(busy)} onClick={() => void submit()}>Submit retained record</button> : null}
            {draft || dirty ? <button type="button" onClick={() => void discard()}><Trash2 size={14} /> Discard working copy</button> : null}
          </div>
        </details>
      </div>
    </header>

    {searchOpen ? <div className="pdfv2-search">
      <Search size={16} />
      <input ref={searchInput} value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => { if (event.key === "Enter") void runSearch(); }} placeholder="Search this PDF" />
      <label><input type="checkbox" checked={Boolean(searchOptions.caseSensitive)} onChange={(event: ChangeEvent<HTMLInputElement>) => setSearchOptions((value) => ({ ...value, caseSensitive: event.target.checked }))} /> Aa</label>
      <label><input type="checkbox" checked={Boolean(searchOptions.wholeWord)} onChange={(event: ChangeEvent<HTMLInputElement>) => setSearchOptions((value) => ({ ...value, wholeWord: event.target.checked }))} /> Word</label>
      <button type="button" disabled={searchBusy || query.trim().length < 2} onClick={() => void runSearch()}>{searchBusy ? <LoaderCircle className="is-spinning" size={15} /> : "Find"}</button>
      <span>{searchResults.length ? `${searchIndex + 1}/${searchResults.length}` : ""}</span>
      <button type="button" aria-label="Previous search result" disabled={!searchResults.length} onClick={() => moveSearch(-1)}><ChevronLeft size={16} /></button>
      <button type="button" aria-label="Next search result" disabled={!searchResults.length} onClick={() => moveSearch(1)}><ChevronRight size={16} /></button>
      <button type="button" aria-label="Close PDF search" onClick={() => { searchController.current?.abort(); setSearchBusy(false); setSearchOpen(false); }}><X size={16} /></button>
    </div> : null}

    {capabilityError ? <div className="pdfv2-notice"><AlertTriangle size={16} />{capabilityError}</div> : null}
    {capabilities.unsupported_reason && !safeForm ? <div className="pdfv2-notice"><AlertTriangle size={16} />{capabilities.unsupported_reason}</div> : null}
    {formDetected && !safeForm && !capabilities.unsupported_reason ? <div className="pdfv2-notice"><AlertTriangle size={16} />This PDF contains form fields, but controlled form execution is unavailable for this document or user.</div> : null}
    {safeForm ? <div className="pdfv2-notice pdfv2-notice--form"><FilePenLine size={16} />Fields are active. Entries stay in a local working copy until you download or submit.<small>{draftState === "SAVING" ? "Saving…" : draftState === "SAVED" ? "Saved" : draftState === "ERROR" ? "Save failed" : ""}</small></div> : null}
    {actionError ? <div className="pdfv2-error" role="alert"><AlertTriangle size={17} />{actionError}</div> : null}
    {record ? <div className="pdfv2-success"><CheckCircle2 size={17} />Record {record.record_number} created.<a href={record.download_url}>Open</a></div> : null}

    <div
      ref={viewportRef}
      className="pdfv2-viewport"
      onScroll={requestPhysicalSync}
      onInput={(event: FormEvent<HTMLDivElement>) => safeForm && markEdited(Number((event.target as HTMLElement).closest("[data-page-number]")?.getAttribute("data-page-number") || currentPageRef.current))}
      onChange={(event: FormEvent<HTMLDivElement>) => safeForm && markEdited(Number((event.target as HTMLElement).closest("[data-page-number]")?.getAttribute("data-page-number") || currentPageRef.current))}
    >
      {loadError ? <div className="pdfv2-error pdfv2-error--viewport" role="alert"><AlertTriangle size={18} />{loadError}</div> : null}
      <PdfDocument
        file={readerFile}
        options={PDF_DOCUMENT_OPTIONS}
        externalLinkTarget="_blank"
        externalLinkRel="noopener noreferrer"
        onLoadSuccess={loadDocument}
        onLoadError={(error: unknown) => setLoadError(error instanceof Error ? error.message : "The PDF could not be opened")}
        onItemClick={(target: PdfItemClickTarget) => { void followPdfItem(target); }}
        loading={<div className="pdfv2-loading"><LoaderCircle className="is-spinning" size={20} />Opening document…</div>}
      >
        <div className="pdfv2-virtual-stage" style={{ height: `${virtualizer.getTotalSize()}px` }}>
          {renderItems.map((item) => {
            const page = item.index + 1;
            return <VirtualPdfPage
              key={page}
              pageNumber={page}
              width={pageWidth}
              item={item}
              documentKey={documentKey}
              safeForm={safeForm}
              devicePixelRatio={pdfDevicePixelRatio(performanceProfile.maxDevicePixelRatio)}
              uncontrolled={uncontrolled}
              current={page === currentPage}
              query={query}
              searchOptions={searchOptions}
              activeSearchResult={activeResult}
              renderPageOverlay={renderPageOverlay}
              onElement={(pageNumber, element) => {
                if (element) pageRefs.current.set(pageNumber, element);
                else pageRefs.current.delete(pageNumber);
              }}
              onMeasure={virtualizer.measureElement}
              onRatio={onPageRatio}
              onReady={onPageReady}
              onFailure={(pageNumber, message) => setActionError(`Page ${pageNumber}: ${message}`)}
              onAnnotations={onPageAnnotations}
              onTextReady={(pageNumber) => {
                if (activeResult?.page === pageNumber) window.requestAnimationFrame(() => revealSearchResult(activeResult));
              }}
            />;
          })}
        </div>
      </PdfDocument>
    </div>
  </section>;
}

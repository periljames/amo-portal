import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FC,
  type ReactNode,
} from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileCheck2,
  FilePenLine,
  LoaderCircle,
  Maximize2,
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
import {
  downloadBlob,
  fetchPublicationBlob,
  publicationPdfSource,
} from "../../services/publications";
import { PDF_DOCUMENT_OPTIONS, pdfDevicePixelRatio } from "./pdfReaderConfig";
import {
  clampPdfValue,
  copyPdfBytes,
  highlightPdfText,
  outputPdfFilename,
  pdfReaderShortcut,
  safePdfFilename,
  searchPdfDocument,
  type PdfSearchOptions,
  type PdfSearchResult,
} from "./pdfReaderEngine";
import {
  deletePdfWorkingCopy,
  readPdfWorkingCopy,
  savePdfWorkingCopy,
  type PdfWorkingCopyIdentity,
  type StoredPdfWorkingCopy,
} from "./pdfWorkingCopyStore";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./pdfReaderEngine.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfDocument = Document as unknown as FC<any>;
const PdfPage = Page as unknown as FC<any>;
let activePdfReaderId: string | null = null;
let pdfReaderSequence = 0;

type PdfAnnotationStorage = {
  onSetModified?: () => void;
  onResetModified?: () => void;
  modified?: boolean;
};

type PdfDocumentHandle = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<any>;
  getOutline?: () => Promise<any[] | null>;
  getDestination?: (name: string) => Promise<any[] | null>;
  getPageIndex?: (reference: unknown) => Promise<number>;
  getFieldObjects?: () => Promise<Record<string, unknown[]> | null>;
  hasJSActions?: () => Promise<boolean>;
  saveDocument?: () => Promise<Uint8Array>;
  annotationStorage?: PdfAnnotationStorage;
};

export type PdfReaderOutlineItem = {
  id: string;
  title: string;
  page: number;
  level: number;
};

export type PdfReaderNavigationRequest = {
  page: number;
  token: number;
};

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

type FitMode = "WIDTH" | "PAGE" | "CUSTOM";

const READ_ONLY_CAPABILITIES: PdfReaderCapabilities = {
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

function readerScroller(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".app-shell__scroll");
}

function scrollPageIntoView(element: HTMLElement, behavior: ScrollBehavior = "smooth"): void {
  const scroller = readerScroller();
  const offset = 104;
  if (scroller) {
    const scrollerRect = scroller.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const top = scroller.scrollTop + elementRect.top - scrollerRect.top - offset;
    scroller.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }
  const top = window.scrollY + element.getBoundingClientRect().top - offset;
  window.scrollTo({ top: Math.max(0, top), behavior });
}

function pagesAround(pageNumber: number, pageCount: number): Set<number> {
  const pages = new Set<number>();
  for (let page = pageNumber - 3; page <= pageNumber + 3; page += 1) {
    if (page >= 1 && page <= pageCount) pages.add(page);
  }
  return pages;
}

function fitModeStorageKey(identity: PdfWorkingCopyIdentity): string {
  return `pdf-reader-fit-mode:v1:${identity.userId}:${identity.tenant}:${identity.manualId}:${identity.revisionId}`;
}

function readFitMode(identity: PdfWorkingCopyIdentity): FitMode {
  try {
    const stored = window.localStorage.getItem(fitModeStorageKey(identity));
    if (stored === "WIDTH" || stored === "PAGE" || stored === "CUSTOM") return stored;
  } catch {
    // Local storage is an optional convenience. The reader remains usable without it.
  }
  return "WIDTH";
}

async function resolveOutline(documentProxy: PdfDocumentHandle): Promise<PdfReaderOutlineItem[]> {
  const outline = await documentProxy.getOutline?.().catch(() => null);
  if (!Array.isArray(outline) || !outline.length) return [];
  const resolved: PdfReaderOutlineItem[] = [];
  const visit = async (items: any[], level: number, path: string): Promise<void> => {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      let destination = item?.dest;
      if (typeof destination === "string") destination = await documentProxy.getDestination?.(destination).catch(() => null);
      const reference = Array.isArray(destination) ? destination[0] : null;
      let page = 0;
      if (typeof reference === "number") page = reference + 1;
      else if (reference && documentProxy.getPageIndex) page = (await documentProxy.getPageIndex(reference).catch(() => -1)) + 1;
      const id = `${path}-${index}`;
      if (page > 0) resolved.push({ id, title: String(item?.title || `Page ${page}`), page, level });
      if (Array.isArray(item?.items) && item.items.length) await visit(item.items, level + 1, id);
    }
  };
  await visit(outline, 1, "pdf-outline");
  return resolved;
}

function countFields(fields: Record<string, unknown[]> | null): number {
  return Object.values(fields || {}).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);
}

export default function PdfReaderCore({
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
}: PdfReaderCoreProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const readerIdRef = useRef(`pdf-reader-${++pdfReaderSequence}`);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const documentRef = useRef<PdfDocumentHandle | null>(null);
  const inspectionGenerationRef = useRef(0);
  const searchControllerRef = useRef<AbortController | null>(null);
  const autosaveTimerRef = useRef<number | null>(null);
  const serializationRef = useRef<Promise<Uint8Array> | null>(null);
  const pendingAutosaveRef = useRef(false);
  const dirtyRef = useRef(false);
  const onPageChangeRef = useRef(onPageChange);
  const onZoomChangeRef = useRef(onZoomChange);
  const onAcroFormDetectedRef = useRef(onAcroFormDetected);
  const onOutlineReadyRef = useRef(onOutlineReady);
  const onDirtyChangeRef = useRef(onDirtyChange);
  const initialPageRef = useRef(initialPage);

  const [resolvedCapabilities, setResolvedCapabilities] = useState<PdfReaderCapabilities | null>(suppliedCapabilities || null);
  const [capabilityError, setCapabilityError] = useState("");
  const [localDraft, setLocalDraft] = useState<StoredPdfWorkingCopy | null>(null);
  const [draftNotice, setDraftNotice] = useState("");
  const [documentProxy, setDocumentProxy] = useState<PdfDocumentHandle | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [pageInput, setPageInput] = useState(String(Math.max(1, initialPage)));
  const [hostWidth, setHostWidth] = useState(960);
  const [hostHeight, setHostHeight] = useState(720);
  const [zoomPercent, setZoomPercent] = useState(clampPdfValue(initialZoom, 50, 250));
  const [fitMode, setFitMode] = useState<FitMode>(() => readFitMode(identity));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [loadError, setLoadError] = useState("");
  const [fieldCount, setFieldCount] = useState(0);
  const [hasJavaScript, setHasJavaScript] = useState(false);
  const [fillMode, setFillMode] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [draftState, setDraftState] = useState<"IDLE" | "SAVING" | "SAVED" | "ERROR">("IDLE");
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOptions, setSearchOptions] = useState<PdfSearchOptions>({ caseSensitive: false, wholeWord: false });
  const [searchResults, setSearchResults] = useState<PdfSearchResult[]>([]);
  const [activeSearchIndex, setActiveSearchIndex] = useState(-1);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchProgress, setSearchProgress] = useState({ completed: 0, total: 0 });
  const [searchError, setSearchError] = useState("");
  const [busyAction, setBusyAction] = useState<"" | "ORIGINAL" | "WORKING" | "FLATTEN" | "SUBMIT">("");
  const [actionError, setActionError] = useState("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);

  const capabilities = resolvedCapabilities || READ_ONLY_CAPABILITIES;
  const originalSource = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const readerFile = useMemo(
    () => localDraft ? { data: new Uint8Array(localDraft.bytes.slice(0)) } : originalSource,
    [localDraft, originalSource],
  );
  const outputFilename = safePdfFilename(filename || "", `${title}.pdf`);
  const canFill = Boolean(
    capabilities.can_fill
    && fieldCount > 0
    && !hasJavaScript
    && !capabilities.has_javascript
    && !capabilities.is_dynamic_xfa,
  );
  const unsafeCapabilityReason = capabilities.has_javascript
    || capabilities.is_dynamic_xfa
    || capabilities.encrypted
    ? capabilities.unsupported_reason
    : null;
  const formRestrictionReason = fieldCount > 0 && !canFill
    ? capabilities.unsupported_reason || "This PDF contains form fields, but editable execution is not enabled for this controlled revision."
    : "";

  const setWorkingDirty = useCallback((value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
  }, []);

  useEffect(() => { initialPageRef.current = initialPage; }, [initialPage]);
  useEffect(() => { onPageChangeRef.current = onPageChange; }, [onPageChange]);
  useEffect(() => { onZoomChangeRef.current = onZoomChange; }, [onZoomChange]);
  useEffect(() => { onAcroFormDetectedRef.current = onAcroFormDetected; }, [onAcroFormDetected]);
  useEffect(() => { onOutlineReadyRef.current = onOutlineReady; }, [onOutlineReady]);
  useEffect(() => { onDirtyChangeRef.current = onDirtyChange; }, [onDirtyChange]);
  useEffect(() => { onDirtyChangeRef.current?.(dirty); }, [dirty]);

  useEffect(() => {
    try {
      window.localStorage.setItem(fitModeStorageKey(identity), fitMode);
    } catch {
      // Persistence is optional and must never block reading.
    }
  }, [fitMode, identity.manualId, identity.revisionId, identity.tenant, identity.userId]);

  useEffect(() => {
    if (canFill) setFillMode(true);
    else setFillMode(false);
  }, [canFill]);

  useEffect(() => {
    if (!activePdfReaderId) activePdfReaderId = readerIdRef.current;
    return () => {
      if (activePdfReaderId === readerIdRef.current) activePdfReaderId = null;
    };
  }, []);

  useEffect(() => {
    if (suppliedCapabilities) {
      setResolvedCapabilities(suppliedCapabilities);
      setCapabilityError("");
      return;
    }
    let active = true;
    setCapabilityError("");
    getPdfReaderCapabilities(identity.tenant, identity.manualId, identity.revisionId)
      .then((value) => { if (active) setResolvedCapabilities(value); })
      .catch((caught) => {
        if (!active) return;
        setResolvedCapabilities(READ_ONLY_CAPABILITIES);
        setCapabilityError(caught instanceof Error ? caught.message : "PDF processing capabilities are unavailable");
      });
    return () => { active = false; };
  }, [identity.manualId, identity.revisionId, identity.tenant, suppliedCapabilities]);

  useEffect(() => {
    let active = true;
    readPdfWorkingCopy(identity)
      .then((draft) => {
        if (!active || !draft) return;
        if (draft.sourceSha256 && capabilities.source_sha256 && draft.sourceSha256 !== capabilities.source_sha256) {
          setDraftNotice("A local working copy belongs to a different source checksum and was not restored.");
          return;
        }
        setLocalDraft((current) => current?.key === draft.key && current.savedAt === draft.savedAt ? current : draft);
        setDraftNotice(`Working copy restored from ${new Date(draft.savedAt).toLocaleString()}.`);
        setWorkingDirty(true);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [capabilities.source_sha256, identity.manualId, identity.revisionId, identity.tenant, identity.userId, setWorkingDirty]);

  useEffect(() => {
    inspectionGenerationRef.current += 1;
    searchControllerRef.current?.abort();
    const existingStorage = documentRef.current?.annotationStorage;
    if (existingStorage) {
      existingStorage.onSetModified = undefined;
      existingStorage.onResetModified = undefined;
    }
    documentRef.current = null;
    setDocumentProxy(null);
    setPageCount(0);
    setCurrentPage(1);
    setPageInput("1");
    setPageRatios({});
    setLoadError("");
    setFieldCount(0);
    setHasJavaScript(false);
    setFillMode(false);
    setSearchResults([]);
    setActiveSearchIndex(-1);
  }, [fileUrl, localDraft?.savedAt]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const scroller = readerScroller();
    const resize = () => {
      const viewportHeight = scroller?.clientHeight || window.innerHeight;
      setHostWidth(Math.max(280, host.clientWidth));
      setHostHeight(Math.max(360, viewportHeight - 112));
    };
    resize();
    window.addEventListener("resize", resize);
    if (typeof ResizeObserver === "undefined") {
      return () => window.removeEventListener("resize", resize);
    }
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    if (scroller) observer.observe(scroller);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);

  const currentRatio = pageRatios[currentPage] || 1.414;
  const availableWidth = Math.max(240, Math.min(1600, hostWidth - (compact ? 16 : 32)));
  const fitPageChrome = searchOpen ? 118 : 74;
  const fitPageWidth = Math.max(220, Math.min(availableWidth, (hostHeight - fitPageChrome) / currentRatio));
  const pageWidth = Math.round(
    fitMode === "PAGE"
      ? fitPageWidth
      : fitMode === "WIDTH"
        ? availableWidth
        : availableWidth * (zoomPercent / 100),
  );

  useEffect(() => {
    const effectiveZoom = fitMode === "CUSTOM" ? zoomPercent : Math.round((pageWidth / availableWidth) * 100);
    onZoomChangeRef.current?.(effectiveZoom);
  }, [availableWidth, fitMode, pageWidth, zoomPercent]);

  const renderedPages = useMemo(() => {
    const pages = pagesAround(currentPage, pageCount);
    if (navigationRequest?.page) {
      pagesAround(clampPdfValue(navigationRequest.page, 1, Math.max(1, pageCount)), pageCount).forEach((page) => pages.add(page));
    }
    const activeResult = searchResults[activeSearchIndex];
    if (activeResult) pagesAround(activeResult.page, pageCount).forEach((page) => pages.add(page));
    return pages;
  }, [activeSearchIndex, currentPage, navigationRequest, pageCount, searchResults]);

  useEffect(() => {
    if (!pageCount || typeof IntersectionObserver === "undefined") return;
    const root = readerScroller();
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting);
      if (!visible.length) return;
      const viewportTop = root?.getBoundingClientRect().top || 0;
      const viewportHeight = root?.clientHeight || window.innerHeight;
      const centre = viewportTop + viewportHeight * 0.42;
      const closest = [...visible].sort((left, right) => {
        const leftCentre = left.boundingClientRect.top + left.boundingClientRect.height / 2;
        const rightCentre = right.boundingClientRect.top + right.boundingClientRect.height / 2;
        return Math.abs(leftCentre - centre) - Math.abs(rightCentre - centre);
      })[0];
      const next = Number((closest.target as HTMLElement).dataset.pageNumber || 1);
      if (!Number.isFinite(next)) return;
      setCurrentPage((previous) => {
        if (previous === next) return previous;
        setPageInput(String(next));
        onPageChangeRef.current?.(next);
        return next;
      });
    }, { root, rootMargin: "-104px 0px -48% 0px", threshold: [0.01, 0.12, 0.35, 0.7] });
    pageRefs.current.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [pageCount, pageWidth]);

  const jumpToPage = useCallback((requestedPage: number, behavior: ScrollBehavior = "smooth") => {
    if (!pageCount) return;
    const page = clampPdfValue(requestedPage, 1, pageCount);
    setCurrentPage(page);
    setPageInput(String(page));
    onPageChangeRef.current?.(page);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const element = pageRefs.current.get(page);
        if (element) scrollPageIntoView(element, behavior);
      });
    });
  }, [pageCount]);

  useEffect(() => {
    if (!pageCount || !navigationRequest) return;
    jumpToPage(navigationRequest.page);
  }, [jumpToPage, navigationRequest, pageCount]);

  useEffect(() => {
    if (!pageCount) return;
    jumpToPage(initialPage, "auto");
  }, [initialPage, jumpToPage, pageCount]);

  const serializeCurrentDocument = useCallback(async (): Promise<Uint8Array> => {
    const document = documentRef.current;
    if (!document?.saveDocument) throw new Error("This PDF cannot be serialized as a working copy");
    if (!serializationRef.current) {
      serializationRef.current = document.saveDocument().finally(() => { serializationRef.current = null; });
    }
    return serializationRef.current;
  }, []);

  const persistDraft = useCallback(async () => {
    if (!capabilities.can_save_draft || !dirtyRef.current) return;
    if (serializationRef.current) {
      pendingAutosaveRef.current = true;
      return;
    }
    setDraftState("SAVING");
    try {
      const bytes = await serializeCurrentDocument();
      await savePdfWorkingCopy(
        identity,
        outputPdfFilename(outputFilename, "WORKING_COPY"),
        copyPdfBytes(bytes),
        capabilities.source_sha256,
      );
      setDraftState("SAVED");
      setDraftNotice("Working copy saved locally on this device.");
    } catch {
      setDraftState("ERROR");
    } finally {
      if (pendingAutosaveRef.current) {
        pendingAutosaveRef.current = false;
        window.setTimeout(() => void persistDraft(), 0);
      }
    }
  }, [capabilities.can_save_draft, capabilities.source_sha256, identity, outputFilename, serializeCurrentDocument]);

  const scheduleAutosave = useCallback(() => {
    setWorkingDirty(true);
    setDraftState("IDLE");
    if (!capabilities.can_save_draft) return;
    if (autosaveTimerRef.current) window.clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = window.setTimeout(() => void persistDraft(), 900);
  }, [capabilities.can_save_draft, persistDraft, setWorkingDirty]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => () => {
    searchControllerRef.current?.abort();
    if (autosaveTimerRef.current) window.clearTimeout(autosaveTimerRef.current);
    const storage = documentRef.current?.annotationStorage;
    if (storage) {
      storage.onSetModified = undefined;
      storage.onResetModified = undefined;
    }
    inspectionGenerationRef.current += 1;
  }, []);

  const inspectDocument = useCallback((loaded: PdfDocumentHandle) => {
    const generation = ++inspectionGenerationRef.current;
    const fields = loaded.getFieldObjects ? loaded.getFieldObjects().catch(() => null) : Promise.resolve(null);
    const scripted = loaded.hasJSActions ? loaded.hasJSActions().catch(() => false) : Promise.resolve(false);
    void Promise.all([fields, scripted, resolveOutline(loaded).catch(() => [])])
      .then(([fieldObjects, hasScripts, outline]) => {
        if (generation !== inspectionGenerationRef.current) return;
        const nextFieldCount = countFields(fieldObjects);
        setFieldCount(nextFieldCount);
        setHasJavaScript(Boolean(hasScripts));
        onAcroFormDetectedRef.current?.(nextFieldCount > 0);
        onOutlineReadyRef.current?.(outline);
      })
      .catch(() => undefined);
  }, []);

  const handleDocumentLoad = useCallback((loaded: PdfDocumentHandle) => {
    documentRef.current = loaded;
    setDocumentProxy(loaded);
    if (loaded.annotationStorage) {
      loaded.annotationStorage.onSetModified = scheduleAutosave;
      loaded.annotationStorage.onResetModified = () => setWorkingDirty(false);
    }
    const nextPageCount = Math.max(1, Number(loaded.numPages || 1));
    const restoredPage = clampPdfValue(initialPageRef.current, 1, nextPageCount);
    setPageCount(nextPageCount);
    setCurrentPage(restoredPage);
    setPageInput(String(restoredPage));
    setLoadError("");
    onPageChangeRef.current?.(restoredPage);
    inspectDocument(loaded);
  }, [inspectDocument, scheduleAutosave, setWorkingDirty]);

  const runSearch = useCallback(async (requestedQuery = query) => {
    const needle = requestedQuery.trim();
    if (!documentProxy || needle.length < 2) {
      setSearchResults([]);
      setActiveSearchIndex(-1);
      return;
    }
    searchControllerRef.current?.abort();
    const controller = new AbortController();
    searchControllerRef.current = controller;
    setSearchBusy(true);
    setSearchError("");
    setSearchProgress({ completed: 0, total: documentProxy.numPages });
    try {
      const results = await searchPdfDocument(
        documentProxy,
        needle,
        searchOptions,
        controller.signal,
        (completed, total) => setSearchProgress({ completed, total }),
      );
      if (controller.signal.aborted) return;
      setSearchResults(results);
      setActiveSearchIndex(results.length ? 0 : -1);
      if (results[0]) jumpToPage(results[0].page);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setSearchError(caught instanceof Error ? caught.message : "Search could not be completed");
    } finally {
      if (!controller.signal.aborted) setSearchBusy(false);
    }
  }, [documentProxy, jumpToPage, query, searchOptions]);

  const moveSearch = (direction: number) => {
    if (!searchResults.length) return;
    const next = (activeSearchIndex + direction + searchResults.length) % searchResults.length;
    setActiveSearchIndex(next);
    jumpToPage(searchResults[next].page);
  };

  const changeZoom = useCallback((delta: number) => {
    setFitMode("CUSTOM");
    setZoomPercent((current) => clampPdfValue(Math.round(current + delta), 50, 250));
  }, []);

  useEffect(() => {
    const readerId = readerIdRef.current;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (activePdfReaderId !== readerId) return;
      const shortcut = pdfReaderShortcut(event);
      if (!shortcut) return;
      event.preventDefault();
      if (shortcut === "SEARCH") {
        setSearchOpen(true);
        window.requestAnimationFrame(() => searchInputRef.current?.focus());
      } else if (shortcut === "ZOOM_IN") changeZoom(10);
      else if (shortcut === "ZOOM_OUT") changeZoom(-10);
      else if (shortcut === "RESET_ZOOM") { setFitMode("WIDTH"); setZoomPercent(100); }
      else if (shortcut === "NEXT_PAGE") jumpToPage(currentPage + 1);
      else if (shortcut === "PREVIOUS_PAGE") jumpToPage(currentPage - 1);
      else if (shortcut === "FIRST_PAGE") jumpToPage(1);
      else if (shortcut === "LAST_PAGE") jumpToPage(pageCount);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [changeZoom, currentPage, jumpToPage, pageCount]);

  const downloadOriginal = async () => {
    setBusyAction("ORIGINAL");
    setActionError("");
    try {
      const result = await fetchPublicationBlob(originalDownloadUrl || fileUrl);
      downloadBlob(result.blob, result.filename || outputFilename);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The original PDF could not be downloaded");
    } finally {
      setBusyAction("");
    }
  };

  const currentWorkingFile = useCallback(async (): Promise<File> => {
    const bytes = await serializeCurrentDocument();
    return new File(
      [copyPdfBytes(bytes)],
      outputPdfFilename(outputFilename, "WORKING_COPY"),
      { type: "application/pdf" },
    );
  }, [outputFilename, serializeCurrentDocument]);

  const downloadWorking = async () => {
    setBusyAction("WORKING");
    setActionError("");
    try {
      const file = await currentWorkingFile();
      downloadBlob(file, file.name);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The working copy could not be downloaded");
    } finally {
      setBusyAction("");
    }
  };

  const downloadFlattened = async () => {
    setBusyAction("FLATTEN");
    setActionError("");
    try {
      const file = await currentWorkingFile();
      const result = await flattenPdfWorkingCopy(identity.tenant, identity.manualId, identity.revisionId, file);
      downloadBlob(result.blob, result.filename || outputPdfFilename(outputFilename, "FLATTENED"));
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The flattened copy could not be created");
    } finally {
      setBusyAction("");
    }
  };

  const submitRecord = async () => {
    if (!window.confirm("Submit this completed PDF as an immutable controlled record?")) return;
    setBusyAction("SUBMIT");
    setActionError("");
    try {
      const file = await currentWorkingFile();
      const created = onSubmitWorkingCopy
        ? await onSubmitWorkingCopy(file)
        : await submitPdfWorkingCopy(identity.tenant, identity.manualId, identity.revisionId, file, { output_mode: "FLATTENED_RECORD" });
      setRecord(created);
      setWorkingDirty(false);
      setDraftState("IDLE");
      await deletePdfWorkingCopy(identity).catch(() => undefined);
      setLocalDraft(null);
      setDraftNotice("");
      onRecordCreated?.(created);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The controlled record could not be submitted");
    } finally {
      setBusyAction("");
    }
  };

  const discardDraft = async () => {
    if (dirty && !window.confirm("Discard the locally saved working copy and reopen the controlled source?")) return;
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setLocalDraft(null);
    setWorkingDirty(false);
    setFillMode(false);
    setDraftNotice("");
    setDraftState("IDLE");
  };

  const activateReader = () => { activePdfReaderId = readerIdRef.current; };
  const activeResult = searchResults[activeSearchIndex] || null;
  const pageNumbers = useMemo(() => Array.from({ length: pageCount }, (_, index) => index + 1), [pageCount]);

  return (
    <section
      ref={hostRef}
      tabIndex={-1}
      onPointerDownCapture={activateReader}
      onFocusCapture={activateReader}
      className={`pdf-engine-reader ${compact ? "pdf-engine-reader--compact" : ""} ${uncontrolled ? "is-uncontrolled" : ""} ${fillMode ? "is-fill-mode" : ""} ${dirty ? "is-dirty" : ""}`}
      aria-label={`${title} controlled PDF reader`}
    >
      <header className="pdf-engine-toolbar">
        <div className="pdf-engine-toolbar__pages" aria-label="Page navigation">
          <button type="button" onClick={() => jumpToPage(currentPage - 1)} disabled={currentPage <= 1} aria-label="Previous page"><ChevronLeft size={17} /></button>
          <input
            value={pageInput}
            inputMode="numeric"
            aria-label="Page number"
            onChange={(event) => setPageInput(event.target.value.replace(/\D+/g, ""))}
            onBlur={() => jumpToPage(Number(pageInput || currentPage))}
            onKeyDown={(event) => { if (event.key === "Enter") jumpToPage(Number(pageInput || currentPage)); }}
          />
          <span>/ {pageCount || "—"}</span>
          <button type="button" onClick={() => jumpToPage(currentPage + 1)} disabled={!pageCount || currentPage >= pageCount} aria-label="Next page"><ChevronRight size={17} /></button>
        </div>

        <div className="pdf-engine-toolbar__zoom" aria-label="Zoom controls">
          <button type="button" onClick={() => changeZoom(-10)} aria-label="Zoom out"><Minus size={17} /></button>
          <button type="button" className="pdf-engine-zoom-value" onClick={() => { setFitMode("CUSTOM"); setZoomPercent(100); }}>{fitMode === "WIDTH" ? "Fit width" : fitMode === "PAGE" ? "Fit page" : `${zoomPercent}%`}</button>
          <button type="button" onClick={() => changeZoom(10)} aria-label="Zoom in"><Plus size={17} /></button>
          <details className="pdf-engine-menu"><summary aria-label="Fit options"><Maximize2 size={16} /></summary><div><button type="button" className={fitMode === "WIDTH" ? "active" : ""} onClick={() => setFitMode("WIDTH")}>Fit width</button><button type="button" className={fitMode === "PAGE" ? "active" : ""} onClick={() => setFitMode("PAGE")}>Fit page</button><button type="button" className={fitMode === "CUSTOM" && zoomPercent === 100 ? "active" : ""} onClick={() => { setFitMode("CUSTOM"); setZoomPercent(100); }}>Actual size</button></div></details>
        </div>

        <div className="pdf-engine-toolbar__actions">
          <button type="button" className={searchOpen ? "active" : ""} onClick={() => { setSearchOpen((value) => !value); window.requestAnimationFrame(() => searchInputRef.current?.focus()); }}><Search size={16} /><span>Search</span></button>
          {canFill ? <button type="button" className={fillMode ? "active" : ""} onClick={() => setFillMode((value) => !value)}><FilePenLine size={16} /><span>{fillMode ? "Exit fill" : "Fill form"}</span></button> : null}
          <details className="pdf-engine-menu pdf-engine-download-menu"><summary><Download size={16} /><span>Download</span></summary><div>
            <button type="button" disabled={Boolean(busyAction) || !capabilities.can_download_original} onClick={() => void downloadOriginal()}>Original controlled source</button>
            <button type="button" disabled={Boolean(busyAction) || !capabilities.can_download_working || !documentProxy?.saveDocument} onClick={() => void downloadWorking()}>Editable working copy</button>
            <button type="button" disabled={Boolean(busyAction) || !capabilities.can_flatten || !documentProxy?.saveDocument} onClick={() => void downloadFlattened()}>Flattened copy</button>
          </div></details>
          <details className="pdf-engine-menu"><summary aria-label="More reader actions"><MoreHorizontal size={18} /></summary><div>
            {capabilities.can_submit ? <button type="button" disabled={Boolean(busyAction) || !documentProxy?.saveDocument} onClick={() => void submitRecord()}>Submit retained record</button> : null}
            {localDraft || dirty ? <button type="button" onClick={() => void discardDraft()}><Trash2 size={14} /> Discard working copy</button> : null}
            <span className="pdf-engine-menu__meta">{capabilities.renderer} · {capabilities.processor} {capabilities.processor_version}</span>
          </div></details>
        </div>
      </header>

      {searchOpen ? <div className="pdf-engine-search" role="search">
        <Search size={16} />
        <input
          ref={searchInputRef}
          value={query}
          placeholder="Search this PDF"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void runSearch(); if (event.key === "Escape") setSearchOpen(false); }}
        />
        <label><input type="checkbox" checked={Boolean(searchOptions.caseSensitive)} onChange={(event) => setSearchOptions((current) => ({ ...current, caseSensitive: event.target.checked }))} /> Aa</label>
        <label><input type="checkbox" checked={Boolean(searchOptions.wholeWord)} onChange={(event) => setSearchOptions((current) => ({ ...current, wholeWord: event.target.checked }))} /> Word</label>
        <button type="button" disabled={searchBusy || query.trim().length < 2} onClick={() => void runSearch()}>{searchBusy ? <LoaderCircle className="is-spinning" size={15} /> : "Find"}</button>
        <span>{searchBusy ? `${searchProgress.completed}/${searchProgress.total} pages` : searchResults.length ? `${activeSearchIndex + 1}/${searchResults.length}` : query.trim() ? "No matches" : ""}</span>
        <button type="button" disabled={!searchResults.length} onClick={() => moveSearch(-1)} aria-label="Previous search result"><ChevronLeft size={16} /></button>
        <button type="button" disabled={!searchResults.length} onClick={() => moveSearch(1)} aria-label="Next search result"><ChevronRight size={16} /></button>
        <button type="button" onClick={() => { searchControllerRef.current?.abort(); setSearchOpen(false); }} aria-label="Close search"><X size={16} /></button>
      </div> : null}

      {capabilityError ? <div className="pdf-engine-notice"><AlertTriangle size={16} /><span>{capabilityError}. Reading and original download remain available.</span></div> : null}
      {unsafeCapabilityReason ? <div className="pdf-engine-notice"><AlertTriangle size={16} /><span>{unsafeCapabilityReason}</span></div> : null}
      {formRestrictionReason && formRestrictionReason !== unsafeCapabilityReason ? <div className="pdf-engine-notice"><FilePenLine size={16} /><span>{formRestrictionReason}</span></div> : null}
      {draftNotice ? <div className="pdf-engine-notice pdf-engine-notice--draft"><FileCheck2 size={16} /><span>{draftNotice}</span>{draftState === "SAVING" ? <small>Saving…</small> : draftState === "SAVED" ? <small>Saved</small> : draftState === "ERROR" ? <small>Save failed</small> : null}</div> : null}
      {actionError || searchError ? <div className="pdf-engine-error" role="alert"><AlertTriangle size={17} /><span>{actionError || searchError}</span></div> : null}
      {record ? <div className="pdf-engine-success" role="status"><CheckCircle2 size={17} /><span>Controlled record {record.record_number} created.</span><a href={record.download_url} target="_blank" rel="noreferrer">Open retained copy</a></div> : null}

      <div className="pdf-engine-viewport" onInput={() => fillMode && scheduleAutosave()} onChange={() => fillMode && scheduleAutosave()}>
        {loadError ? <div className="pdf-engine-error" role="alert"><AlertTriangle size={18} /><span>{loadError}</span></div> : null}
        <PdfDocument
          file={readerFile}
          options={PDF_DOCUMENT_OPTIONS}
          onLoadSuccess={handleDocumentLoad}
          onItemClick={({ pageIndex, pageNumber }: { pageIndex?: number; pageNumber?: number }) => {
            const targetPage = Number(pageNumber || (Number.isFinite(pageIndex) ? Number(pageIndex) + 1 : 0));
            if (targetPage > 0) jumpToPage(targetPage);
          }}
          onLoadError={(caught: unknown) => {
            inspectionGenerationRef.current += 1;
            setLoadError(caught instanceof Error ? caught.message : "The PDF could not be opened");
          }}
          loading={<div className="pdf-engine-loading"><LoaderCircle className="is-spinning" size={20} /> Opening first page…</div>}
          error={<div className="pdf-engine-error" role="alert"><AlertTriangle size={18} /><span>The controlled PDF could not be rendered.</span></div>}
        >
          <div className="pdf-engine-pages">
            {pageNumbers.map((pageNumber) => {
              const ratio = pageRatios[pageNumber] || 1.414;
              const style = {
                "--pdf-engine-page-width": `${pageWidth}px`,
                "--pdf-engine-page-height": `${Math.round(pageWidth * ratio)}px`,
              } as CSSProperties;
              const shouldRender = renderedPages.has(pageNumber);
              return <div
                key={pageNumber}
                ref={(element) => { if (element) pageRefs.current.set(pageNumber, element); else pageRefs.current.delete(pageNumber); }}
                className={`pdf-engine-page ${currentPage === pageNumber ? "is-current" : ""}`}
                data-page-number={pageNumber}
                style={style}
              >
                <span className="pdf-engine-page__label">{pageNumber}</span>
                {uncontrolled ? <span className="pdf-engine-page__watermark" aria-hidden="true">UNCONTROLLED DRAFT</span> : null}
                {shouldRender ? <PdfPage
                  pageNumber={pageNumber}
                  width={pageWidth}
                  renderMode="canvas"
                  renderTextLayer
                  renderAnnotationLayer
                  renderForms={fillMode && canFill}
                  externalLinkTarget="_blank"
                  externalLinkRel="noopener noreferrer nofollow"
                  devicePixelRatio={pdfDevicePixelRatio()}
                  customTextRenderer={({ str }: { str: string }) => highlightPdfText(str, query, searchOptions, activeResult?.page === pageNumber)}
                  loading={<div className="pdf-engine-page__placeholder">Rendering page {pageNumber}…</div>}
                  error={<div className="pdf-engine-page__placeholder">Page {pageNumber} could not be rendered.</div>}
                  onGetAnnotationsSuccess={(annotations: any[]) => {
                    if (!fieldCount && annotations.some((annotation) => annotation?.subtype === "Widget" || annotation?.fieldType)) {
                      setFieldCount(1);
                      onAcroFormDetectedRef.current?.(true);
                    }
                  }}
                  onLoadSuccess={(page: any) => {
                    const width = Number(page?.originalWidth || page?.view?.[2] || 1);
                    const height = Number(page?.originalHeight || page?.view?.[3] || width * 1.414);
                    const ratioValue = width > 0 && height > 0 ? height / width : 1.414;
                    setPageRatios((current) => Math.abs((current[pageNumber] || 0) - ratioValue) < 0.001 ? current : { ...current, [pageNumber]: ratioValue });
                  }}
                /> : <PdfPage
                  pageNumber={pageNumber}
                  width={pageWidth}
                  renderMode="none"
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  loading={<div className="pdf-engine-page__placeholder" aria-label={`Page ${pageNumber} is ready to render`} />}
                />}
                {renderPageOverlay?.(pageNumber)}
              </div>;
            })}
          </div>
        </PdfDocument>
      </div>
    </section>
  );
}

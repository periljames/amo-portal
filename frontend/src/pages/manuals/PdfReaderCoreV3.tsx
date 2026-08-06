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
import { defaultRangeExtractor, useVirtualizer, type Range } from "@tanstack/react-virtual";
import { Document, Page, pdfjs } from "react-pdf";

import type { DocumentationRecord } from "../../services/documentation";
import {
  flattenPdfWorkingCopy,
  submitPdfWorkingCopy,
  type PdfReaderCapabilities,
} from "../../services/pdfReader";
import {
  downloadBlob,
  fetchPublicationBlob,
  publicationPdfSource,
} from "../../services/publications";
import {
  PDF_DOCUMENT_OPTIONS,
  getPdfReaderPerformanceProfile,
  pdfDevicePixelRatio,
} from "./pdfReaderConfig";
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
  deletePdfWorkingCopy,
  readPdfWorkingCopy,
  savePdfWorkingCopy,
  type PdfWorkingCopyIdentity,
  type StoredPdfWorkingCopy,
} from "./pdfWorkingCopyStore";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./pdfReaderEngineV3.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const PdfDocument = Document as unknown as FC<any>;
const PdfPage = Page as unknown as FC<any>;
const PAGE_GAP = 18;
const PAGE_TOP_INSET = 14;
const NAVIGATION_TIMEOUT_MS = 4_000;

type PdfDocumentHandle = {
  numPages: number;
  getOutline?: () => Promise<any[] | null>;
  getDestination?: (name: string) => Promise<any[] | null>;
  getPageIndex?: (value: unknown) => Promise<number>;
  getFieldObjects?: () => Promise<Record<string, Array<Record<string, unknown>>> | null>;
  saveDocument?: () => Promise<Uint8Array>;
  annotationStorage?: {
    onSetModified?: () => void;
    onResetModified?: () => void;
  };
};

type PdfItemClickTarget = {
  id?: string | null;
  subtype?: string | null;
  dest?: string | unknown[] | null;
  pageIndex?: number | null;
  pageNumber?: number | null;
  url?: string | null;
  unsafeUrl?: string | null;
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

const READ_ONLY: PdfReaderCapabilities = {
  renderer: "PDF.js",
  processor: "PDFium",
  processor_version: "unavailable",
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

const uniquePages = (values: Iterable<number>): number[] => [...new Set(values)]
  .filter((value) => Number.isInteger(value) && value > 0)
  .sort((left, right) => left - right);

async function resolveOutline(pdf: PdfDocumentHandle): Promise<PdfReaderOutlineItem[]> {
  const source = await pdf.getOutline?.().catch(() => null);
  if (!Array.isArray(source)) return [];
  const rows: PdfReaderOutlineItem[] = [];

  const visit = async (items: any[], level: number, prefix: string): Promise<void> => {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      let destination = item?.dest;
      if (typeof destination === "string") {
        destination = await pdf.getDestination?.(destination).catch(() => null);
      }
      const reference = Array.isArray(destination) ? destination[0] : null;
      let page = typeof reference === "number" ? reference + 1 : 0;
      if (!page && reference && pdf.getPageIndex) {
        page = (await pdf.getPageIndex(reference).catch(() => -1)) + 1;
      }
      const id = `${prefix}-${index}`;
      if (page > 0) {
        rows.push({
          id,
          title: String(item?.title || `Page ${page}`),
          page,
          level,
        });
      }
      if (item?.items?.length) await visit(item.items, level + 1, id);
    }
  };

  await visit(source, 1, "outline");
  return rows;
}

function detectedFormPages(
  fields: Record<string, Array<Record<string, unknown>>> | null,
  pageCount: number,
): number[] {
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
  page,
  width,
  safeForm,
  query,
  searchOptions,
  uncontrolled,
  active,
  renderOverlay,
  maxDevicePixelRatio,
  onRatio,
  onFormDetected,
  onEdited,
  onTextReady,
  resolveInternalPage,
  onInternalPage,
}: {
  page: number;
  width: number;
  safeForm: boolean;
  query: string;
  searchOptions: PdfSearchOptions;
  uncontrolled: boolean;
  active: boolean;
  renderOverlay?: (pageNumber: number) => ReactNode;
  maxDevicePixelRatio: number;
  onRatio: (page: number, ratio: number) => void;
  onFormDetected: (page: number) => void;
  onEdited: (page: number) => void;
  onTextReady: (page: number) => void;
  resolveInternalPage: (target: PdfItemClickTarget) => Promise<number | null>;
  onInternalPage: (page: number) => void;
}) {
  const pageRef = useRef<HTMLElement | null>(null);
  const annotationGenerationRef = useRef(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState("");
  const [internalTargets, setInternalTargets] = useState<Record<string, PdfItemClickTarget>>({});
  const [internalPages, setInternalPages] = useState<Record<string, number>>({});

  useEffect(() => {
    annotationGenerationRef.current += 1;
    setReady(false);
    setFailed("");
    setInternalTargets({});
    setInternalPages({});
  }, [page, width]);

  useEffect(() => {
    if (!ready || !pageRef.current) return;
    const keys = Object.keys(internalTargets);
    const annotations = [...pageRef.current.querySelectorAll<HTMLElement>(".annotationLayer .linkAnnotation")];
    annotations.forEach((annotation, index) => {
      const id = annotation.dataset.annotationId || annotation.getAttribute("data-annotation-id") || keys[index];
      const targetPage = id ? internalPages[id] : undefined;
      const anchor = annotation.querySelector<HTMLAnchorElement>("a");
      if (!anchor || !targetPage) return;
      anchor.href = `#pdf-page-${targetPage}`;
      anchor.dataset.pdfTargetPage = String(targetPage);
      anchor.setAttribute("aria-label", `${anchor.getAttribute("aria-label") || "PDF link"} · page ${targetPage}`);
    });
  }, [internalPages, internalTargets, ready]);

  return (
    <article
      ref={pageRef}
      id={`pdf-page-${page}`}
      className={`pdfv3-page${ready ? " is-ready" : ""}${active ? " is-current" : ""}`}
      data-page-number={page}
      style={{ "--pdfv3-page-width": `${width}px` } as CSSProperties}
      onClickCapture={(event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        const annotation = target.closest<HTMLElement>(".annotationLayer .linkAnnotation");
        if (!annotation || !pageRef.current?.contains(annotation)) return;
        const keys = Object.keys(internalTargets);
        const annotations = [...pageRef.current.querySelectorAll<HTMLElement>(".annotationLayer .linkAnnotation")];
        const annotationId = annotation.dataset.annotationId
          || annotation.getAttribute("data-annotation-id")
          || keys[annotations.indexOf(annotation)];
        const targetPage = annotationId ? internalPages[annotationId] : undefined;
        if (!targetPage) return;
        event.preventDefault();
        event.stopPropagation();
        onInternalPage(targetPage);
      }}
      onInput={(event: FormEvent<HTMLElement>) => {
        if (safeForm && (event.target as HTMLElement).closest(".annotationLayer")) onEdited(page);
      }}
      onChange={(event: FormEvent<HTMLElement>) => {
        if (safeForm && (event.target as HTMLElement).closest(".annotationLayer")) onEdited(page);
      }}
    >
      {!ready ? (
        <div className="pdfv3-page-skeleton" role="status" aria-label={`Rendering page ${page}`}>
          {failed ? (
            <>
              <AlertTriangle size={18} />
              <span>{failed}</span>
            </>
          ) : (
            <>
              <LoaderCircle className="is-spinning" size={18} />
              <span>Rendering page {page}…</span>
            </>
          )}
        </div>
      ) : null}

      <div className="pdfv3-page-surface" aria-hidden={!ready}>
        <PdfPage
          pageNumber={page}
          width={width}
          renderMode="canvas"
          renderTextLayer
          renderAnnotationLayer
          renderForms={safeForm}
          devicePixelRatio={pdfDevicePixelRatio(maxDevicePixelRatio)}
          customTextRenderer={({ str }: { str: string }) => (
            highlightPdfText(str, query, searchOptions, false)
          )}
          loading={null}
          error={null}
          onGetAnnotationsSuccess={(annotations: PdfItemClickTarget[]) => {
            if (annotations.some((item) => item?.subtype === "Widget" || (item as any)?.fieldType)) {
              onFormDetected(page);
            }

            const links = annotations.filter((item) => (
              item?.subtype === "Link"
              && !item?.url
              && !item?.unsafeUrl
              && Boolean(
                item?.dest
                || item?.pageNumber
                || (item?.pageIndex !== undefined && item?.pageIndex !== null)
              )
            ));
            const targets = Object.fromEntries(
              links.map((item, index) => [String(item.id || `link-${index}`), item]),
            );
            setInternalTargets(targets);
            const generation = ++annotationGenerationRef.current;
            void Promise.all(
              Object.entries(targets).map(async ([id, item]) => [id, await resolveInternalPage(item)] as const),
            ).then((resolved) => {
              if (generation !== annotationGenerationRef.current) return;
              setInternalPages(Object.fromEntries(
                resolved.filter((entry): entry is readonly [string, number] => Boolean(entry[1])),
              ));
            });
          }}
          onLoadSuccess={(loaded: any) => {
            const originalWidth = Number(loaded?.originalWidth || loaded?.view?.[2] || 1);
            const originalHeight = Number(
              loaded?.originalHeight || loaded?.view?.[3] || originalWidth * 1.414,
            );
            onRatio(page, originalHeight / originalWidth);
          }}
          onRenderSuccess={() => {
            setFailed("");
            setReady(true);
          }}
          onRenderError={(error: unknown) => {
            setReady(false);
            setFailed(error instanceof Error ? error.message : `Page ${page} could not be rendered.`);
          }}
          onRenderTextLayerSuccess={() => onTextReady(page)}
        />
      </div>

      {uncontrolled ? <span className="pdfv3-watermark">UNCONTROLLED DRAFT</span> : null}
      {renderOverlay?.(page)}
    </article>
  );
}

export default function PdfReaderCoreV3({
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
  const capabilities = suppliedCapabilities || READ_ONLY;
  const profile = useMemo(() => getPdfReaderPerformanceProfile(), []);
  const hostRef = useRef<HTMLElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pdfRef = useRef<PdfDocumentHandle | null>(null);
  const serializationRef = useRef<Promise<Uint8Array> | null>(null);
  const autosaveTimerRef = useRef<number | null>(null);
  const autosaveInFlightRef = useRef<Promise<void> | null>(null);
  const autosaveQueuedRef = useRef(false);
  const editGenerationRef = useRef(0);
  const lifecycleGenerationRef = useRef(0);
  const dirtyRef = useRef(false);
  const editedPagesRef = useRef<number[]>([]);
  const currentPageRef = useRef(Math.max(1, initialPage));
  const pendingPageRef = useRef<number | null>(null);
  const navigationTimerRef = useRef<number | null>(null);
  const scrollFrameRef = useRef<number | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const searchControllerRef = useRef<AbortController | null>(null);

  const [draft, setDraft] = useState<StoredPdfWorkingCopy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [pageInput, setPageInput] = useState(String(Math.max(1, initialPage)));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [hostSize, setHostSize] = useState({ width: 960, height: 720 });
  const [zoom, setZoom] = useState(clampPdfValue(initialZoom, 50, 250));
  const [fitMode, setFitMode] = useState<"WIDTH" | "PAGE" | "CUSTOM">("WIDTH");
  const [formPages, setFormPages] = useState<number[]>([]);
  const [formDetectedByDocument, setFormDetectedByDocument] = useState(false);
  const [editedPages, setEditedPages] = useState<number[]>([]);
  const [dirty, setDirty] = useState(false);
  const [draftState, setDraftState] = useState<"" | "SAVING" | "SAVED" | "ERROR">("");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState<"" | "ORIGINAL" | "WORKING" | "FLATTEN" | "SUBMIT">("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOptions, setSearchOptions] = useState<PdfSearchOptions>({
    caseSensitive: false,
    wholeWord: false,
  });
  const [searchResults, setSearchResults] = useState<PdfSearchResult[]>([]);
  const [searchIndex, setSearchIndex] = useState(-1);
  const [searchBusy, setSearchBusy] = useState(false);
  const [hotIndexes, setHotIndexes] = useState<number[]>([]);

  const source = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const readerFile = useMemo(
    () => (draft ? { data: new Uint8Array(draft.bytes.slice(0)) } : source),
    [draft, source],
  );
  const outputName = safePdfFilename(filename || "", `${title}.pdf`);
  const formDetected = Boolean(capabilities.has_acroform || formDetectedByDocument);
  const safeForm = Boolean(
    capabilities.can_fill
      && formDetected
      && !capabilities.has_javascript
      && !capabilities.is_dynamic_xfa
      && !capabilities.encrypted,
  );

  const availableWidth = Math.max(280, Math.min(1800, hostSize.width - (compact ? 16 : 34)));
  const currentRatio = pageRatios[currentPage] || 1.414;
  const pageWidth = Math.round(
    fitMode === "PAGE"
      ? Math.max(230, Math.min(availableWidth, (hostSize.height - 48) / currentRatio))
      : fitMode === "CUSTOM"
        ? availableWidth * (zoom / 100)
        : availableWidth,
  );

  const rangeExtractor = useCallback((range: Range) => {
    const visible = defaultRangeExtractor(range);
    const retained = hotIndexes.filter((index) => index >= 0 && index < pageCount);
    return [...new Set([...visible, ...retained])].sort((left, right) => left - right);
  }, [hotIndexes, pageCount]);

  const virtualizer = useVirtualizer({
    count: pageCount,
    getScrollElement: () => viewportRef.current,
    estimateSize: (index) => (
      Math.round(pageWidth * (pageRatios[index + 1] || 1.414)) + PAGE_GAP
    ),
    overscan: profile.mode === "constrained" ? 1 : profile.mode === "burst" ? 3 : 2,
    rangeExtractor,
    getItemKey: (index) => index + 1,
  });

  const settleNavigation = useCallback((page: number) => {
    if (pendingPageRef.current !== page) return;
    pendingPageRef.current = null;
    setActionError("");
    if (navigationTimerRef.current !== null) {
      window.clearTimeout(navigationTimerRef.current);
      navigationTimerRef.current = null;
    }
  }, []);

  const pageIsAtReadingLine = useCallback((page: number): boolean => {
    const viewport = viewportRef.current;
    if (!viewport) return false;
    const anchor = viewport.scrollTop + PAGE_TOP_INSET;
    const item = virtualizer.getVirtualItems().find((candidate) => candidate.index === page - 1);
    return Boolean(item && item.start <= anchor + 2 && item.end > anchor);
  }, [virtualizer]);

  const publishPhysicalPage = useCallback((page: number) => {
    const next = clampPdfValue(page, 1, Math.max(1, pageCount));
    settleNavigation(next);
    if (next === currentPageRef.current) return;
    currentPageRef.current = next;
    setCurrentPage(next);
    setPageInput(String(next));
    onPageChange?.(next);

    setHotIndexes((current) => {
      const candidates = [
        next - 1,
        next,
        next + 1,
        ...current.map((index) => index + 1),
      ]
        .filter((value) => value >= 1 && value <= pageCount)
        .map((value) => value - 1);
      const limit = profile.mode === "burst" ? 10 : profile.mode === "constrained" ? 4 : 7;
      return [...new Set(candidates)].slice(0, limit);
    });

  }, [onPageChange, pageCount, profile.mode, settleNavigation]);

  const synchronizePhysicalPage = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !pageCount) return;
    const anchor = viewport.scrollTop + PAGE_TOP_INSET;
    const items = virtualizer.getVirtualItems();
    if (!items.length) return;

    const containing = items.find((item) => item.start <= anchor && item.end > anchor);
    const closest = containing || items.reduce((best, item) => (
      Math.abs(item.start - anchor) < Math.abs(best.start - anchor) ? item : best
    ), items[0]);
    publishPhysicalPage(closest.index + 1);
  }, [pageCount, publishPhysicalPage, virtualizer]);

  const schedulePhysicalSync = useCallback(() => {
    if (scrollFrameRef.current !== null) return;
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      synchronizePhysicalPage();
    });
  }, [synchronizePhysicalPage]);

  const jump = useCallback((requested: number, behavior: ScrollBehavior = "auto") => {
    if (!pageCount) return;
    const page = clampPdfValue(requested, 1, pageCount);
    pendingPageRef.current = page;
    setActionError("");

    if (navigationTimerRef.current !== null) window.clearTimeout(navigationTimerRef.current);
    navigationTimerRef.current = window.setTimeout(() => {
      window.requestAnimationFrame(() => {
        synchronizePhysicalPage();
        if (currentPageRef.current === page || pageIsAtReadingLine(page)) {
          settleNavigation(page);
        } else if (pendingPageRef.current === page) {
          pendingPageRef.current = null;
          setActionError(`Page ${page} could not be brought into view. Retry the navigation action.`);
        }
        navigationTimerRef.current = null;
      });
    }, NAVIGATION_TIMEOUT_MS);

    virtualizer.scrollToIndex(page - 1, { align: "start", behavior });
    window.requestAnimationFrame(() => {
      virtualizer.scrollToIndex(page - 1, { align: "start", behavior: "auto" });
      schedulePhysicalSync();
    });
  }, [
    pageCount,
    pageIsAtReadingLine,
    schedulePhysicalSync,
    settleNavigation,
    synchronizePhysicalPage,
    virtualizer,
  ]);

  const setDirtyState = useCallback((value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
    onDirtyChange?.(value);
  }, [onDirtyChange]);

  const setEditedState = useCallback((values: Iterable<number>) => {
    const pages = uniquePages(values);
    editedPagesRef.current = pages;
    setEditedPages(pages);
  }, []);

  const clearAutosaveTimer = useCallback(() => {
    if (autosaveTimerRef.current !== null) {
      window.clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
  }, []);

  const serialize = useCallback(async (): Promise<Uint8Array> => {
    if (!pdfRef.current?.saveDocument) {
      throw new Error("This PDF cannot be saved as a working copy.");
    }
    if (!serializationRef.current) {
      serializationRef.current = pdfRef.current.saveDocument()
        .finally(() => { serializationRef.current = null; });
    }
    return serializationRef.current;
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
    const savingPages = [...editedPagesRef.current];
    setDraftState("SAVING");

    const task = (async () => {
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
        if (isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)) {
          setDraftState("ERROR");
        }
      } finally {
        autosaveInFlightRef.current = null;
        const followUp = autosaveQueuedRef.current
          && isPdfDraftLifecycleCurrent(savingLifecycle, lifecycleGenerationRef.current)
          && dirtyRef.current;
        autosaveQueuedRef.current = false;
        if (followUp) window.setTimeout(() => void persistDraft(), 0);
      }
    })();

    autosaveInFlightRef.current = task;
    await task;
  }, [
    capabilities.can_save_draft,
    capabilities.source_sha256,
    identity,
    outputName,
    serialize,
    setDirtyState,
  ]);

  const markEdited = useCallback((page: number) => {
    editGenerationRef.current += 1;
    setEditedState([...editedPagesRef.current, Math.max(1, page)]);
    setDirtyState(true);
    setDraftState("");
    clearAutosaveTimer();
    if (capabilities.can_save_draft) {
      autosaveTimerRef.current = window.setTimeout(() => {
        autosaveTimerRef.current = null;
        void persistDraft();
      }, 700);
    }
  }, [
    capabilities.can_save_draft,
    clearAutosaveTimer,
    persistDraft,
    setDirtyState,
    setEditedState,
  ]);

  useEffect(() => {
    const host = hostRef.current;
    const viewport = viewportRef.current;
    if (!host || !viewport) return;

    const update = () => setHostSize({
      width: Math.max(320, viewport.clientWidth),
      height: Math.max(420, viewport.clientHeight),
    });
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(viewport);
    return () => observer?.disconnect();
  }, []);

  useEffect(() => {
    virtualizer.measure();
  }, [pageRatios, pageWidth, virtualizer]);

  useEffect(() => {
    onZoomChange?.(
      fitMode === "CUSTOM" ? zoom : Math.round((pageWidth / availableWidth) * 100),
    );
  }, [availableWidth, fitMode, onZoomChange, pageWidth, zoom]);

  useEffect(() => {
    onAcroFormDetected?.(formDetected);
  }, [formDetected, onAcroFormDetected]);

  useEffect(() => {
    lifecycleGenerationRef.current += 1;
    editGenerationRef.current = 0;
    autosaveQueuedRef.current = false;
    clearAutosaveTimer();
  }, [
    capabilities.source_sha256,
    clearAutosaveTimer,
    identity.manualId,
    identity.revisionId,
    identity.tenant,
  ]);

  useEffect(() => {
    if (!capabilities.source_sha256) return;
    let active = true;
    readPdfWorkingCopy(identity)
      .then((stored) => {
        if (!active || !stored) return;
        setDraft(stored);
        setEditedState(stored.editedPages || []);
        setDirtyState(true);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [
    capabilities.source_sha256,
    identity,
    setDirtyState,
    setEditedState,
  ]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  useEffect(() => () => {
    lifecycleGenerationRef.current += 1;
    clearAutosaveTimer();
    searchControllerRef.current?.abort();
    if (navigationTimerRef.current !== null) window.clearTimeout(navigationTimerRef.current);
    if (scrollFrameRef.current !== null) window.cancelAnimationFrame(scrollFrameRef.current);
  }, [clearAutosaveTimer]);

  useEffect(() => {
    if (navigationRequest?.page && pageCount) {
      jump(navigationRequest.page, "auto");
    }
  }, [jump, navigationRequest?.page, navigationRequest?.token, pageCount]);

  useEffect(() => {
    if (!pageCount) return;
    const openHashDestination = () => {
      const match = window.location.hash.match(/^#pdf-page-(\d+)$/i);
      if (!match) return;
      jump(Number(match[1]), "auto");
    };
    openHashDestination();
    window.addEventListener("hashchange", openHashDestination);
    return () => window.removeEventListener("hashchange", openHashDestination);
  }, [jump, pageCount]);

  const loadDocument = useCallback((pdf: PdfDocumentHandle) => {
    pdfRef.current = pdf;
    const count = Math.max(1, Number(pdf.numPages || 1));
    const restored = clampPdfValue(initialPage, 1, count);
    currentPageRef.current = restored;
    setCurrentPage(restored);
    setPageInput(String(restored));
    setPageCount(count);
    setPageRatios({});
    setLoadError("");
    setHotIndexes([restored - 1]);

    if (pdf.annotationStorage) {
      pdf.annotationStorage.onSetModified = () => markEdited(currentPageRef.current);
    }

    Promise.all([
      pdf.getFieldObjects?.().catch(() => null) || null,
      resolveOutline(pdf),
    ]).then(([fields, outline]) => {
      const pages = detectedFormPages(fields, count);
      setFormPages(pages);
      setFormDetectedByDocument(Boolean(Object.values(fields || {}).flat().length));
      onOutlineReady?.(outline);
    }).catch(() => undefined);

    window.requestAnimationFrame(() => {
      virtualizer.scrollToIndex(restored - 1, { align: "start", behavior: "auto" });
      schedulePhysicalSync();
    });
  }, [
    initialPage,
    markEdited,
    onOutlineReady,
    schedulePhysicalSync,
    virtualizer,
  ]);

  const resolvePdfTargetPage = useCallback(async (
    target: PdfItemClickTarget,
  ): Promise<number | null> => {
    let page = Number(target.pageNumber || 0);
    if (!page && target.pageIndex !== null && target.pageIndex !== undefined) {
      const index = Number(target.pageIndex);
      if (Number.isInteger(index) && index >= 0) page = index + 1;
    }

    let destination = target.dest;
    const pdf = pdfRef.current;
    if (!page && typeof destination === "string" && pdf?.getDestination) {
      destination = await pdf.getDestination(destination).catch(() => null);
    }
    if (!page && Array.isArray(destination)) {
      const reference = destination[0];
      if (typeof reference === "number") page = reference + 1;
      else if (reference && pdf?.getPageIndex) {
        page = (await pdf.getPageIndex(reference).catch(() => -1)) + 1;
      }
    }

    return page > 0 ? clampPdfValue(page, 1, Math.max(1, pageCount)) : null;
  }, [pageCount]);

  const followPdfItem = useCallback(async (target: PdfItemClickTarget) => {
    try {
      const page = await resolvePdfTargetPage(target);
      if (page) {
        window.history.replaceState(null, "", `#pdf-page-${page}`);
        jump(page, "auto");
        return;
      }
      setActionError("The selected PDF link does not contain a resolvable page destination.");
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "The selected PDF link could not be opened.",
      );
    }
  }, [jump, resolvePdfTargetPage]);

  const workingFile = useCallback(async () => new File(
    [copyPdfBytes(await serialize())],
    outputPdfFilename(outputName, "WORKING_COPY"),
    { type: "application/pdf" },
  ), [outputName, serialize]);

  const perform = async (
    kind: typeof busy,
    action: () => Promise<void>,
  ): Promise<void> => {
    setBusy(kind);
    setActionError("");
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The PDF action failed.");
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
      : await submitPdfWorkingCopy(
        identity.tenant,
        identity.manualId,
        identity.revisionId,
        file,
        { completed_page_numbers: editedPages.length ? editedPages : formPages },
      );

    lifecycleGenerationRef.current += 1;
    editGenerationRef.current = 0;
    setRecord(created);
    setDirtyState(false);
    setEditedState([]);
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setDraft(null);
    onRecordCreated?.(created);
  });

  const discard = async (): Promise<void> => {
    if (dirty && !window.confirm("Discard the working copy?")) return;
    lifecycleGenerationRef.current += 1;
    editGenerationRef.current = 0;
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setDraft(null);
    setDirtyState(false);
    setEditedState([]);
    setDraftState("");
  };

  const revealSearchResult = useCallback((result?: PdfSearchResult, attempt = 0) => {
    if (!result) return;
    const viewport = viewportRef.current;
    const page = viewport?.querySelector<HTMLElement>(
      `[data-page-number="${result.page}"]`,
    );
    if (!viewport || !page) {
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
    const viewportRect = viewport.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    if (
      targetRect.top < viewportRect.top + 18
      || targetRect.bottom > viewportRect.bottom - 18
    ) {
      viewport.scrollBy({
        top: targetRect.top - viewportRect.top - 40,
        behavior: "smooth",
      });
    }
  }, []);

  const runSearch = async (): Promise<void> => {
    if (!pdfRef.current || query.trim().length < 2) return;
    searchControllerRef.current?.abort();
    const controller = new AbortController();
    searchControllerRef.current = controller;
    setSearchBusy(true);

    try {
      const rows = await searchPdfDocument(
        pdfRef.current as any,
        query.trim(),
        searchOptions,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setSearchResults(rows);
      setSearchIndex(rows.length ? 0 : -1);
      if (rows[0]) {
        jump(rows[0].page, "auto");
        window.setTimeout(() => revealSearchResult(rows[0]), 80);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setActionError(error instanceof Error ? error.message : "PDF search failed.");
      }
    } finally {
      if (searchControllerRef.current === controller) searchControllerRef.current = null;
      if (!controller.signal.aborted) setSearchBusy(false);
    }
  };

  const moveSearch = (step: number): void => {
    if (!searchResults.length) return;
    const index = (searchIndex + step + searchResults.length) % searchResults.length;
    const result = searchResults[index];
    setSearchIndex(index);
    jump(result.page, "auto");
    window.setTimeout(() => revealSearchResult(result), 80);
  };

  const activeResult = searchResults[searchIndex];
  const virtualItems = virtualizer.getVirtualItems();
  const requestedIndex = pendingPageRef.current ? pendingPageRef.current - 1 : -1;
  const currentIndex = currentPage - 1;
  const orderedVirtualItems = [...virtualItems].sort((left, right) => {
    const priority = (index: number) => (
      index === requestedIndex ? 0 : index === currentIndex ? 1 : 2
    );
    const difference = priority(left.index) - priority(right.index);
    return difference || left.index - right.index;
  });

  return (
    <section
      ref={hostRef}
      className={`pdfv3-reader${compact ? " is-compact" : ""}${safeForm ? " is-form-active" : ""}`}
      onKeyDown={(event: ReactKeyboardEvent<HTMLElement>) => {
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "f") return;
        event.preventDefault();
        setSearchOpen(true);
        window.requestAnimationFrame(() => searchInputRef.current?.focus());
      }}
    >
      <header className="pdfv3-toolbar">
        <div className="pdfv3-pages">
          <button
            type="button"
            aria-label="Previous page"
            onClick={() => jump(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            <ChevronLeft size={17} />
          </button>
          <input
            value={pageInput}
            aria-label="Page number"
            inputMode="numeric"
            onChange={(event: ChangeEvent<HTMLInputElement>) => (
              setPageInput(event.target.value.replace(/\D+/g, ""))
            )}
            onBlur={() => jump(Number(pageInput || currentPage))}
            onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
              if (event.key === "Enter") jump(Number(pageInput || currentPage));
            }}
          />
          <span>/ {pageCount || "—"}</span>
          <button
            type="button"
            aria-label="Next page"
            onClick={() => jump(currentPage + 1)}
            disabled={!pageCount || currentPage >= pageCount}
          >
            <ChevronRight size={17} />
          </button>
        </div>

        <div className="pdfv3-zoom">
          <button
            type="button"
            aria-label="Zoom out"
            onClick={() => {
              setFitMode("CUSTOM");
              setZoom((value) => clampPdfValue(value - 10, 50, 250));
            }}
          >
            <Minus size={17} />
          </button>
          <button
            type="button"
            onClick={() => {
              if (fitMode === "WIDTH") setFitMode("PAGE");
              else if (fitMode === "PAGE") {
                setFitMode("CUSTOM");
                setZoom(100);
              } else setFitMode("WIDTH");
            }}
          >
            {fitMode === "WIDTH" ? "Fit width" : fitMode === "PAGE" ? "Fit page" : `${zoom}%`}
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            onClick={() => {
              setFitMode("CUSTOM");
              setZoom((value) => clampPdfValue(value + 10, 50, 250));
            }}
          >
            <Plus size={17} />
          </button>
        </div>

        <div className="pdfv3-actions">
          <button
            type="button"
            className={searchOpen ? "active" : ""}
            onClick={() => {
              setSearchOpen((value) => !value);
              window.requestAnimationFrame(() => searchInputRef.current?.focus());
            }}
          >
            <Search size={16} />
            <span>Search</span>
          </button>

          {safeForm ? (
            <span className="pdfv3-form-state">
              <FilePenLine size={15} />
              Form active{editedPages.length ? ` · ${editedPages.length} changed` : ""}
            </span>
          ) : null}

          <details className="pdfv3-menu">
            <summary>
              <Download size={16} />
              <span>Download</span>
            </summary>
            <div>
              <button
                type="button"
                disabled={Boolean(busy) || !capabilities.can_download_original}
                onClick={() => void downloadOriginal()}
              >
                Original PDF
              </button>
              <button
                type="button"
                disabled={
                  Boolean(busy)
                  || !capabilities.can_download_working
                  || !pdfRef.current?.saveDocument
                }
                onClick={() => void downloadWorking()}
              >
                Editable PDF
              </button>
              <button
                type="button"
                disabled={
                  Boolean(busy)
                  || !capabilities.can_flatten
                  || !safeForm
                  || !pdfRef.current?.saveDocument
                }
                onClick={() => void downloadCompleted()}
              >
                Completed form pages{editedPages.length ? ` (${editedPages.length})` : ""}
              </button>
            </div>
          </details>

          <details className="pdfv3-menu">
            <summary aria-label="More PDF actions">
              <MoreHorizontal size={18} />
            </summary>
            <div>
              {capabilities.can_submit ? (
                <button type="button" disabled={Boolean(busy)} onClick={() => void submit()}>
                  Submit retained record
                </button>
              ) : null}
              {draft || dirty ? (
                <button type="button" onClick={() => void discard()}>
                  <Trash2 size={14} />
                  Discard working copy
                </button>
              ) : null}
            </div>
          </details>
        </div>
      </header>

      {searchOpen ? (
        <div className="pdfv3-search">
          <Search size={16} />
          <input
            ref={searchInputRef}
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
            onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
              if (event.key === "Enter") void runSearch();
            }}
            placeholder="Search this PDF"
          />
          <label>
            <input
              type="checkbox"
              checked={Boolean(searchOptions.caseSensitive)}
              onChange={(event: ChangeEvent<HTMLInputElement>) => (
                setSearchOptions((value) => ({
                  ...value,
                  caseSensitive: event.target.checked,
                }))
              )}
            />
            Aa
          </label>
          <label>
            <input
              type="checkbox"
              checked={Boolean(searchOptions.wholeWord)}
              onChange={(event: ChangeEvent<HTMLInputElement>) => (
                setSearchOptions((value) => ({
                  ...value,
                  wholeWord: event.target.checked,
                }))
              )}
            />
            Word
          </label>
          <button
            type="button"
            disabled={searchBusy || query.trim().length < 2}
            onClick={() => void runSearch()}
          >
            {searchBusy ? <LoaderCircle className="is-spinning" size={15} /> : "Find"}
          </button>
          <span>{searchResults.length ? `${searchIndex + 1}/${searchResults.length}` : ""}</span>
          <button
            type="button"
            aria-label="Previous search result"
            disabled={!searchResults.length}
            onClick={() => moveSearch(-1)}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            aria-label="Next search result"
            disabled={!searchResults.length}
            onClick={() => moveSearch(1)}
          >
            <ChevronRight size={16} />
          </button>
          <button
            type="button"
            aria-label="Close PDF search"
            onClick={() => {
              searchControllerRef.current?.abort();
              setSearchBusy(false);
              setSearchOpen(false);
            }}
          >
            <X size={16} />
          </button>
        </div>
      ) : null}

      {capabilities.unsupported_reason && !safeForm ? (
        <div className="pdfv3-notice">
          <AlertTriangle size={16} />
          {capabilities.unsupported_reason}
        </div>
      ) : null}
      {formDetected && !safeForm && !capabilities.unsupported_reason ? (
        <div className="pdfv3-notice">
          <AlertTriangle size={16} />
          This PDF contains form fields, but controlled form execution is unavailable.
        </div>
      ) : null}
      {safeForm ? (
        <div className="pdfv3-notice pdfv3-notice--form">
          <FilePenLine size={16} />
          Fields are active. Entries remain in a local working copy until download or submission.
          <small>
            {draftState === "SAVING"
              ? "Saving…"
              : draftState === "SAVED"
                ? "Saved"
                : draftState === "ERROR"
                  ? "Save failed"
                  : ""}
          </small>
        </div>
      ) : null}
      {actionError ? (
        <div className="pdfv3-error" role="alert">
          <AlertTriangle size={17} />
          {actionError}
        </div>
      ) : null}
      {record ? (
        <div className="pdfv3-success">
          <CheckCircle2 size={17} />
          Record {record.record_number} created.
          <a href={record.download_url}>Open</a>
        </div>
      ) : null}

      <div
        ref={viewportRef}
        className="pdfv3-viewport"
        onScroll={schedulePhysicalSync}
      >
        {loadError ? (
          <div className="pdfv3-document-error" role="alert">
            <AlertTriangle size={20} />
            <strong>The PDF could not be opened.</strong>
            <span>{loadError}</span>
          </div>
        ) : null}

        <PdfDocument
          file={readerFile}
          options={PDF_DOCUMENT_OPTIONS}
          externalLinkTarget="_blank"
          externalLinkRel="noopener noreferrer"
          onLoadSuccess={loadDocument}
          onLoadError={(error: unknown) => {
            setLoadError(error instanceof Error ? error.message : "The PDF could not be opened.");
          }}
          onItemClick={(target: PdfItemClickTarget) => { void followPdfItem(target); }}
          loading={(
            <div className="pdfv3-document-loading" role="status">
              <LoaderCircle className="is-spinning" size={20} />
              Opening document…
            </div>
          )}
        >
          <div
            className="pdfv3-virtual-canvas"
            style={{ height: `${virtualizer.getTotalSize()}px` }}
          >
            {orderedVirtualItems.map((item) => {
              const page = item.index + 1;
              return (
                <div
                  key={item.key}
                  ref={(element) => {
                    if (element) virtualizer.measureElement(element);
                  }}
                  className="pdfv3-virtual-row"
                  data-index={item.index}
                  style={{
                    transform: `translateY(${item.start}px)`,
                    minHeight: `${item.size}px`,
                  }}
                >
                  <VirtualPdfPage
                    page={page}
                    width={pageWidth}
                    safeForm={safeForm}
                    query={query}
                    searchOptions={searchOptions}
                    uncontrolled={uncontrolled}
                    active={page === currentPage}
                    renderOverlay={renderPageOverlay}
                    maxDevicePixelRatio={profile.maxDevicePixelRatio}
                    onRatio={(pageNumber, nextRatio) => {
                      setPageRatios((values) => (
                        Math.abs((values[pageNumber] || 0) - nextRatio) < 0.0001
                          ? values
                          : { ...values, [pageNumber]: nextRatio }
                      ));
                    }}
                    onFormDetected={(pageNumber) => {
                      setFormDetectedByDocument(true);
                      setFormPages((values) => uniquePages([...values, pageNumber]));
                      onAcroFormDetected?.(true);
                    }}
                    onEdited={markEdited}
                    onTextReady={(pageNumber) => {
                      if (activeResult?.page === pageNumber) {
                        window.requestAnimationFrame(() => revealSearchResult(activeResult));
                      }
                    }}
                    resolveInternalPage={resolvePdfTargetPage}
                    onInternalPage={(pageNumber) => {
                      window.history.replaceState(null, "", `#pdf-page-${pageNumber}`);
                      jump(pageNumber, "auto");
                    }}
                  />
                </div>
              );
            })}
          </div>
        </PdfDocument>
      </div>
    </section>
  );
}

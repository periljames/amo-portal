import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
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
import * as pdfjsLib from "pdfjs-dist";
import * as pdfjsViewer from "pdfjs-dist/web/pdf_viewer.mjs";

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
  copyPdfBytes,
  outputPdfFilename,
  safePdfFilename,
} from "./pdfReaderEngine";
import { PDF_DOCUMENT_OPTIONS } from "./pdfReaderConfig";
import {
  deletePdfWorkingCopy,
  readPdfWorkingCopy,
  savePdfWorkingCopy,
  type PdfWorkingCopyIdentity,
  type StoredPdfWorkingCopy,
} from "./pdfWorkingCopyStore";
import "pdfjs-dist/web/pdf_viewer.css";
import "./pdfJsControlledViewer.css";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type PdfDocumentHandle = {
  numPages: number;
  annotationStorage?: {
    onSetModified?: () => void;
    onResetModified?: () => void;
  };
  getOutline?: () => Promise<any[] | null>;
  getDestination?: (name: string) => Promise<any[] | null>;
  getPageIndex?: (value: unknown) => Promise<number>;
  getFieldObjects?: () => Promise<Record<string, Array<Record<string, unknown>>> | null>;
  saveDocument?: () => Promise<Uint8Array>;
  destroy?: () => Promise<void>;
};

type PdfLoadingTask = {
  promise: Promise<PdfDocumentHandle>;
  destroy?: () => Promise<void>;
};

type PdfViewerHandle = {
  pagesCount: number;
  currentPageNumber: number;
  currentScale: number;
  currentScaleValue: string | number;
  setDocument: (document: PdfDocumentHandle | null) => void;
  scrollPageIntoView: (options: { pageNumber: number; destArray?: unknown[] }) => void;
  cleanup?: () => void;
};

type PdfLinkServiceHandle = {
  setViewer: (viewer: PdfViewerHandle) => void;
  setDocument: (document: PdfDocumentHandle | null, baseUrl?: string | null) => void;
};

type PdfFindControllerHandle = {
  setDocument?: (document: PdfDocumentHandle | null) => void;
};

type ViewerEventBus = {
  on: (name: string, listener: (event: any) => void) => void;
  off: (name: string, listener: (event: any) => void) => void;
  dispatch: (name: string, payload: Record<string, unknown>) => void;
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

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

const normalizedPages = (values: Iterable<number>) =>
  [...new Set(values)]
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
  return rows.sort((left, right) => left.page - right.page || left.level - right.level);
}

function formPagesFromFields(
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
  return normalizedPages(pages);
}

function pageNumberFromTarget(target: EventTarget | null, fallback: number): number {
  if (!(target instanceof Element)) return fallback;
  const page = Number(target.closest<HTMLElement>(".page[data-page-number]")?.dataset.pageNumber || 0);
  return Number.isInteger(page) && page > 0 ? page : fallback;
}

/**
 * Controlled PDF reader built on PDF.js' own PDFViewer, rendering queue,
 * link service and find controller. The browser viewer owns page lifecycle;
 * React owns only commands, verified state and controlled-record actions.
 */
export default function PdfReaderCoreV2({
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
  const hostRef = useRef<HTMLElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const viewerElementRef = useRef<HTMLDivElement | null>(null);
  const pdfRef = useRef<PdfDocumentHandle | null>(null);
  const viewerRef = useRef<PdfViewerHandle | null>(null);
  const eventBusRef = useRef<ViewerEventBus | null>(null);
  const loadingTaskRef = useRef<PdfLoadingTask | null>(null);
  const currentPageRef = useRef(Math.max(1, initialPage));
  const autosaveTimerRef = useRef<number | null>(null);
  const serializingRef = useRef<Promise<Uint8Array> | null>(null);
  const editedPagesRef = useRef(new Set<number>());
  const dirtyRef = useRef(false);
  const overlayNodesRef = useRef(new Map<number, HTMLElement>());
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [draftResolved, setDraftResolved] = useState(!capabilities.source_sha256);
  const [draft, setDraft] = useState<StoredPdfWorkingCopy | null>(null);
  const [hasDraft, setHasDraft] = useState(false);
  const [pageCount, setPageCount] = useState(Math.max(0, capabilities.page_count || 0));
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [pageInput, setPageInput] = useState(String(Math.max(1, initialPage)));
  const [zoomMode, setZoomMode] = useState<"WIDTH" | "PAGE" | "CUSTOM">(
    initialZoom === 100 ? "WIDTH" : "CUSTOM",
  );
  const [zoomPercent, setZoomPercent] = useState(clamp(initialZoom, 50, 250));
  const [fieldCount, setFieldCount] = useState(0);
  const [formPages, setFormPages] = useState<number[]>([]);
  const [editedPages, setEditedPages] = useState<number[]>([]);
  const [dirty, setDirty] = useState(false);
  const [draftState, setDraftState] = useState<"" | "SAVING" | "SAVED" | "ERROR">("");
  const [loadState, setLoadState] = useState<"LOADING" | "READY" | "ERROR">("LOADING");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState<"" | "ORIGINAL" | "WORKING" | "FLATTEN" | "SUBMIT">("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [findCount, setFindCount] = useState({ current: 0, total: 0 });
  const [overlayRevision, setOverlayRevision] = useState(0);

  const outputName = safePdfFilename(filename || "", `${title}.pdf`);
  const formDetected = Boolean(capabilities.has_acroform || fieldCount > 0);
  const safeForm = Boolean(
    capabilities.can_fill
      && formDetected
      && !capabilities.has_javascript
      && !capabilities.is_dynamic_xfa
      && !capabilities.encrypted,
  );

  const setDirtyState = useCallback((value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
    onDirtyChange?.(value);
  }, [onDirtyChange]);

  const setEdited = useCallback((values: Iterable<number>) => {
    const pages = normalizedPages(values);
    editedPagesRef.current = new Set(pages);
    setEditedPages(pages);
  }, []);

  useEffect(() => {
    let active = true;
    if (!capabilities.source_sha256) {
      setDraftResolved(true);
      return () => { active = false; };
    }

    setDraftResolved(false);
    readPdfWorkingCopy(identity)
      .then((stored) => {
        if (!active) return;
        if (stored) {
          setDraft(stored);
          setHasDraft(true);
          setEdited(stored.editedPages || []);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setDraftResolved(true);
      });

    return () => { active = false; };
  }, [
    capabilities.source_sha256,
    identity.manualId,
    identity.revisionId,
    identity.tenant,
    identity.userId,
    setEdited,
  ]);

  const source = useMemo(() => {
    if (draft) {
      return {
        data: new Uint8Array(draft.bytes.slice(0)),
        ...PDF_DOCUMENT_OPTIONS,
        enableXfa: false,
        isEvalSupported: false,
      };
    }
    return {
      ...publicationPdfSource(fileUrl),
      ...PDF_DOCUMENT_OPTIONS,
      enableXfa: false,
      isEvalSupported: false,
    };
  }, [draft, fileUrl]);

  const sourceKey = draft
    ? `draft:${draft.savedAt}:${draft.byteLength}`
    : `source:${fileUrl}:${capabilities.source_sha256}`;

  const publishConfirmedPage = useCallback((page: number) => {
    if (!Number.isInteger(page) || page < 1) return;
    currentPageRef.current = page;
    setCurrentPage((value) => value === page ? value : page);
    setPageInput(String(page));
    onPageChange?.(page);

    const viewer = viewerElementRef.current;
    viewer?.querySelectorAll<HTMLElement>(".page.is-current").forEach((element) => {
      element.classList.remove("is-current");
    });
    viewer?.querySelector<HTMLElement>(`.page[data-page-number="${page}"]`)?.classList.add("is-current");
    hostRef.current?.setAttribute("data-current-page", String(page));
  }, [onPageChange]);

  const navigateToPage = useCallback((requested: number) => {
    const viewer = viewerRef.current;
    const count = pageCount || viewer?.pagesCount || 0;
    if (!viewer || !count) return;
    const page = clamp(Math.trunc(requested || currentPageRef.current), 1, count);
    setActionError("");
    viewer.scrollPageIntoView({ pageNumber: page });
    // Do not publish here. updateviewarea is the single authority after the
    // physical viewer has moved.
  }, [pageCount]);

  const applyScale = useCallback((mode: "WIDTH" | "PAGE" | "CUSTOM", value = zoomPercent) => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    setZoomMode(mode);
    if (mode === "CUSTOM") setZoomPercent(clamp(value, 50, 250));
    if (mode === "WIDTH") viewer.currentScaleValue = "page-width";
    else if (mode === "PAGE") viewer.currentScaleValue = "page-fit";
    else viewer.currentScaleValue = clamp(value, 50, 250) / 100;
  }, [zoomPercent]);

  useEffect(() => {
    if (!draftResolved) return;
    const container = viewportRef.current;
    const viewerElement = viewerElementRef.current;
    if (!container || !viewerElement) return;

    let active = true;
    setLoadState("LOADING");
    setLoadError("");
    setActionError("");
    setPageCount(Math.max(0, capabilities.page_count || 0));
    overlayNodesRef.current.clear();
    viewerElement.replaceChildren();

    const eventBus = new pdfjsViewer.EventBus() as unknown as ViewerEventBus;
    const linkService = new pdfjsViewer.PDFLinkService({
      eventBus,
      externalLinkTarget: 2,
      externalLinkRel: "noopener noreferrer",
    } as any) as unknown as PdfLinkServiceHandle;
    const findController = new pdfjsViewer.PDFFindController({
      eventBus,
      linkService,
    }) as unknown as PdfFindControllerHandle;
    const viewer = new pdfjsViewer.PDFViewer({
      container,
      eventBus,
      linkService,
      findController,
      annotationMode: pdfjsLib.AnnotationMode.ENABLE_FORMS,
      textLayerMode: 1,
      removePageBorders: false,
      enableHWA: true,
    } as any) as unknown as PdfViewerHandle;

    eventBusRef.current = eventBus;
    viewerRef.current = viewer;
    linkService.setViewer(viewer);

    const onPagesInit = () => {
      if (!active) return;
      setLoadState("READY");
      const mode = zoomMode;
      if (mode === "WIDTH") viewer.currentScaleValue = "page-width";
      else if (mode === "PAGE") viewer.currentScaleValue = "page-fit";
      else viewer.currentScaleValue = clamp(zoomPercent, 50, 250) / 100;
      window.requestAnimationFrame(() => navigateToPage(clamp(initialPage, 1, viewer.pagesCount || 1)));
    };

    const onPagesLoaded = (event: any) => {
      if (!active) return;
      setPageCount(Math.max(1, Number(event?.pagesCount || viewer.pagesCount || pdfRef.current?.numPages || 1)));
    };

    const onUpdateViewArea = (event: any) => {
      if (!active) return;
      const page = Number(event?.location?.pageNumber || viewer.currentPageNumber || 0);
      if (Number.isInteger(page) && page > 0) publishConfirmedPage(page);
    };

    const onPageRendered = (event: any) => {
      if (!active) return;
      const page = Number(event?.pageNumber || 0);
      if (!Number.isInteger(page) || page < 1) return;
      const pageElement = viewerElement.querySelector<HTMLElement>(`.page[data-page-number="${page}"]`);
      if (!pageElement) return;
      pageElement.classList.add("is-rendered");
      let overlay = pageElement.querySelector<HTMLElement>(":scope > .pdfv2-page-overlay");
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "pdfv2-page-overlay";
        pageElement.appendChild(overlay);
      }
      overlayNodesRef.current.set(page, overlay);
      setOverlayRevision((value) => value + 1);
    };

    const onScaleChanging = (event: any) => {
      if (!active) return;
      const next = Math.round(Number(event?.scale || viewer.currentScale || 1) * 100);
      if (Number.isFinite(next) && next > 0) {
        setZoomPercent(next);
        onZoomChange?.(next);
      }
    };

    const onFindMatchesCount = (event: any) => {
      if (!active) return;
      setFindCount({
        current: Math.max(0, Number(event?.matchesCount?.current || 0)),
        total: Math.max(0, Number(event?.matchesCount?.total || 0)),
      });
    };

    const onFindControlState = (event: any) => {
      if (!active) return;
      const total = Math.max(0, Number(event?.matchesCount?.total || 0));
      if (total === 0 && query.trim()) setFindCount({ current: 0, total: 0 });
    };

    eventBus.on("pagesinit", onPagesInit);
    eventBus.on("pagesloaded", onPagesLoaded);
    eventBus.on("updateviewarea", onUpdateViewArea);
    eventBus.on("pagerendered", onPageRendered);
    eventBus.on("scalechanging", onScaleChanging);
    eventBus.on("updatefindmatchescount", onFindMatchesCount);
    eventBus.on("updatefindcontrolstate", onFindControlState);

    const loadingTask = pdfjsLib.getDocument(source as any) as unknown as PdfLoadingTask;
    loadingTaskRef.current = loadingTask;
    loadingTask.promise
      .then(async (pdf) => {
        if (!active) {
          await pdf.destroy?.().catch(() => undefined);
          return;
        }
        pdfRef.current = pdf;
        setPageCount(Math.max(1, pdf.numPages));
        viewer.setDocument(pdf);
        linkService.setDocument(pdf, null);
        findController.setDocument?.(pdf);

        if (pdf.annotationStorage) {
          pdf.annotationStorage.onSetModified = () => {
            const page = currentPageRef.current;
            setEdited(new Set([...editedPagesRef.current, page]));
            setDirtyState(true);
            setDraftState("");
          };
        }

        Promise.all([
          pdf.getFieldObjects?.().catch(() => null) || Promise.resolve(null),
          outlineItems(pdf),
        ])
          .then(([fields, outline]) => {
            if (!active) return;
            const count = Object.values(fields || {}).flat().length;
            setFieldCount(count);
            setFormPages(formPagesFromFields(fields, pdf.numPages));
            onAcroFormDetected?.(Boolean(capabilities.has_acroform || count > 0));
            onOutlineReady?.(outline);
          })
          .catch(() => undefined);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setLoadState("ERROR");
        setLoadError(error instanceof Error ? error.message : "The PDF could not be opened.");
      });

    return () => {
      active = false;
      eventBus.off("pagesinit", onPagesInit);
      eventBus.off("pagesloaded", onPagesLoaded);
      eventBus.off("updateviewarea", onUpdateViewArea);
      eventBus.off("pagerendered", onPageRendered);
      eventBus.off("scalechanging", onScaleChanging);
      eventBus.off("updatefindmatchescount", onFindMatchesCount);
      eventBus.off("updatefindcontrolstate", onFindControlState);
      overlayNodesRef.current.clear();
      setOverlayRevision((value) => value + 1);
      viewer.cleanup?.();
      viewer.setDocument(null);
      linkService.setDocument(null);
      findController.setDocument?.(null);
      void loadingTask.destroy?.().catch(() => undefined);
      void pdfRef.current?.destroy?.().catch(() => undefined);
      loadingTaskRef.current = null;
      pdfRef.current = null;
      viewerRef.current = null;
      eventBusRef.current = null;
      viewerElement.replaceChildren();
    };
    // The immutable source key is the only document-lifecycle dependency.
    // Capability display changes and navigation never reload the PDF.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftResolved, sourceKey]);

  useEffect(() => {
    if (!navigationRequest?.page || !pageCount) return;
    navigateToPage(navigationRequest.page);
  }, [navigateToPage, navigationRequest?.page, navigationRequest?.token, pageCount]);

  useEffect(() => {
    onAcroFormDetected?.(formDetected);
  }, [formDetected, onAcroFormDetected]);

  const serialize = useCallback(async () => {
    const pdf = pdfRef.current;
    if (!pdf?.saveDocument) throw new Error("This PDF cannot be saved as a working copy.");
    if (!serializingRef.current) {
      serializingRef.current = pdf.saveDocument().finally(() => {
        serializingRef.current = null;
      });
    }
    return serializingRef.current;
  }, []);

  const persistDraft = useCallback(async () => {
    if (!capabilities.can_save_draft || !dirtyRef.current) return;
    setDraftState("SAVING");
    try {
      const bytes = await serialize();
      await savePdfWorkingCopy(
        identity,
        outputPdfFilename(outputName, "WORKING_COPY"),
        copyPdfBytes(bytes),
        capabilities.source_sha256,
        [...editedPagesRef.current],
      );
      setHasDraft(true);
      setDirtyState(false);
      setDraftState("SAVED");
    } catch {
      setDraftState("ERROR");
    }
  }, [
    capabilities.can_save_draft,
    capabilities.source_sha256,
    identity,
    outputName,
    serialize,
    setDirtyState,
  ]);

  const markEdited = useCallback((page: number) => {
    setEdited(new Set([...editedPagesRef.current, Math.max(1, page)]));
    setDirtyState(true);
    setDraftState("");
    if (autosaveTimerRef.current !== null) window.clearTimeout(autosaveTimerRef.current);
    if (capabilities.can_save_draft) {
      autosaveTimerRef.current = window.setTimeout(() => {
        autosaveTimerRef.current = null;
        void persistDraft();
      }, 800);
    }
  }, [capabilities.can_save_draft, persistDraft, setDirtyState, setEdited]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      if (autosaveTimerRef.current !== null) window.clearTimeout(autosaveTimerRef.current);
    };
  }, []);

  const workingFile = useCallback(async () => new File(
    [copyPdfBytes(await serialize())],
    outputPdfFilename(outputName, "WORKING_COPY"),
    { type: "application/pdf" },
  ), [outputName, serialize]);

  const perform = useCallback(async (
    kind: typeof busy,
    action: () => Promise<void>,
  ) => {
    setBusy(kind);
    setActionError("");
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The PDF action failed.");
    } finally {
      setBusy("");
    }
  }, []);

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
    setRecord(created);
    setDirtyState(false);
    setEdited([]);
    setDraft(null);
    setHasDraft(false);
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    onRecordCreated?.(created);
  });

  const discard = async () => {
    if (dirty && !window.confirm("Discard the working copy?")) return;
    await deletePdfWorkingCopy(identity).catch(() => undefined);
    setDraft(null);
    setHasDraft(false);
    setDirtyState(false);
    setEdited([]);
    setDraftState("");
  };

  const dispatchFind = useCallback((type: "" | "again", findPrevious = false) => {
    const eventBus = eventBusRef.current;
    if (!eventBus) return;
    const text = query.trim();
    if (!text) {
      setFindCount({ current: 0, total: 0 });
      return;
    }
    eventBus.dispatch("find", {
      source: hostRef.current,
      type,
      query: text,
      phraseSearch: true,
      caseSensitive,
      entireWord: wholeWord,
      highlightAll: true,
      findPrevious,
      matchDiacritics: false,
    });
  }, [caseSensitive, query, wholeWord]);

  const zoomBy = (delta: number) => {
    const next = clamp(zoomPercent + delta, 50, 250);
    setZoomPercent(next);
    applyScale("CUSTOM", next);
  };

  const overlays = renderPageOverlay
    ? [...overlayNodesRef.current.entries()].map(([page, node]) => (
      createPortal(renderPageOverlay(page), node, `pdf-overlay-${page}-${overlayRevision}`)
    ))
    : null;

  return (
    <section
      ref={hostRef}
      className={[
        "pdfv2-reader",
        compact ? "is-compact" : "",
        uncontrolled ? "is-uncontrolled" : "",
        safeForm ? "is-form-active" : "",
      ].filter(Boolean).join(" ")}
      onKeyDown={(event: ReactKeyboardEvent<HTMLElement>) => {
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "f") return;
        event.preventDefault();
        setSearchOpen(true);
        window.requestAnimationFrame(() => searchInputRef.current?.focus());
      }}
    >
      <header className="pdfv2-toolbar">
        <div className="pdfv2-pages">
          <button
            type="button"
            aria-label="Previous page"
            onClick={() => navigateToPage(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            <ChevronLeft size={17} />
          </button>
          <input
            value={pageInput}
            aria-label="Page number"
            inputMode="numeric"
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setPageInput(event.target.value.replace(/\D+/g, ""));
            }}
            onBlur={() => navigateToPage(Number(pageInput || currentPage))}
            onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
              if (event.key === "Enter") navigateToPage(Number(pageInput || currentPage));
            }}
          />
          <span>/ {pageCount || "—"}</span>
          <button
            type="button"
            aria-label="Next page"
            onClick={() => navigateToPage(currentPage + 1)}
            disabled={!pageCount || currentPage >= pageCount}
          >
            <ChevronRight size={17} />
          </button>
        </div>

        <div className="pdfv2-zoom">
          <button type="button" aria-label="Zoom out" onClick={() => zoomBy(-10)}>
            <Minus size={17} />
          </button>
          <button
            type="button"
            onClick={() => {
              if (zoomMode === "WIDTH") applyScale("PAGE");
              else if (zoomMode === "PAGE") applyScale("CUSTOM", 100);
              else applyScale("WIDTH");
            }}
          >
            {zoomMode === "WIDTH" ? "Fit width" : zoomMode === "PAGE" ? "Fit page" : `${zoomPercent}%`}
          </button>
          <button type="button" aria-label="Zoom in" onClick={() => zoomBy(10)}>
            <Plus size={17} />
          </button>
        </div>

        <div className="pdfv2-actions">
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
            <span className="pdfv2-form-state">
              <FilePenLine size={15} />
              Form active{editedPages.length ? ` · ${editedPages.length} changed` : ""}
            </span>
          ) : null}
          <details className="pdfv2-menu">
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
                disabled={Boolean(busy) || !capabilities.can_download_working || !pdfRef.current?.saveDocument}
                onClick={() => void downloadWorking()}
              >
                Editable PDF
              </button>
              <button
                type="button"
                disabled={Boolean(busy) || !capabilities.can_flatten || !safeForm || !pdfRef.current?.saveDocument}
                onClick={() => void downloadCompleted()}
              >
                Completed form pages{editedPages.length ? ` (${editedPages.length})` : ""}
              </button>
            </div>
          </details>
          <details className="pdfv2-menu">
            <summary aria-label="More PDF actions">
              <MoreHorizontal size={18} />
            </summary>
            <div>
              {capabilities.can_submit ? (
                <button type="button" disabled={Boolean(busy)} onClick={() => void submit()}>
                  Submit retained record
                </button>
              ) : null}
              {hasDraft || dirty ? (
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
        <div className="pdfv2-search">
          <Search size={16} />
          <input
            ref={searchInputRef}
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
            onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
              if (event.key === "Enter") dispatchFind("");
            }}
            placeholder="Search this PDF"
          />
          <label>
            <input
              type="checkbox"
              checked={caseSensitive}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setCaseSensitive(event.target.checked)}
            />
            Aa
          </label>
          <label>
            <input
              type="checkbox"
              checked={wholeWord}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setWholeWord(event.target.checked)}
            />
            Word
          </label>
          <button type="button" disabled={query.trim().length < 2} onClick={() => dispatchFind("")}>
            Find
          </button>
          <span>{findCount.total ? `${findCount.current}/${findCount.total}` : ""}</span>
          <button
            type="button"
            aria-label="Previous search result"
            disabled={!findCount.total}
            onClick={() => dispatchFind("again", true)}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            aria-label="Next search result"
            disabled={!findCount.total}
            onClick={() => dispatchFind("again", false)}
          >
            <ChevronRight size={16} />
          </button>
          <button
            type="button"
            aria-label="Close PDF search"
            onClick={() => {
              setSearchOpen(false);
              setFindCount({ current: 0, total: 0 });
              eventBusRef.current?.dispatch("find", {
                source: hostRef.current,
                type: "",
                query: "",
                highlightAll: false,
              });
            }}
          >
            <X size={16} />
          </button>
        </div>
      ) : null}

      {capabilities.unsupported_reason && !safeForm ? (
        <div className="pdfv2-notice">
          <AlertTriangle size={16} />
          {capabilities.unsupported_reason}
        </div>
      ) : null}
      {formDetected && !safeForm && !capabilities.unsupported_reason ? (
        <div className="pdfv2-notice">
          <AlertTriangle size={16} />
          This PDF contains form fields, but controlled form execution is unavailable for this document or user.
        </div>
      ) : null}
      {safeForm ? (
        <div className="pdfv2-notice pdfv2-notice--form">
          <FilePenLine size={16} />
          Fields are active. Entries stay in a local working copy until you download or submit.
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
        <div className="pdfv2-error">
          <AlertTriangle size={17} />
          {actionError}
        </div>
      ) : null}
      {record ? (
        <div className="pdfv2-success">
          <CheckCircle2 size={17} />
          Record {record.record_number} created.
          <a href={record.download_url}>Open</a>
        </div>
      ) : null}

      <div
        ref={viewportRef}
        className="pdfv2-viewport pdf-engine-viewport"
        tabIndex={0}
        onInput={(event: FormEvent<HTMLDivElement>) => {
          if (safeForm) markEdited(pageNumberFromTarget(event.target, currentPageRef.current));
        }}
        onChange={(event: FormEvent<HTMLDivElement>) => {
          if (safeForm) markEdited(pageNumberFromTarget(event.target, currentPageRef.current));
        }}
      >
        <div ref={viewerElementRef} className="pdfViewer" />
        {loadState === "LOADING" ? (
          <div className="pdfv2-loading" role="status">
            <LoaderCircle className="is-spinning" size={20} />
            Opening document…
          </div>
        ) : null}
        {loadState === "ERROR" ? (
          <div className="pdfv2-error pdfv2-error--viewport" role="alert">
            <AlertTriangle size={18} />
            {loadError}
          </div>
        ) : null}
      </div>
      {overlays}
    </section>
  );
}

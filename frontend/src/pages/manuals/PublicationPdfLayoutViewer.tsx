import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FC } from "react";
import { AlertTriangle, Link2, List, Maximize2, Minus, Plus, X } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import {
  getPublicationReferences,
  type DocumentationReference,
  type DocumentationIndexState,
} from "../../services/documentation";
import { publicationPdfSource } from "../../services/publications";
import LinkedDocumentationPanel from "./LinkedDocumentationPanel";
import { PDF_DOCUMENT_OPTIONS, pdfDevicePixelRatio } from "./pdfReaderConfig";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./publicationReaderZoom.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfDocument = Document as unknown as FC<any>;
const PdfPage = Page as unknown as FC<any>;

export type PdfOutlineItem = {
  id: string;
  title: string;
  page: number;
  level: number;
};

type PdfNavigationRequest = {
  page: number;
  token: number;
};

type PublicationPdfLayoutViewerProps = {
  fileUrl: string;
  title: string;
  uncontrolled?: boolean;
  navigationRequest?: PdfNavigationRequest | null;
  initialPage?: number;
  initialZoom?: number;
  references?: DocumentationReference[];
  activeReferenceId?: string | null;
  onReferenceClick?: (reference: DocumentationReference) => void;
  onPageChange?: (pageNumber: number) => void;
  onZoomChange?: (zoomPercent: number) => void;
  onAcroFormDetected?: (hasAcroForm: boolean) => void;
  onOutlineReady?: (items: PdfOutlineItem[]) => void;
};

type SourceIdentity = { tenant: string; manualId: string; revisionId: string };

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function humanize(value: unknown, fallback = "Pending review"): string {
  const text = String(value ?? "").trim();
  return text ? text.replaceAll("_", " ") : fallback;
}

function sourceIdentity(fileUrl: string): SourceIdentity | null {
  const path = fileUrl.split("?", 1)[0];
  const match = path.match(/\/manuals\/t\/([^/]+)\/([^/]+)\/rev\/([^/]+)\//i);
  if (!match) return null;
  try {
    return {
      tenant: decodeURIComponent(match[1]),
      manualId: decodeURIComponent(match[2]),
      revisionId: decodeURIComponent(match[3]),
    };
  } catch {
    return null;
  }
}

function pagesAround(pageNumber: number, pageCount: number): Set<number> {
  const pages = new Set<number>();
  for (let page = pageNumber - 3; page <= pageNumber + 3; page += 1) {
    if (page >= 1 && page <= pageCount) pages.add(page);
  }
  return pages;
}

function readerScroller(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".app-shell__scroll");
}

function scrollElementPrecisely(element: HTMLElement, behavior: ScrollBehavior = "smooth"): void {
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

async function resolveOutline(documentProxy: any): Promise<PdfOutlineItem[]> {
  const outline = await documentProxy.getOutline().catch(() => null);
  if (!Array.isArray(outline) || !outline.length) return [];
  const resolved: PdfOutlineItem[] = [];

  const visit = async (items: any[], level: number, path: string) => {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      let destination = item?.dest;
      if (typeof destination === "string") destination = await documentProxy.getDestination(destination).catch(() => null);
      let page = 0;
      const reference = Array.isArray(destination) ? destination[0] : null;
      if (reference) {
        if (typeof reference === "number") page = reference + 1;
        else page = (await documentProxy.getPageIndex(reference).catch(() => -1)) + 1;
      }
      const id = `${path}-${index}`;
      if (page > 0) resolved.push({ id, title: String(item?.title || `Page ${page}`), page, level });
      if (Array.isArray(item?.items) && item.items.length) await visit(item.items, level + 1, id);
    }
  };

  await visit(outline, 1, "pdf-outline");
  return resolved;
}

function hotspotStyle(reference: DocumentationReference): CSSProperties | null {
  const box = reference.source?.bbox || {};
  const x = Number(box.x);
  const y = Number(box.y);
  const width = Number(box.width);
  const height = Number(box.height);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  return {
    left: `${clamp(x, 0, 1) * 100}%`,
    top: `${clamp(y, 0, 1) * 100}%`,
    width: `${clamp(width, 0.004, 1) * 100}%`,
    height: `${clamp(height, 0.006, 1) * 100}%`,
  };
}

function indexing(index?: DocumentationIndexState | null): boolean {
  return ["PENDING", "RUNNING"].includes(String(index?.status || "").toUpperCase());
}

export default function PublicationPdfLayoutViewer({
  fileUrl,
  title,
  uncontrolled = false,
  navigationRequest,
  initialPage = 1,
  initialZoom = 100,
  references = [],
  activeReferenceId,
  onReferenceClick,
  onPageChange,
  onZoomChange,
  onAcroFormDetected,
  onOutlineReady,
}: PublicationPdfLayoutViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const onPageChangeRef = useRef(onPageChange);
  const onZoomChangeRef = useRef(onZoomChange);
  const onAcroFormDetectedRef = useRef(onAcroFormDetected);
  const onOutlineReadyRef = useRef(onOutlineReady);
  const inspectionGenerationRef = useRef(0);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [hostWidth, setHostWidth] = useState(960);
  const [zoom, setZoom] = useState(clamp(initialZoom / 100, 0.65, 1.8));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [loadError, setLoadError] = useState("");
  const [hasAcroForm, setHasAcroForm] = useState(false);
  const [automaticReferences, setAutomaticReferences] = useState<DocumentationReference[]>([]);
  const [indexState, setIndexState] = useState<DocumentationIndexState | null>(null);
  const [selectedReferenceId, setSelectedReferenceId] = useState<string | null>(activeReferenceId || null);
  const [referenceListOpen, setReferenceListOpen] = useState(false);

  const identity = useMemo(() => sourceIdentity(fileUrl), [fileUrl]);
  const pdfSource = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const allReferences = references.length ? references : automaticReferences;
  const effectiveActiveReferenceId = activeReferenceId || selectedReferenceId;

  useEffect(() => {
    inspectionGenerationRef.current += 1;
    setPageCount(0);
    setCurrentPage(Math.max(1, initialPage));
    setPageRatios({});
    setLoadError("");
    setHasAcroForm(false);
    onAcroFormDetectedRef.current?.(false);
  }, [fileUrl, initialPage]);

  useEffect(() => {
    if (!identity || references.length) return;
    let active = true;
    let timer = 0;
    const load = () => {
      getPublicationReferences(identity.tenant, identity.manualId, identity.revisionId)
        .then((response) => {
          if (!active) return;
          setAutomaticReferences(response.items || []);
          setIndexState(response.index || null);
          if (indexing(response.index)) timer = window.setTimeout(load, 1400);
        })
        .catch(() => {
          if (active) timer = window.setTimeout(load, 3500);
        });
    };
    load();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [identity, references.length]);

  useEffect(() => {
    setSelectedReferenceId(activeReferenceId || null);
  }, [activeReferenceId]);

  const referencesByPage = useMemo(() => {
    const grouped = new Map<number, DocumentationReference[]>();
    for (const reference of allReferences) {
      const page = Number(reference.source?.page_number || 0);
      if (!page) continue;
      grouped.set(page, [...(grouped.get(page) || []), reference]);
    }
    return grouped;
  }, [allReferences]);

  const selectedReference = allReferences.find((reference) => reference.id === effectiveActiveReferenceId) || null;
  const currentReferences = referencesByPage.get(currentPage) || [];

  const openReference = (reference: DocumentationReference) => {
    if (!reference.target) return;
    setSelectedReferenceId(reference.id);
    setReferenceListOpen(false);
    onReferenceClick?.(reference);
  };

  useEffect(() => { onPageChangeRef.current = onPageChange; }, [onPageChange]);
  useEffect(() => { onZoomChangeRef.current = onZoomChange; }, [onZoomChange]);
  useEffect(() => { onAcroFormDetectedRef.current = onAcroFormDetected; }, [onAcroFormDetected]);
  useEffect(() => { onOutlineReadyRef.current = onOutlineReady; }, [onOutlineReady]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const updateWidth = () => setHostWidth(Math.max(360, host.clientWidth));
    updateWidth();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateWidth);
      return () => window.removeEventListener("resize", updateWidth);
    }
    const observer = new ResizeObserver(updateWidth);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => { onZoomChangeRef.current?.(Math.round(zoom * 100)); }, [zoom]);

  const basePageWidth = Math.max(320, Math.min(selectedReference ? 820 : 1180, hostWidth - 48));
  const pageWidth = Math.round(basePageWidth * zoom);

  const renderedPages = useMemo(() => {
    const pages = pagesAround(currentPage, pageCount);
    if (navigationRequest?.page) {
      for (const page of pagesAround(clamp(navigationRequest.page, 1, Math.max(1, pageCount)), pageCount)) pages.add(page);
    }
    return pages;
  }, [currentPage, navigationRequest, pageCount]);

  useEffect(() => {
    if (!pageCount || typeof IntersectionObserver === "undefined") return;
    const root = readerScroller();
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (!visible.length) return;
        const viewportTop = root?.getBoundingClientRect().top || 0;
        const viewportHeight = root?.clientHeight || window.innerHeight;
        const viewportCentre = viewportTop + viewportHeight * 0.42;
        const closest = [...visible].sort((a, b) => {
          const aCentre = a.boundingClientRect.top + a.boundingClientRect.height / 2;
          const bCentre = b.boundingClientRect.top + b.boundingClientRect.height / 2;
          return Math.abs(aCentre - viewportCentre) - Math.abs(bCentre - viewportCentre);
        })[0];
        const pageNumber = Number((closest.target as HTMLElement).dataset.pageNumber || 1);
        if (!Number.isFinite(pageNumber)) return;
        setCurrentPage((previous) => {
          if (previous === pageNumber) return previous;
          onPageChangeRef.current?.(pageNumber);
          return pageNumber;
        });
      },
      { root, rootMargin: "-104px 0px -48% 0px", threshold: [0.01, 0.12, 0.35, 0.7] },
    );
    pageRefs.current.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [pageCount, pageWidth]);

  const jumpToPage = useCallback((requestedPage: number, behavior: ScrollBehavior = "smooth") => {
    if (!pageCount) return;
    const pageNumber = clamp(requestedPage, 1, pageCount);
    setCurrentPage(pageNumber);
    onPageChangeRef.current?.(pageNumber);
    window.requestAnimationFrame(() => {
      const element = pageRefs.current.get(pageNumber);
      if (element) scrollElementPrecisely(element, behavior);
    });
  }, [pageCount]);

  useEffect(() => {
    if (!navigationRequest || !pageCount) return;
    jumpToPage(navigationRequest.page);
  }, [jumpToPage, navigationRequest, pageCount]);

  const handleDocumentLoadSuccess = useCallback((documentProxy: any) => {
    const nextPageCount = Math.max(1, Number(documentProxy?.numPages || 1));
    const restoredPage = clamp(initialPage || 1, 1, nextPageCount);
    setPageCount(nextPageCount);
    setCurrentPage(restoredPage);
    setLoadError("");
    onPageChangeRef.current?.(restoredPage);

    window.requestAnimationFrame(() => {
      const element = pageRefs.current.get(restoredPage);
      if (element && restoredPage > 1) scrollElementPrecisely(element, "auto");
    });

    const generation = ++inspectionGenerationRef.current;
    const fieldsPromise = typeof documentProxy?.getFieldObjects === "function"
      ? documentProxy.getFieldObjects().catch(() => null)
      : Promise.resolve(null);
    void Promise.all([
      fieldsPromise,
      resolveOutline(documentProxy).catch(() => []),
    ]).then(([fieldObjects, outline]) => {
      if (generation !== inspectionGenerationRef.current) return;
      const formsDetected = Boolean(fieldObjects && Object.keys(fieldObjects).length);
      setHasAcroForm(formsDetected);
      onAcroFormDetectedRef.current?.(formsDetected);
      if (outline.length) onOutlineReadyRef.current?.(outline);
    }).catch(() => {
      if (generation === inspectionGenerationRef.current) {
        setHasAcroForm(false);
        onAcroFormDetectedRef.current?.(false);
      }
    });
  }, [initialPage]);

  const handleDocumentLoadError = useCallback((caught: unknown) => {
    inspectionGenerationRef.current += 1;
    setPageCount(0);
    setLoadError(caught instanceof Error ? caught.message : "Unable to load PDF document.");
  }, []);

  const pageNumbers = useMemo(() => Array.from({ length: pageCount }, (_, index) => index + 1), [pageCount]);

  return (
    <div className={`publication-linked-layout ${selectedReference ? "has-selection" : ""}`}>
      <section className={`publication-native-pdf ${uncontrolled ? "is-uncontrolled" : ""}`} ref={hostRef} aria-label={`${title} original layout`}>
        <div className="publication-native-pdf__toolbar">
          <div className="publication-native-pdf__page-state" aria-live="polite">
            <strong>Page {currentPage}</strong>
            <span>{pageCount ? `of ${pageCount}` : ""}</span>
            {indexing(indexState) ? <span>Indexing linked documents…</span> : null}
            {currentReferences.length ? <button type="button" className="publication-page-links-button" onClick={() => setReferenceListOpen((value) => !value)}><Link2 size={13} /> {currentReferences.length} linked</button> : null}
            {hasAcroForm ? <span className="publication-native-pdf__form-state">AcroForm · read-only</span> : null}
          </div>
          <div className="publication-native-pdf__zoom" aria-label="Document zoom controls">
            <button type="button" onClick={() => setZoom((value) => clamp(Number((value - 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom out"><Minus size={16} /></button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => setZoom((value) => clamp(Number((value + 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom in"><Plus size={16} /></button>
            <button type="button" onClick={() => setZoom(1)} aria-label="Fit document to available width"><Maximize2 size={15} /> Fit width</button>
          </div>
          {referenceListOpen ? <div className="publication-page-links-popover">
            <header><strong>Linked items on page {currentPage}</strong><button type="button" onClick={() => setReferenceListOpen(false)} aria-label="Close linked items"><X size={14} /></button></header>
            {currentReferences.map((reference) => <button type="button" key={reference.id} disabled={!reference.target} onClick={() => openReference(reference)}>
              <List size={14} /><span><strong>{reference.raw_token}</strong><small>{reference.target ? `${reference.target.code} · ${reference.target.title}` : `${humanize(reference.status)} · awaiting Document Control`}</small></span>
            </button>)}
          </div> : null}
        </div>

        {loadError ? <div className="publication-native-pdf__error" role="alert"><AlertTriangle size={18} /><div><strong>The original layout could not be rendered.</strong><span>{loadError}</span></div></div> : null}

        <PdfDocument
          file={pdfSource}
          loading={<div className="publication-native-pdf__loading">Opening the first available pages…</div>}
          error={<div className="publication-native-pdf__error" role="alert"><AlertTriangle size={18} /><div><strong>The PDF reader could not open this controlled copy.</strong><span>Reload the page or use the Download action while the reader is recovered.</span></div></div>}
          onLoadSuccess={handleDocumentLoadSuccess}
          onLoadError={handleDocumentLoadError}
          onItemClick={(item: any) => { const pageNumber = Number(item?.pageNumber || 0); if (pageNumber > 0) jumpToPage(pageNumber); }}
          options={PDF_DOCUMENT_OPTIONS}
        >
          <div className="publication-native-pdf__pages">
            {pageNumbers.map((pageNumber) => {
              const ratio = pageRatios[pageNumber] || 1.414;
              const style = {
                "--publication-native-page-width": `${pageWidth}px`,
                "--publication-native-page-height": `${Math.round(pageWidth * ratio)}px`,
              } as CSSProperties;
              const shouldRender = renderedPages.has(pageNumber);
              return <div
                key={pageNumber}
                ref={(element) => { if (element) pageRefs.current.set(pageNumber, element); else pageRefs.current.delete(pageNumber); }}
                className={`publication-native-pdf__page ${currentPage === pageNumber ? "is-current" : ""}`}
                data-page-number={pageNumber}
                style={style}
              >
                <span className="publication-native-pdf__page-label">{pageNumber}</span>
                {uncontrolled ? <span className="publication-native-pdf__watermark" aria-hidden="true">UNCONTROLLED DRAFT</span> : null}
                {shouldRender ? <PdfPage
                  pageNumber={pageNumber}
                  width={pageWidth}
                  renderMode="canvas"
                  renderTextLayer
                  renderAnnotationLayer
                  renderForms={false}
                  externalLinkTarget="_blank"
                  devicePixelRatio={pdfDevicePixelRatio()}
                  loading={<div className="publication-native-pdf__placeholder">Rendering page {pageNumber}…</div>}
                  error={<div className="publication-native-pdf__placeholder">Page {pageNumber} could not be rendered.</div>}
                  onGetAnnotationsSuccess={(annotations: any[]) => {
                    if (!hasAcroForm && annotations.some((annotation) => annotation?.subtype === "Widget" || annotation?.fieldType)) {
                      setHasAcroForm(true);
                      onAcroFormDetectedRef.current?.(true);
                    }
                  }}
                  onLoadSuccess={(page: any) => {
                    const width = Number(page?.originalWidth || page?.view?.[2] || 1);
                    const height = Number(page?.originalHeight || page?.view?.[3] || width * 1.414);
                    const nextRatio = width > 0 && height > 0 ? height / width : 1.414;
                    setPageRatios((current) => Math.abs((current[pageNumber] || 0) - nextRatio) < 0.001 ? current : { ...current, [pageNumber]: nextRatio });
                  }}
                /> : <div className="publication-native-pdf__placeholder" aria-label={`Page ${pageNumber} is ready to render`} />}
                {(referencesByPage.get(pageNumber) || []).map((reference) => {
                  const referenceStyle = hotspotStyle(reference);
                  if (!referenceStyle || !reference.target) return null;
                  return <button
                    type="button"
                    key={reference.id}
                    className={`publication-reference-hotspot ${effectiveActiveReferenceId === reference.id ? "active" : ""}`}
                    style={referenceStyle}
                    aria-label={`${reference.raw_token}: open ${reference.target.code}`}
                    onClick={() => openReference(reference)}
                  />;
                })}
              </div>;
            })}
          </div>
        </PdfDocument>
      </section>
      {identity && selectedReference ? <LinkedDocumentationPanel tenant={identity.tenant} referenceId={selectedReference.id} onClose={() => setSelectedReferenceId(null)} /> : null}
    </div>
  );
}

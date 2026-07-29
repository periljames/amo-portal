import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import type { DocumentationReference } from "../../services/documentation";
import { publicationPdfSource } from "../../services/publications";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./publicationReaderZoom.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfDocument = Document as unknown as React.FC<any>;
const PdfPage = Page as unknown as React.FC<any>;

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

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
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
      if (page > 0) {
        resolved.push({ id, title: String(item?.title || `Page ${page}`), page, level });
      }
      if (Array.isArray(item?.items) && item.items.length) await visit(item.items, level + 1, id);
    }
  };

  await visit(outline, 1, "pdf-outline");
  return resolved;
}

function hotspotStyle(reference: DocumentationReference): CSSProperties | null {
  const box = reference.source.bbox || {};
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
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [hostWidth, setHostWidth] = useState(960);
  const [zoom, setZoom] = useState(clamp(initialZoom / 100, 0.65, 1.8));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [loadError, setLoadError] = useState("");
  const [hasAcroForm, setHasAcroForm] = useState(false);

  const pdfSource = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const referencesByPage = useMemo(() => {
    const grouped = new Map<number, DocumentationReference[]>();
    for (const reference of references) {
      const page = Number(reference.source.page_number || 0);
      if (!page || !reference.target || !hotspotStyle(reference)) continue;
      grouped.set(page, [...(grouped.get(page) || []), reference]);
    }
    return grouped;
  }, [references]);

  useEffect(() => {
    onPageChangeRef.current = onPageChange;
  }, [onPageChange]);

  useEffect(() => {
    onZoomChangeRef.current = onZoomChange;
  }, [onZoomChange]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const updateWidth = () => setHostWidth(Math.max(360, host.clientWidth));
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    onZoomChangeRef.current?.(Math.round(zoom * 100));
  }, [zoom]);

  const basePageWidth = Math.max(320, Math.min(1180, hostWidth - 48));
  const pageWidth = Math.round(basePageWidth * zoom);

  const renderedPages = useMemo(() => {
    const pages = pagesAround(currentPage, pageCount);
    if (navigationRequest?.page) {
      for (const page of pagesAround(clamp(navigationRequest.page, 1, Math.max(1, pageCount)), pageCount)) pages.add(page);
    }
    return pages;
  }, [currentPage, navigationRequest, pageCount]);

  useEffect(() => {
    if (!pageCount) return;
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

  const jumpToPage = (requestedPage: number, behavior: ScrollBehavior = "smooth") => {
    if (!pageCount) return;
    const pageNumber = clamp(requestedPage, 1, pageCount);
    setCurrentPage(pageNumber);
    onPageChangeRef.current?.(pageNumber);
    window.requestAnimationFrame(() => {
      const element = pageRefs.current.get(pageNumber);
      if (element) scrollElementPrecisely(element, behavior);
    });
  };

  useEffect(() => {
    if (!navigationRequest || !pageCount) return;
    jumpToPage(navigationRequest.page);
  }, [navigationRequest, pageCount]);

  const pageNumbers = useMemo(
    () => Array.from({ length: pageCount }, (_, index) => index + 1),
    [pageCount],
  );

  return (
    <section className={`publication-native-pdf ${uncontrolled ? "is-uncontrolled" : ""}`} ref={hostRef} aria-label={`${title} original layout`}>
      <div className="publication-native-pdf__toolbar">
        <div className="publication-native-pdf__page-state" aria-live="polite">
          <strong>Page {currentPage}</strong>
          <span>{pageCount ? `of ${pageCount}` : ""}</span>
          {referencesByPage.get(currentPage)?.length ? <span>{referencesByPage.get(currentPage)?.length} linked item(s)</span> : null}
          {hasAcroForm ? <span className="publication-native-pdf__form-state">AcroForm · read-only</span> : null}
        </div>
        <div className="publication-native-pdf__zoom" aria-label="Document zoom controls">
          <button type="button" onClick={() => setZoom((value) => clamp(Number((value - 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom out"><Minus size={16} /></button>
          <span>{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom((value) => clamp(Number((value + 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom in"><Plus size={16} /></button>
          <button type="button" onClick={() => setZoom(1)} aria-label="Fit document to available width"><Maximize2 size={15} /> Fit width</button>
        </div>
      </div>

      {loadError ? <div className="publication-native-pdf__error" role="alert"><strong>The original layout could not be rendered.</strong><span>{loadError}</span></div> : null}

      <PdfDocument
        file={pdfSource}
        loading={<div className="publication-native-pdf__loading">Opening the first available pages…</div>}
        onLoadSuccess={async (documentProxy: any) => {
          setPageCount(documentProxy.numPages);
          const restoredPage = clamp(initialPage || 1, 1, documentProxy.numPages);
          setCurrentPage(restoredPage);
          setLoadError("");
          onPageChangeRef.current?.(restoredPage);
          const fieldObjects = typeof documentProxy.getFieldObjects === "function"
            ? await documentProxy.getFieldObjects().catch(() => null)
            : null;
          const formsDetected = Boolean(fieldObjects && Object.keys(fieldObjects).length);
          setHasAcroForm(formsDetected);
          onAcroFormDetected?.(formsDetected);
          const outline = await resolveOutline(documentProxy);
          if (outline.length) onOutlineReady?.(outline);
          window.requestAnimationFrame(() => {
            const element = pageRefs.current.get(restoredPage);
            if (element && restoredPage > 1) scrollElementPrecisely(element, "auto");
          });
        }}
        onLoadError={(caught: unknown) => setLoadError(caught instanceof Error ? caught.message : "Unable to load PDF document.")}
        onItemClick={(item: any) => {
          const pageNumber = Number(item?.pageNumber || 0);
          if (pageNumber > 0) jumpToPage(pageNumber);
        }}
        options={{ isEvalSupported: false, enableXfa: true }}
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
                devicePixelRatio={Math.min(typeof window === "undefined" ? 1 : window.devicePixelRatio || 1, 1.6)}
                loading={<div className="publication-native-pdf__placeholder">Rendering page {pageNumber}…</div>}
                onGetAnnotationsSuccess={(annotations: any[]) => {
                  if (!hasAcroForm && annotations.some((annotation) => annotation?.subtype === "Widget" || annotation?.fieldType)) {
                    setHasAcroForm(true);
                    onAcroFormDetected?.(true);
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
                if (!referenceStyle) return null;
                return <button
                  type="button"
                  key={reference.id}
                  className={`publication-reference-hotspot ${activeReferenceId === reference.id ? "active" : ""}`}
                  style={referenceStyle}
                  aria-label={`${reference.raw_token}: open ${reference.target?.code || "linked document"}`}
                  onClick={() => onReferenceClick?.(reference)}
                />;
              })}
            </div>;
          })}
        </div>
      </PdfDocument>
    </section>
  );
}

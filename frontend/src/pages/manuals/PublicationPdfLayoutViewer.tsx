import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PdfPage = Page as unknown as React.FC<any>;

type PdfNavigationRequest = {
  page: number;
  token: number;
};

type PublicationPdfLayoutViewerProps = {
  fileUrl: string;
  title: string;
  navigationRequest?: PdfNavigationRequest | null;
  onPageChange?: (pageNumber: number) => void;
};

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function pagesAround(pageNumber: number, pageCount: number): Set<number> {
  const pages = new Set<number>();
  for (let page = pageNumber - 2; page <= pageNumber + 2; page += 1) {
    if (page >= 1 && page <= pageCount) pages.add(page);
  }
  return pages;
}

export default function PublicationPdfLayoutViewer({
  fileUrl,
  title,
  navigationRequest,
  onPageChange,
}: PublicationPdfLayoutViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const onPageChangeRef = useRef(onPageChange);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [hostWidth, setHostWidth] = useState(960);
  const [zoom, setZoom] = useState(1);
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    onPageChangeRef.current = onPageChange;
  }, [onPageChange]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const updateWidth = () => setHostWidth(Math.max(360, host.clientWidth));
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  const basePageWidth = Math.max(320, Math.min(1040, hostWidth - 48));
  const pageWidth = Math.round(basePageWidth * zoom);

  const renderedPages = useMemo(() => {
    const pages = pagesAround(currentPage, pageCount);
    if (navigationRequest?.page) {
      for (const page of pagesAround(clamp(navigationRequest.page, 1, Math.max(1, pageCount)), pageCount)) {
        pages.add(page);
      }
    }
    return pages;
  }, [currentPage, navigationRequest, pageCount]);

  useEffect(() => {
    if (!pageCount) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (!visible.length) return;
        const viewportCentre = window.innerHeight / 2;
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
      { root: null, rootMargin: "-8% 0px -42% 0px", threshold: [0.01, 0.15, 0.35, 0.65] },
    );

    pageRefs.current.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [pageCount, pageWidth]);

  useEffect(() => {
    if (!navigationRequest || !pageCount) return;
    const pageNumber = clamp(navigationRequest.page, 1, pageCount);
    setCurrentPage(pageNumber);
    window.requestAnimationFrame(() => {
      pageRefs.current.get(pageNumber)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [navigationRequest, pageCount]);

  const pageNumbers = useMemo(
    () => Array.from({ length: pageCount }, (_, index) => index + 1),
    [pageCount],
  );

  return (
    <section className="publication-native-pdf" ref={hostRef} aria-label={`${title} original layout`}>
      <div className="publication-native-pdf__toolbar">
        <div className="publication-native-pdf__page-state" aria-live="polite">
          <strong>Page {currentPage}</strong>
          <span>{pageCount ? `of ${pageCount}` : ""}</span>
        </div>
        <div className="publication-native-pdf__zoom" aria-label="Document zoom controls">
          <button type="button" onClick={() => setZoom((value) => clamp(Number((value - 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom out">
            <Minus size={16} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom((value) => clamp(Number((value + 0.1).toFixed(2)), 0.65, 1.8))} aria-label="Zoom in">
            <Plus size={16} />
          </button>
          <button type="button" onClick={() => setZoom(1)} aria-label="Fit document to available width">
            <Maximize2 size={15} /> Fit width
          </button>
        </div>
      </div>

      {loadError ? (
        <div className="publication-native-pdf__error" role="alert">
          <strong>The original layout could not be rendered.</strong>
          <span>{loadError}</span>
        </div>
      ) : null}

      <Document
        file={fileUrl}
        loading={<div className="publication-native-pdf__loading">Preparing the original document layout…</div>}
        onLoadSuccess={(document) => {
          setPageCount(document.numPages);
          setCurrentPage(1);
          setLoadError("");
          onPageChangeRef.current?.(1);
        }}
        onLoadError={(caught) => setLoadError(caught instanceof Error ? caught.message : "Unable to load PDF document.")}
      >
        <div className="publication-native-pdf__pages">
          {pageNumbers.map((pageNumber) => {
            const ratio = pageRatios[pageNumber] || 1.414;
            const style = {
              "--publication-native-page-width": `${pageWidth}px`,
              "--publication-native-page-height": `${Math.round(pageWidth * ratio)}px`,
            } as CSSProperties;
            const shouldRender = renderedPages.has(pageNumber);
            return (
              <div
                key={pageNumber}
                ref={(element) => {
                  if (element) pageRefs.current.set(pageNumber, element);
                  else pageRefs.current.delete(pageNumber);
                }}
                className={`publication-native-pdf__page ${currentPage === pageNumber ? "is-current" : ""}`}
                data-page-number={pageNumber}
                style={style}
              >
                <span className="publication-native-pdf__page-label">{pageNumber}</span>
                {shouldRender ? (
                  <PdfPage
                    pageNumber={pageNumber}
                    width={pageWidth}
                    renderMode="canvas"
                    renderTextLayer
                    renderAnnotationLayer
                    devicePixelRatio={Math.min(typeof window === "undefined" ? 1 : window.devicePixelRatio || 1, 1.75)}
                    loading={<div className="publication-native-pdf__placeholder">Rendering page {pageNumber}…</div>}
                    onLoadSuccess={(page: any) => {
                      const width = Number(page?.originalWidth || page?.view?.[2] || 1);
                      const height = Number(page?.originalHeight || page?.view?.[3] || width * 1.414);
                      const nextRatio = width > 0 && height > 0 ? height / width : 1.414;
                      setPageRatios((current) => Math.abs((current[pageNumber] || 0) - nextRatio) < 0.001 ? current : { ...current, [pageNumber]: nextRatio });
                    }}
                  />
                ) : (
                  <div className="publication-native-pdf__placeholder" aria-label={`Page ${pageNumber} is ready to render`} />
                )}
              </div>
            );
          })}
        </div>
      </Document>
    </section>
  );
}

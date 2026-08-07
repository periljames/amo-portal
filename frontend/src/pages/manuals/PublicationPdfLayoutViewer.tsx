import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Link2,
  List,
  Maximize2,
  Minimize2,
  Share2,
  X,
} from "lucide-react";

import {
  getPublicationReferences,
  type DocumentationIndexState,
  type DocumentationReference,
} from "../../services/documentation";
import LinkedDocumentationPanel from "./LinkedDocumentationPanel";
import PdfReaderCore, {
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCore";
import "./publicationReaderZoom.css";
import "./publicationReaderFocusMode.css";

export type PdfOutlineItem = PdfReaderOutlineItem;

type PublicationPdfLayoutViewerProps = {
  fileUrl: string;
  title: string;
  uncontrolled?: boolean;
  navigationRequest?: PdfReaderNavigationRequest | null;
  initialPage?: number;
  initialZoom?: number;
  references?: DocumentationReference[];
  activeReferenceId?: string | null;
  onReferenceClick?: (reference: DocumentationReference) => void;
  onPageChange?: (pageNumber: number) => void;
  onZoomChange?: (zoomPercent: number) => void;
  onAcroFormDetected?: (hasAcroForm: boolean) => void;
  onOutlineReady?: (items: PdfOutlineItem[]) => void;
  governedAnnotations?: Array<{
    id: string;
    annotation_type: string;
    color: string;
    note_text?: string | null;
    location?: { page_number?: number | null; normalized_rects?: Array<Record<string, number>> } | null;
  }>;
  onGovernedAnnotationClick?: (annotationId: string) => void;
};

type SourceIdentity = {
  tenant: string;
  manualId: string;
  revisionId: string;
};

const READER_MODE_CLASS = "publication-reader-page--reader-mode";
const READER_MODE_BODY_CLASS = "publication-reader-mode-active";
const NAVIGATION_COMMAND_TTL_MS = 15_000;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
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

function hotspotStyle(reference: DocumentationReference): CSSProperties | null {
  const box = reference.source?.bbox || {};
  const x = Number(box.x);
  const y = Number(box.y);
  const width = Number(box.width);
  const height = Number(box.height);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
    return null;
  }
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

function humanize(value: unknown, fallback = "Pending review"): string {
  const text = String(value ?? "").trim();
  return text ? text.replaceAll("_", " ") : fallback;
}

function searchResultPage(button: Element): number | null {
  const label = button.querySelector("small")?.textContent || "";
  const match = label.match(/\bpage\s+(\d+)\b/i);
  const page = Number(match?.[1] || 0);
  return Number.isInteger(page) && page > 0 ? page : null;
}

/**
 * Layout integration intentionally has no second TOC state controller.
 *
 * PublicationsReaderPage remains the sole owner of active navigation rows.
 * This component translates reader outline data and explicit search/reference
 * actions into one-shot reader navigation commands. Once the reader begins to
 * move, the command is released so resize, fit and virtualizer remeasurement
 * cannot replay an old destination and snap the user back.
 */
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
  governedAnnotations = [],
  onGovernedAnnotationClick,
}: PublicationPdfLayoutViewerProps) {
  const identity = useMemo(() => sourceIdentity(fileUrl), [fileUrl]);
  const readerRootRef = useRef<HTMLDivElement | null>(null);
  const navigationClearTimerRef = useRef<number | null>(null);
  const [automaticReferences, setAutomaticReferences] = useState<DocumentationReference[]>([]);
  const [indexState, setIndexState] = useState<DocumentationIndexState | null>(null);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [selectedReferenceId, setSelectedReferenceId] = useState<string | null>(
    activeReferenceId || null,
  );
  const [referenceListOpen, setReferenceListOpen] = useState(false);
  const [readerNavigationRequest, setReaderNavigationRequest] =
    useState<PdfReaderNavigationRequest | null>(navigationRequest || null);
  const [readerMode, setReaderMode] = useState(false);
  const [pageLinkCopied, setPageLinkCopied] = useState(false);

  const clearReaderNavigationCommand = useCallback(() => {
    if (navigationClearTimerRef.current !== null) {
      window.clearTimeout(navigationClearTimerRef.current);
      navigationClearTimerRef.current = null;
    }
    setReaderNavigationRequest(null);
  }, []);

  const dispatchReaderNavigation = useCallback((request: PdfReaderNavigationRequest) => {
    if (navigationClearTimerRef.current !== null) {
      window.clearTimeout(navigationClearTimerRef.current);
    }
    setReaderNavigationRequest(request);
    navigationClearTimerRef.current = window.setTimeout(() => {
      navigationClearTimerRef.current = null;
      setReaderNavigationRequest((current) => (
        current?.token === request.token ? null : current
      ));
    }, NAVIGATION_COMMAND_TTL_MS);
  }, []);

  useEffect(() => {
    if (!navigationRequest) return;
    dispatchReaderNavigation(navigationRequest);
  }, [
    dispatchReaderNavigation,
    navigationRequest?.page,
    navigationRequest?.token,
  ]);

  useEffect(() => {
    const root = readerRootRef.current;
    if (!root) return;

    const releaseConsumedCommand = () => clearReaderNavigationCommand();
    root.addEventListener("scroll", releaseConsumedCommand, true);
    return () => root.removeEventListener("scroll", releaseConsumedCommand, true);
  }, [clearReaderNavigationCommand]);

  useEffect(() => {
    const page = document.querySelector<HTMLElement>(".publication-reader-page");
    if (!page) return;

    const routeIndexedSearchToPdf = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest(".publication-search-results button");
      if (!button || !page.contains(button)) return;
      const destination = searchResultPage(button);
      if (!destination) return;

      event.preventDefault();
      event.stopPropagation();
      dispatchReaderNavigation({ page: destination, token: Date.now() });
    };

    page.addEventListener("click", routeIndexedSearchToPdf, true);
    return () => page.removeEventListener("click", routeIndexedSearchToPdf, true);
  }, [dispatchReaderNavigation]);

  const readerPageElement = useCallback(() => (
    readerRootRef.current?.closest<HTMLElement>(".publication-reader-page") || null
  ), []);

  const leaveReaderMode = useCallback(() => {
    const page = readerPageElement();
    page?.classList.remove(READER_MODE_CLASS);
    document.body.classList.remove(READER_MODE_BODY_CLASS);
    setReaderMode(false);
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => undefined);
    }
  }, [readerPageElement]);

  const enterReaderMode = useCallback(() => {
    const page = readerPageElement();
    if (!page) return;
    page.classList.add(READER_MODE_CLASS);
    document.body.classList.add(READER_MODE_BODY_CLASS);
    setReaderMode(true);
    if (page.requestFullscreen && !document.fullscreenElement) {
      void page.requestFullscreen().catch(() => undefined);
    }
  }, [readerPageElement]);

  useEffect(() => {
    const synchronizeFullscreenState = () => {
      const page = readerPageElement();
      if (!page) return;
      if (document.fullscreenElement === page) {
        page.classList.add(READER_MODE_CLASS);
        document.body.classList.add(READER_MODE_BODY_CLASS);
        setReaderMode(true);
        return;
      }
      if (!document.fullscreenElement && page.classList.contains(READER_MODE_CLASS)) {
        page.classList.remove(READER_MODE_CLASS);
        document.body.classList.remove(READER_MODE_BODY_CLASS);
        setReaderMode(false);
      }
    };

    const exitFallbackOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const page = readerPageElement();
      if (!page?.classList.contains(READER_MODE_CLASS)) return;
      page.classList.remove(READER_MODE_CLASS);
      document.body.classList.remove(READER_MODE_BODY_CLASS);
      setReaderMode(false);
    };

    document.addEventListener("fullscreenchange", synchronizeFullscreenState);
    document.addEventListener("keydown", exitFallbackOnEscape);
    return () => {
      document.removeEventListener("fullscreenchange", synchronizeFullscreenState);
      document.removeEventListener("keydown", exitFallbackOnEscape);
      const page = readerPageElement();
      page?.classList.remove(READER_MODE_CLASS);
      document.body.classList.remove(READER_MODE_BODY_CLASS);
      if (navigationClearTimerRef.current !== null) {
        window.clearTimeout(navigationClearTimerRef.current);
      }
    };
  }, [readerPageElement]);

  useEffect(() => {
    if (!identity || references.length) return;
    let active = true;
    let timer = 0;

    const load = () => {
      getPublicationReferences(
        identity.tenant,
        identity.manualId,
        identity.revisionId,
      )
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
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [identity, references.length]);

  useEffect(() => {
    setSelectedReferenceId(activeReferenceId || null);
  }, [activeReferenceId]);

  const allReferences = references.length ? references : automaticReferences;
  const referencesByPage = useMemo(() => {
    const grouped = new Map<number, DocumentationReference[]>();
    for (const reference of allReferences) {
      const page = Number(reference.source?.page_number || 0);
      if (!page) continue;
      grouped.set(page, [...(grouped.get(page) || []), reference]);
    }
    return grouped;
  }, [allReferences]);

  const selectedReference =
    allReferences.find(
      (reference) => reference.id === (activeReferenceId || selectedReferenceId),
    ) || null;
  const currentReferences = referencesByPage.get(currentPage) || [];
  const annotationsByPage = useMemo(() => {
    const grouped = new Map<number, typeof governedAnnotations>();
    for (const annotation of governedAnnotations) {
      const page = Number(annotation.location?.page_number || 0);
      if (!page) continue;
      grouped.set(page, [...(grouped.get(page) || []), annotation]);
    }
    return grouped;
  }, [governedAnnotations]);

  const openReference = (reference: DocumentationReference) => {
    if (!reference.target) return;
    setSelectedReferenceId(reference.id);
    setReferenceListOpen(false);
    onReferenceClick?.(reference);
  };

  const copyControlledPageLink = async () => {
    const url = new URL(window.location.href);
    url.hash = `pdf-page-${currentPage}`;
    await navigator.clipboard.writeText(url.toString());
    setPageLinkCopied(true);
    window.setTimeout(() => setPageLinkCopied(false), 1800);
  };

  if (!identity) {
    return (
      <div className="publication-native-pdf__error" role="alert">
        The controlled PDF source could not be identified.
      </div>
    );
  }

  const readerIdentityKey =
    `${identity.tenant}:${identity.manualId}:${identity.revisionId}`;

  return (
    <div
      ref={readerRootRef}
      className={`publication-linked-layout ${selectedReference ? "has-selection" : ""}`}
      onPointerDownCapture={(event) => {
        const target = event.target;
        if (target instanceof Element && target.closest(".pdfv3-zoom")) {
          clearReaderNavigationCommand();
        }
      }}
    >
      <div className="publication-native-pdf">
        <div className="publication-reader-utility-dock" aria-label="Reader utilities">
          <button
            type="button"
            onClick={() => void copyControlledPageLink()}
            title="Copy a permission-controlled link to this revision and page"
          >
            <Share2 size={15} />
            <span>{pageLinkCopied ? "Link copied" : "Copy page link"}</span>
          </button>
          <button
            type="button"
            className="publication-reader-mode-toggle"
            aria-pressed={readerMode}
            onClick={() => {
              if (readerMode) leaveReaderMode();
              else enterReaderMode();
            }}
          >
            {readerMode ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            <span>{readerMode ? "Exit reader mode" : "Reader mode"}</span>
            {readerMode ? <kbd>Esc</kbd> : null}
          </button>
        </div>

        {indexing(indexState) ? (
          <div className="pdf-engine-notice">Indexing linked documents…</div>
        ) : null}

        {currentReferences.length ? (
          <div className="publication-page-links-control">
            <button
              type="button"
              className="publication-page-links-button"
              onClick={() => setReferenceListOpen((value) => !value)}
            >
              <Link2 size={14} />
              {currentReferences.length} linked
            </button>
            {referenceListOpen ? (
              <div className="publication-page-links-popover">
                <header>
                  <strong>Linked items on page {currentPage}</strong>
                  <button
                    type="button"
                    onClick={() => setReferenceListOpen(false)}
                    aria-label="Close linked items"
                  >
                    <X size={14} />
                  </button>
                </header>
                {currentReferences.map((reference) => (
                  <button
                    type="button"
                    key={reference.id}
                    disabled={!reference.target}
                    onClick={() => openReference(reference)}
                  >
                    <List size={14} />
                    <span>
                      <strong>{reference.raw_token}</strong>
                      <small>
                        {reference.target
                          ? `${reference.target.code} · ${reference.target.title}`
                          : `${humanize(reference.status)} · awaiting Document Control`}
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <PdfReaderCore
          key={readerIdentityKey}
          fileUrl={fileUrl}
          originalDownloadUrl={fileUrl}
          title={title}
          filename={`${title}.pdf`}
          identity={identity}
          uncontrolled={uncontrolled}
          navigationRequest={readerNavigationRequest}
          initialPage={initialPage}
          initialZoom={initialZoom}
          onPageChange={(pageNumber) => {
            setCurrentPage(pageNumber);
            setReaderNavigationRequest((current) => (
              current?.page === pageNumber ? null : current
            ));
            onPageChange?.(pageNumber);
          }}
          onZoomChange={onZoomChange}
          onAcroFormDetected={onAcroFormDetected}
          onOutlineReady={onOutlineReady}
          renderPageOverlay={(pageNumber) => (
            <>
              {(referencesByPage.get(pageNumber) || []).map((reference) => {
                const style = hotspotStyle(reference);
                if (!style || !reference.target) return null;
                return (
                  <button
                    type="button"
                    key={reference.id}
                    className={[
                      "publication-reference-hotspot",
                      (activeReferenceId || selectedReferenceId) === reference.id
                        ? "active"
                        : "",
                    ].filter(Boolean).join(" ")}
                    style={style}
                    aria-label={`${reference.raw_token}: open ${reference.target.code}`}
                    onClick={() => openReference(reference)}
                  />
                );
              })}
              {(annotationsByPage.get(pageNumber) || []).flatMap((annotation, annotationIndex) => {
                const rects = annotation.location?.normalized_rects || [];
                if (!rects.length) {
                  return [<button
                    type="button"
                    key={`annotation-${annotation.id}`}
                    className="publication-governed-annotation-pin"
                    style={{ top: `${10 + annotationIndex * 30}px` }}
                    title={annotation.note_text || annotation.annotation_type.replaceAll("_", " ")}
                    aria-label={`Open ${annotation.annotation_type.replaceAll("_", " ")} annotation`}
                    onClick={() => onGovernedAnnotationClick?.(annotation.id)}
                  />];
                }
                return rects.map((rect, rectIndex) => (
                  <button
                    type="button"
                    key={`annotation-${annotation.id}-${rectIndex}`}
                    className={`publication-governed-annotation-mark is-${annotation.annotation_type.toLowerCase()}`}
                    style={{
                      left: `${Math.max(0, Math.min(1, Number(rect.x) || 0)) * 100}%`,
                      top: `${Math.max(0, Math.min(1, Number(rect.y) || 0)) * 100}%`,
                      width: `${Math.max(0.004, Math.min(1, Number(rect.width) || 0.004)) * 100}%`,
                      height: `${Math.max(0.006, Math.min(1, Number(rect.height) || 0.006)) * 100}%`,
                    }}
                    title={annotation.note_text || annotation.annotation_type.replaceAll("_", " ")}
                    aria-label={`Open ${annotation.annotation_type.replaceAll("_", " ")} annotation`}
                    onClick={() => onGovernedAnnotationClick?.(annotation.id)}
                  />
                ));
              })}
            </>
          )}
        />
      </div>

      {selectedReference ? (
        <LinkedDocumentationPanel
          tenant={identity.tenant}
          referenceId={selectedReference.id}
          onClose={() => setSelectedReferenceId(null)}
        />
      ) : null}
    </div>
  );
}

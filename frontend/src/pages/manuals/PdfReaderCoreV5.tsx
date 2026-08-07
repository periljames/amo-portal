import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { Files, ListTree, LoaderCircle, Search, X } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";

import {
  getPublicationReaderBootstrap,
  readCachedPublicationBootstrap,
  searchPublicationReader,
  type PublicationSearchResult,
} from "../../services/publications";
import PdfReaderCoreV4, {
  type PdfReaderCoreProps,
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCoreV4";
import "./pdfReaderNavigatorV5.css";

type NavigatorTab = "contents" | "pages" | "search";

const MOBILE_NAV_QUERY = "(max-width: 760px)";
const SCALE_SETTLE_MS = 90;

type ReaderNavigationItem = PdfReaderOutlineItem & {
  source: "PDF" | "INDEX";
};

function indexedOutline(
  sections: Array<{
    id: string;
    heading: string;
    level?: number | null;
    page_start?: number | null;
  }>,
): ReaderNavigationItem[] {
  return sections
    .map((section, index) => ({
      id: `index-${section.id || index}`,
      title: String(section.heading || `Page ${section.page_start || index + 1}`),
      page: Math.max(0, Number(section.page_start || 0)),
      level: Math.max(1, Math.min(5, Number(section.level || 1))),
      source: "INDEX" as const,
    }))
    .filter((item) => item.page > 0);
}

function matchingOutline(
  items: ReaderNavigationItem[],
  rawQuery: string,
): ReaderNavigationItem[] {
  const query = rawQuery.trim().toLocaleLowerCase();
  if (!query) return items;
  const direct = new Set(
    items
      .filter((item) => item.title.toLocaleLowerCase().includes(query))
      .map((item) => item.id),
  );
  if (!direct.size) return [];

  return items.filter((item) => (
    direct.has(item.id)
    || [...direct].some((id) => id.startsWith(`${item.id}-`))
  ));
}

function activeOutlineItem(
  items: ReaderNavigationItem[],
  page: number,
): ReaderNavigationItem | null {
  const eligible = items.filter((item) => item.page <= page);
  if (!eligible.length) return items[0] || null;
  return eligible.reduce((best, item) => (
    item.page >= best.page ? item : best
  ));
}

function initialNavigationOpen(): boolean {
  if (typeof window === "undefined") return true;
  return !window.matchMedia(MOBILE_NAV_QUERY).matches;
}

function clearReaderHash(): void {
  if (typeof window === "undefined" || !/^#pdf-page-\d+$/i.test(window.location.hash)) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
}

export default function PdfReaderCoreV5(props: PdfReaderCoreProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const pageListRef = useRef<HTMLDivElement | null>(null);
  const tokenRef = useRef(Date.now());
  const scaleSettleTimerRef = useRef<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(initialNavigationOpen);
  const [tab, setTab] = useState<NavigatorTab>("contents");
  const [nativeOutline, setNativeOutline] = useState<ReaderNavigationItem[]>([]);
  const [fallbackOutline, setFallbackOutline] = useState<ReaderNavigationItem[]>([]);
  const [tocFilter, setTocFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(Math.max(1, props.initialPage || 1));
  const [internalNavigation, setInternalNavigation] = useState<PdfReaderNavigationRequest | null>(null);
  const [releasedExternalToken, setReleasedExternalToken] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PublicationSearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");

  const pageCount = Math.max(
    0,
    Number(props.capabilities?.page_count || 0),
    ...nativeOutline.map((item) => item.page),
    ...fallbackOutline.map((item) => item.page),
  );
  const outline = nativeOutline.length ? nativeOutline : fallbackOutline;
  const filteredOutline = useMemo(
    () => matchingOutline(outline, tocFilter),
    [outline, tocFilter],
  );
  const activeOutline = useMemo(
    () => activeOutlineItem(outline, currentPage),
    [currentPage, outline],
  );

  const rowCount = Math.ceil(pageCount / 2);
  const pageVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => pageListRef.current,
    estimateSize: () => 132,
    overscan: 3,
  });

  const closeMobileNavigation = useCallback(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia(MOBILE_NAV_QUERY).matches) setSidebarOpen(false);
  }, []);

  const ownNavigate = useCallback((page: number) => {
    if (!Number.isInteger(page) || page < 1) return;
    tokenRef.current = Math.max(Date.now(), tokenRef.current + 1);
    setInternalNavigation({ page, token: tokenRef.current });
    closeMobileNavigation();
  }, [closeMobileNavigation]);

  const releaseProgrammaticNavigation = useCallback(() => {
    if (scaleSettleTimerRef.current !== null) {
      window.clearTimeout(scaleSettleTimerRef.current);
      scaleSettleTimerRef.current = null;
    }
    setInternalNavigation((current) => current ? null : current);
    if (props.navigationRequest?.token) setReleasedExternalToken(props.navigationRequest.token);
    clearReaderHash();
  }, [props.navigationRequest?.token]);

  const scheduleScaleStabilization = useCallback(() => {
    if (scaleSettleTimerRef.current !== null) window.clearTimeout(scaleSettleTimerRef.current);
    if (props.navigationRequest?.token) setReleasedExternalToken(props.navigationRequest.token);
    setInternalNavigation((current) => current ? null : current);
    clearReaderHash();

    const pageToKeep = currentPage;
    scaleSettleTimerRef.current = window.setTimeout(() => {
      scaleSettleTimerRef.current = null;
      ownNavigate(pageToKeep);
    }, SCALE_SETTLE_MS);
  }, [currentPage, ownNavigate, props.navigationRequest?.token]);

  const activeExternalNavigation = props.navigationRequest?.token === releasedExternalToken
    ? null
    : props.navigationRequest;

  const effectiveNavigation = useMemo(() => {
    const external = activeExternalNavigation;
    if (!external) return internalNavigation;
    if (!internalNavigation) return external;
    return external.token >= internalNavigation.token ? external : internalNavigation;
  }, [activeExternalNavigation, internalNavigation]);

  useEffect(() => {
    const page = rootRef.current?.closest<HTMLElement>(".publication-reader-page");
    if (!page) return;
    page.classList.add("publication-reader-page--dense-pdf-reader");
    return () => page.classList.remove("publication-reader-page--dense-pdf-reader");
  }, []);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_NAV_QUERY);
    const handleViewportChange = (event: MediaQueryListEvent) => {
      if (event.matches) setSidebarOpen(false);
    };
    media.addEventListener("change", handleViewportChange);
    return () => media.removeEventListener("change", handleViewportChange);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !window.matchMedia(MOBILE_NAV_QUERY).matches) return;
      event.preventDefault();
      setSidebarOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [sidebarOpen]);

  useEffect(() => () => {
    if (scaleSettleTimerRef.current !== null) window.clearTimeout(scaleSettleTimerRef.current);
  }, []);

  useEffect(() => {
    const { tenant, manualId, revisionId } = props.identity;
    if (!tenant || !manualId || !revisionId) return;
    let active = true;

    const apply = (bootstrap: ReturnType<typeof readCachedPublicationBootstrap>) => {
      if (!active || !bootstrap) return;
      setFallbackOutline(indexedOutline(bootstrap.read.sections || []));
    };

    const cached = readCachedPublicationBootstrap(tenant, manualId, revisionId);
    apply(cached);
    if (cached) return () => { active = false; };

    void getPublicationReaderBootstrap(tenant, manualId, revisionId)
      .then((bootstrap) => apply(bootstrap))
      .catch(() => undefined);
    return () => { active = false; };
  }, [props.identity.manualId, props.identity.revisionId, props.identity.tenant]);

  useEffect(() => {
    if (tab !== "search") return;
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, [tab]);

  const openSearch = useCallback(() => {
    setSidebarOpen(true);
    setTab("search");
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  const captureToolbarClick = (event: ReactMouseEvent<HTMLDivElement>) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>("button");
    if (!button) return;
    const label = button.getAttribute("aria-label") || "";
    if (label === "Show or hide document navigation") {
      event.preventDefault();
      event.stopPropagation();
      setSidebarOpen((value) => !value);
      return;
    }
    if (label === "Search this PDF") {
      event.preventDefault();
      event.stopPropagation();
      openSearch();
      return;
    }
    if (label === "Zoom in" || label === "Zoom out") {
      scheduleScaleStabilization();
    }
  };

  const captureSearchShortcut = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLocaleLowerCase() !== "f") return;
    event.preventDefault();
    event.stopPropagation();
    openSearch();
  };

  const releaseIfReaderViewport = (target: EventTarget | null) => {
    if (!(target instanceof Element) || !target.closest(".pdfv3-viewport")) return;
    releaseProgrammaticNavigation();
  };

  const runIndexedSearch = async (): Promise<void> => {
    const value = query.trim();
    if (value.length < 2) return;
    setSearchBusy(true);
    setSearchError("");
    try {
      const results = await searchPublicationReader(
        props.identity.tenant,
        props.identity.manualId,
        props.identity.revisionId,
        value,
      );
      setSearchResults(results);
    } catch (error) {
      setSearchResults([]);
      setSearchError(error instanceof Error ? error.message : "Publication search failed.");
    } finally {
      setSearchBusy(false);
    }
  };

  return (
    <div
      ref={rootRef}
      className={`pdfv5-shell${sidebarOpen ? "" : " is-navigation-collapsed"}${sidebarOpen && tab === "search" ? " is-search-panel-open" : ""}`}
      onClickCapture={captureToolbarClick}
      onKeyDownCapture={captureSearchShortcut}
      onWheelCapture={(event) => releaseIfReaderViewport(event.target)}
      onTouchStartCapture={(event) => releaseIfReaderViewport(event.target)}
      onPointerDownCapture={(event) => releaseIfReaderViewport(event.target)}
      onChangeCapture={(event) => {
        const target = event.target;
        if (target instanceof HTMLSelectElement && target.classList.contains("pdfv4-scale-select")) {
          scheduleScaleStabilization();
        }
      }}
    >
      {sidebarOpen ? (
        <button
          type="button"
          className="pdfv5-mobile-scrim"
          aria-label="Close document navigation"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      {sidebarOpen ? (
        <aside className="pdfv5-navigator" aria-label="Document navigation">
          <div className="pdfv5-navigator-head">
            <div className="pdfv5-tabs" role="tablist" aria-label="Reader navigation modes">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "contents"}
                className={tab === "contents" ? "active" : ""}
                onClick={() => setTab("contents")}
              >
                <ListTree size={15} />
                <span>Contents</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "pages"}
                className={tab === "pages" ? "active" : ""}
                onClick={() => setTab("pages")}
              >
                <Files size={15} />
                <span>Pages</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "search"}
                className={tab === "search" ? "active" : ""}
                onClick={openSearch}
              >
                <Search size={15} />
                <span>Search</span>
              </button>
            </div>
            <button
              type="button"
              className="pdfv5-mobile-close"
              aria-label="Close document navigation"
              title="Close document navigation"
              onClick={() => setSidebarOpen(false)}
            >
              <X size={18} />
            </button>
          </div>

          {tab === "contents" ? (
            <div className="pdfv5-contents">
              <label className="pdfv5-filter">
                <Search size={15} />
                <input
                  value={tocFilter}
                  onChange={(event) => setTocFilter(event.target.value)}
                  placeholder="Filter contents"
                  aria-label="Filter document contents"
                />
                {tocFilter ? (
                  <button type="button" onClick={() => setTocFilter("")} aria-label="Clear contents filter">×</button>
                ) : null}
              </label>
              <div className="pdfv5-outline" aria-label="Document contents">
                {filteredOutline.length ? filteredOutline.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className={item.id === activeOutline?.id ? "active" : ""}
                    style={{ "--pdfv5-level": Math.max(0, item.level - 1) } as CSSProperties}
                    onClick={() => ownNavigate(item.page)}
                    title={`${item.title} · page ${item.page}`}
                  >
                    <span>{item.title}</span>
                    <small>{item.page}</small>
                  </button>
                )) : (
                  <p className="pdfv5-empty">
                    {tocFilter ? "No contents match this filter." : "No dependable document outline is available."}
                  </p>
                )}
              </div>
            </div>
          ) : null}

          {tab === "pages" ? (
            <div ref={pageListRef} className="pdfv5-page-browser" aria-label="Page browser">
              {pageCount ? (
                <div
                  className="pdfv5-page-virtualizer"
                  style={{ height: `${pageVirtualizer.getTotalSize()}px` }}
                >
                  {pageVirtualizer.getVirtualItems().map((row) => {
                    const first = row.index * 2 + 1;
                    const pages = [first, first + 1].filter((page) => page <= pageCount);
                    return (
                      <div
                        key={row.key}
                        className="pdfv5-page-row"
                        style={{ transform: `translateY(${row.start}px)` }}
                      >
                        {pages.map((page) => (
                          <button
                            type="button"
                            key={page}
                            className={page === currentPage ? "active" : ""}
                            onClick={() => ownNavigate(page)}
                            aria-label={`Open page ${page}`}
                          >
                            <span className="pdfv5-page-sheet" aria-hidden="true">
                              <i />
                              <i />
                              <i />
                            </span>
                            <strong>{page}</strong>
                          </button>
                        ))}
                      </div>
                    );
                  })}
                </div>
              ) : <p className="pdfv5-empty">Page count is not available yet.</p>}
            </div>
          ) : null}

          {tab === "search" ? (
            <div className="pdfv5-search-panel">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void runIndexedSearch();
                }}
              >
                <label>
                  <Search size={15} />
                  <input
                    ref={searchInputRef}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search this publication"
                    aria-label="Search this publication"
                  />
                </label>
                <button type="submit" disabled={searchBusy || query.trim().length < 2}>
                  {searchBusy ? <LoaderCircle className="is-spinning" size={15} /> : "Find"}
                </button>
              </form>
              {searchError ? <p className="pdfv5-search-error">{searchError}</p> : null}
              <div className="pdfv5-search-results" aria-live="polite">
                {!searchBusy && query.trim().length >= 2 ? (
                  <p>{searchResults.length} result{searchResults.length === 1 ? "" : "s"}</p>
                ) : null}
                {searchResults.map((result) => (
                  <button
                    type="button"
                    key={`${result.section_id}:${result.page_start || 0}`}
                    disabled={!result.page_start}
                    onClick={() => result.page_start && ownNavigate(result.page_start)}
                  >
                    <strong>{result.heading}</strong>
                    <span>{result.snippet}</span>
                    {result.page_start ? <small>Page {result.page_start}</small> : null}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </aside>
      ) : null}

      <div className="pdfv5-reader-host">
        <PdfReaderCoreV4
          {...props}
          navigationRequest={effectiveNavigation}
          onPageChange={(page) => {
            setCurrentPage(page);
            if (internalNavigation?.page === page) setInternalNavigation(null);
            props.onPageChange?.(page);
          }}
          onOutlineReady={(items) => {
            setNativeOutline(items.map((item) => ({ ...item, source: "PDF" as const })));
            props.onOutlineReady?.(items);
          }}
        />
      </div>
    </div>
  );
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};

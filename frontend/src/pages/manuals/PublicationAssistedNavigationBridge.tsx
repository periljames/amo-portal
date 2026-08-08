import { useEffect, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import "./publicationAssistedNavigation.css";

export type PublicationNavigationDetail = {
  manualId?: string | null;
  revisionId?: string | null;
  pageNumber?: number | null;
  sectionId?: string | null;
  anchor?: string | null;
};

function safeAnchor(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]+/g, "-");
}

function appScroller(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".app-shell__scroll");
}

function scrollPrecisely(element: HTMLElement): void {
  const readerViewport = element.closest<HTMLElement>(".pdfv3-viewport");
  if (readerViewport) {
    const viewportRect = readerViewport.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const top = readerViewport.scrollTop + elementRect.top - viewportRect.top - 14;
    readerViewport.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    return;
  }

  const scroller = appScroller();
  const offset = 64;
  if (scroller) {
    const scrollerRect = scroller.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const top = scroller.scrollTop + elementRect.top - scrollerRect.top - offset;
    scroller.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    return;
  }
  window.scrollTo({ top: Math.max(0, window.scrollY + element.getBoundingClientRect().top - offset), behavior: "auto" });
}

function targetElement(detail: PublicationNavigationDetail): HTMLElement | null {
  const page = Number(detail.pageNumber || 0);
  if (page > 0) {
    const pageElement = document.querySelector<HTMLElement>(
      `.pdfv3-page[data-page-number="${page}"], .pdf-engine-page[data-page-number="${page}"], .publication-native-pdf__page[data-page-number="${page}"]`,
    );
    if (pageElement) return pageElement;
  }
  const anchor = String(detail.anchor || "").trim();
  if (anchor) {
    const escaped = CSS.escape(anchor);
    return document.querySelector<HTMLElement>(`[data-anchor="${escaped}"], #${CSS.escape(safeAnchor(anchor))}`);
  }
  const sectionId = String(detail.sectionId || "").trim();
  if (sectionId) return document.querySelector<HTMLElement>(`[data-section-id="${CSS.escape(sectionId)}"]`);
  return null;
}

export default function PublicationAssistedNavigationBridge() {
  const params = useParams<{ manualId?: string; revId?: string }>();
  const [searchParams] = useSearchParams();
  const handledRoute = useRef("");

  useEffect(() => {
    let timer = 0;
    let active = true;

    const navigateTo = (detail: PublicationNavigationDetail) => {
      if (detail.manualId && detail.manualId !== params.manualId) return;
      if (detail.revisionId && detail.revisionId !== params.revId) return;
      let attempts = 0;
      const attempt = () => {
        if (!active) return;
        const element = targetElement(detail);
        if (element) {
          scrollPrecisely(element);
          element.classList.add("publication-assisted-navigation-target");
          window.setTimeout(() => element.classList.remove("publication-assisted-navigation-target"), 1800);
          return;
        }
        attempts += 1;
        if (attempts < 80) timer = window.setTimeout(attempt, 100);
      };
      attempt();
    };

    const routeDetail: PublicationNavigationDetail = {
      manualId: params.manualId,
      revisionId: params.revId,
      pageNumber: Number(searchParams.get("page") || 0) || null,
      anchor: searchParams.get("anchor"),
      sectionId: searchParams.get("section"),
    };
    const routeKey = JSON.stringify(routeDetail);
    if ((routeDetail.pageNumber || routeDetail.anchor || routeDetail.sectionId) && handledRoute.current !== routeKey) {
      handledRoute.current = routeKey;
      navigateTo(routeDetail);
    }

    const listener = (event: Event) => navigateTo((event as CustomEvent<PublicationNavigationDetail>).detail || {});
    window.addEventListener("amo:publication-navigate", listener);
    return () => {
      active = false;
      window.removeEventListener("amo:publication-navigate", listener);
      if (timer) window.clearTimeout(timer);
    };
  }, [params.manualId, params.revId, searchParams]);

  return null;
}

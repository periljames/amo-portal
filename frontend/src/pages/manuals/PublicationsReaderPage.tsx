import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeCheck,
  Bookmark,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Download,
  Eye,
  FileText,
  ListTree,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Printer,
  Search,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import {
  acknowledgeRevision,
  emitManualsUpdated,
  getRevisionWorkflow,
  type ManualReadPayload,
  type ManualWorkflowPayload,
} from "../../services/manuals";
import {
  cachePublicationBootstrap,
  downloadBlob,
  fetchPublicationBlob,
  formatFileSize,
  getPublicationReaderBootstrap,
  getPublicationReaderContent,
  readCachedPublicationBootstrap,
  searchPublicationReader,
  updatePublicationReaderPosition,
  type PublicationAcknowledgement,
  type PublicationReaderBootstrap,
  type PublicationReaderMetadata,
  type PublicationSearchResult,
} from "../../services/publications";
import PublicationPdfLayoutViewer, { type PdfOutlineItem } from "./PublicationPdfLayoutViewer";
import PublicationGovernancePanel from "./PublicationGovernancePanel";
import { listReaderAnnotations, type ReaderAnnotation } from "../../services/readerGovernance";
import { useManualRouteContext } from "./context";
import "./manualReader.css";
import "./publicationReaderGovernance.css";
import "./publicationReaderLayout.css";


type ReaderTab = "detail" | "history" | "citations" | "subsidiary";
type NavigationTab = "toc" | "search";
type ViewMode = "layout" | "text";
type ReaderTheme = "neutral" | "warm" | "sepia" | "contrast";
type ReadingWidth = "fit" | "focus" | "wide";

type ReaderSection = ManualReadPayload["sections"][number] & {
  page_start?: number | null;
  page_end?: number | null;
};

type ExtendedReadPayload = Omit<ManualReadPayload, "sections"> & {
  sections: ReaderSection[];
  revision?: {
    id: string;
    rev_number?: string | null;
    issue_number?: string | null;
    effective_date?: string | null;
    published_at?: string | null;
    source_filename?: string | null;
    source_type?: string | null;
    source_mime_type?: string | null;
    source_page_count?: number | null;
    source_available?: boolean;
    source_url?: string | null;
  };
  progress?: {
    last_section_id?: string | null;
    last_anchor_slug?: string | null;
    last_page_number?: number | null;
    scroll_percent?: number;
    zoom_percent?: number;
    last_opened_at?: string | null;
  };
};

type PdfNavigationRequest = { page: number; token: number };

type NavigationItem = {
  key: string;
  renderKey: string;
  title: string;
  level: number;
  page?: number | null;
  section?: ReaderSection;
};

const TAB_VALUES = new Set<ReaderTab>(["detail", "history", "citations", "subsidiary"]);
const ACKNOWLEDGEMENT_TEXT = "I acknowledge that I have read and understood this controlled publication revision.";
const TEXT_PREFETCH_SECTIONS = 10;

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" }).format(parsed);
}

function safeAnchor(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]+/g, "-");
}

function publicationCitation(metadata: PublicationReaderMetadata): string {
  const issue = metadata.issue_number ? `Issue ${metadata.issue_number}` : "Issue not recorded";
  const revision = metadata.revision_number ? `Revision ${metadata.revision_number}` : "Revision not recorded";
  return `${metadata.code} — ${metadata.title}, ${issue}, ${revision}${metadata.date ? `, effective ${formatDate(metadata.date)}` : ""}.`;
}

function sectionForPage(sections: ReaderSection[], pageNumber: number): ReaderSection | null {
  let resolved: ReaderSection | null = null;
  for (const section of sections) {
    const start = Number(section.page_start || 0);
    const end = Number(section.page_end || start || 0);
    if (!start) continue;
    if (pageNumber >= start && (!end || pageNumber <= end)) resolved = section;
    if (start <= pageNumber) resolved = section;
    if (start > pageNumber) break;
  }
  return resolved;
}

function outlineForPage(items: PdfOutlineItem[], pageNumber: number): PdfOutlineItem | null {
  let active: PdfOutlineItem | null = null;
  for (const item of items) {
    if (item.page <= pageNumber) active = item;
    else break;
  }
  return active;
}

function appScroller(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".app-shell__scroll");
}

function scrollPrecisely(element: HTMLElement, behavior: ScrollBehavior = "smooth"): void {
  const scroller = appScroller();
  const stickyOffset = 106;
  if (scroller) {
    const scrollerRect = scroller.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const top = scroller.scrollTop + elementRect.top - scrollerRect.top - stickyOffset;
    scroller.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }
  window.scrollTo({ top: Math.max(0, window.scrollY + element.getBoundingClientRect().top - stickyOffset), behavior });
}

function ReaderStatus({ message }: { message: string }) {
  return <div className="publication-reader-status" role="status"><span className="publication-reader-spinner" aria-hidden="true" /><span>{message}</span></div>;
}

function localPositionKey(tenant: string, manualId: string, revisionId: string): string {
  return `amo-publication-position:v2:${tenant}:${manualId}:${revisionId}`;
}

function loadLocalPosition(tenant: string, manualId: string, revisionId: string): { page: number; zoom: number; anchor: string } {
  try {
    const raw = window.localStorage.getItem(localPositionKey(tenant, manualId, revisionId));
    if (!raw) return { page: 1, zoom: 100, anchor: "" };
    const parsed = JSON.parse(raw) as { page?: number; zoom?: number; anchor?: string };
    return {
      page: Math.max(1, Number(parsed.page || 1)),
      zoom: Math.max(50, Math.min(250, Number(parsed.zoom || 100))),
      anchor: String(parsed.anchor || ""),
    };
  } catch {
    return { page: 1, zoom: 100, anchor: "" };
  }
}

function initialBootstrap(tenant: string, manualId: string, revisionId: string): PublicationReaderBootstrap | null {
  return tenant && manualId && revisionId ? readCachedPublicationBootstrap(tenant, manualId, revisionId) : null;
}

export default function PublicationsReaderPage() {
  const { tenant, amoCode, manualId, revId } = useManualRouteContext();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const cached = useMemo(() => initialBootstrap(tenant, manualId || "", revId || ""), [manualId, revId, tenant]);
  const [payload, setPayload] = useState<ExtendedReadPayload | null>(() => cached?.read as ExtendedReadPayload || null);
  const [metadata, setMetadata] = useState<PublicationReaderMetadata | null>(() => cached?.metadata || null);
  const [workflow, setWorkflow] = useState<ManualWorkflowPayload | null>(null);
  const [acknowledgement, setAcknowledgement] = useState<PublicationAcknowledgement | null>(() => cached?.acknowledgement || null);
  const [acknowledgementBusy, setAcknowledgementBusy] = useState(false);
  const [acknowledgementError, setAcknowledgementError] = useState("");
  const [loading, setLoading] = useState(!cached);
  const [refreshing, setRefreshing] = useState(Boolean(cached));
  const [error, setError] = useState("");
  const [navigationTab, setNavigationTab] = useState<NavigationTab>("toc");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PublicationSearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [activeSection, setActiveSection] = useState(() => cached?.read.progress?.last_anchor_slug || cached?.read.sections[0]?.anchor_slug || "");
  const [activeOutlineKey, setActiveOutlineKey] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(() => String(cached?.metadata.source_type || "").toUpperCase() === "PDF" ? "layout" : "text");
  const [pdfNavigationRequest, setPdfNavigationRequest] = useState<PdfNavigationRequest | null>(null);
  const localPosition = useMemo(() => loadLocalPosition(tenant, manualId || "", revId || ""), [manualId, revId, tenant]);
  const [currentPdfPage, setCurrentPdfPage] = useState(() => cached?.read.progress?.last_page_number || localPosition.page || 1);
  const [zoomPercent, setZoomPercent] = useState(() => cached?.read.progress?.zoom_percent || localPosition.zoom || 100);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const [governanceOpen, setGovernanceOpen] = useState(() => Boolean(searchParams.get("annotation")));
  const [readerAnnotations, setReaderAnnotations] = useState<ReaderAnnotation[]>([]);
  const [nativeOutline, setNativeOutline] = useState<PdfOutlineItem[]>([]);
  const [hasAcroForm, setHasAcroForm] = useState(false);
  const [readerTheme, setReaderTheme] = useState<ReaderTheme>(() => (window.localStorage.getItem("amo-publication-reader-theme") as ReaderTheme) || "neutral");
  const [readingWidth, setReadingWidth] = useState<ReadingWidth>(() => (window.localStorage.getItem("amo-publication-reader-width") as ReadingWidth) || "fit");
  const [blocksBySection, setBlocksBySection] = useState<Record<string, ExtendedReadPayload["blocks"]>>({});
  const [loadingSections, setLoadingSections] = useState<Set<string>>(new Set());
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const navRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const tocListRef = useRef<HTMLDivElement | null>(null);
  const loadedSectionsRef = useRef<Set<string>>(new Set());
  const positionTimerRef = useRef<number | null>(null);

  const requestedTab = searchParams.get("tab") as ReaderTab | null;
  const activeTab: ReaderTab = requestedTab && TAB_VALUES.has(requestedTab) ? requestedTab : "detail";
  const isPublished = Boolean(metadata?.is_published && !payload?.not_published);
  const sourceIsPdf = String(metadata?.source_type || payload?.revision?.source_type || "").toUpperCase() === "PDF";
  const sections = useMemo(() => payload?.sections ?? [], [payload?.sections]);
  const textAvailable = sections.length > 0 && !metadata?.image_only;
  const layoutAvailable = Boolean(metadata?.rendered_pdf_url);
  const viewerPdfPath = metadata?.source_url || metadata?.rendered_pdf_url || "";
  const uncontrolledDownloadPath = tenant && manualId && revId
    ? `/manuals/t/${encodeURIComponent(tenant)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revId)}/rendered.pdf`
    : "";
  const downloadPath = !isPublished && sourceIsPdf ? uncontrolledDownloadPath : metadata?.rendered_pdf_url || "";

  const applyBootstrap = useCallback((bootstrap: PublicationReaderBootstrap) => {
    const readPayload = bootstrap.read as ExtendedReadPayload;
    setPayload(readPayload);
    setMetadata(bootstrap.metadata);
    setAcknowledgement(bootstrap.acknowledgement);
    setActiveSection((current) => current || readPayload.progress?.last_anchor_slug || readPayload.sections[0]?.anchor_slug || "");
    setCurrentPdfPage((current) => readPayload.progress?.last_page_number || current || 1);
    setZoomPercent((current) => readPayload.progress?.zoom_percent || current || 100);
    setViewMode((current) => {
      const uploadedAsPdf = String(bootstrap.metadata.source_type || readPayload.revision?.source_type || "").toUpperCase() === "PDF";
      return uploadedAsPdf || bootstrap.metadata.image_only ? "layout" : current;
    });
    cachePublicationBootstrap(tenant, manualId || "", revId || "", bootstrap);
  }, [manualId, revId, tenant]);

  useEffect(() => {
    if (!tenant || !manualId || !revId) {
      setLoading(false);
      setError("The publication route is incomplete.");
      return;
    }
    let active = true;
    const existing = readCachedPublicationBootstrap(tenant, manualId, revId);
    if (existing) {
      applyBootstrap(existing);
      setLoading(false);
      setRefreshing(true);
    } else {
      setLoading(true);
      setRefreshing(false);
    }
    setError("");
    setAcknowledgementError("");
    getPublicationReaderBootstrap(tenant, manualId, revId)
      .then((bootstrap) => {
        if (!active) return;
        applyBootstrap(bootstrap);
        setError("");
      })
      .catch((caught: unknown) => {
        if (!active || existing) return;
        setError(caught instanceof Error ? caught.message : "The publication could not be loaded.");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          setRefreshing(false);
        }
      });

    const idle = window.setTimeout(() => {
      getRevisionWorkflow(tenant, manualId, revId).then((value) => active && setWorkflow(value)).catch(() => undefined);
    }, existing ? 150 : 700);
    return () => {
      active = false;
      window.clearTimeout(idle);
    };
  }, [applyBootstrap, manualId, revId, tenant]);

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    setSaved(window.localStorage.getItem(`amo-publication-saved:${tenant}:${manualId}:${revId}`) === "1");
  }, [manualId, revId, tenant]);

  const loadTextSections = useCallback(async (sectionIds: string[]) => {
    if (!tenant || !manualId || !revId) return;
    const required = [...new Set(sectionIds.filter((id) => id && !loadedSectionsRef.current.has(id)))];
    if (!required.length) return;
    setLoadingSections((current) => new Set([...current, ...required]));
    try {
      const result = await getPublicationReaderContent(tenant, manualId, revId, required);
      const grouped: Record<string, ExtendedReadPayload["blocks"]> = {};
      for (const section of result.sections) grouped[section.id] = [];
      for (const block of result.blocks) {
        if (!grouped[block.section_id]) grouped[block.section_id] = [];
        grouped[block.section_id].push(block);
      }
      setBlocksBySection((current) => ({ ...current, ...grouped }));
      required.forEach((id) => loadedSectionsRef.current.add(id));
    } finally {
      setLoadingSections((current) => {
        const next = new Set(current);
        required.forEach((id) => next.delete(id));
        return next;
      });
    }
  }, [manualId, revId, tenant]);

  useEffect(() => {
    if (viewMode !== "text" || !sections.length) return;
    const initialIndex = Math.max(0, sections.findIndex((section) => section.anchor_slug === activeSection));
    const selected = sections.slice(initialIndex, initialIndex + TEXT_PREFETCH_SECTIONS).map((section) => section.id);
    void loadTextSections(selected.length ? selected : sections.slice(0, TEXT_PREFETCH_SECTIONS).map((section) => section.id));
  }, [activeSection, loadTextSections, sections, viewMode]);

  useEffect(() => {
    if (viewMode !== "text" || activeTab !== "detail") return;
    const root = appScroller();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const id = String((entry.target as HTMLElement).dataset.sectionId || "");
        const index = sections.findIndex((section) => section.id === id);
        if (index >= 0) void loadTextSections(sections.slice(index, index + 4).map((section) => section.id));
      }
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      const anchor = visible ? String((visible.target as HTMLElement).dataset.anchor || "") : "";
      if (anchor) setActiveSection(anchor);
    }, { root, rootMargin: "700px 0px 700px 0px", threshold: [0, 0.05, 0.25] });
    Object.values(sectionRefs.current).forEach((element) => element && observer.observe(element));
    return () => observer.disconnect();
  }, [activeTab, loadTextSections, sections, viewMode]);

  useEffect(() => {
    const needle = query.trim();
    if (!needle || needle.length < 2 || !tenant || !manualId || !revId) {
      setSearchResults([]);
      setSearchBusy(false);
      return;
    }
    let active = true;
    setSearchBusy(true);
    const timer = window.setTimeout(() => {
      searchPublicationReader(tenant, manualId, revId, needle)
        .then((items) => active && setSearchResults(items))
        .catch(() => active && setSearchResults([]))
        .finally(() => active && setSearchBusy(false));
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [manualId, query, revId, tenant]);

  const navigationItems = useMemo<NavigationItem[]>(() => {
    if (viewMode === "layout" && nativeOutline.length) {
      return nativeOutline.map((item) => ({
        key: item.id,
        renderKey: `outline:${item.id}`,
        title: item.title,
        level: item.level,
        page: item.page,
      }));
    }
    return sections.map((section, index) => ({
      key: section.anchor_slug,
      renderKey: `section:${section.id}:${index}`,
      title: section.heading,
      level: section.level || 1,
      page: section.page_start,
      section,
    }));
  }, [nativeOutline, sections, viewMode]);

  const activeNavigationKey = viewMode === "layout" && nativeOutline.length ? activeOutlineKey : activeSection;
  const activeNavigationRenderKey = navigationItems.find((item) => item.key === activeNavigationKey)?.renderKey
    || navigationItems.find((item) => safeAnchor(item.key) === safeAnchor(activeNavigationKey))?.renderKey
    || "";

  const expandAncestors = useCallback((renderKey: string) => {
    const index = navigationItems.findIndex((item) => item.renderKey === renderKey);
    if (index < 0) return;
    const level = navigationItems[index].level || 1;
    const ancestors: string[] = [];
    let expected = level - 1;
    for (let cursor = index - 1; cursor >= 0 && expected > 0; cursor -= 1) {
      const item = navigationItems[cursor];
      if ((item.level || 1) === expected) {
        ancestors.push(item.renderKey);
        expected -= 1;
      }
    }
    if (!ancestors.length) return;
    setCollapsed((current) => {
      const next = new Set(current);
      ancestors.forEach((ancestor) => next.delete(ancestor));
      return next;
    });
  }, [navigationItems]);

  useEffect(() => {
    if (!activeNavigationRenderKey) return;
    expandAncestors(activeNavigationRenderKey);
    const row = navRowRefs.current[activeNavigationRenderKey];
    const container = tocListRef.current;
    if (!row || !container) return;
    const rowTop = row.offsetTop;
    const rowBottom = rowTop + row.offsetHeight;
    const visibleTop = container.scrollTop;
    const visibleBottom = visibleTop + container.clientHeight;
    if (rowTop < visibleTop + 12) container.scrollTo({ top: Math.max(0, rowTop - 20), behavior: "smooth" });
    else if (rowBottom > visibleBottom - 12) container.scrollTo({ top: rowBottom - container.clientHeight + 24, behavior: "smooth" });
  }, [activeNavigationRenderKey, expandAncestors]);

  const schedulePositionSave = useCallback((next: { page?: number; zoom?: number; anchor?: string; sectionId?: string }) => {
    if (!tenant || !manualId || !revId) return;
    const current = loadLocalPosition(tenant, manualId, revId);
    const value = {
      page: next.page || current.page || currentPdfPage || 1,
      zoom: next.zoom || current.zoom || zoomPercent || 100,
      anchor: next.anchor ?? current.anchor ?? activeSection,
    };
    window.localStorage.setItem(localPositionKey(tenant, manualId, revId), JSON.stringify(value));
    if (positionTimerRef.current) window.clearTimeout(positionTimerRef.current);
    positionTimerRef.current = window.setTimeout(() => {
      void updatePublicationReaderPosition(tenant, manualId, revId, {
        page_number: value.page,
        zoom_percent: value.zoom,
        anchor_slug: value.anchor || undefined,
        section_id: next.sectionId,
      });
    }, 750);
  }, [activeSection, currentPdfPage, manualId, revId, tenant, zoomPercent]);

  useEffect(() => () => {
    if (positionTimerRef.current) window.clearTimeout(positionTimerRef.current);
  }, []);

  const openTextSection = async (section: ReaderSection) => {
    setViewMode("text");
    setActiveSection(section.anchor_slug);
    setMobileNavigationOpen(false);
    await loadTextSections([section.id]);
    window.requestAnimationFrame(() => {
      const element = sectionRefs.current[section.anchor_slug] || document.getElementById(safeAnchor(section.anchor_slug));
      if (element) scrollPrecisely(element);
    });
    schedulePositionSave({ anchor: section.anchor_slug, sectionId: section.id });
  };

  const openNavigationItem = (item: NavigationItem) => {
    setMobileNavigationOpen(false);
    if (item.page && (viewMode === "layout" || !item.section || !textAvailable)) {
      setViewMode("layout");
      setActiveOutlineKey(item.key);
      setPdfNavigationRequest({ page: item.page, token: Date.now() });
      return;
    }
    if (item.section) void openTextSection(item.section);
  };

  const onPdfPageChange = (pageNumber: number) => {
    setCurrentPdfPage(pageNumber);
    if (nativeOutline.length) {
      const outline = outlineForPage(nativeOutline, pageNumber);
      if (outline) setActiveOutlineKey(outline.id);
    } else {
      const section = sectionForPage(sections, pageNumber);
      if (section) setActiveSection(section.anchor_slug);
    }
    schedulePositionSave({ page: pageNumber });
  };

  const onZoomChange = (value: number) => {
    setZoomPercent(value);
    schedulePositionSave({ zoom: value });
  };

  const setTab = (tab: ReaderTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "detail") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: false });
  };

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    let active = true;
    listReaderAnnotations(tenant, manualId, revId)
      .then((value) => { if (active) setReaderAnnotations(value.items); })
      .catch(() => { if (active) setReaderAnnotations([]); });
    return () => { active = false; };
  }, [manualId, revId, tenant]);

  const toggleSaved = () => {
    if (!tenant || !manualId || !revId) return;
    const next = !saved;
    setSaved(next);
    window.localStorage.setItem(`amo-publication-saved:${tenant}:${manualId}:${revId}`, next ? "1" : "0");
  };

  const copyCitation = async () => {
    if (!metadata) return;
    await navigator.clipboard.writeText(publicationCitation(metadata));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const downloadPdf = async () => {
    if (!metadata || !downloadPath) return;
    setDownloadBusy(true);
    try {
      const { blob, filename } = await fetchPublicationBlob(downloadPath);
      downloadBlob(blob, filename || metadata.download_filename);
    } finally {
      setDownloadBusy(false);
    }
  };

  const openPrintablePdf = async () => {
    if (!downloadPath) return;
    const popup = window.open("", "_blank", "noopener,noreferrer");
    try {
      const { blob } = await fetchPublicationBlob(downloadPath);
      const url = URL.createObjectURL(blob);
      if (popup) popup.location.href = url;
      else window.location.assign(url);
      window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
    } catch (caught) {
      popup?.close();
      throw caught;
    }
  };

  const acknowledgePublication = async () => {
    if (!tenant || !manualId || !revId || !acknowledgement?.pending || !isPublished) return;
    if (!window.confirm("Confirm that you have read and understood this controlled publication revision.")) return;
    setAcknowledgementBusy(true);
    setAcknowledgementError("");
    try {
      await acknowledgeRevision(tenant, manualId, revId, ACKNOWLEDGEMENT_TEXT);
      const acknowledgedAt = new Date().toISOString();
      setAcknowledgement((current) => ({
        ...(current || { required: true }), required: true, pending: false, status: "ACKNOWLEDGED",
        acknowledged_at: acknowledgedAt, acknowledgement_text: ACKNOWLEDGEMENT_TEXT,
      }));
      emitManualsUpdated(tenant, "revision-acknowledged");
      getRevisionWorkflow(tenant, manualId, revId).then(setWorkflow).catch(() => undefined);
    } catch (caught: unknown) {
      setAcknowledgementError(caught instanceof Error ? caught.message : "The acknowledgement could not be recorded.");
    } finally {
      setAcknowledgementBusy(false);
    }
  };

  const toggleCollapsed = (key: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const hiddenByCollapsedParent = (index: number): boolean => {
    const level = navigationItems[index]?.level || 1;
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const candidate = navigationItems[cursor];
      if ((candidate.level || 1) < level) {
        if (collapsed.has(candidate.renderKey)) return true;
        if ((candidate.level || 1) === 1) break;
      }
    }
    return false;
  };

  const collapseAll = () => {
    setCollapsed(new Set(navigationItems.filter((item, index) => navigationItems[index + 1] && navigationItems[index + 1].level > item.level).map((item) => item.renderKey)));
  };

  const setTheme = (theme: ReaderTheme) => {
    setReaderTheme(theme);
    window.localStorage.setItem("amo-publication-reader-theme", theme);
  };

  const setWidth = (width: ReadingWidth) => {
    setReadingWidth(width);
    window.localStorage.setItem("amo-publication-reader-width", width);
  };

  const scrollToTop = () => {
    const scroller = appScroller();
    if (scroller) scroller.scrollTo({ top: 0, behavior: "smooth" });
    else window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const navigation = (
    <aside className={`publication-navigation ${mobileNavigationOpen ? "publication-navigation--open" : ""}`} aria-label="Publication navigation">
      <div className="publication-navigation__mobile-head"><strong>Navigate publication</strong><button type="button" onClick={() => setMobileNavigationOpen(false)} aria-label="Close navigation"><X size={18} /></button></div>
      <div className="publication-navigation__tabs" role="tablist">
        <button type="button" className={navigationTab === "toc" ? "active" : ""} onClick={() => setNavigationTab("toc")}><ListTree size={15} /> Contents</button>
        <button type="button" className={navigationTab === "search" ? "active" : ""} onClick={() => setNavigationTab("search")}><Search size={15} /> Search</button>
      </div>
      {navigationTab === "toc" ? (
        <div className="publication-toc">
          <div className="publication-toc__tools">
            <button type="button" onClick={() => setCollapsed(new Set())}>Expand all</button>
            <button type="button" onClick={collapseAll}>Collapse branches</button>
            <button type="button" className="publication-toc__hide" onClick={() => setNavigationCollapsed(true)}><PanelLeftClose size={13} /> Hide</button>
          </div>
          <div className="publication-toc__list" ref={tocListRef}>
            {navigationItems.map((item, index) => {
              if (hiddenByCollapsedParent(index)) return null;
              const hasChildren = navigationItems[index + 1] && navigationItems[index + 1].level > item.level;
              const isCollapsed = collapsed.has(item.renderKey);
              const isActive = activeNavigationKey === item.key || safeAnchor(activeNavigationKey) === safeAnchor(item.key);
              return (
                <div
                  key={item.renderKey}
                  ref={(element) => { navRowRefs.current[item.renderKey] = element; }}
                  className={`publication-toc__row level-${Math.max(1, Math.min(5, item.level || 1))} ${isActive ? "active" : ""}`}
                >
                  {hasChildren ? <button type="button" className="publication-toc__toggle" onClick={() => toggleCollapsed(item.renderKey)} aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${item.title}`}>{isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</button> : <span className="publication-toc__spacer" />}
                  <button type="button" className="publication-toc__link" onClick={() => openNavigationItem(item)}><span>{item.title}</span>{item.page ? <small>p. {item.page}</small> : null}</button>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="publication-search-panel">
          <label><span className="sr-only">Search publication</span><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this publication" autoFocus /></label>
          <p>{searchBusy ? "Searching indexed text…" : query.trim() ? `${searchResults.length} matching section(s)` : "Enter a word or exact phrase."}</p>
          <div className="publication-search-results">
            {searchResults.map((result) => (
              <button type="button" key={result.section_id} onClick={() => {
                const section = sections.find((candidate) => candidate.id === result.section_id);
                if (section) void openTextSection(section);
                else if (result.page_start) {
                  setViewMode("layout");
                  setPdfNavigationRequest({ page: result.page_start, token: Date.now() });
                }
              }}>
                <strong>{result.heading}</strong><span>{result.snippet}</span>{result.page_start ? <small>Page {result.page_start}</small> : null}
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );

  const activeSectionLabel = viewMode === "layout" && nativeOutline.length
    ? nativeOutline.find((item) => item.id === activeOutlineKey)?.title || `Page ${currentPdfPage}`
    : sections.find((section) => section.anchor_slug === activeSection)?.heading || "Document detail";
  const activeSectionId = sections.find((section) => section.anchor_slug === activeSection)?.id;
  const contextLabel = viewMode === "layout" ? `${activeSectionLabel} · page ${currentPdfPage}` : activeSectionLabel;
  const layoutLabel = sourceIsPdf ? "Original layout" : "PDF proof";
  const textLabel = sourceIsPdf ? "Accessible text" : "Readable document";

  const content = (
    <div className={`publication-reader-page publication-reader-theme--${readerTheme} publication-reader-width--${readingWidth} ${navigationCollapsed ? "publication-reader-page--nav-collapsed" : ""}`}>
      {loading ? <ReaderStatus message="Opening publication index…" /> : null}
      {!loading && error ? <div className="publication-reader-error" role="alert"><TriangleAlert size={22} /><div><strong>Publication could not be opened</strong><p>{error}</p></div><button type="button" onClick={() => window.location.reload()}>Retry</button></div> : null}
      {!loading && metadata && payload ? (
        <>
          <header className="publication-document-header">
            <div className="publication-document-header__title">
              <button type="button" className="publication-mobile-nav-button" onClick={() => setMobileNavigationOpen(true)} aria-label="Open table of contents"><Menu size={18} /></button>
              <div><p>{metadata.manual_type || "Publication"}</p><h1>{metadata.title}</h1><span>{metadata.code} · Issue {metadata.issue_number || "—"} · Revision {metadata.revision_number || "—"}</span><span className={`publication-control-status ${isPublished ? "publication-control-status--controlled" : "publication-control-status--uncontrolled"}`}>{isPublished ? "Controlled publication" : "Uncontrolled draft"}</span></div>
            </div>
            <div className="publication-document-header__actions">
              {refreshing ? <span className="publication-cache-state">Refreshing index…</span> : <span className="publication-cache-state">Reader ready</span>}
              <button type="button" className={saved ? "active" : ""} onClick={toggleSaved}><Bookmark size={16} fill={saved ? "currentColor" : "none"} /> {saved ? "Saved" : "Save"}</button>
              <button type="button" onClick={() => void copyCitation()}><ClipboardCopy size={16} /> {copied ? "Copied" : "Citation"}</button>
              {isPublished && acknowledgement?.required && acknowledgement.pending ? <button type="button" className="publication-acknowledgement-action" disabled={acknowledgementBusy} onClick={() => void acknowledgePublication()}><BadgeCheck size={16} /> {acknowledgementBusy ? "Recording…" : "Acknowledge"}</button> : null}
              <button type="button" className="primary" disabled={downloadBusy} onClick={() => void downloadPdf()}><Download size={16} /> {downloadBusy ? "Preparing…" : `Download (${formatFileSize(metadata.rendered_pdf_size_bytes || metadata.source_size_bytes)})`}</button>
              <button type="button" onClick={() => void openPrintablePdf()}><Printer size={16} /> Print</button>
              <button type="button" className={governanceOpen ? "active" : ""} onClick={() => setGovernanceOpen(true)}><ShieldCheck size={16} /> Governance</button>
              <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode || tenant)}/document-control/library/${encodeURIComponent(manualId || "")}?tab=changes`)}>Report problem</button>
            </div>
          </header>

          {!isPublished ? <div className="publication-control-banner" role="status"><TriangleAlert size={18} /><div><strong>Uncontrolled draft</strong>The source is shown exactly as uploaded. A translucent non-destructive reader watermark remains behind the page content; downloaded and printed draft copies remain formally marked uncontrolled.</div></div> : null}

          <div className="publication-floating-header">
            {navigationCollapsed ? <button type="button" className="publication-nav-restore" onClick={() => setNavigationCollapsed(false)} aria-label="Show document navigation"><PanelLeftOpen size={17} /></button> : <button type="button" onClick={() => setMobileNavigationOpen(true)} aria-label="Open document navigation"><Menu size={17} /></button>}
            <strong>{metadata.title}</strong><span>{contextLabel}</span>
            <div className="publication-reader-controls">
              <select value={readerTheme} onChange={(event) => setTheme(event.target.value as ReaderTheme)} aria-label="Reading theme"><option value="neutral">Neutral</option><option value="warm">Warm</option><option value="sepia">Sepia</option><option value="contrast">High contrast</option></select>
              <select value={readingWidth} onChange={(event) => setWidth(event.target.value as ReadingWidth)} aria-label="Reading width"><option value="fit">Fit</option><option value="focus">Focus</option><option value="wide">Wide</option></select>
              <button type="button" className={viewMode === "layout" ? "active" : ""} disabled={!layoutAvailable} onClick={() => setViewMode("layout")}>{layoutLabel}</button>
              <button type="button" className={viewMode === "text" ? "active" : ""} disabled={!textAvailable} onClick={() => setViewMode("text")}>{textLabel}</button>
            </div>
          </div>

          <nav className="publication-document-tabs" aria-label="Publication record tabs">
            <button type="button" className={activeTab === "detail" ? "active" : ""} onClick={() => setTab("detail")}><FileText size={15} /> Document</button>
            <button type="button" className={activeTab === "history" ? "active" : ""} onClick={() => setTab("history")}>History</button>
            <button type="button" className={activeTab === "citations" ? "active" : ""} onClick={() => setTab("citations")}>Citations <span>{metadata.citation_current} / {metadata.citation_total}</span></button>
            <button type="button" className={activeTab === "subsidiary" ? "active" : ""} onClick={() => setTab("subsidiary")}>Subsidiary legislation <span>{metadata.subsidiary_count}</span></button>
          </nav>

          {activeTab === "detail" ? (
            <>
              <section className="publication-metadata" aria-label="Document metadata"><dl>
                <div><dt>Date</dt><dd>{formatDate(metadata.date)}</dd></div><div><dt>Language</dt><dd>{metadata.language || "Not recorded"}</dd></div><div><dt>Status</dt><dd>{metadata.status || payload.status} · {isPublished ? "Controlled" : "Uncontrolled"}</dd></div>
                <div><dt>Source fidelity</dt><dd>{metadata.source_exact ? "Exact uploaded PDF · figures, signatures, annotations and approval marks preserved" : "Generated readable proof"}</dd></div>
                {hasAcroForm || metadata.form_policy === "READ_ONLY_PRESERVED" ? <div><dt>PDF forms</dt><dd><Eye size={15} /> AcroForm appearances are preserved in read-only mode; the portal does not alter field values.</dd></div> : null}
                {acknowledgement?.required ? <div><dt>Acknowledgement</dt><dd>{acknowledgement.pending ? <span className="publication-acknowledgement-state publication-acknowledgement-state--pending">Pending{acknowledgement.due_at ? ` · due ${formatDate(acknowledgement.due_at)}` : ""}{isPublished ? <button type="button" disabled={acknowledgementBusy} onClick={() => void acknowledgePublication()}>Acknowledge now</button> : null}</span> : <span className="publication-acknowledgement-state publication-acknowledgement-state--complete"><BadgeCheck size={16} /> Acknowledged{acknowledgement.acknowledged_at ? ` on ${formatDate(acknowledgement.acknowledged_at)}` : ""}</span>}{acknowledgementError ? <span className="publication-acknowledgement-error">{acknowledgementError}</span> : null}</dd></div> : null}
              </dl></section>

              <div className="publication-reader-workspace">
                {navigationCollapsed ? <button type="button" className="publication-navigation-rail" onClick={() => setNavigationCollapsed(false)} title="Show table of contents"><PanelLeftOpen size={17} /><span>Contents</span></button> : navigation}
                <main className="publication-document-canvas" id="publication-document-content">
                  {metadata.image_only ? <div className="publication-reader-notice"><TriangleAlert size={17} /><span>This PDF has no dependable text layer. Original-layout mode preserves every page, table, figure, signature, form appearance, and approval mark.</span></div> : null}
                  {viewMode === "layout" ? (
                    viewerPdfPath ? <PublicationPdfLayoutViewer
                      fileUrl={viewerPdfPath}
                      title={metadata.title}
                      uncontrolled={!isPublished}
                      navigationRequest={pdfNavigationRequest}
                      initialPage={payload.progress?.last_page_number || localPosition.page || 1}
                      initialZoom={payload.progress?.zoom_percent || localPosition.zoom || 100}
                      onPageChange={onPdfPageChange}
                      onZoomChange={onZoomChange}
                      onAcroFormDetected={setHasAcroForm}
                      governedAnnotations={readerAnnotations}
                      onGovernedAnnotationClick={() => setGovernanceOpen(true)}
                      onOutlineReady={(items) => { setNativeOutline(items); const active = outlineForPage(items, currentPdfPage); if (active) setActiveOutlineKey(active.id); }}
                    /> : <div className="publication-empty-reader"><h2>Original layout unavailable</h2><p>The source PDF could not be resolved.</p></div>
                  ) : (
                    <article className="publication-html-document">
                      <header><p>{metadata.owner_role || "AMO Document Control"}</p><h2>{metadata.title}</h2><strong>{metadata.code}</strong><span>Issue {metadata.issue_number || "—"} · Revision {metadata.revision_number || "—"}</span></header>
                      {sections.length ? sections.map((section) => {
                        const blocks = blocksBySection[section.id];
                        const pending = loadingSections.has(section.id);
                        return <section key={section.id} id={safeAnchor(section.anchor_slug)} data-section-id={section.id} data-anchor={section.anchor_slug} ref={(element) => { sectionRefs.current[section.anchor_slug] = element; }} className={`publication-html-section level-${Math.max(1, Math.min(5, section.level || 1))}`}>
                          {section.level === 1 ? <h2>{section.heading}</h2> : section.level === 2 ? <h3>{section.heading}</h3> : <h4>{section.heading}</h4>}
                          {blocks ? blocks.map((block, index) => <div key={`${block.change_hash}-${index}`} className="publication-html-block" dangerouslySetInnerHTML={{ __html: block.html }} />) : <div className="publication-html-section__deferred">{pending ? "Loading this section…" : "Scroll here to load this section."}</div>}
                          {blocks && !blocks.length ? <p className="publication-empty-section">No searchable text was extracted for this section. Use original-layout mode for the authoritative page.</p> : null}
                        </section>;
                      }) : <div className="publication-empty-reader"><h2>No readable text is available</h2><p>Use the original-layout reader.</p></div>}
                    </article>
                  )}
                </main>
              </div>
            </>
          ) : null}

          {activeTab === "history" ? <section className="publication-record-panel"><h2>Publication history</h2><p>Workflow and controlled-record events for this revision.</p><div className="publication-history-list">{(workflow?.history || []).length ? workflow?.history.map((item, index) => <article key={`${item.action}-${item.at}-${index}`}><strong>{item.action.replaceAll("_", " ")}</strong><span>{formatDate(item.at)}</span><small>{item.actor_id || "System"}</small></article>) : <div className="publication-record-empty">History is loading or has not been recorded.</div>}</div></section> : null}
          {activeTab === "citations" ? <section className="publication-record-panel"><h2>Citations</h2><p>References from other controlled publications, regulations, findings, and records will appear here.</p><div className="publication-record-empty">No citations are currently linked to this revision.</div></section> : null}
          {activeTab === "subsidiary" ? <section className="publication-record-panel"><h2>Subsidiary legislation</h2><p>Linked schedules, notices, directives, forms, and subordinate publications will appear here.</p><div className="publication-record-empty">No subsidiary publication is currently linked to this revision.</div></section> : null}

          <PublicationGovernancePanel
            open={governanceOpen}
            onClose={() => setGovernanceOpen(false)}
            tenant={tenant}
            manualId={manualId || ""}
            revisionId={revId || ""}
            currentPage={currentPdfPage}
            activeSectionId={activeSectionId}
            viewMode={viewMode}
            onAnnotationsChanged={setReaderAnnotations}
          />
          <button type="button" className="publication-to-top" onClick={scrollToTop}>To the top</button>
          {mobileNavigationOpen ? <button type="button" className="publication-navigation-backdrop" onClick={() => setMobileNavigationOpen(false)} aria-label="Close navigation overlay" /> : null}
        </>
      ) : null}
    </div>
  );

  if (!amoCode) return content;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="document-control">{content}</DepartmentLayout>;
}

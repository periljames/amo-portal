import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bookmark,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Download,
  FileText,
  ListTree,
  Menu,
  Printer,
  Search,
  TriangleAlert,
  X,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getRevisionRead, getRevisionWorkflow, type ManualReadPayload, type ManualWorkflowPayload } from "../../services/manuals";
import {
  downloadBlob,
  fetchPublicationBlob,
  formatFileSize,
  getPublicationReaderMetadata,
  type PublicationReaderMetadata,
} from "../../services/publications";
import { useManualRouteContext } from "./context";
import "./manualReader.css";

type ReaderTab = "detail" | "history" | "citations" | "subsidiary";
type NavigationTab = "toc" | "search";
type ViewMode = "html" | "pdf";

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
};

const TAB_VALUES = new Set<ReaderTab>(["detail", "history", "citations", "subsidiary"]);

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

function ReaderStatus({ message }: { message: string }) {
  return (
    <div className="publication-reader-status" role="status">
      <span className="publication-reader-spinner" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export default function PublicationsReaderPage() {
  const { tenant, amoCode, manualId, revId, basePath } = useManualRouteContext();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [payload, setPayload] = useState<ExtendedReadPayload | null>(null);
  const [metadata, setMetadata] = useState<PublicationReaderMetadata | null>(null);
  const [workflow, setWorkflow] = useState<ManualWorkflowPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [navigationTab, setNavigationTab] = useState<NavigationTab>("toc");
  const [query, setQuery] = useState("");
  const [activeSection, setActiveSection] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("html");
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const requestedTab = searchParams.get("tab") as ReaderTab | null;
  const activeTab: ReaderTab = requestedTab && TAB_VALUES.has(requestedTab) ? requestedTab : "detail";

  useEffect(() => {
    if (!tenant || !manualId || !revId) {
      setLoading(false);
      setError("The publication route is incomplete.");
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      getRevisionRead(tenant, manualId, revId) as Promise<ExtendedReadPayload>,
      getPublicationReaderMetadata(tenant, manualId, revId),
      getRevisionWorkflow(tenant, manualId, revId).catch(() => null),
    ])
      .then(([readPayload, readerMetadata, workflowPayload]) => {
        if (!active) return;
        setPayload(readPayload);
        setMetadata(readerMetadata);
        setWorkflow(workflowPayload);
        const firstAnchor = readPayload.sections[0]?.anchor_slug || "";
        setActiveSection(firstAnchor);
        setViewMode(readerMetadata.reader_mode === "pdf" ? "pdf" : "html");
        const savedKey = `amo-publication-saved:${tenant}:${manualId}:${revId}`;
        setSaved(window.localStorage.getItem(savedKey) === "1");
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "The publication could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tenant, manualId, revId]);

  useEffect(() => {
    if (viewMode !== "pdf" || !metadata?.rendered_pdf_url) {
      setPdfUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return "";
      });
      return;
    }
    let active = true;
    let objectUrl = "";
    setPdfLoading(true);
    fetchPublicationBlob(metadata.rendered_pdf_url)
      .then(({ blob }) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "The PDF could not be opened.");
      })
      .finally(() => {
        if (active) setPdfLoading(false);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [viewMode, metadata?.rendered_pdf_url]);

  const blocksBySection = useMemo(() => {
    const grouped: Record<string, ExtendedReadPayload["blocks"]> = {};
    for (const block of payload?.blocks || []) {
      if (!grouped[block.section_id]) grouped[block.section_id] = [];
      grouped[block.section_id].push(block);
    }
    return grouped;
  }, [payload?.blocks]);

  const searchHits = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [] as ReaderSection[];
    return (payload?.sections || []).filter((section) => {
      if (section.heading.toLowerCase().includes(needle)) return true;
      return (blocksBySection[section.id] || []).some((block) => block.text.toLowerCase().includes(needle));
    });
  }, [blocksBySection, payload?.sections, query]);

  useEffect(() => {
    if (viewMode !== "html" || activeTab !== "detail") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible?.target?.id) setActiveSection(visible.target.id);
      },
      { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.15, 0.5] },
    );
    Object.values(sectionRefs.current).forEach((element) => element && observer.observe(element));
    return () => observer.disconnect();
  }, [activeTab, payload?.sections, viewMode]);

  const openSection = (section: ReaderSection) => {
    setViewMode("html");
    setActiveSection(section.anchor_slug);
    setMobileNavigationOpen(false);
    window.requestAnimationFrame(() => {
      document.getElementById(safeAnchor(section.anchor_slug))?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const setTab = (tab: ReaderTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "detail") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: false });
  };

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
    if (!metadata) return;
    setDownloadBusy(true);
    try {
      const { blob, filename } = await fetchPublicationBlob(metadata.rendered_pdf_url);
      downloadBlob(blob, filename || metadata.download_filename);
    } finally {
      setDownloadBusy(false);
    }
  };

  const openPrintablePdf = async () => {
    if (!metadata) return;
    const popup = window.open("", "_blank", "noopener,noreferrer");
    try {
      const { blob } = await fetchPublicationBlob(metadata.rendered_pdf_url);
      const url = URL.createObjectURL(blob);
      if (popup) popup.location.href = url;
      else window.location.assign(url);
      window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
    } catch (caught) {
      popup?.close();
      throw caught;
    }
  };

  const toggleCollapsed = (anchor: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(anchor)) next.delete(anchor);
      else next.add(anchor);
      return next;
    });
  };

  const sections = payload?.sections || [];
  const hiddenByCollapsedParent = (index: number): boolean => {
    const level = sections[index]?.level || 1;
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const candidate = sections[cursor];
      if ((candidate.level || 1) < level) {
        if (collapsed.has(candidate.anchor_slug)) return true;
        if ((candidate.level || 1) === 1) break;
      }
    }
    return false;
  };

  const navigation = (
    <aside className={`publication-navigation ${mobileNavigationOpen ? "publication-navigation--open" : ""}`} aria-label="Publication navigation">
      <div className="publication-navigation__mobile-head">
        <strong>Navigate publication</strong>
        <button type="button" onClick={() => setMobileNavigationOpen(false)} aria-label="Close navigation"><X size={18} /></button>
      </div>
      <div className="publication-navigation__tabs" role="tablist">
        <button type="button" className={navigationTab === "toc" ? "active" : ""} onClick={() => setNavigationTab("toc")}><ListTree size={15} /> Table of contents</button>
        <button type="button" className={navigationTab === "search" ? "active" : ""} onClick={() => setNavigationTab("search")}><Search size={15} /> Search</button>
      </div>
      {navigationTab === "toc" ? (
        <div className="publication-toc">
          <div className="publication-toc__tools">
            <button type="button" onClick={() => setCollapsed(new Set())}>Expand all</button>
            <button type="button" onClick={() => setCollapsed(new Set(sections.filter((section) => section.level < 3).map((section) => section.anchor_slug)))}>Collapse all</button>
          </div>
          <div className="publication-toc__list">
            {sections.map((section, index) => {
              if (hiddenByCollapsedParent(index)) return null;
              const hasChildren = sections[index + 1] && (sections[index + 1].level || 1) > (section.level || 1);
              const isCollapsed = collapsed.has(section.anchor_slug);
              const isActive = activeSection === safeAnchor(section.anchor_slug) || activeSection === section.anchor_slug;
              return (
                <div key={section.id} className={`publication-toc__row level-${Math.max(1, Math.min(3, section.level || 1))} ${isActive ? "active" : ""}`}>
                  {hasChildren ? (
                    <button type="button" className="publication-toc__toggle" onClick={() => toggleCollapsed(section.anchor_slug)} aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${section.heading}`}>
                      {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                  ) : <span className="publication-toc__spacer" />}
                  <button type="button" className="publication-toc__link" onClick={() => openSection(section)}>
                    <span>{section.heading}</span>
                    {section.page_start ? <small>p. {section.page_start}</small> : null}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="publication-search-panel">
          <label>
            <span className="sr-only">Search publication</span>
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this publication" autoFocus />
          </label>
          <p>{query.trim() ? `${searchHits.length} matching section(s)` : "Enter a word or exact phrase."}</p>
          <div className="publication-search-results">
            {searchHits.map((section) => (
              <button type="button" key={section.id} onClick={() => openSection(section)}>
                <strong>{section.heading}</strong>
                <span>{(blocksBySection[section.id]?.find((block) => block.text.toLowerCase().includes(query.trim().toLowerCase()))?.text || "Section heading match").slice(0, 180)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );

  const content = (
    <div className="publication-reader-page">
      {loading ? <ReaderStatus message="Preparing publication reader…" /> : null}
      {!loading && error ? (
        <div className="publication-reader-error" role="alert">
          <TriangleAlert size={22} />
          <div><strong>Publication could not be opened</strong><p>{error}</p></div>
          <button type="button" onClick={() => window.location.reload()}>Retry</button>
        </div>
      ) : null}
      {!loading && metadata && payload ? (
        <>
          <header className="publication-document-header">
            <div className="publication-document-header__title">
              <button type="button" className="publication-mobile-nav-button" onClick={() => setMobileNavigationOpen(true)} aria-label="Open table of contents"><Menu size={18} /></button>
              <div>
                <p>{metadata.manual_type || "Controlled publication"}</p>
                <h1>{metadata.title}</h1>
                <span>{metadata.code} · Issue {metadata.issue_number || "—"} · Revision {metadata.revision_number || "—"}</span>
              </div>
            </div>
            <div className="publication-document-header__actions">
              <button type="button" className={saved ? "active" : ""} onClick={toggleSaved}><Bookmark size={16} fill={saved ? "currentColor" : "none"} /> {saved ? "Saved" : "Save document"}</button>
              <button type="button" onClick={() => void copyCitation()}><ClipboardCopy size={16} /> {copied ? "Copied" : "Copy citation"}</button>
              <button type="button" className="primary" disabled={downloadBusy} onClick={() => void downloadPdf()}><Download size={16} /> {downloadBusy ? "Preparing…" : `Download PDF (${formatFileSize(metadata.rendered_pdf_size_bytes)})`}</button>
              <button type="button" onClick={() => void openPrintablePdf()}><Printer size={16} /> Print PDF</button>
              <button type="button" onClick={() => navigate(`/maintenance/${amoCode || tenant}/document-control/change-proposals?publication=${encodeURIComponent(manualId || "")}&revision=${encodeURIComponent(revId || "")}`)}>Report a problem</button>
            </div>
          </header>

          <div className="publication-floating-header">
            <button type="button" onClick={() => setMobileNavigationOpen(true)} aria-label="Open document navigation"><Menu size={17} /></button>
            <strong>{metadata.title}</strong>
            <span>{activeSection ? sections.find((section) => section.anchor_slug === activeSection)?.heading || activeSection : "Document detail"}</span>
            <div>
              <button type="button" className={viewMode === "html" ? "active" : ""} disabled={!sections.length} onClick={() => setViewMode("html")}>Readable text</button>
              <button type="button" className={viewMode === "pdf" ? "active" : ""} onClick={() => setViewMode("pdf")}>Original PDF</button>
            </div>
          </div>

          <nav className="publication-document-tabs" aria-label="Publication record tabs">
            <button type="button" className={activeTab === "detail" ? "active" : ""} onClick={() => setTab("detail")}><FileText size={15} /> Document detail</button>
            <button type="button" className={activeTab === "history" ? "active" : ""} onClick={() => setTab("history")}>History</button>
            <button type="button" className={activeTab === "citations" ? "active" : ""} onClick={() => setTab("citations")}>Citations <span>{metadata.citation_current} / {metadata.citation_total}</span></button>
            <button type="button" className={activeTab === "subsidiary" ? "active" : ""} onClick={() => setTab("subsidiary")}>Subsidiary legislation <span>{metadata.subsidiary_count}</span></button>
          </nav>

          {activeTab === "detail" ? (
            <>
              <section className="publication-metadata" aria-label="Document metadata">
                <dl>
                  <div><dt>Date</dt><dd>{formatDate(metadata.date)}</dd></div>
                  <div><dt>Language</dt><dd>{metadata.language || "Not recorded"}</dd></div>
                  <div><dt>Original Issue</dt><dd><button type="button" onClick={() => void downloadPdf()}>Download original issue (PDF)</button> <span>({formatFileSize(metadata.rendered_pdf_size_bytes)})</span></dd></div>
                  <div><dt>Source</dt><dd>{metadata.source_filename || metadata.source_type || "Not recorded"}{metadata.source_size_bytes ? ` (${formatFileSize(metadata.source_size_bytes)})` : ""}</dd></div>
                </dl>
              </section>

              <div className="publication-reader-workspace">
                {navigation}
                <main className="publication-document-canvas" id="publication-document-content">
                  {metadata.image_only ? (
                    <div className="publication-reader-notice"><TriangleAlert size={17} /><span>This PDF contains no dependable text layer. The reader has switched to the original PDF view instead of presenting inaccurate OCR text.</span></div>
                  ) : null}
                  {viewMode === "pdf" ? (
                    <div className="publication-pdf-viewer">
                      {pdfLoading ? <ReaderStatus message="Loading PDF viewer…" /> : null}
                      {pdfUrl ? <iframe title={`${metadata.title} PDF`} src={pdfUrl} /> : null}
                    </div>
                  ) : (
                    <article className="publication-html-document">
                      <header>
                        <p>{metadata.owner_role || "AMO Document Control"}</p>
                        <h2>{metadata.title}</h2>
                        <strong>{metadata.code}</strong>
                        <span>Issue {metadata.issue_number || "—"} · Revision {metadata.revision_number || "—"}</span>
                      </header>
                      {sections.length ? sections.map((section) => (
                        <section
                          key={section.id}
                          id={safeAnchor(section.anchor_slug)}
                          ref={(element) => { sectionRefs.current[section.anchor_slug] = element; }}
                          className={`publication-html-section level-${Math.max(1, Math.min(3, section.level || 1))}`}
                        >
                          {section.level === 1 ? <h2>{section.heading}</h2> : section.level === 2 ? <h3>{section.heading}</h3> : <h4>{section.heading}</h4>}
                          {(blocksBySection[section.id] || []).map((block, index) => (
                            <div key={`${block.change_hash}-${index}`} className="publication-html-block" dangerouslySetInnerHTML={{ __html: block.html }} />
                          ))}
                          {!(blocksBySection[section.id] || []).length ? <p className="publication-empty-section">No searchable text was extracted for this section.</p> : null}
                        </section>
                      )) : (
                        <div className="publication-empty-reader"><h2>No readable text is available</h2><p>Open the Original PDF view to read this publication.</p></div>
                      )}
                    </article>
                  )}
                </main>
              </div>
            </>
          ) : null}

          {activeTab === "history" ? (
            <section className="publication-record-panel">
              <h2>Publication history</h2>
              <p>Workflow and controlled-record events for this revision.</p>
              <div className="publication-history-list">
                {(workflow?.history || []).length ? workflow?.history.map((item, index) => (
                  <article key={`${item.action}-${item.at}-${index}`}>
                    <strong>{item.action.replaceAll("_", " ")}</strong>
                    <span>{formatDate(item.at)}</span>
                    <small>{item.actor_id || "System"}</small>
                  </article>
                )) : <div className="publication-record-empty">No history has been recorded for this revision.</div>}
              </div>
            </section>
          ) : null}

          {activeTab === "citations" ? (
            <section className="publication-record-panel">
              <h2>Citations</h2>
              <p>References from other controlled publications, regulations, findings, and records will appear here.</p>
              <div className="publication-record-empty">No citations are currently linked to this revision.</div>
            </section>
          ) : null}

          {activeTab === "subsidiary" ? (
            <section className="publication-record-panel">
              <h2>Subsidiary legislation</h2>
              <p>Linked schedules, notices, directives, forms, and subordinate publications will appear here.</p>
              <div className="publication-record-empty">No subsidiary publication is currently linked to this revision.</div>
            </section>
          ) : null}

          <button type="button" className="publication-to-top" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>To the top</button>
          {mobileNavigationOpen ? <button type="button" className="publication-navigation-backdrop" onClick={() => setMobileNavigationOpen(false)} aria-label="Close navigation overlay" /> : null}
        </>
      ) : null}
    </div>
  );

  if (!amoCode) return content;
  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="document-control">
      {content}
    </DepartmentLayout>
  );
}

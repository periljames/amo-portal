import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, RefreshCcw, ScanLine, FileText, Loader2, ChevronRight, ChevronDown, Search, ZoomIn, ZoomOut } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useNavigate } from "react-router-dom";
import {
  acknowledgeRevision,
  createRevisionExport,
  createStampedOverlay,
  generateOutline,
  getProcessingStatus,
  getRevisionDiff,
  getRevisionRead,
  getRevisionWorkflow,
  runOcr,
  runProcessor,
  verifyOcrLetter,
  type ManualOCRVerifyPayload,
  type ManualReadPayload,
  type ManualProcessingStatus,
} from "../../services/manuals";
import { authHeaders, getCachedUser } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import { useManualRouteContext } from "./context";
import "./manualReader.css";
import { ManualsReaderShell, TenantBrandingProvider, type ReaderActionId } from "../../packages/manuals-reader";

type ReaderMode = "section" | "figure" | "search" | "history" | "task" | "change-request";
type ContextPanel = "metadata" | "search" | "history" | "task" | "change-request" | "figure" | "order-list";
type HistoryItem = { route: string; timestamp: string; manual: string; chapter?: string; section?: string; title?: string; source: "reader" };

type FigureRef = {
  id: string;
  src: string;
  title: string;
  sectionId: string;
  sectionHeading: string;
  chapterLabel: string;
};

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

function sectionToChapterLabel(heading: string) {
  const match = heading.match(/^(\d{1,2})/);
  return match ? `ATA ${match[1]}` : "General";
}

export default function ManualReaderPage() {
  const { tenant, manualId, revId, amoCode, chapterId, sectionId, subSectionId, figureId } = useManualRouteContext();
  const navigate = useNavigate();
  const [payload, setPayload] = useState<ManualReadPayload | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState("Loading");
  const [diffSummary, setDiffSummary] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [activeSection, setActiveSection] = useState("");
  const [layout, setLayout] = useState<"continuous" | "paged-1" | "paged-2" | "paged-3">((localStorage.getItem("manuals.layout") as any) || "continuous");
  const [zoom, setZoom] = useState(Number(localStorage.getItem("manuals.zoom") || "100"));
  const [figureZoom, setFigureZoom] = useState(Number(localStorage.getItem("manuals.figureZoom") || "100"));
  const [tocOpen, setTocOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [tab, setTab] = useState<"revision" | "ack" | "export">("revision");
  const [ackChecked, setAckChecked] = useState(false);
  const [ackComment, setAckComment] = useState("");
  const [controlled, setControlled] = useState(false);
  const [watermarkOn, setWatermarkOn] = useState(true);
  const [processing, setProcessing] = useState<ManualProcessingStatus | null>(null);
  const [busy, setBusy] = useState<"processor" | "ocr" | "outline" | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [integrityCompromised, setIntegrityCompromised] = useState(false);
  const [readerMode, setReaderMode] = useState<ReaderMode>(figureId ? "figure" : "section");
  const [panel, setPanel] = useState<ContextPanel>("metadata");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [taskTab, setTaskTab] = useState<"current" | "visited" | "all">("current");
  const [activeFigureId, setActiveFigureId] = useState<string | null>(figureId || null);
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("manuals.readerHistory") || "[]");
    } catch {
      return [];
    }
  });

  const [crForm, setCrForm] = useState({
    partNumber: "",
    manualType: "",
    title: "",
    model: "",
    publicationDate: "",
    revisionNumber: revId || "",
    ataChapter: chapterId || "",
    section: sectionId || "",
    subSection: subSectionId || "",
    figure: figureId || "",
    pageNumber: "",
    artFigure: "",
    other: "",
    otherPublications: "",
    suggestion: "",
    requestUpdates: true,
  });
  const [ocrTypedRef, setOcrTypedRef] = useState("");
  const [ocrTypedDate, setOcrTypedDate] = useState("");
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrResult, setOcrResult] = useState<ManualOCRVerifyPayload | null>(null);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [stampName, setStampName] = useState("");
  const [stampRole, setStampRole] = useState("Head of Quality");
  const [stampLabel, setStampLabel] = useState("APPROVED FOR SUBMISSION");
  const [stampBusy, setStampBusy] = useState(false);
  const [stampMessage, setStampMessage] = useState("");
  const [gpuMode, setGpuMode] = useState<"webgpu" | "webgl2" | "css" | "none">("none");

  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const pagedParentRef = useRef<HTMLDivElement | null>(null);

  const refresh = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionRead(tenant, manualId, revId).then(setPayload).catch(() => setPayload(null));
    getRevisionWorkflow(tenant, manualId, revId).then((v) => setWorkflowStatus(v.status || "Metadata incomplete")).catch(() => setWorkflowStatus("Metadata incomplete"));
    getRevisionDiff(tenant, manualId, revId).then((v) => setDiffSummary(v.summary_json || {})).catch(() => setDiffSummary({}));
    getProcessingStatus(tenant, manualId, revId).then(setProcessing).catch(() => setProcessing(null));
  };

  useEffect(() => { refresh(); }, [tenant, manualId, revId]);

  useEffect(() => {
    const user = getCachedUser() as any;
    const name = user?.full_name || user?.name || user?.display_name || user?.username || "";
    if (name) setStampName((prev) => prev || name);
  }, []);

  useEffect(() => {
    const canvas = document.createElement("canvas");
    const webgl2 = typeof window !== "undefined" ? canvas.getContext("webgl2") : null;
    const nav = navigator as Navigator & { gpu?: unknown };
    if (nav.gpu) {
      setGpuMode("webgpu");
      return;
    }
    if (webgl2) {
      setGpuMode("webgl2");
      return;
    }
    if (typeof CSS !== "undefined" && CSS.supports("transform", "translate3d(0,0,0)")) {
      setGpuMode("css");
      return;
    }
    setGpuMode("none");
  }, []);

  useEffect(() => {
    if (!manualId || !revId) {
      setIntegrityCompromised(false);
      return;
    }
    let alive = true;
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(`${getApiBaseUrl()}/quality/qms/documents/${manualId}/revisions/${revId}/open`, {
          method: "GET",
          headers: { ...authHeaders(), Range: "bytes=0-0" },
          signal: controller.signal,
        });
        const integrity = (response.headers.get("X-Document-Integrity") || "").toLowerCase();
        if (alive) setIntegrityCompromised(integrity === "compromised");
      } catch {
        if (alive) setIntegrityCompromised(false);
      }
    })();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [manualId, revId]);

  useEffect(() => {
    localStorage.setItem("manuals.layout", layout);
    localStorage.setItem("manuals.zoom", String(zoom));
    localStorage.setItem("manuals.figureZoom", String(figureZoom));
  }, [layout, zoom, figureZoom]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.getElementById("manual-reader-search")?.focus();
      }
      if (e.key === "[") setTocOpen((v) => !v);
      if (e.key === "]") setInspectorOpen((v) => !v);
      if (e.altKey && e.key === "ArrowRight") goRelativeSection(1);
      if (e.altKey && e.key === "ArrowLeft") goRelativeSection(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    const obs = new IntersectionObserver((entries) => {
      const top = entries.find((e) => e.isIntersecting);
      if (top?.target?.id) setActiveSection(top.target.id);
    }, { rootMargin: "-10% 0px -75% 0px", threshold: [0.2] });
    Object.values(sectionRefs.current).forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [payload?.sections]);

  useEffect(() => {
    const source = new EventSource(new URL("/api/events", window.location.origin));
    source.onmessage = (event) => {
      try {
        const v = JSON.parse(event.data || "{}");
        const type = String(v.entity_type || v.entityType || "");
        const entityId = String(v.entity_id || v.entityId || "");
        if (type.includes("manual") || entityId === manualId || entityId === revId) refresh();
      } catch {}
    };
    source.addEventListener("reset", () => refresh());
    return () => source.close();
  }, [manualId, revId]);

  const blocksBySection = useMemo(() => {
    const grouped: Record<string, ManualReadPayload["blocks"]> = {};
    (payload?.blocks || []).forEach((b) => ((grouped[b.section_id] = grouped[b.section_id] || []).push(b)));
    return grouped;
  }, [payload?.blocks]);

  const figures = useMemo<FigureRef[]>(() => {
    const refs: FigureRef[] = [];
    (payload?.sections || []).forEach((section) => {
      (blocksBySection[section.id] || []).forEach((b, idx) => {
        const regex = /<img[^>]+src=["']([^"']+)["'][^>]*?(?:alt=["']([^"']*)["'])?[^>]*>/gi;
        let m: RegExpExecArray | null;
        while ((m = regex.exec(b.html))) {
          refs.push({
            id: `${section.id}-fig-${idx}-${refs.length}`,
            src: m[1],
            title: m[2] || `Figure ${refs.length + 1}`,
            sectionId: section.anchor_slug,
            sectionHeading: section.heading,
            chapterLabel: sectionToChapterLabel(section.heading),
          });
        }
      });
    });
    return refs;
  }, [payload?.sections, blocksBySection]);

  useEffect(() => {
    if (!activeFigureId && figures.length) setActiveFigureId(figures[0].id);
  }, [figures, activeFigureId]);

  const activeFigure = useMemo(() => figures.find((f) => f.id === activeFigureId) || null, [figures, activeFigureId]);

  const filteredSections = useMemo(
    () => (payload?.sections || []).filter((s) => s.heading.toLowerCase().includes(search.toLowerCase()) || (blocksBySection[s.id] || []).some((b) => b.text.toLowerCase().includes(search.toLowerCase()))),
    [payload?.sections, blocksBySection, search],
  );

  const pages = useMemo(() => chunk(filteredSections.map((section) => ({ section, blocks: blocksBySection[section.id] || [] })), 1), [filteredSections, blocksBySection]);
  const columns = layout === "paged-3" ? 3 : layout === "paged-2" ? 2 : 1;
  const rows = useMemo(() => chunk(pages, columns), [pages, columns]);
  const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => pagedParentRef.current, estimateSize: () => 930, overscan: 3 });

  const missingMetaFields = [!revId && "revision id", !workflowStatus && "workflow status"].filter(Boolean) as string[];
  const noContent = !filteredSections.length;

  const setRouteSection = (anchor: string) => {
    const base = amoCode ? `/maintenance/${amoCode}/publications/${manualId}` : `/t/${tenant}/publications/${manualId}`;
    const chapter = anchor.split("-")[0] || "chapter";
    navigate(`${base}/${chapter}/${anchor}`);
  };

  const pushHistory = (title: string, sectionAnchor?: string) => {
    const next: HistoryItem = {
      route: window.location.pathname,
      timestamp: new Date().toISOString(),
      manual: manualId || "manual",
      chapter: sectionAnchor?.split("-")[0],
      section: sectionAnchor,
      title,
      source: "reader",
    };
    const merged = [next, ...history].slice(0, 250);
    setHistory(merged);
    localStorage.setItem("manuals.readerHistory", JSON.stringify(merged));
  };

  const goRelativeSection = (delta: number) => {
    if (!filteredSections.length) return;
    const idx = filteredSections.findIndex((s) => s.anchor_slug === activeSection);
    const next = filteredSections[Math.max(0, Math.min(filteredSections.length - 1, (idx === -1 ? 0 : idx) + delta))];
    if (!next) return;
    setActiveSection(next.anchor_slug);
    location.hash = `#${next.anchor_slug}`;
    setRouteSection(next.anchor_slug);
    pushHistory(next.heading, next.anchor_slug);
  };

  const run = async (kind: "processor" | "ocr" | "outline") => {
    if (!tenant || !manualId || !revId) return;
    setBusy(kind);
    try {
      if (kind === "processor") await runProcessor(tenant, manualId, revId);
      if (kind === "ocr") await runOcr(tenant, manualId, revId);
      if (kind === "outline") await generateOutline(tenant, manualId, revId);
      refresh();
    } finally {
      setBusy(null);
    }
  };

  const verifyApprovalLetter = async () => {
    if (!tenant || !manualId || !revId || !ocrFile) return;
    setOcrBusy(true);
    setStampMessage("");
    try {
      const result = await verifyOcrLetter(tenant, manualId, revId, {
        file: ocrFile,
        typed_ref: ocrTypedRef || undefined,
        typed_date: ocrTypedDate || undefined,
      });
      setOcrResult(result);
      refresh();
    } finally {
      setOcrBusy(false);
    }
  };

  const createStampedPdf = async () => {
    if (!tenant || !manualId || !revId || !stampName.trim() || !stampRole.trim()) return;
    setStampBusy(true);
    setStampMessage("");
    try {
      const out = await createStampedOverlay(tenant, manualId, revId, {
        signer_name: stampName.trim(),
        signer_role: stampRole.trim(),
        stamp_label: stampLabel.trim() || "APPROVED FOR SUBMISSION",
        controlled_bool: controlled,
      });
      setStampMessage(`Stamped PDF created. SHA256 ${out.sha256.slice(0, 12)}…`);
      refresh();
    } finally {
      setStampBusy(false);
    }
  };

  const onActionClick = (action: ReaderActionId) => {
    if (action === "change-request") {
      setReaderMode("change-request");
      setPanel("change-request");
      return;
    }
    if (action === "history") {
      setReaderMode("history");
      setPanel("history");
      return;
    }
    if (action === "task") {
      setReaderMode("task");
      setPanel("task");
      return;
    }
    if (action === "order-list") {
      setPanel("order-list");
      return;
    }
    if (action === "notifications" || action === "delta" || action === "support" || action === "help" || action === "account") {
      setPanel("metadata");
    }
    if (action === "home") navigate(amoCode ? `/maintenance/${amoCode}` : `/t/${tenant}`);
  };

  const breadcrumb = useMemo(() => {
    const sec = filteredSections.find((s) => s.anchor_slug === activeSection) || filteredSections[0];
    return {
      make: "AMO",
      library: "Technical Publications",
      manual: payload?.manual ? `${payload.manual.code} · ${payload.manual.title}` : `Manual ${manualId || ""}` ,
      chapter: sec ? sectionToChapterLabel(sec.heading) : chapterId || "Chapter",
      section: sec?.heading || sectionId || "Section",
    };
  }, [filteredSections, activeSection, manualId, chapterId, sectionId]);

  useEffect(() => {
    setCrForm((prev) => ({
      ...prev,
      partNumber: manualId || prev.partNumber,
      manualType: "Technical Manual",
      title: `Manual ${manualId || ""}`,
      model: prev.model || "N/A",
      publicationDate: prev.publicationDate || new Date().toISOString().slice(0, 10),
      revisionNumber: revId || prev.revisionNumber,
      ataChapter: breadcrumb.chapter,
      section: breadcrumb.section,
      figure: activeFigure?.title || prev.figure,
    }));
  }, [manualId, revId, breadcrumb.chapter, breadcrumb.section, activeFigure?.title]);

  const viewer = readerMode === "figure" && activeFigure ? (
    <div>
      <div className="manual-reader-figure-toolbar">
        <button className="manual-reader-icon-btn" onClick={() => setFigureZoom((z) => Math.max(40, z - 10))}><ZoomOut size={14} /> Zoom out</button>
        <button className="manual-reader-icon-btn" onClick={() => setFigureZoom(100)}>Reset view</button>
        <button className="manual-reader-icon-btn" onClick={() => setFigureZoom((z) => Math.min(320, z + 10))}><ZoomIn size={14} /> Zoom in</button>
        <button className="manual-reader-icon-btn" onClick={() => setFigureZoom(125)}>Fit width</button>
        <button className="manual-reader-icon-btn" onClick={() => setFigureZoom(100)}>Fit page</button>
        <button className="manual-reader-icon-btn" onClick={() => {
          const idx = figures.findIndex((f) => f.id === activeFigure.id);
          if (idx > 0) setActiveFigureId(figures[idx - 1].id);
        }}>Previous figure</button>
        <button className="manual-reader-icon-btn" onClick={() => {
          const idx = figures.findIndex((f) => f.id === activeFigure.id);
          if (idx < figures.length - 1) setActiveFigureId(figures[idx + 1].id);
        }}>Next figure</button>
        <button className="manual-reader-icon-btn" onClick={() => {
          setReaderMode("section");
          location.hash = `#${activeFigure.sectionId}`;
        }}>Back to section</button>
      </div>
      <div className="manual-reader-figure-view">
        <p><strong>{activeFigure.title}</strong> · {activeFigure.chapterLabel} · {activeFigure.sectionHeading}</p>
        <img src={activeFigure.src} alt={activeFigure.title} style={{ transform: `scale(${figureZoom / 100})`, transformOrigin: "top left" }} />
      </div>
    </div>
  ) : layout === "continuous" ? (
    <div className="manual-reader-pane">
      {filteredSections.map((s) => (
        <article key={s.id} id={s.anchor_slug} ref={(el) => { sectionRefs.current[s.anchor_slug] = el; }} className="manual-reader-section">
          <h2>{s.heading}</h2>
          {(blocksBySection[s.id] || []).map((b, i) => <div key={`${s.id}-${i}`} className="manual-reader-content" dangerouslySetInnerHTML={{ __html: b.html }} />)}
          <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
            <button className="manual-reader-icon-btn" onClick={() => {
              const fig = figures.find((f) => f.sectionId === s.anchor_slug);
              if (fig) {
                setActiveFigureId(fig.id);
                setReaderMode("figure");
                setPanel("figure");
                pushHistory(`Figure ${fig.title}`, s.anchor_slug);
              }
            }}>Open figure mode</button>
            <button className="manual-reader-icon-btn" onClick={() => {
              setReaderMode("change-request");
              setPanel("change-request");
            }}>Raise change request</button>
          </div>
        </article>
      ))}
    </div>
  ) : (
    <div ref={pagedParentRef} className="manual-reader-pane overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
        {virtualizer.getVirtualItems().map((row) => (
          <div key={row.key} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${row.start}px)` }}>
            <div className="manual-paged-grid" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0,1fr))` }}>
              {(rows[row.index] || []).map((page, idx) => (
                <section key={`p-${row.index}-${idx}`} className="manual-page">
                  {(page || []).map((entry) => (
                    <div key={entry.section.id} className="manual-reader-content"><h3>{entry.section.heading}</h3>{entry.blocks.map((b, i) => <div key={`${entry.section.id}-${i}`} dangerouslySetInnerHTML={{ __html: b.html }} />)}</div>
                  ))}
                </section>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const fallbackPath = amoCode ? `/maintenance/${amoCode}/manuals` : `/t/${tenant || ""}/manuals`;

  const publicationTree = (
    <div>
      <div className="manual-panel-title">Publication hierarchy</div>
      <div style={{ padding: 8, fontSize: 12 }}>
        <div className="manual-tree-node active"><ChevronDown size={12} /> {breadcrumb.make}</div>
        <div className="manual-tree-children">
          <div className="manual-tree-node active"><ChevronDown size={12} /> {breadcrumb.library}</div>
          <div className="manual-tree-children">
            <div className="manual-tree-node active"><ChevronDown size={12} /> {breadcrumb.manual}</div>
            <div className="manual-tree-children">
              {filteredSections.map((s) => {
                const active = s.anchor_slug === activeSection;
                return (
                  <div key={s.id}>
                    <button className={`manual-tree-node ${active ? "active" : ""}`} onClick={() => {
                      setActiveSection(s.anchor_slug);
                      setRouteSection(s.anchor_slug);
                      location.hash = `#${s.anchor_slug}`;
                      pushHistory(s.heading, s.anchor_slug);
                    }}>
                      {active ? <ChevronDown size={12} /> : <ChevronRight size={12} />} {s.heading}
                    </button>
                    {active ? (
                      <div className="manual-tree-children">
                        {figures.filter((f) => f.sectionId === s.anchor_slug).map((f) => (
                          <button key={f.id} className="manual-tree-node" onClick={() => { setActiveFigureId(f.id); setReaderMode("figure"); }}>
                            Figure: {f.title}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <TenantBrandingProvider tenantSlug={tenant || "default"}>
      <ManualsReaderShell
        tenantSlug={tenant || "default"}
        mode={window.location.search.includes("standalone=1") ? "standalone" : "embedded"}
        manualLabel={payload?.manual ? `${payload.manual.code} · ${payload.manual.title}` : manualId ? `Manual ${manualId}` : "Manual"}
        statusBadge={workflowStatus}
        revMeta={`Rev ${revId || "n/a"}`}
        locationLabel={activeSection || "Reader"}
        missingMetaFields={missingMetaFields.length ? missingMetaFields : undefined}
        fallbackPath={fallbackPath}
        searchValue={search}
        onSearchChange={(value) => { setSearch(value); setPanel("search"); setReaderMode("search"); }}
        onToggleToc={() => setTocOpen((v) => !v)}
        onToggleInspector={() => setInspectorOpen((v) => !v)}
        onLayoutChange={(next) => setLayout(next)}
        onZoomIn={() => setZoom((z) => Math.min(220, z + 10))}
        onZoomOut={() => setZoom((z) => Math.max(60, z - 10))}
        onZoomReset={() => setZoom(100)}
        onActionClick={onActionClick}
        activeAction={panel === "change-request" ? "change-request" : panel === "history" ? "history" : panel === "task" ? "task" : panel === "order-list" ? "order-list" : null}
      >
        {integrityCompromised ? (
          <div className="manual-card" style={{ borderColor: "var(--danger, #d9534f)", background: "rgba(217, 83, 79, 0.12)", marginBottom: 12 }}>
            <strong>CRITICAL: DOCUMENT INTEGRITY COMPROMISED</strong>
            <p>This revision hash does not match the immutable record. Stop use and notify Quality Management immediately.</p>
          </div>
        ) : null}

        {advancedOpen ? (
          <div className="manual-card" style={{ marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}><strong>Advanced publication search</strong><button className="manual-reader-icon-btn" onClick={() => setAdvancedOpen(false)}>Close</button></div>
            <div style={{ display: "grid", gap: 6, gridTemplateColumns: "repeat(5,minmax(0,1fr))" }}>
              <input className="manual-input" placeholder="Make" />
              <input className="manual-input" placeholder="Library" />
              <input className="manual-input" placeholder="Manual" />
              <input className="manual-input" placeholder="Search phrase" />
              <select className="manual-input"><option>any words</option><option>all words</option><option>exact phrase</option><option>starts with</option></select>
            </div>
          </div>
        ) : null}

        <div className="manual-reader-workspace">
          {tocOpen ? <aside className="manual-reader-toc">{publicationTree}</aside> : null}

          <section className="manual-reader-viewer" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top center" }}>
            <div className="manual-reader-breadcrumbs">
              <button>{breadcrumb.make}</button> / <button>{breadcrumb.library}</button> / <button>{breadcrumb.manual}</button> / <button>{breadcrumb.chapter}</button> / <button>{breadcrumb.section}</button>
            </div>
            <div className="manual-publication-meta">
              <div className="meta-chip"><strong>Model/PN</strong><br />N/A / {manualId || "n/a"}</div>
              <div className="meta-chip"><strong>Revision</strong><br />{revId || "n/a"}</div>
              <div className="meta-chip"><strong>Mode</strong><br />{readerMode.toUpperCase()}</div>
            </div>

            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <button className="manual-reader-icon-btn" onClick={() => goRelativeSection(-1)}>Previous section</button>
              <button className="manual-reader-icon-btn" onClick={() => goRelativeSection(1)}>Next section</button>
              <button className="manual-reader-icon-btn" onClick={() => setAdvancedOpen(true)}><Search size={14} /> Advanced search</button>
            </div>

            {noContent ? (
              <div className="manual-empty-hub">
                <h2>This revision has no rendered content yet</h2>
                <p>Upload a source document, run processing, or use OCR for scanned PDFs.</p>
                <div className="manual-empty-actions">
                  <label className="manual-reader-icon-btn"><Upload size={14} /> Upload Document<input type="file" accept=".pdf,.docx" hidden onChange={(e) => setUploadName(e.target.files?.[0]?.name || "")} /></label>
                  <button className="manual-reader-icon-btn" onClick={() => run("processor")} disabled={busy !== null}>{busy === "processor" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />} Run Processor</button>
                  <button className="manual-reader-icon-btn" onClick={() => run("ocr")} disabled={busy !== null}>{busy === "ocr" ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />} Run OCR</button>
                  <a className="manual-reader-icon-btn" href="#processor-logs"><FileText size={14} /> View logs</a>
                </div>
                {uploadName ? <p className="manual-upload-caption">Selected: {uploadName}</p> : null}
                {processing ? <p className="manual-upload-caption">Status: {processing.stage} · Last run by {processing.actor_id || "system"}</p> : null}
                <p className="manual-upload-caption">Hardware acceleration: {gpuMode === "webgpu" ? "WebGPU" : gpuMode === "webgl2" ? "WebGL2" : gpuMode === "css" ? "CSS GPU" : "Not available"}</p>
              </div>
            ) : viewer}
          </section>

          {inspectorOpen ? (
            <aside className="manual-reader-aside">
              <div className="manual-tabs">
                {(["revision", "ack", "export"] as const).map((t) => <button key={t} className={`manual-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{t.toUpperCase()}</button>)}
              </div>
              <div className="manual-context-panel">
                {panel === "search" ? (
                  <>
                    <strong>Search hits</strong>
                    <div className="manual-mini-list">
                      {filteredSections.map((s) => (
                        <button key={s.id} className="manual-mini-item" onClick={() => { setActiveSection(s.anchor_slug); setReaderMode("section"); }}>{s.heading}<span>Open</span></button>
                      ))}
                    </div>
                  </>
                ) : null}

                {panel === "history" ? (
                  <>
                    <strong>History</strong>
                    <div className="manual-mini-list">
                      {history.map((h, idx) => (
                        <button key={`${h.timestamp}-${idx}`} className="manual-mini-item" onClick={() => navigate(h.route)}>
                          <span>{h.title || h.section || h.manual}</span>
                          <span>{new Date(h.timestamp).toLocaleDateString()}</span>
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}

                {panel === "task" ? (
                  <>
                    <strong>Task workspace</strong>
                    <div style={{ display: "flex", gap: 6 }}>
                      {(["current", "visited", "all"] as const).map((t) => <button key={t} className={`manual-reader-icon-btn ${taskTab === t ? "active" : ""}`} onClick={() => setTaskTab(t)}>{t}</button>)}
                    </div>
                    <div className="manual-mini-list">
                      {["Inspection doc", "Figure pack", "Section print queue"].map((n) => <div key={n} className="manual-mini-item"><span>{n}</span><span>Queued</span></div>)}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button className="manual-reader-icon-btn">Email</button>
                      <button className="manual-reader-icon-btn">Print</button>
                      <button className="manual-reader-icon-btn">Save as PDF</button>
                    </div>
                  </>
                ) : null}

                {panel === "order-list" ? (
                  <>
                    <strong>Order / Parts list</strong>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button className="manual-reader-icon-btn">Open</button>
                      <button className="manual-reader-icon-btn">Import</button>
                      <button className="manual-reader-icon-btn">Save</button>
                      <button className="manual-reader-icon-btn">Save as</button>
                      <button className="manual-reader-icon-btn">Export TXT</button>
                      <button className="manual-reader-icon-btn">Export PDF</button>
                    </div>
                    <div className="manual-mini-list">
                      {["P/N 123-00", "P/N 234-11"].map((n) => <div key={n} className="manual-mini-item"><span>{n}</span><input style={{ width: 54 }} defaultValue={1} /></div>)}
                    </div>
                  </>
                ) : null}

                {panel === "change-request" ? (
                  <>
                    <strong>Publication Change Request</strong>
                    <div style={{ display: "grid", gap: 6 }}>
                      {[
                        ["Part Number", "partNumber"], ["Manual Type", "manualType"], ["Title", "title"], ["Model", "model"], ["Publication Date", "publicationDate"], ["Revision Number", "revisionNumber"],
                        ["ATA Chapter", "ataChapter"], ["Section", "section"], ["Sub Section", "subSection"], ["Figure", "figure"], ["Page Number", "pageNumber"], ["Art/Figure", "artFigure"],
                      ].map(([label, key]) => (
                        <input key={key} className="manual-input" placeholder={label} value={(crForm as any)[key]} onChange={(e) => setCrForm((v) => ({ ...v, [key]: e.target.value }))} />
                      ))}
                      <textarea className="manual-textarea" rows={3} placeholder="Other publications affected" value={crForm.otherPublications} onChange={(e) => setCrForm((v) => ({ ...v, otherPublications: e.target.value }))} />
                      <textarea className="manual-textarea" rows={4} placeholder="Suggestion for change" value={crForm.suggestion} onChange={(e) => setCrForm((v) => ({ ...v, suggestion: e.target.value }))} />
                      <label className="manual-check"><input type="checkbox" checked={crForm.requestUpdates} onChange={(e) => setCrForm((v) => ({ ...v, requestUpdates: e.target.checked }))} /> Request updates</label>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="manual-reader-icon-btn" onClick={() => setSelectorOpen(true)}>Select Publication</button>
                        <button className="manual-reader-icon-btn">Submit</button>
                      </div>
                    </div>
                  </>
                ) : null}

                {panel === "metadata" || panel === "figure" ? (
                  <>
                    {tab === "revision" ? (
                      <div className="manual-card">
                        <p>Changed sections: {diffSummary.changed_sections || 0}</p>
                        <p>Changed blocks: {diffSummary.changed_blocks || 0}</p>
                        <p>Added {diffSummary.added || 0} · Removed {diffSummary.removed || 0}</p>
                        <div className="manual-card-block">
                          <strong>KCAA OCR verification</strong>
                          <input className="manual-input" placeholder="Typed KCAA reference" value={ocrTypedRef} onChange={(e) => setOcrTypedRef(e.target.value)} />
                          <input className="manual-input" type="date" value={ocrTypedDate} onChange={(e) => setOcrTypedDate(e.target.value)} />
                          <input className="manual-input" type="file" accept="application/pdf,.pdf" onChange={(e) => setOcrFile(e.target.files?.[0] || null)} />
                          <button className="manual-reader-icon-btn" disabled={!ocrFile || ocrBusy} onClick={() => void verifyApprovalLetter()}>
                            {ocrBusy ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />} Verify KCAA letter
                          </button>
                          {ocrResult ? (
                            <div className="manual-ocr-result">
                              <div><strong>Detected REF:</strong> {ocrResult.detected_ref || "Not found"}</div>
                              <div><strong>Detected date:</strong> {ocrResult.detected_date || "Not found"}</div>
                              <div><strong>REF match:</strong> {ocrResult.ref_match ? "Yes" : "No"}</div>
                              <div><strong>Date match:</strong> {ocrResult.date_match ? "Yes" : "No"}</div>
                              <div><strong>Publish unlocked:</strong> {ocrResult.verified ? "Yes" : "No"}</div>
                              <pre className="manual-ocr-excerpt">{ocrResult.text_excerpt}</pre>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                    {tab === "ack" ? (
                      <div className="manual-card">
                        <p>I acknowledge receipt and review of this revision.</p>
                        <label className="manual-check"><input type="checkbox" checked={ackChecked} onChange={(e) => setAckChecked(e.target.checked)} /> I acknowledge the transmittal requirement.</label>
                        <textarea className="manual-textarea" rows={3} placeholder="Optional comment" value={ackComment} onChange={(e) => setAckComment(e.target.value)} />
                        <button className="manual-reader-icon-btn" disabled={!ackChecked} onClick={() => tenant && manualId && revId && acknowledgeRevision(tenant, manualId, revId, `I acknowledge receipt and review.${ackComment ? ` Note: ${ackComment}` : ""}`)}>Acknowledge</button>
                      </div>
                    ) : null}
                    {tab === "export" ? (
                      <div className="manual-card">
                        <label className="manual-switch-row"><span>UNCONTROLLED watermark</span><input type="checkbox" checked={watermarkOn} disabled={controlled} onChange={(e) => setWatermarkOn(e.target.checked)} /></label>
                        <label className="manual-switch-row"><span>Controlled hard copy</span><input type="checkbox" checked={controlled} onChange={(e) => { const next = e.target.checked; setControlled(next); if (next) setWatermarkOn(false); }} /></label>
                        {controlled ? <><input className="manual-input" placeholder="Manual Copy No" /><input className="manual-input" placeholder="Copy Holder" /><input className="manual-input" placeholder="Purpose" /></> : null}
                        <button className="manual-reader-icon-btn" onClick={() => tenant && manualId && revId && createRevisionExport(tenant, manualId, revId, { controlled_bool: controlled, watermark_uncontrolled_bool: watermarkOn, version_label: `rev-${revId}` })}>Generate PDF Artifact</button>
                        <div className="manual-card-block">
                          <strong>Digital stamp / sign overlay</strong>
                          <input className="manual-input" placeholder="Signer name" value={stampName} onChange={(e) => setStampName(e.target.value)} />
                          <input className="manual-input" placeholder="Signer role" value={stampRole} onChange={(e) => setStampRole(e.target.value)} />
                          <input className="manual-input" placeholder="Stamp label" value={stampLabel} onChange={(e) => setStampLabel(e.target.value)} />
                          <button className="manual-reader-icon-btn" disabled={stampBusy || !stampName.trim() || !stampRole.trim()} onClick={() => void createStampedPdf()}>
                            {stampBusy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} Create stamped PDF
                          </button>
                          {stampMessage ? <p className="manual-upload-caption">{stampMessage}</p> : null}
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
            </aside>
          ) : null}
        </div>

        {selectorOpen ? (
          <div className="manual-card" style={{ position: "fixed", inset: "20% 20% auto", zIndex: 100, background: "white" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}><strong>Select Publication</strong><button className="manual-reader-icon-btn" onClick={() => setSelectorOpen(false)}>Close</button></div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 6 }}>
              <input className="manual-input" placeholder="Model" />
              <input className="manual-input" placeholder="Type" />
              <input className="manual-input" placeholder="P/N" />
              <input className="manual-input" placeholder="Title" />
            </div>
            <table className="manual-reader-content">
              <thead><tr><th>Part Number</th><th>Type</th><th>Title</th><th>Last Rev</th><th>Pub Date</th></tr></thead>
              <tbody><tr><td>{manualId || "N/A"}</td><td>Technical Manual</td><td>{`Manual ${manualId || ""}`}</td><td>{revId || "N/A"}</td><td>{new Date().toISOString().slice(0, 10)}</td></tr></tbody>
            </table>
          </div>
        ) : null}
      </ManualsReaderShell>
    </TenantBrandingProvider>
  );
}

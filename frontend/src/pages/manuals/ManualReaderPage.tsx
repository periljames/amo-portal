import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ClipboardPlus,
  FileImage,
  FileText,
  History,
  Loader2,
  Search,
  Send,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getCachedUser } from "../../services/auth";
import {
  getRevisionDiff,
  getRevisionRead,
  getRevisionWorkflow,
  searchPublicationSelector,
  submitPublicationChangeRequest,
  type ManualReadPayload,
  type PublicationSelectorItem,
} from "../../services/manuals";
import { ManualsReaderShell, TenantBrandingProvider, type ReaderActionId } from "../../packages/manuals-reader";
import { useManualRouteContext } from "./context";
import "./manualReader.css";

type MainTab = "reader" | "figures" | "history" | "pcr";
type InspectorTab = "details" | "history" | "pcr";

type FigureRef = {
  id: string;
  src: string;
  title: string;
  sectionAnchor: string;
  sectionHeading: string;
};

type ReaderHistoryItem = {
  id: string;
  label: string;
  kind: "section" | "figure" | "request";
  at: string;
};

type PcrFormState = {
  requestedByFirstName: string;
  requestedByLastName: string;
  email: string;
  phone: string;
  manualId: string;
  partNumber: string;
  manualType: string;
  title: string;
  model: string;
  publicationDate: string;
  revisionNumber: string;
  ataChapter: string;
  section: string;
  subSection: string;
  figure: string;
  pageNumber: string;
  artFigure: string;
  other: string;
  otherPublicationsAffected: string;
  suggestionForChange: string;
  requestUpdates: boolean;
};

const READER_HISTORY_KEY = "amo_portal_manual_reader_history";

function splitName(value?: string | null) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return {
    first: parts[0] || "",
    last: parts.length > 1 ? parts.slice(1).join(" ") : "",
  };
}

function chapterFromHeading(heading?: string | null): string {
  const match = String(heading || "").match(/(\d{2})/);
  return match ? match[1] : "";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

function chunk<T>(items: T[], size: number): T[][] {
  const output: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    output.push(items.slice(index, index + size));
  }
  return output;
}

function extractFigures(payload: ManualReadPayload | null): FigureRef[] {
  if (!payload) return [];
  const blockMap = new Map<string, Array<{ html: string }>>();
  payload.blocks.forEach((block) => {
    const bucket = blockMap.get(block.section_id) || [];
    bucket.push({ html: block.html });
    blockMap.set(block.section_id, bucket);
  });

  const figures: FigureRef[] = [];
  payload.sections.forEach((section) => {
    const blocks = blockMap.get(section.id) || [];
    blocks.forEach((block, blockIndex) => {
      const regex = /<img[^>]+src=["']([^"']+)["'][^>]*?(?:alt=["']([^"']*)["'])?[^>]*>/gi;
      let match: RegExpExecArray | null;
      while ((match = regex.exec(block.html))) {
        figures.push({
          id: `${section.anchor_slug}-figure-${blockIndex}-${figures.length + 1}`,
          src: match[1],
          title: match[2] || `Figure ${figures.length + 1}`,
          sectionAnchor: section.anchor_slug,
          sectionHeading: section.heading,
        });
      }
    });
  });
  return figures;
}

export default function ManualReaderPage() {
  const navigate = useNavigate();
  const { tenant, manualId, revId, sectionId, figureId, basePath } = useManualRouteContext();
  const user = getCachedUser();
  const requestor = splitName((user as any)?.full_name || (user as any)?.name);

  const [payload, setPayload] = useState<ManualReadPayload | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState("Loading");
  const [diffSummary, setDiffSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [mainTab, setMainTab] = useState<MainTab>(figureId ? "figures" : "reader");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("details");
  const [layout, setLayout] = useState<"continuous" | "paged-1" | "paged-2" | "paged-3">(
    (localStorage.getItem("manuals.layout") as "continuous" | "paged-1" | "paged-2" | "paged-3") || "continuous",
  );
  const [zoom, setZoom] = useState<number>(Number(localStorage.getItem("manuals.zoom") || "100"));
  const [figureZoom, setFigureZoom] = useState<number>(Number(localStorage.getItem("manuals.figureZoom") || "100"));
  const [tocOpen, setTocOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [activeSection, setActiveSection] = useState(sectionId || "");
  const [activeFigureId, setActiveFigureId] = useState<string | null>(figureId || null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectorQuery, setSelectorQuery] = useState("");
  const [selectorLoading, setSelectorLoading] = useState(false);
  const [selectorItems, setSelectorItems] = useState<PublicationSelectorItem[]>([]);
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [submitMessage, setSubmitMessage] = useState("");
  const [history, setHistory] = useState<ReaderHistoryItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(READER_HISTORY_KEY) || "[]") as ReaderHistoryItem[];
    } catch {
      return [];
    }
  });

  const [pcrForm, setPcrForm] = useState<PcrFormState>({
    requestedByFirstName: requestor.first,
    requestedByLastName: requestor.last,
    email: (user as any)?.email || "",
    phone: (user as any)?.phone || (user as any)?.secondary_phone || "",
    manualId: manualId || "",
    partNumber: manualId || "",
    manualType: "Technical Publication",
    title: manualId ? `Manual ${manualId}` : "",
    model: "",
    publicationDate: "",
    revisionNumber: revId || "",
    ataChapter: "",
    section: "",
    subSection: "",
    figure: "",
    pageNumber: "",
    artFigure: "",
    other: "",
    otherPublicationsAffected: "",
    suggestionForChange: "",
    requestUpdates: true,
  });

  const refresh = async () => {
    if (!tenant || !manualId || !revId) return;
    setLoading(true);
    setError("");
    try {
      const [readResponse, workflowResponse, diffResponse] = await Promise.all([
        getRevisionRead(tenant, manualId, revId),
        getRevisionWorkflow(tenant, manualId, revId),
        getRevisionDiff(tenant, manualId, revId),
      ]);
      setPayload(readResponse);
      setWorkflowStatus(workflowResponse.status || "Ready");
      setDiffSummary(diffResponse.summary_json || {});
      setActiveSection((prev) => prev || sectionId || readResponse.sections[0]?.anchor_slug || "");
      setError("");
    } catch (err) {
      setPayload(null);
      setWorkflowStatus("Unavailable");
      setDiffSummary({});
      setError(err instanceof Error ? err.message : "Unable to load the selected manual revision.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [tenant, manualId, revId]);

  useEffect(() => {
    localStorage.setItem("manuals.layout", layout);
    localStorage.setItem("manuals.zoom", String(zoom));
    localStorage.setItem("manuals.figureZoom", String(figureZoom));
  }, [figureZoom, layout, zoom]);

  const blocksBySection = useMemo(() => {
    const grouped = new Map<string, Array<{ html: string; text: string }>>();
    (payload?.blocks || []).forEach((block) => {
      const bucket = grouped.get(block.section_id) || [];
      bucket.push({ html: block.html, text: block.text });
      grouped.set(block.section_id, bucket);
    });
    return grouped;
  }, [payload]);

  const figures = useMemo(() => extractFigures(payload), [payload]);
  const activeFigure = useMemo(() => figures.find((figure) => figure.id === activeFigureId) || null, [activeFigureId, figures]);

  const filteredSections = useMemo(() => {
    const sections = payload?.sections || [];
    if (!search.trim()) return sections;
    const needle = search.trim().toLowerCase();
    return sections.filter((section) => {
      if (section.heading.toLowerCase().includes(needle)) return true;
      const blocks = blocksBySection.get(section.id) || [];
      return blocks.some((block) => block.text.toLowerCase().includes(needle));
    });
  }, [blocksBySection, payload?.sections, search]);

  const activeSectionRecord = useMemo(
    () => filteredSections.find((section) => section.anchor_slug === activeSection) || payload?.sections?.[0] || null,
    [activeSection, filteredSections, payload?.sections],
  );

  const pagedSections = useMemo(() => {
    const width = layout === "paged-3" ? 3 : layout === "paged-2" ? 2 : 1;
    return chunk(filteredSections, width);
  }, [filteredSections, layout]);

  const pushHistory = (label: string, kind: ReaderHistoryItem["kind"]) => {
    const next: ReaderHistoryItem = {
      id: `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      label,
      kind,
      at: new Date().toISOString(),
    };
    const merged = [next, ...history].slice(0, 80);
    setHistory(merged);
    localStorage.setItem(READER_HISTORY_KEY, JSON.stringify(merged));
  };

  const openSection = (anchor: string) => {
    setMainTab("reader");
    setInspectorTab("details");
    setActiveSection(anchor);
    const section = payload?.sections.find((entry) => entry.anchor_slug === anchor);
    if (section) {
      setPcrForm((prev) => ({
        ...prev,
        ataChapter: chapterFromHeading(section.heading),
        section: section.heading,
        figure: "",
      }));
      pushHistory(section.heading, "section");
    }
    requestAnimationFrame(() => {
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const openFigure = (figure: FigureRef) => {
    setMainTab("figures");
    setInspectorTab("details");
    setActiveFigureId(figure.id);
    setActiveSection(figure.sectionAnchor);
    setPcrForm((prev) => ({
      ...prev,
      ataChapter: chapterFromHeading(figure.sectionHeading),
      section: figure.sectionHeading,
      figure: figure.title,
    }));
    pushHistory(figure.title, "figure");
  };

  useEffect(() => {
    if (figures.length && !activeFigureId) {
      setActiveFigureId(figures[0].id);
    }
  }, [activeFigureId, figures]);

  useEffect(() => {
    setPcrForm((prev) => ({
      ...prev,
      manualId: manualId || prev.manualId,
      partNumber: manualId || prev.partNumber,
      manualType: prev.manualType || "Technical Publication",
      title: prev.title || (manualId ? `Manual ${manualId}` : ""),
      publicationDate: prev.publicationDate || new Date().toISOString().slice(0, 10),
      revisionNumber: revId || prev.revisionNumber,
      ataChapter: prev.ataChapter || chapterFromHeading(activeSectionRecord?.heading),
      section: prev.section || activeSectionRecord?.heading || "",
      figure: activeFigure?.title || prev.figure,
    }));
  }, [activeFigure?.title, activeSectionRecord?.heading, manualId, revId]);

  const selectorSearch = async () => {
    if (!tenant) return;
    setSelectorLoading(true);
    try {
      const rows = await searchPublicationSelector(tenant, { q: selectorQuery.trim() || undefined });
      setSelectorItems(rows);
    } catch {
      setSelectorItems([]);
    } finally {
      setSelectorLoading(false);
    }
  };

  useEffect(() => {
    if (!selectorOpen || !tenant) return;
    void selectorSearch();
  }, [selectorOpen, tenant]);

  const pickPublication = (item: PublicationSelectorItem) => {
    setPcrForm((prev) => ({
      ...prev,
      manualId: item.manual_id,
      partNumber: item.code,
      manualType: item.manual_type,
      title: item.title,
      model: item.model || "",
      publicationDate: item.publication_date || prev.publicationDate,
      revisionNumber: item.current_revision || prev.revisionNumber,
    }));
    setSelectorOpen(false);
  };

  const submitPcr = async () => {
    if (!tenant || !pcrForm.manualId || !pcrForm.partNumber || !pcrForm.revisionNumber || !pcrForm.suggestionForChange.trim()) {
      setSubmitState("error");
      setSubmitMessage("Complete the publication, revision, and suggestion fields before submitting.");
      return;
    }
    setSubmitState("submitting");
    setSubmitMessage("");
    try {
      const response = await submitPublicationChangeRequest(tenant, {
        requested_by_first_name: pcrForm.requestedByFirstName,
        requested_by_last_name: pcrForm.requestedByLastName,
        email: pcrForm.email,
        phone: pcrForm.phone,
        manual_id: pcrForm.manualId,
        part_number: pcrForm.partNumber,
        manual_type: pcrForm.manualType,
        title: pcrForm.title,
        model: pcrForm.model || null,
        publication_date: pcrForm.publicationDate || null,
        revision_number: pcrForm.revisionNumber,
        ata_chapter: pcrForm.ataChapter || null,
        section: pcrForm.section || null,
        sub_section: pcrForm.subSection || null,
        figure: pcrForm.figure || null,
        page_number: pcrForm.pageNumber || null,
        art_figure: pcrForm.artFigure || null,
        other: pcrForm.other || null,
        other_publications_affected: pcrForm.otherPublicationsAffected || null,
        suggestion_for_change: pcrForm.suggestionForChange,
        request_updates: pcrForm.requestUpdates,
      });
      setSubmitState("done");
      setSubmitMessage(`${response.message} Ref ${response.id}`);
      pushHistory(`PCR ${response.id}`, "request");
      setPcrForm((prev) => ({
        ...prev,
        other: "",
        otherPublicationsAffected: "",
        suggestionForChange: "",
      }));
    } catch (err) {
      setSubmitState("error");
      setSubmitMessage(err instanceof Error ? err.message : "Unable to submit the publication change request.");
    }
  };

  const onActionClick = (action: ReaderActionId) => {
    if (action === "change-request") {
      setInspectorTab("pcr");
      setInspectorOpen(true);
      return;
    }
    if (action === "history") {
      setInspectorTab("history");
      setInspectorOpen(true);
      return;
    }
    if (action === "home") {
      navigate(basePath);
      return;
    }
    setInspectorTab("details");
  };

  const activeAction = inspectorTab === "pcr" ? "change-request" : inspectorTab === "history" ? "history" : null;
  const locationLabel = activeFigure ? activeFigure.title : activeSectionRecord?.heading || "Manual reader";

  const renderReader = () => {
    if (!filteredSections.length) {
      return (
        <div className="manual-reader-empty">
          <Search size={18} />
          <h3>No sections match this search</h3>
          <p>Clear the search term or switch to another tab.</p>
        </div>
      );
    }

    if (layout === "continuous") {
      return (
        <div className="manual-reader-article" style={{ fontSize: `${zoom}%` }}>
          {filteredSections.map((section) => {
            const blocks = blocksBySection.get(section.id) || [];
            const sectionFigures = figures.filter((figure) => figure.sectionAnchor === section.anchor_slug);
            return (
              <section key={section.id} id={section.anchor_slug} className="manual-reader-block">
                <div className="manual-reader-block__header">
                  <div>
                    <span className="manual-reader-block__eyebrow">ATA {chapterFromHeading(section.heading) || "—"}</span>
                    <h2>{section.heading}</h2>
                  </div>
                  {sectionFigures.length ? (
                    <button type="button" className="manual-reader-icon-btn" onClick={() => openFigure(sectionFigures[0])}>
                      <FileImage size={14} />
                      View figure
                    </button>
                  ) : null}
                </div>
                {blocks.map((block, index) => (
                  <div key={`${section.id}-${index}`} className="manual-reader-html" dangerouslySetInnerHTML={{ __html: block.html }} />
                ))}
              </section>
            );
          })}
        </div>
      );
    }

    return (
      <div className={`manual-reader-paged manual-reader-paged--${layout}`} style={{ fontSize: `${zoom}%` }}>
        {pagedSections.map((page, pageIndex) => (
          <div key={`page-${pageIndex}`} className="manual-reader-page">
            {page.map((section) => {
              const blocks = blocksBySection.get(section.id) || [];
              return (
                <section key={section.id} className="manual-reader-block">
                  <span className="manual-reader-block__eyebrow">ATA {chapterFromHeading(section.heading) || "—"}</span>
                  <h3>{section.heading}</h3>
                  {blocks.map((block, index) => (
                    <div key={`${section.id}-${index}`} className="manual-reader-html" dangerouslySetInnerHTML={{ __html: block.html }} />
                  ))}
                </section>
              );
            })}
          </div>
        ))}
      </div>
    );
  };

  const renderFigures = () => (
    <div className="manual-figure-workspace">
      <aside className="manual-figure-list">
        {figures.length ? (
          figures.map((figure) => (
            <button
              key={figure.id}
              type="button"
              className={`manual-figure-list__item${activeFigureId === figure.id ? " is-active" : ""}`}
              onClick={() => openFigure(figure)}
            >
              <span className="manual-figure-list__title">{figure.title}</span>
              <span className="manual-figure-list__meta">{figure.sectionHeading}</span>
            </button>
          ))
        ) : (
          <div className="manual-reader-empty manual-reader-empty--compact">
            <FileImage size={18} />
            <p>No figures were extracted from this revision.</p>
          </div>
        )}
      </aside>
      <div className="manual-figure-stage">
        <div className="manual-figure-toolbar">
          <button type="button" className="manual-reader-icon-btn" onClick={() => setFigureZoom((value) => Math.max(50, value - 10))}>
            <ZoomOut size={14} />
            Zoom out
          </button>
          <button type="button" className="manual-reader-icon-btn" onClick={() => setFigureZoom(100)}>Reset</button>
          <button type="button" className="manual-reader-icon-btn" onClick={() => setFigureZoom((value) => Math.min(220, value + 10))}>
            <ZoomIn size={14} />
            Zoom in
          </button>
          {activeFigure ? (
            <button type="button" className="manual-reader-icon-btn" onClick={() => openSection(activeFigure.sectionAnchor)}>
              <FileText size={14} />
              Open section
            </button>
          ) : null}
        </div>
        {activeFigure ? (
          <div className="manual-figure-view">
            <div className="manual-figure-view__meta">
              <span>{activeFigure.sectionHeading}</span>
              <strong>{activeFigure.title}</strong>
            </div>
            <div className="manual-figure-view__canvas">
              <img src={activeFigure.src} alt={activeFigure.title} style={{ transform: `scale(${figureZoom / 100})`, transformOrigin: "top left" }} />
            </div>
          </div>
        ) : (
          <div className="manual-reader-empty">
            <FileImage size={18} />
            <h3>Select a figure</h3>
            <p>Use the figure tab to move directly to illustrations referenced in the publication.</p>
          </div>
        )}
      </div>
    </div>
  );

  const renderHistory = () => (
    <div className="manual-history-list">
      {history.length ? (
        history.map((item) => (
          <div key={item.id} className="manual-history-list__item">
            <div>
              <strong>{item.label}</strong>
              <p>{item.kind}</p>
            </div>
            <span>{new Date(item.at).toLocaleString()}</span>
          </div>
        ))
      ) : (
        <div className="manual-reader-empty manual-reader-empty--compact">
          <History size={18} />
          <p>No recent manual navigation yet.</p>
        </div>
      )}
    </div>
  );

  const renderPcrForm = () => (
    <div className="manual-pcr-form">
      <section className="manual-pcr-section">
        <div className="manual-pcr-section__header">
          <strong>Requested by</strong>
        </div>
        <div className="manual-pcr-grid manual-pcr-grid--four">
          <label>
            <span>First name</span>
            <input className="manual-input" value={pcrForm.requestedByFirstName} onChange={(event) => setPcrForm((prev) => ({ ...prev, requestedByFirstName: event.target.value }))} />
          </label>
          <label>
            <span>Last name</span>
            <input className="manual-input" value={pcrForm.requestedByLastName} onChange={(event) => setPcrForm((prev) => ({ ...prev, requestedByLastName: event.target.value }))} />
          </label>
          <label>
            <span>Email address</span>
            <input className="manual-input" type="email" value={pcrForm.email} onChange={(event) => setPcrForm((prev) => ({ ...prev, email: event.target.value }))} />
          </label>
          <label>
            <span>Phone number</span>
            <input className="manual-input" value={pcrForm.phone} onChange={(event) => setPcrForm((prev) => ({ ...prev, phone: event.target.value }))} />
          </label>
        </div>
      </section>

      <section className="manual-pcr-section">
        <div className="manual-pcr-section__header manual-pcr-section__header--action">
          <strong>Publication affected</strong>
          <button type="button" className="manual-reader-icon-btn" onClick={() => setSelectorOpen(true)}>
            <Search size={14} />
            Select publication
          </button>
        </div>
        <div className="manual-pcr-grid manual-pcr-grid--four">
          <label>
            <span>Part number</span>
            <input className="manual-input" value={pcrForm.partNumber} onChange={(event) => setPcrForm((prev) => ({ ...prev, partNumber: event.target.value }))} />
          </label>
          <label>
            <span>Manual type</span>
            <input className="manual-input" value={pcrForm.manualType} onChange={(event) => setPcrForm((prev) => ({ ...prev, manualType: event.target.value }))} />
          </label>
          <label>
            <span>Title</span>
            <input className="manual-input" value={pcrForm.title} onChange={(event) => setPcrForm((prev) => ({ ...prev, title: event.target.value }))} />
          </label>
          <label>
            <span>Model</span>
            <input className="manual-input" value={pcrForm.model} onChange={(event) => setPcrForm((prev) => ({ ...prev, model: event.target.value }))} />
          </label>
          <label>
            <span>Publication date</span>
            <input className="manual-input" type="date" value={pcrForm.publicationDate} onChange={(event) => setPcrForm((prev) => ({ ...prev, publicationDate: event.target.value }))} />
          </label>
          <label>
            <span>Revision number</span>
            <input className="manual-input" value={pcrForm.revisionNumber} onChange={(event) => setPcrForm((prev) => ({ ...prev, revisionNumber: event.target.value }))} />
          </label>
        </div>
      </section>

      <section className="manual-pcr-section">
        <div className="manual-pcr-section__header">
          <strong>Location in the publication</strong>
        </div>
        <div className="manual-pcr-grid manual-pcr-grid--four">
          <label>
            <span>ATA chapter</span>
            <input className="manual-input" value={pcrForm.ataChapter} onChange={(event) => setPcrForm((prev) => ({ ...prev, ataChapter: event.target.value }))} />
          </label>
          <label>
            <span>Section</span>
            <input className="manual-input" value={pcrForm.section} onChange={(event) => setPcrForm((prev) => ({ ...prev, section: event.target.value }))} />
          </label>
          <label>
            <span>Sub section</span>
            <input className="manual-input" value={pcrForm.subSection} onChange={(event) => setPcrForm((prev) => ({ ...prev, subSection: event.target.value }))} />
          </label>
          <label>
            <span>Figure</span>
            <input className="manual-input" value={pcrForm.figure} onChange={(event) => setPcrForm((prev) => ({ ...prev, figure: event.target.value }))} />
          </label>
          <label>
            <span>Page number</span>
            <input className="manual-input" value={pcrForm.pageNumber} onChange={(event) => setPcrForm((prev) => ({ ...prev, pageNumber: event.target.value }))} />
          </label>
          <label>
            <span>Art/Figure</span>
            <input className="manual-input" value={pcrForm.artFigure} onChange={(event) => setPcrForm((prev) => ({ ...prev, artFigure: event.target.value }))} />
          </label>
          <label className="manual-pcr-grid__span-2">
            <span>Other</span>
            <input className="manual-input" value={pcrForm.other} onChange={(event) => setPcrForm((prev) => ({ ...prev, other: event.target.value }))} />
          </label>
        </div>
      </section>

      <section className="manual-pcr-section">
        <div className="manual-pcr-section__header">
          <strong>Change requested</strong>
        </div>
        <div className="manual-pcr-grid">
          <label>
            <span>Other publications affected</span>
            <textarea className="manual-textarea" rows={3} value={pcrForm.otherPublicationsAffected} onChange={(event) => setPcrForm((prev) => ({ ...prev, otherPublicationsAffected: event.target.value }))} />
          </label>
          <label>
            <span>Suggestion for change</span>
            <textarea className="manual-textarea" rows={6} value={pcrForm.suggestionForChange} onChange={(event) => setPcrForm((prev) => ({ ...prev, suggestionForChange: event.target.value }))} />
          </label>
        </div>
        <label className="manual-check">
          <input type="checkbox" checked={pcrForm.requestUpdates} onChange={(event) => setPcrForm((prev) => ({ ...prev, requestUpdates: event.target.checked }))} />
          <span>Receive email updates for this publication change request</span>
        </label>
        {submitMessage ? <div className={`manual-pcr-feedback is-${submitState}`}>{submitMessage}</div> : null}
        <div className="manual-pcr-actions">
          <button type="button" className="manual-reader-icon-btn" onClick={submitPcr} disabled={submitState === "submitting"}>
            {submitState === "submitting" ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Submit request
          </button>
        </div>
      </section>
    </div>
  );

  return (
    <TenantBrandingProvider tenantSlug={tenant || "default"}>
      <ManualsReaderShell
        tenantSlug={tenant || "default"}
        mode={window.location.search.includes("standalone=1") ? "standalone" : "embedded"}
        manualLabel={manualId ? `Manual ${manualId}` : "Manual"}
        statusBadge={workflowStatus}
        revMeta={`Rev ${revId || "n/a"}`}
        locationLabel={locationLabel}
        fallbackPath={basePath}
        searchValue={search}
        onSearchChange={setSearch}
        onToggleToc={() => setTocOpen((value) => !value)}
        onToggleInspector={() => setInspectorOpen((value) => !value)}
        onLayoutChange={setLayout}
        onZoomIn={() => setZoom((value) => Math.min(180, value + 10))}
        onZoomOut={() => setZoom((value) => Math.max(80, value - 10))}
        onZoomReset={() => setZoom(100)}
        onActionClick={onActionClick}
        activeAction={activeAction}
      >
        <div className="manual-reader-workspace-v2">
          {tocOpen ? (
            <aside className="manual-reader-nav">
              <div className="manual-reader-nav__header">
                <strong>Publication</strong>
                <span>{filteredSections.length} section(s)</span>
              </div>
              <div className="manual-reader-nav__body">
                {filteredSections.map((section) => {
                  const sectionFigures = figures.filter((figure) => figure.sectionAnchor === section.anchor_slug);
                  const isActive = section.anchor_slug === activeSection;
                  return (
                    <div key={section.id} className="manual-tree-group">
                      <button type="button" className={`manual-tree-node${isActive ? " is-active" : ""}`} onClick={() => openSection(section.anchor_slug)}>
                        {isActive ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        <span>{section.heading}</span>
                      </button>
                      {isActive && sectionFigures.length ? (
                        <div className="manual-tree-children">
                          {sectionFigures.map((figure) => (
                            <button key={figure.id} type="button" className={`manual-tree-child${activeFigureId === figure.id ? " is-active" : ""}`} onClick={() => openFigure(figure)}>
                              <FileImage size={13} />
                              <span>{figure.title}</span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </aside>
          ) : null}

          <section className="manual-reader-stage">
            <div className="manual-reader-stage__header">
              <div className="manual-reader-stage__meta">
                <span className="manual-reader-stage__eyebrow">Technical publications</span>
                <h1>{manualId ? `Manual ${manualId}` : "Manual reader"}</h1>
                <p>{activeSectionRecord?.heading || "Select a section from the publication tree."}</p>
              </div>
              <div className="manual-reader-view-tabs">
                <button type="button" className={mainTab === "reader" ? "is-active" : ""} onClick={() => setMainTab("reader")}>
                  <FileText size={14} />
                  Reader
                </button>
                <button type="button" className={mainTab === "figures" ? "is-active" : ""} onClick={() => setMainTab("figures")}>
                  <FileImage size={14} />
                  Figures
                </button>
                <button type="button" className={mainTab === "history" ? "is-active" : ""} onClick={() => setMainTab("history")}>
                  <History size={14} />
                  History
                </button>
                <button type="button" className={mainTab === "pcr" ? "is-active" : ""} onClick={() => setMainTab("pcr")}>
                  <ClipboardPlus size={14} />
                  PCR
                </button>
              </div>
            </div>

            {loading ? (
              <div className="manual-reader-empty">
                <Loader2 size={18} className="animate-spin" />
                <h3>Loading publication</h3>
                <p>Please wait while the selected revision is prepared.</p>
              </div>
            ) : error ? (
              <div className="manual-reader-empty">
                <FileText size={18} />
                <h3>Unable to load publication</h3>
                <p>{error}</p>
                <button type="button" className="manual-reader-icon-btn" onClick={() => void refresh()}>Retry</button>
              </div>
            ) : mainTab === "figures" ? (
              renderFigures()
            ) : mainTab === "history" ? (
              renderHistory()
            ) : mainTab === "pcr" ? (
              renderPcrForm()
            ) : (
              renderReader()
            )}
          </section>

          {inspectorOpen ? (
            <aside className="manual-reader-inspector">
              <div className="manual-reader-inspector__tabs">
                <button type="button" className={inspectorTab === "details" ? "is-active" : ""} onClick={() => setInspectorTab("details")}>Details</button>
                <button type="button" className={inspectorTab === "history" ? "is-active" : ""} onClick={() => setInspectorTab("history")}>History</button>
                <button type="button" className={inspectorTab === "pcr" ? "is-active" : ""} onClick={() => setInspectorTab("pcr")}>PCR</button>
              </div>

              {inspectorTab === "details" ? (
                <div className="manual-reader-inspector__panel">
                  <div className="manual-inspector-card">
                    <span className="manual-inspector-card__label">Workflow</span>
                    <strong>{workflowStatus}</strong>
                  </div>
                  <div className="manual-inspector-card-grid">
                    <div className="manual-inspector-card">
                      <span className="manual-inspector-card__label">Revision</span>
                      <strong>{revId || "—"}</strong>
                    </div>
                    <div className="manual-inspector-card">
                      <span className="manual-inspector-card__label">Publication date</span>
                      <strong>{formatDate(pcrForm.publicationDate)}</strong>
                    </div>
                    <div className="manual-inspector-card">
                      <span className="manual-inspector-card__label">Current chapter</span>
                      <strong>{pcrForm.ataChapter || "—"}</strong>
                    </div>
                    <div className="manual-inspector-card">
                      <span className="manual-inspector-card__label">Current figure</span>
                      <strong>{activeFigure?.title || "—"}</strong>
                    </div>
                  </div>
                  <div className="manual-inspector-card">
                    <span className="manual-inspector-card__label">Revision delta</span>
                    <ul className="manual-inspector-list">
                      <li><span>Changed sections</span><strong>{diffSummary.changed_sections || 0}</strong></li>
                      <li><span>Changed blocks</span><strong>{diffSummary.changed_blocks || 0}</strong></li>
                      <li><span>Added</span><strong>{diffSummary.added || 0}</strong></li>
                      <li><span>Removed</span><strong>{diffSummary.removed || 0}</strong></li>
                    </ul>
                  </div>
                </div>
              ) : null}

              {inspectorTab === "history" ? renderHistory() : null}
              {inspectorTab === "pcr" ? renderPcrForm() : null}
            </aside>
          ) : null}
        </div>

        {selectorOpen ? (
          <div className="manual-selector-modal">
            <div className="manual-selector-modal__backdrop" onClick={() => setSelectorOpen(false)} />
            <div className="manual-selector-modal__dialog">
              <div className="manual-selector-modal__header">
                <div>
                  <strong>Select publication</strong>
                  <p>Pick the affected publication, then continue the request from the reader context.</p>
                </div>
                <button type="button" className="manual-reader-icon-btn" onClick={() => setSelectorOpen(false)}>Close</button>
              </div>
              <div className="manual-selector-modal__toolbar">
                <input className="manual-input" placeholder="Search code, title, or type" value={selectorQuery} onChange={(event) => setSelectorQuery(event.target.value)} />
                <button type="button" className="manual-reader-icon-btn" onClick={() => void selectorSearch()}>
                  {selectorLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  Search
                </button>
              </div>
              <div className="manual-selector-table">
                <div className="manual-selector-table__head">
                  <span>Part number</span>
                  <span>Type</span>
                  <span>Title</span>
                  <span>Revision</span>
                  <span>Publication date</span>
                  <span />
                </div>
                {selectorItems.length ? (
                  selectorItems.map((item) => (
                    <div key={item.manual_id} className="manual-selector-table__row">
                      <span>{item.code}</span>
                      <span>{item.manual_type}</span>
                      <span>{item.title}</span>
                      <span>{item.current_revision || "—"}</span>
                      <span>{formatDate(item.publication_date)}</span>
                      <button type="button" className="manual-reader-icon-btn" onClick={() => pickPublication(item)}>Use</button>
                    </div>
                  ))
                ) : (
                  <div className="manual-reader-empty manual-reader-empty--compact">
                    {selectorLoading ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                    <p>{selectorLoading ? "Searching publications…" : "No publications found."}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </ManualsReaderShell>
    </TenantBrandingProvider>
  );
}

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  ExternalLink,
  FileCheck2,
  FileText,
  LoaderCircle,
  Navigation,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  assistDocumentation,
  type DocumentationAssistMode,
  type DocumentationAssistResponse,
  type DocumentationAssistSource,
} from "../../services/documentationAssistant";
import "./documentationAssistantPanel.css";

export type DocumentationAssistantPanelProps = {
  tenant: string;
  manualId?: string | null;
  revisionId?: string | null;
  pageNumber?: number | null;
  embedded?: boolean;
  defaultOpen?: boolean;
  title?: string;
};

const MODE_OPTIONS: Array<{ value: DocumentationAssistMode; label: string; icon: typeof Search }> = [
  { value: "ASSIST", label: "Ask", icon: Sparkles },
  { value: "SEARCH", label: "Search", icon: Search },
  { value: "NAVIGATE", label: "Navigate", icon: Navigation },
];

const FLOATING_MIN_WIDTH = 360;
const FLOATING_MAX_WIDTH = 760;
const FLOATING_DEFAULT_WIDTH = 460;
const FLOATING_WIDTH_STORAGE_KEY = "amo_documentation_assistant_width";

function maximumAssistantWidth(viewportWidth: number): number {
  return Math.max(FLOATING_MIN_WIDTH, Math.min(FLOATING_MAX_WIDTH, viewportWidth - 56));
}

function clampAssistantWidth(value: number, viewportWidth = 1440): number {
  return Math.min(maximumAssistantWidth(viewportWidth), Math.max(FLOATING_MIN_WIDTH, value));
}

function readStoredAssistantWidth(): number {
  if (typeof window === "undefined") return FLOATING_DEFAULT_WIDTH;
  try {
    const storedValue = window.localStorage.getItem(FLOATING_WIDTH_STORAGE_KEY);
    if (!storedValue) return clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);
    const stored = Number(storedValue);
    return Number.isFinite(stored)
      ? clampAssistantWidth(stored, window.innerWidth)
      : clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);
  } catch {
    return clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);
  }
}

function persistAssistantWidth(width: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FLOATING_WIDTH_STORAGE_KEY, String(Math.round(width)));
  } catch {
    // Storage may be unavailable in hardened/private browser sessions.
  }
}


function sourceIcon(source: DocumentationAssistSource) {
  return source.executable ? FileCheck2 : source.kind === "SECTION" ? FileText : BookOpen;
}

function hierarchyLabel(path?: string | null): string {
  return String(path || "")
    .split("/")
    .filter(Boolean)
    .map((part) => part.split("~")[0].replaceAll("-", " "))
    .join(" › ");
}

function visibleReaderPage(explicitPage?: number | null): number | undefined {
  if (explicitPage && explicitPage > 0) return explicitPage;
  const current = document.querySelector<HTMLElement>(".publication-native-pdf__page.is-current");
  const page = Number(current?.dataset.pageNumber || 0);
  return Number.isFinite(page) && page > 0 ? page : undefined;
}

export default function DocumentationAssistantPanel({
  tenant,
  manualId,
  revisionId,
  pageNumber,
  embedded = false,
  defaultOpen = false,
  title = "Document assistant",
}: DocumentationAssistantPanelProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(embedded || defaultOpen);
  const [mode, setMode] = useState<DocumentationAssistMode>("ASSIST");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<DocumentationAssistResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [panelWidth, setPanelWidth] = useState(readStoredAssistantWidth);
  const [resizing, setResizing] = useState(false);
  const latestPanelWidth = useRef(panelWidth);

  useEffect(() => {
    latestPanelWidth.current = panelWidth;
  }, [panelWidth]);

  useEffect(() => {
    if (!resizing || embedded || typeof window === "undefined") return undefined;

    const resize = (event: PointerEvent) => {
      const next = clampAssistantWidth(window.innerWidth - event.clientX, window.innerWidth);
      latestPanelWidth.current = next;
      setPanelWidth(next);
    };
    const stop = () => {
      setResizing(false);
      document.body.classList.remove("documentation-assistant-is-resizing");
      persistAssistantWidth(latestPanelWidth.current);
    };

    document.body.classList.add("documentation-assistant-is-resizing");
    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
    return () => {
      document.body.classList.remove("documentation-assistant-is-resizing");
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [embedded, resizing]);

  useEffect(() => {
    if (embedded || typeof window === "undefined") return undefined;
    const keepWithinViewport = () => {
      setPanelWidth((current) => {
        const next = clampAssistantWidth(current, window.innerWidth);
        latestPanelWidth.current = next;
        return next;
      });
    };
    window.addEventListener("resize", keepWithinViewport);
    return () => window.removeEventListener("resize", keepWithinViewport);
  }, [embedded]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (embedded) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setResizing(true);
  };

  const resizeWithKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (embedded || typeof window === "undefined") return;
    let next = panelWidth;
    if (event.key === "ArrowLeft") next += 24;
    else if (event.key === "ArrowRight") next -= 24;
    else if (event.key === "Home") next = FLOATING_MIN_WIDTH;
    else if (event.key === "End") next = maximumAssistantWidth(window.innerWidth);
    else return;
    event.preventDefault();
    const clamped = clampAssistantWidth(next, window.innerWidth);
    latestPanelWidth.current = clamped;
    setPanelWidth(clamped);
    persistAssistantWidth(clamped);
  };

  const resetWidth = () => {
    if (typeof window === "undefined") return;
    const next = clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);
    latestPanelWidth.current = next;
    setPanelWidth(next);
    persistAssistantWidth(next);
  };

  const ActiveModeIcon = MODE_OPTIONS.find((option) => option.value === mode)?.icon || Bot;

  const suggestions = useMemo(() => manualId
    ? ["Where is the applicable form?", "Show linked checklists", "Find the procedure for this section"]
    : ["Find QAM 51", "Show quality forms", "Where is the audit checklist?"], [manualId]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const clean = query.replace(/\s+/g, " ").trim();
    if (clean.length < 2 || !tenant) return;
    setBusy(true);
    setError("");
    try {
      const response = await assistDocumentation(tenant, {
        query: clean,
        mode,
        manual_id: manualId || undefined,
        revision_id: revisionId || undefined,
        page_number: visibleReaderPage(pageNumber),
        limit: 12,
      });
      setResult(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Assisted document search could not be completed.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  const openSource = (source: DocumentationAssistSource) => {
    if (source.manual_id === manualId && source.revision_id === revisionId) {
      window.dispatchEvent(new CustomEvent("amo:publication-navigate", {
        detail: {
          manualId: source.manual_id,
          revisionId: source.revision_id,
          pageNumber: source.page_number,
          sectionId: source.section_id,
          anchor: source.anchor,
        },
      }));
      if (!embedded) setOpen(false);
      return;
    }
    navigate(source.reader_url);
  };

  if (!embedded && !open) {
    return <button type="button" className="documentation-assistant-launcher" onClick={() => setOpen(true)} aria-expanded="false">
      <span className="documentation-assistant-launcher__icon" aria-hidden="true"><Bot size={18} /><Sparkles size={11} /></span>
      <span>Assisted search</span>
    </button>;
  }

  const floatingStyle = !embedded
    ? ({ "--documentation-assistant-width": `${panelWidth}px` } as CSSProperties)
    : undefined;

  return <aside
    className={`documentation-assistant ${embedded ? "is-embedded" : "is-floating"} ${busy ? "is-busy" : ""}`}
    aria-label={title}
    style={floatingStyle}
    data-resizing={resizing ? "true" : "false"}
    data-mode={mode.toLowerCase()}
  >
    {!embedded ? <div
      className="documentation-assistant__resize-handle"
      role="separator"
      aria-label="Resize document assistant"
      aria-orientation="vertical"
      aria-valuemin={FLOATING_MIN_WIDTH}
      aria-valuemax={typeof window === "undefined" ? FLOATING_MAX_WIDTH : maximumAssistantWidth(window.innerWidth)}
      aria-valuenow={Math.round(panelWidth)}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={startResize}
      onKeyDown={resizeWithKeyboard}
      onDoubleClick={resetWidth}
    ><span className="documentation-assistant__resize-grip" aria-hidden="true" /></div> : null}
    <header className="documentation-assistant__header">
      <div>
        <span className="documentation-assistant__eyebrow">{busy ? <LoaderCircle className="is-spinning" size={14} /> : <ActiveModeIcon size={14} />} Controlled-document assistance</span>
        <h2>{title}</h2>
        <p>Searches only documents this session is permitted to read.</p>
      </div>
      {!embedded ? <button type="button" className="documentation-assistant__close" onClick={() => setOpen(false)} aria-label="Close document assistant"><X size={18} /></button> : null}
    </header>

    <div className="documentation-assistant__body">
    <div className="documentation-assistant__modes" role="tablist" aria-label="Assistance mode">
      {MODE_OPTIONS.map(({ value, label, icon: Icon }) => <button
        key={value}
        type="button"
        role="tab"
        aria-selected={mode === value}
        className={mode === value ? "active" : ""}
        onClick={() => setMode(value)}
      ><Icon size={15} /> {label}</button>)}
    </div>

    <form className="documentation-assistant__query" onSubmit={(event) => void submit(event)}>
      <label htmlFor={`documentation-assistant-query-${embedded ? "embedded" : "floating"}`}>Question or document reference</label>
      <div>
        <input
          id={`documentation-assistant-query-${embedded ? "embedded" : "floating"}`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          maxLength={500}
          placeholder={mode === "NAVIGATE" ? "Take me to QAM 51 or the audit checklist" : "Ask using a code, title, phrase, form, or procedure"}
          autoComplete="off"
        />
        <button type="submit" disabled={busy || query.trim().length < 2}>{busy ? "Searching…" : mode === "ASSIST" ? "Ask" : mode === "NAVIGATE" ? "Find" : "Search"}</button>
      </div>
    </form>

    {!result && !busy ? <div className="documentation-assistant__suggestions">
      <span>Try</span>
      <div>{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setQuery(suggestion)}>{suggestion}</button>)}</div>
    </div> : null}

    {error ? <div className="documentation-assistant__message is-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div> : null}

    {result ? <div className="documentation-assistant__result" aria-live="polite">
      <div className="documentation-assistant__answer">
        <div className="documentation-assistant__answer-meta">
          <span className={result.provider_mode === "OPENAI" ? "is-ai" : "is-search"}>{result.provider_mode === "OPENAI" ? <><Sparkles size={13} /> AI synthesis</> : <><Search size={13} /> Assisted retrieval</>}</span>
          <span>{result.sources.length} controlled source{result.sources.length === 1 ? "" : "s"}</span>
        </div>
        <p>{result.answer}</p>
        {result.warning ? <div className="documentation-assistant__warning"><AlertTriangle size={15} /><span>{result.warning}</span></div> : null}
      </div>

      <div className="documentation-assistant__sources">
        {result.sources.map((source) => {
          const Icon = sourceIcon(source);
          const cited = result.citations.includes(source.id);
          return <article key={source.id} className={cited ? "is-cited" : ""}>
            <button type="button" onClick={() => openSource(source)}>
              <span className="documentation-assistant__source-rank">{source.rank}</span>
              <span className="documentation-assistant__source-main">
                <span className="documentation-assistant__source-title"><Icon size={16} /><strong>{source.code}</strong><span>{source.title}</span>{cited ? <em>Cited</em> : null}</span>
                {source.heading ? <span className="documentation-assistant__source-heading">{source.heading}</span> : null}
                <span className="documentation-assistant__source-snippet">{source.snippet}</span>
                <span className="documentation-assistant__source-meta">
                  {source.page_number ? `Page ${source.page_number}` : source.kind === "DOCUMENT" ? "Document record" : "Indexed section"}
                  {source.executable ? " · Executable form/checklist" : ""}
                  {hierarchyLabel(source.hierarchy_path) ? ` · ${hierarchyLabel(source.hierarchy_path)}` : ""}
                </span>
              </span>
              <ExternalLink size={15} />
            </button>
          </article>;
        })}
      </div>

      <div className="documentation-assistant__authority-note">
        <ShieldCheck size={16} />
        <p><strong>The controlled source remains authoritative.</strong> Assistance cannot approve, publish, acknowledge, complete, or alter a document or record.</p>
      </div>
    </div> : null}
    </div>
  </aside>;
}

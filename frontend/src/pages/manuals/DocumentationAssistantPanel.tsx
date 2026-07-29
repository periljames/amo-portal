import { useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  ExternalLink,
  FileCheck2,
  FileText,
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
    return <button type="button" className="documentation-assistant-launcher" onClick={() => setOpen(true)}>
      <Bot size={18} />
      <span>Assisted search</span>
    </button>;
  }

  return <aside className={`documentation-assistant ${embedded ? "is-embedded" : "is-floating"}`} aria-label={title}>
    <header className="documentation-assistant__header">
      <div>
        <span className="documentation-assistant__eyebrow"><Bot size={14} /> Controlled-document assistance</span>
        <h2>{title}</h2>
        <p>Searches only documents this session is permitted to read.</p>
      </div>
      {!embedded ? <button type="button" className="documentation-assistant__close" onClick={() => setOpen(false)} aria-label="Close document assistant"><X size={18} /></button> : null}
    </header>

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
  </aside>;
}

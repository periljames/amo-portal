import React, { useEffect, useMemo, useRef, useState } from "react";
import { Command, Search, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { getContext } from "../../services/auth";
import { searchAssuranceCommands, type AssuranceCommandResult } from "../../services/assuranceCockpit";
import "./qms-command-palette.css";

const QUICK_ACTIONS = [
  { id: "open-assurance", title: "Open Audit Assurance", subtitle: "Live assurance cockpit", path: "audits/dashboard" },
  { id: "schedule-audit", title: "Open Audit Planner", subtitle: "Commit programme work to an exact date and team", path: "audits/plan" },
  { id: "open-programme", title: "Open Audit Programme", subtitle: "Coverage, readiness and surveillance requirements", path: "audits/program" },
  { id: "open-findings", title: "Open Findings Register", subtitle: "Findings and corrective-action closeout", path: "audits/register?tab=findings" },
  { id: "open-evidence", title: "Open Evidence Vault", subtitle: "Retained assurance evidence", path: "evidence-vault/search" },
] as const;

function activeAmoCode(pathname: string): string | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)/i);
  if (match?.[1]) return decodeURIComponent(match[1]);
  return getContext().amoCode || null;
}

const QmsCommandPalette: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const requestRef = useRef(0);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AssuranceCommandResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [sourceMessage, setSourceMessage] = useState<string | null>(null);
  const actorView = new URLSearchParams(location.search).get("view") === "mine" ? "mine" : "global";
  const amoCode = activeAmoCode(location.pathname);
  const qualityBase = amoCode ? `/maintenance/${encodeURIComponent(amoCode)}/quality/` : null;

  const quickResults = useMemo<AssuranceCommandResult[]>(() => {
    if (!qualityBase) return [];
    return QUICK_ACTIONS.map((item) => ({
      kind: "action",
      id: item.id,
      title: item.title,
      subtitle: item.subtitle,
      path: `${qualityBase}${item.path}`,
      status: null,
      reference: null,
    }));
  }, [qualityBase]);

  const visibleResults = query.trim().length >= 2 ? results : quickResults;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (!amoCode) return;
        setOpen(true);
        window.requestAnimationFrame(() => inputRef.current?.focus());
        return;
      }
      if (!open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, Math.max(0, visibleResults.length - 1)));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (event.key === "Enter" && visibleResults[activeIndex]) {
        event.preventDefault();
        navigate(visibleResults[activeIndex].path);
        setOpen(false);
        setQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, amoCode, navigate, open, visibleResults]);

  useEffect(() => {
    if (!open || !amoCode) return;
    const clean = query.trim();
    const requestId = ++requestRef.current;
    setActiveIndex(0);
    if (clean.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setSearching(true);
      void searchAssuranceCommands(amoCode, clean, 20, actorView)
        .then((response) => {
          if (requestId === requestRef.current) {
            setResults(response.items || []);
            setSourceMessage(response.warnings?.length ? "Some search sources are unavailable; results are incomplete." : null);
          }
        })
        .catch(() => {
          if (requestId === requestRef.current) { setResults([]); setSourceMessage("Search unavailable. Retry when the connection is restored."); }
        })
        .finally(() => {
          if (requestId === requestRef.current) setSearching(false);
        });
    }, 180);
    return () => window.clearTimeout(timer);
  }, [amoCode, actorView, open, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setActiveIndex(0);
    }
  }, [open]);

  if (!amoCode || !open) return null;

  const select = (result: AssuranceCommandResult) => {
    navigate(result.path);
    setOpen(false);
  };

  return (
    <div className="qms-command-palette" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setOpen(false);
    }}>
      <section className="qms-command-palette__dialog" role="dialog" aria-modal="true" aria-label="QMS command palette">
        {sourceMessage ? <p role="status">{sourceMessage}</p> : null}
        <header className="qms-command-palette__search-row">
          <Search size={19} aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search audits, CARs, controlled documents, clauses or actions…"
            aria-label="Search QMS"
            autoComplete="off"
          />
          <kbd>{navigator.platform?.toLowerCase().includes("mac") ? "⌘ K" : "Ctrl K"}</kbd>
          <button type="button" onClick={() => setOpen(false)} aria-label="Close command palette"><X size={17} /></button>
        </header>

        <div className="qms-command-palette__meta">
          <span><Command size={14} aria-hidden /> {query.trim().length >= 2 ? "Search results" : "Quick actions"}</span>
          <small>{searching ? "Searching…" : `${visibleResults.length} result${visibleResults.length === 1 ? "" : "s"}`}</small>
        </div>

        <div className="qms-command-palette__results" role="listbox" aria-label="Command results">
          {visibleResults.map((result, index) => (
            <button
              key={`${result.kind}-${result.id}`}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? "is-active" : undefined}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => select(result)}
            >
              <span className="qms-command-palette__kind">{result.kind.replaceAll("_", " ")}</span>
              <span className="qms-command-palette__copy">
                <strong>{result.reference ? `${result.reference} · ${result.title}` : result.title}</strong>
                <small>{result.subtitle || "Open record"}</small>
              </span>
              {result.status ? <span className="qms-command-palette__status">{result.status.replaceAll("_", " ")}</span> : null}
            </button>
          ))}
          {!searching && query.trim().length >= 2 && visibleResults.length === 0 ? (
            <div className="qms-command-palette__empty">
              <strong>No matching QMS records</strong>
              <span>Try an audit reference, CAR number, document code, clause or action.</span>
            </div>
          ) : null}
        </div>

        <footer className="qms-command-palette__footer">
          <span>↑ ↓ Navigate</span><span>Enter Open</span><span>Esc Close</span>
        </footer>
      </section>
    </div>
  );
};

export default QmsCommandPalette;

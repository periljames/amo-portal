import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Command, Search, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { QMS_COMMAND_PALETTE_OPEN, openQmsCommandPalette } from "../../services/qmsCommandPalette";
import { qmsModulePath, QMS_ROUTE_REGISTRY } from "../../pages/qms/routes/qmsRouteRegistry";
import { buildPreservedQmsQuery, withQmsQuery } from "../../pages/qms/routes/qmsQueryState";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { getContext } from "../../services/auth";
import { searchAssuranceCommands, type AssuranceCommandResult } from "../../services/assuranceCockpit";
import "./qms-command-palette.css";

const QUICK_ACTIONS = [
  { id: "open-assurance", title: "Open Audit Assurance", subtitle: "Live assurance cockpit", path: "audits/dashboard" },
  { id: "schedule-audit", title: "Open Audit Planner", subtitle: "Commit programme work to an exact date and team", path: "audits/plan" },
  { id: "open-programme", title: "Open Audit Programme", subtitle: "Coverage, readiness and surveillance requirements", path: "audits/program" },
  { id: "open-findings", title: "Open Findings Register", subtitle: "Findings and corrective-action closeout", path: "audits/register" },
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
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const listId = useId();
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
  // The Planner has its own Ctrl/Cmd+K command surface and plain-key shortcuts.
  // Let that route own the keyboard accelerator so a second modal cannot remain
  // underneath it and capture the next planner shortcut after Escape.
  const plannerOwnsCommandShortcut = /\/quality\/calendar(?:\/|$)/i.test(location.pathname);

  const quickResults = useMemo<AssuranceCommandResult[]>(() => {
    if (!amoCode) return [];
    return QUICK_ACTIONS.filter((item) => hasQmsRolePermission(QMS_ROUTE_REGISTRY.find((module) => module.id === item.path.split("/")[0])?.permission || "qms.dashboard.view")).map((item) => ({
      kind: "action",
      id: item.id,
      title: item.title,
      subtitle: item.subtitle,
      path: withQmsQuery(qmsModulePath(amoCode, item.path.split("/")[0], item.path.split("/")[1]), buildPreservedQmsQuery(new URLSearchParams(location.search), {}, item.path.startsWith("audits/") ? ["view", "period"] : [])),
      status: null,
      reference: null,
    }));
  }, [amoCode, location.search]);

  const visibleResults = query.trim().length >= 2 ? results : quickResults;

  const close = useCallback(() => setOpen(false), []);
  const show = useCallback(() => {
    if (!amoCode || open) return;
    triggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpen(true);
  }, [amoCode, open]);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        if (plannerOwnsCommandShortcut) return;
        event.preventDefault();
        openQmsCommandPalette();
      }
    };
    window.addEventListener(QMS_COMMAND_PALETTE_OPEN, show);
    window.addEventListener("keydown", shortcut);
    return () => { window.removeEventListener(QMS_COMMAND_PALETTE_OPEN, show); window.removeEventListener("keydown", shortcut); };
  }, [plannerOwnsCommandShortcut, show]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog) return;
    // Native modal behavior is supported by ModalTopLayerGuard and makes the
    // rest of the document inert, traps focus, and handles nested top layers.
    dialog.showModal();
    inputRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      if (triggerRef.current?.isConnected) triggerRef.current.focus();
    };
  }, [open]);

  useEffect(() => {
    dialogRef.current?.querySelector(`#${CSS.escape(listId)}-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, listId]);

  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      setActiveIndex((index) => event.key === "Home" ? 0 : event.key === "End" ? Math.max(0, visibleResults.length - 1) : Math.max(0, Math.min(visibleResults.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
    } else if (event.key === "Enter" && visibleResults[activeIndex]) {
      event.preventDefault();
      navigate(visibleResults[activeIndex].path);
      close();
    }
  };

  useEffect(() => {
    if (!open || !amoCode) return;
    const clean = query.trim();
    const requestId = ++requestRef.current;
    setActiveIndex(0);
    setSourceMessage(null);
    setResults([]);
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
    return () => { window.clearTimeout(timer); requestRef.current += 1; };
  }, [amoCode, actorView, open, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSourceMessage(null);
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
    <dialog ref={dialogRef} className="qms-command-palette" aria-modal="true" aria-label="QMS command palette"
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
      <section className="qms-command-palette__dialog">
        {sourceMessage ? <p role="status">{sourceMessage}</p> : null}
        <header className="qms-command-palette__search-row">
          <Search size={19} aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search audits, CARs, controlled documents, clauses or actions…"
            aria-label="Search QMS"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={visibleResults[activeIndex] ? `${listId}-option-${activeIndex}` : undefined}
            onKeyDown={onSearchKeyDown}
            autoComplete="off"
          />
          <kbd>{navigator.platform?.toLowerCase().includes("mac") ? "⌘ K" : "Ctrl K"}</kbd>
          <button type="button" onClick={() => setOpen(false)} aria-label="Close command palette"><X size={17} /></button>
        </header>

        <div className="qms-command-palette__meta">
          <span><Command size={14} aria-hidden /> {query.trim().length >= 2 ? "Search results" : "Quick actions"}</span>
          <small>{searching ? "Searching…" : `${visibleResults.length} result${visibleResults.length === 1 ? "" : "s"}`}</small>
        </div>

        <div id={listId} className="qms-command-palette__results" role="listbox" aria-busy={searching} aria-label="Command results">
          {visibleResults.map((result, index) => (
            <button
              key={`${result.kind}-${result.id}`}
              type="button"
              role="option"
              id={`${listId}-option-${index}`}
              tabIndex={-1}
              onMouseDown={(event) => event.preventDefault()}
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
    </dialog>
  );
};

export default QmsCommandPalette;

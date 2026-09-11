import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { CalendarPlus, ClipboardPlus, FileSearch, Search, ShieldCheck, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { searchQmsCommands, type QmsCommandSearchItem, type QmsCommandSearchView } from "../../services/qmsCommandSearch";
import "../../styles/qms-command-palette.css";

type PaletteAction = {
  id: string;
  title: string;
  subtitle: string;
  path: string;
  keywords: string;
  icon: React.ComponentType<{ size?: number }>;
};

function qualityContext(pathname: string): { amoCode: string } | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/|$)/i);
  return match ? { amoCode: decodeURIComponent(match[1]) } : null;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

const QualityCommandPalette: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const context = useMemo(() => qualityContext(location.pathname), [location.pathname]);
  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const view: QmsCommandSearchView = searchParams.get("view") === "mine" ? "mine" : "global";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const actions = useMemo<PaletteAction[]>(() => {
    if (!context) return [];
    const base = `/maintenance/${encodeURIComponent(context.amoCode)}/quality`;
    return [
      { id: "schedule-audit", title: "Schedule audit", subtitle: "Open the Quality Planner and create a governed audit commitment", path: `${base}/calendar/week?intent=create-audit`, keywords: "create schedule audit planner new", icon: CalendarPlus },
      { id: "raise-car", title: "Create corrective action", subtitle: "Open the CAR workspace to raise or manage corrective action", path: `${base}/cars?intent=create`, keywords: "create raise car capa corrective action", icon: ClipboardPlus },
      { id: "programme", title: "Open Audit Programme", subtitle: "Manage baseline coverage, readiness and surveillance requirements", path: `${base}/audits/program`, keywords: "programme coverage readiness baseline audit", icon: ShieldCheck },
      { id: "register", title: "Open Findings & CAR Register", subtitle: "Inspect findings, linked CARs and closure state", path: `${base}/audits/register`, keywords: "finding register car closeout", icon: FileSearch },
    ];
  }, [context]);

  const cleanQuery = query.trim();
  const normalized = normalize(cleanQuery);
  const matchedActions = useMemo(() => {
    if (!normalized) return actions;
    return actions.filter((action) => `${action.title} ${action.subtitle} ${action.keywords}`.toLowerCase().includes(normalized));
  }, [actions, normalized]);

  const searchQuery = useQuery({
    queryKey: ["qms-command-search", context?.amoCode, cleanQuery, view],
    queryFn: ({ signal }) => searchQmsCommands(context!.amoCode, cleanQuery, view, signal),
    enabled: open && Boolean(context) && cleanQuery.length >= 2,
    staleTime: 2_000,
  });

  const recordResults = searchQuery.data?.items ?? [];
  const combined = useMemo(
    () => [
      ...matchedActions.map((action) => ({ type: "action" as const, action })),
      ...recordResults.map((item) => ({ type: "record" as const, item })),
    ],
    [matchedActions, recordResults],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
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
        setActiveIndex((index) => Math.min(index + 1, Math.max(0, combined.length - 1)));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(index - 1, 0));
        return;
      }
      if (event.key === "Enter" && combined[activeIndex]) {
        event.preventDefault();
        const choice = combined[activeIndex];
        navigate(choice.type === "action" ? choice.action.path : choice.item.path);
        setOpen(false);
        setQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, combined, navigate, open]);

  useEffect(() => {
    if (!open) return;
    setActiveIndex(0);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [cleanQuery, recordResults.length, matchedActions.length]);

  if (!context || !open) return null;

  const choosePath = (path: string) => {
    navigate(path);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="qms-command-palette" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section className="qms-command-palette__dialog" role="dialog" aria-modal="true" aria-label="Quality command palette">
        <header className="qms-command-palette__search">
          <Search size={20} aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search audits, findings, CARs or type a command…"
            aria-label="Search Quality workspace"
            autoComplete="off"
          />
          <span>{view === "mine" ? "My Work" : "Global"}</span>
          <kbd>Esc</kbd>
          <button type="button" onClick={() => setOpen(false)} aria-label="Close command palette"><X size={17} /></button>
        </header>

        <div className="qms-command-palette__results" role="listbox" aria-label="Command results">
          {!cleanQuery ? <p className="qms-command-palette__hint">Type a reference such as QAR/MO/26/003, a requirement, or an action such as “schedule audit”.</p> : null}
          {searchQuery.isError ? <p className="qms-command-palette__error">Live record search is unavailable. Navigation commands remain available.</p> : null}
          {combined.map((choice, index) => {
            const active = index === activeIndex;
            if (choice.type === "action") {
              const Icon = choice.action.icon;
              return (
                <button
                  key={choice.action.id}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={active ? "is-active" : undefined}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => choosePath(choice.action.path)}
                >
                  <Icon size={18} aria-hidden />
                  <span><strong>{choice.action.title}</strong><small>{choice.action.subtitle}</small></span>
                  <em>Action</em>
                </button>
              );
            }
            const item: QmsCommandSearchItem = choice.item;
            return (
              <button
                key={`${item.kind}-${item.id}`}
                type="button"
                role="option"
                aria-selected={active}
                className={active ? "is-active" : undefined}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choosePath(item.path)}
              >
                <FileSearch size={18} aria-hidden />
                <span><strong>{item.reference ? `${item.reference} · ` : ""}{item.title}</strong><small>{item.subtitle || item.kind}</small></span>
                <em>{item.status || item.kind}</em>
              </button>
            );
          })}
          {!searchQuery.isFetching && cleanQuery.length >= 2 && combined.length === 0 ? (
            <div className="qms-command-palette__empty"><strong>No matching Quality records</strong><span>Try a reference, title, requirement or another command.</span></div>
          ) : null}
        </div>

        <footer className="qms-command-palette__footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>K</kbd> toggle</span>
          {searchQuery.isFetching ? <strong>Searching…</strong> : null}
        </footer>
      </section>
    </div>
  );
};

export default QualityCommandPalette;

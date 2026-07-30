from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor missing in {path}: {old[:140]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, block: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if marker in text:
        return
    file.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Workforce readiness: future SUSPENDED records conflict with contract creation,
# so they must be surfaced for editing just like ACTIVE/ONBOARDING future rows.
# ---------------------------------------------------------------------------
replace_once(
    "backend/amodb/apps/workforce/hr_service.py",
    """        models.EmploymentContract.employment_status.in_([\n            models.EmploymentStatus.ACTIVE,\n            models.EmploymentStatus.ONBOARDING,\n        ]),""",
    """        models.EmploymentContract.employment_status.in_([\n            models.EmploymentStatus.ACTIVE,\n            models.EmploymentStatus.ONBOARDING,\n            models.EmploymentStatus.SUSPENDED,\n        ]),""",
)
replace_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    """    assert \"effective_from > on_date\" in lookup_source\n    assert \"effective_from.asc()\" in lookup_source""",
    """    assert \"effective_from > on_date\" in lookup_source\n    assert \"EmploymentStatus.SUSPENDED\" in lookup_source\n    assert \"effective_from.asc()\" in lookup_source""",
)


# ---------------------------------------------------------------------------
# Documentation assistant: conventional right drawer with accessible edge resize,
# persisted width, mode-aware iconography, independent scrolling and reduced motion.
# ---------------------------------------------------------------------------
panel_path = ROOT / "frontend/src/pages/manuals/DocumentationAssistantPanel.tsx"
panel = panel_path.read_text(encoding="utf-8")

old_react_import = 'import { useMemo, useState, type FormEvent } from "react";'
new_react_import = '''import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";'''
if old_react_import not in panel:
    raise RuntimeError("Documentation assistant React import anchor missing")
panel = panel.replace(old_react_import, new_react_import, 1)

icon_anchor = """  FileText,\n  Navigation,"""
if icon_anchor not in panel:
    raise RuntimeError("Documentation assistant icon anchor missing")
panel = panel.replace(
    icon_anchor,
    """  FileText,\n  GripVertical,\n  LoaderCircle,\n  Navigation,""",
    1,
)

mode_anchor = '''const MODE_OPTIONS: Array<{ value: DocumentationAssistMode; label: string; icon: typeof Search }> = [
  { value: "ASSIST", label: "Ask", icon: Sparkles },
  { value: "SEARCH", label: "Search", icon: Search },
  { value: "NAVIGATE", label: "Navigate", icon: Navigation },
];'''
if mode_anchor not in panel:
    raise RuntimeError("Documentation assistant mode anchor missing")
panel = panel.replace(
    mode_anchor,
    mode_anchor
    + '''

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
    const stored = Number(window.localStorage.getItem(FLOATING_WIDTH_STORAGE_KEY));
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
''',
    1,
)

state_anchor = '''  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");'''
if state_anchor not in panel:
    raise RuntimeError("Documentation assistant state anchor missing")
panel = panel.replace(
    state_anchor,
    state_anchor
    + '''
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

  const ActiveModeIcon = MODE_OPTIONS.find((option) => option.value === mode)?.icon || Bot;''',
    1,
)

launcher_old = '''    return <button type="button" className="documentation-assistant-launcher" onClick={() => setOpen(true)}>
      <Bot size={18} />
      <span>Assisted search</span>
    </button>;'''
launcher_new = '''    return <button type="button" className="documentation-assistant-launcher" onClick={() => setOpen(true)} aria-expanded="false">
      <span className="documentation-assistant-launcher__icon" aria-hidden="true"><Bot size={18} /><Sparkles size={11} /></span>
      <span>Assisted search</span>
    </button>;'''
if launcher_old not in panel:
    raise RuntimeError("Documentation assistant launcher anchor missing")
panel = panel.replace(launcher_old, launcher_new, 1)

aside_old = '''  return <aside className={`documentation-assistant ${embedded ? "is-embedded" : "is-floating"}`} aria-label={title}>
    <header className="documentation-assistant__header">'''
aside_new = '''  const floatingStyle = !embedded
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
    ><GripVertical size={16} /></div> : null}
    <header className="documentation-assistant__header">'''
if aside_old not in panel:
    raise RuntimeError("Documentation assistant aside anchor missing")
panel = panel.replace(aside_old, aside_new, 1)

header_icon_old = '<span className="documentation-assistant__eyebrow"><Bot size={14} /> Controlled-document assistance</span>'
header_icon_new = '<span className="documentation-assistant__eyebrow">{busy ? <LoaderCircle className="is-spinning" size={14} /> : <ActiveModeIcon size={14} />} Controlled-document assistance</span>'
if header_icon_old not in panel:
    raise RuntimeError("Documentation assistant header icon anchor missing")
panel = panel.replace(header_icon_old, header_icon_new, 1)

body_open_anchor = '''    </header>

    <div className="documentation-assistant__modes"'''
if body_open_anchor not in panel:
    raise RuntimeError("Documentation assistant body-open anchor missing")
panel = panel.replace(
    body_open_anchor,
    '''    </header>

    <div className="documentation-assistant__body">
    <div className="documentation-assistant__modes"''',
    1,
)

body_close_anchor = '''    </div> : null}
  </aside>;'''
if body_close_anchor not in panel:
    raise RuntimeError("Documentation assistant body-close anchor missing")
panel = panel.replace(
    body_close_anchor,
    '''    </div> : null}
    </div>
  </aside>;''',
    1,
)
panel_path.write_text(panel, encoding="utf-8")

append_once(
    "frontend/src/pages/manuals/documentationAssistantPanel.css",
    "/* PR377 final assistant drawer refinement */",
    r'''
/* PR377 final assistant drawer refinement */
.documentation-assistant {
  --assistant-muted: var(--text-secondary, #475569);
  font-size: 1rem;
}

.documentation-assistant.is-floating {
  width: min(var(--documentation-assistant-width, 460px), calc(100vw - 56px));
  min-width: min(360px, 100vw);
  max-width: min(760px, calc(100vw - 56px));
  overflow: hidden;
  transition: width 180ms ease, box-shadow 180ms ease;
}

.documentation-assistant.is-floating[data-resizing="true"] {
  transition: none;
  box-shadow: -24px 0 60px rgb(15 23 42 / 24%);
}

.documentation-assistant__body {
  min-height: 0;
}

.documentation-assistant.is-floating .documentation-assistant__body {
  flex: 1;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.documentation-assistant__resize-handle {
  position: absolute;
  z-index: 8;
  top: 0;
  bottom: 0;
  left: -7px;
  display: grid;
  place-items: center;
  width: 14px;
  color: var(--assistant-muted);
  cursor: col-resize;
  outline: 0;
  touch-action: none;
}

.documentation-assistant__resize-handle::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 6px;
  width: 2px;
  background: transparent;
  content: "";
  transition: background 140ms ease, width 140ms ease;
}

.documentation-assistant__resize-handle svg {
  position: relative;
  z-index: 1;
  box-sizing: content-box;
  padding: 2px;
  border: 1px solid var(--assistant-border);
  border-radius: 999px;
  background: var(--surface-raised, #fff);
  opacity: 0;
  transition: opacity 140ms ease, transform 140ms ease;
}

.documentation-assistant__resize-handle:hover::before,
.documentation-assistant__resize-handle:focus-visible::before,
.documentation-assistant[data-resizing="true"] .documentation-assistant__resize-handle::before {
  width: 3px;
  background: var(--color-primary, #2563eb);
}

.documentation-assistant__resize-handle:hover svg,
.documentation-assistant__resize-handle:focus-visible svg,
.documentation-assistant[data-resizing="true"] .documentation-assistant__resize-handle svg {
  opacity: 1;
  transform: scale(1.06);
}

.documentation-assistant-launcher__icon {
  position: relative;
  display: grid;
  place-items: center;
}

.documentation-assistant-launcher__icon > svg:first-child {
  transition: transform 160ms ease;
}

.documentation-assistant-launcher__icon svg:last-child {
  position: absolute;
  top: -6px;
  right: -7px;
  color: var(--color-primary, #2563eb);
  animation: documentation-assistant-spark 2.4s ease-in-out infinite;
}

.documentation-assistant-launcher:hover .documentation-assistant-launcher__icon > svg:first-child {
  transform: translateY(-1px) rotate(-4deg);
}

.documentation-assistant__eyebrow .is-spinning {
  animation: documentation-assistant-spin .8s linear infinite;
}

.documentation-assistant__header h2 { font-size: 1.14rem; }
.documentation-assistant__header p { font-size: .84rem; line-height: 1.45; }
.documentation-assistant__eyebrow,
.documentation-assistant__answer-meta,
.documentation-assistant__source-meta { font-size: .75rem; }
.documentation-assistant__modes button { min-height: 38px; font-size: .84rem; }
.documentation-assistant__query > label { font-size: .8rem; }
.documentation-assistant__query input { min-height: 44px; font-size: .92rem; }
.documentation-assistant__query button { min-width: 84px; font-size: .86rem; }
.documentation-assistant__suggestions button { font-size: .78rem; }
.documentation-assistant__answer > p { font-size: .94rem; line-height: 1.62; }
.documentation-assistant__source-title,
.documentation-assistant__source-heading { font-size: .85rem; }
.documentation-assistant__source-snippet { font-size: .81rem; line-height: 1.5; }
.documentation-assistant__authority-note { font-size: .78rem; }

body.documentation-assistant-is-resizing,
body.documentation-assistant-is-resizing * {
  cursor: col-resize !important;
  user-select: none !important;
}

@keyframes documentation-assistant-spin { to { transform: rotate(360deg); } }
@keyframes documentation-assistant-spark {
  0%, 100% { opacity: .55; transform: scale(.88) rotate(0deg); }
  50% { opacity: 1; transform: scale(1.1) rotate(12deg); }
}

@media (max-width: 900px) {
  .documentation-assistant.is-floating {
    top: 0;
    width: 100%;
    min-width: 0;
    max-width: 100%;
  }

  .documentation-assistant__resize-handle { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .documentation-assistant.is-floating,
  .documentation-assistant-launcher__icon svg,
  .documentation-assistant__resize-handle::before,
  .documentation-assistant__resize-handle svg {
    animation: none !important;
    transition: none !important;
  }
}
''',
)


# ---------------------------------------------------------------------------
# Workforce UI: bounded desktop canvas, stronger light-theme contrast, readable
# operational type and responsive register cards instead of horizontal overflow.
# ---------------------------------------------------------------------------
append_once(
    "frontend/src/pages/rostering/components/workforce-hr-workspace.css",
    "/* PR377 final Workforce readability refinement */",
    r'''
/* PR377 final Workforce readability refinement */
.hr-workspace {
  width: min(100%, 1480px);
  margin-inline: auto;
  gap: 14px;
  color: var(--text-primary, var(--text-strong, #172033));
}

.hr-workspace__nav {
  position: sticky;
  z-index: 6;
  top: 0;
  padding: 6px;
  background: color-mix(in srgb, var(--surface-raised, #fff) 96%, transparent);
  box-shadow: 0 7px 22px rgb(15 23 42 / 7%);
  backdrop-filter: blur(14px);
}

.hr-workspace__nav button {
  min-height: 38px;
  padding-inline: 14px;
  color: var(--text-secondary, #475569);
  font-size: .87rem;
}

.hr-workspace .wr-panel {
  min-width: 0;
  padding: clamp(14px, 1vw, 18px);
}

.hr-workspace .wr-section-heading h2 {
  color: var(--text-primary, #172033);
  font-size: clamp(1rem, .92vw, 1.16rem);
}

.hr-workspace .wr-section-heading p {
  max-width: 76ch;
  color: var(--text-secondary, #475569);
  font-size: .84rem;
  line-height: 1.5;
}

.hr-metrics {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.hr-metrics article,
.hr-mini-grid article {
  padding: 14px;
  background: var(--surface-raised, #fff);
}

.hr-metrics span,
.hr-metrics small,
.hr-mini-grid span {
  color: var(--text-secondary, #475569);
  font-size: .78rem;
  line-height: 1.4;
}

.hr-metrics strong,
.hr-mini-grid strong {
  font-size: clamp(1.4rem, 1.25vw, 1.7rem);
}

.hr-overview-grid {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  align-items: start;
  gap: 14px;
}

.hr-action-list strong,
.hr-people-table strong,
.hr-approval-list strong,
.hr-pattern-list strong {
  color: var(--text-primary, #172033);
  font-size: .86rem;
}

.hr-action-list p,
.hr-people-table span,
.hr-people-table small,
.hr-approval-list span,
.hr-pattern-list span,
.hr-readiness-list span,
.hr-ownership p,
.hr-person-source {
  color: var(--text-secondary, #475569);
  font-size: .79rem;
  line-height: 1.5;
}

.hr-action-list a,
.hr-action-link { font-size: .8rem; }

.hr-search {
  min-width: min(320px, 100%);
  min-height: 40px;
  background: var(--surface-standard, var(--surface-solid, #fff));
}

.hr-search input {
  color: var(--text-primary, #172033);
  font-size: .84rem;
}

.hr-people-table {
  overflow-x: auto;
  scrollbar-gutter: stable;
}

.hr-people-table header,
.hr-people-table article {
  grid-template-columns: minmax(180px, 1.1fr) minmax(132px, .75fr) minmax(72px, .36fr) minmax(145px, .82fr) minmax(180px, 1fr) minmax(116px, auto);
  min-width: 820px;
}

.hr-people-table header {
  color: var(--text-secondary, #475569);
  font-size: .72rem;
}

.hr-people-table article { min-height: 64px; }

.hr-decision { width: min(620px, calc(100vw - 32px)); }
.hr-decision h3 { font-size: 1.06rem; }
.hr-decision p { color: var(--text-secondary, #475569); font-size: .82rem; line-height: 1.5; }
.hr-decision label,
.hr-assignment-grid label,
.hr-contract-grid label { color: var(--text-secondary, #475569); font-size: .78rem; }
.hr-decision textarea,
.hr-assignment-grid input,
.hr-assignment-grid select,
.hr-contract-grid input,
.hr-contract-grid select { min-height: 42px; font-size: .86rem; }

@media (max-width: 1180px) {
  .hr-overview-grid { grid-template-columns: 1fr; }
  .hr-people-table { overflow: visible; }
  .hr-people-table header { display: none; }
  .hr-people-table article {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    min-width: 0;
    margin-bottom: 9px;
    padding: 12px;
    border: 1px solid var(--border-subtle, rgba(100, 116, 139, .22));
    border-radius: 11px;
    background: var(--surface-raised, #fff);
  }
  .hr-people-table article > :nth-child(5) { grid-column: 1 / -1; }
  .hr-people-table article > :nth-child(6) { justify-self: start; }
}

@media (max-width: 640px) {
  .hr-workspace { gap: 10px; }
  .hr-workspace__nav button { font-size: .82rem; }
  .hr-people-table article { grid-template-columns: 1fr; }
  .hr-people-table article > :nth-child(5),
  .hr-people-table article > :nth-child(6) { grid-column: 1; }
}
''',
)


# Source-level contracts run inside the existing Rostering Vitest sweep.
test_path = ROOT / "frontend/src/pages/rostering/documentationAssistantUx.test.ts"
test_path.write_text(
    '''import { readFileSync } from "node:fs";\nimport { describe, expect, it } from "vitest";\n\nconst assistant = readFileSync(new URL("../manuals/DocumentationAssistantPanel.tsx", import.meta.url), "utf8");\nconst assistantCss = readFileSync(new URL("../manuals/documentationAssistantPanel.css", import.meta.url), "utf8");\nconst workforceCss = readFileSync(new URL("./components/workforce-hr-workspace.css", import.meta.url), "utf8");\n\ndescribe("documentation assistant interaction contract", () => {\n  it("supports persisted pointer and keyboard resizing", () => {\n    expect(assistant).toContain("amo_documentation_assistant_width");\n    expect(assistant).toContain("onPointerDown={startResize}");\n    expect(assistant).toContain("onKeyDown={resizeWithKeyboard}");\n    expect(assistant).toContain("onDoubleClick={resetWidth}");\n    expect(assistant).toContain("role=\\\"separator\\\"");\n    expect(assistantCss).toContain("--documentation-assistant-width");\n    expect(assistantCss).toContain("cursor: col-resize");\n    expect(assistantCss).toContain("prefers-reduced-motion");\n  });\n\n  it("keeps the Workforce register bounded, legible and responsive", () => {\n    expect(workforceCss).toContain("width: min(100%, 1480px)");\n    expect(workforceCss).toContain("var(--text-secondary, #475569)");\n    expect(workforceCss).toContain("@media (max-width: 1180px)");\n    expect(workforceCss).toContain("grid-template-columns: repeat(2, minmax(0, 1fr))");\n  });\n});\n''',
    encoding="utf-8",
)

print("PR377 backend and UX correction applied")

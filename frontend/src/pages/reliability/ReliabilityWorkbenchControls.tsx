import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import { spreadsheetSafeText } from "./ReliabilityWorkbenchUtils";

export type WorkbenchDensity = "compact" | "comfortable";

type Preferences = {
  density: WorkbenchDensity;
  wrapCells: boolean;
  guidedMode: boolean;
};

type ContextValue = Preferences & {
  setDensity: (value: WorkbenchDensity) => void;
  setWrapCells: (value: boolean) => void;
  setGuidedMode: (value: boolean) => void;
  reset: () => void;
};

type MenuState = {
  x: number;
  y: number;
  row: HTMLTableRowElement;
  cell: HTMLTableCellElement | null;
  table: HTMLTableElement;
} | null;

const STORAGE_KEY = "amo.reliability.workbench.v2";
const DEFAULTS: Preferences = { density: "compact", wrapCells: false, guidedMode: true };
const WorkbenchContext = createContext<ContextValue | null>(null);

function loadPreferences(): Preferences {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") as Partial<Preferences>;
    return {
      density: parsed.density === "comfortable" ? "comfortable" : "compact",
      wrapCells: Boolean(parsed.wrapCells),
      guidedMode: parsed.guidedMode !== false,
    };
  } catch {
    return DEFAULTS;
  }
}

function rowMatrix(rows: HTMLTableRowElement[]): string[][] {
  return rows.map((row) => Array.from(row.cells)
    .filter((cell) => cell.getAttribute("data-wb-hidden") !== "true")
    .map((cell) => spreadsheetSafeText(cell.innerText.trim()).replaceAll(/\r?\n/g, " ")));
}

function tsv(rows: string[][]): string {
  return rows.map((row) => row.map((value) => value.replaceAll("\t", " ")).join("\t")).join("\n");
}

function csv(rows: string[][]): string {
  return rows.map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(",")).join("\n");
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.readOnly = true;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      return copied;
    } catch {
      return false;
    }
  }
}

function download(filename: string, body: string, type: string): void {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function selectedRows(table: HTMLTableElement): HTMLTableRowElement[] {
  const selected = Array.from(table.querySelectorAll<HTMLTableRowElement>("tbody tr[data-wb-selected='true']"));
  return selected.length ? selected : [];
}

function tableName(table: HTMLTableElement): string {
  const label = table.getAttribute("aria-label") || table.closest("section, .rel-wp__panel")?.querySelector("h2,h3")?.textContent || "reliability-table";
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "reliability-table";
}

export function ReliabilityWorkbenchProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [preferences, setPreferences] = useState<Preferences>(loadPreferences);
  const [menu, setMenu] = useState<MenuState>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences)); } catch { /* preferences are optional */ }
    const root = document.querySelector<HTMLElement>("[data-testid='reliability-workbook-parity']");
    if (root) {
      root.dataset.density = preferences.density;
      root.dataset.wrapCells = String(preferences.wrapCells);
      root.dataset.guidedMode = String(preferences.guidedMode);
    }
  }, [preferences]);

  useEffect(() => {
    const prepare = () => document.querySelectorAll<HTMLTableCellElement>(".rel-wp__table tbody td").forEach((cell) => {
      if (!cell.hasAttribute("tabindex")) cell.tabIndex = 0;
    });
    prepare();
    const observer = new MutationObserver(prepare);
    observer.observe(document.body, { childList: true, subtree: true });

    const onKey = (event: KeyboardEvent) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      const target = event.target as HTMLElement;
      if (target.matches("input, textarea, select") || target.isContentEditable) return;
      const cell = target.closest<HTMLTableCellElement>(".rel-wp__table td");
      const row = cell?.parentElement as HTMLTableRowElement | null;
      const table = cell?.closest<HTMLTableElement>("table");
      if (!cell || !row || !table) return;
      const bodyRows = Array.from(table.tBodies[0]?.rows || []).filter((candidate) => !candidate.classList.contains("rel-wp__detail-row"));
      const rowIndex = bodyRows.indexOf(row);
      let nextRow = rowIndex;
      let nextColumn = cell.cellIndex;
      if (event.key === "ArrowLeft") nextColumn -= 1;
      if (event.key === "ArrowRight") nextColumn += 1;
      if (event.key === "ArrowUp") nextRow -= 1;
      if (event.key === "ArrowDown") nextRow += 1;
      if (event.key === "Home") nextColumn = 0;
      if (event.key === "End") nextColumn = row.cells.length - 1;
      nextRow = Math.max(0, Math.min(bodyRows.length - 1, nextRow));
      const destinationRow = bodyRows[nextRow];
      const destination = destinationRow?.cells[Math.max(0, Math.min(destinationRow.cells.length - 1, nextColumn))] as HTMLTableCellElement | undefined;
      if (!destination || destination === cell) return;
      event.preventDefault();
      destination.focus();
    };

    const onContext = (event: MouseEvent) => {
      const cell = (event.target as HTMLElement).closest<HTMLTableCellElement>(".rel-wp__table tbody td");
      const row = cell?.parentElement as HTMLTableRowElement | null;
      const table = cell?.closest<HTMLTableElement>("table");
      if (!cell || !row || !table) return;
      event.preventDefault();
      if (row.dataset.wbSelected !== "true") {
        table.querySelectorAll<HTMLTableRowElement>("tbody tr[data-wb-selected='true']").forEach((selected) => delete selected.dataset.wbSelected);
        row.dataset.wbSelected = "true";
      }
      setMenu({ x: event.clientX, y: event.clientY, row, cell, table });
    };

    const onClick = (event: MouseEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const row = (event.target as HTMLElement).closest<HTMLTableRowElement>(".rel-wp__table tbody tr");
      if (!row || (event.target as HTMLElement).closest("button,a,input,select,textarea")) return;
      row.dataset.wbSelected = row.dataset.wbSelected === "true" ? "false" : "true";
    };

    document.addEventListener("keydown", onKey);
    document.addEventListener("contextmenu", onContext);
    document.addEventListener("click", onClick);
    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("contextmenu", onContext);
      document.removeEventListener("click", onClick);
    };
  }, []);

  useEffect(() => {
    if (!menu) return;
    const close = (event: Event) => {
      if ((event.target as HTMLElement).closest(".rel-wp__context-menu")) return;
      setMenu(null);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(null); };
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", escape);
    };
  }, [menu]);

  const value = useMemo<ContextValue>(() => ({
    ...preferences,
    setDensity: (density) => setPreferences((current) => ({ ...current, density })),
    setWrapCells: (wrapCells) => setPreferences((current) => ({ ...current, wrapCells })),
    setGuidedMode: (guidedMode) => setPreferences((current) => ({ ...current, guidedMode })),
    reset: () => setPreferences(DEFAULTS),
  }), [preferences]);

  const actOnRows = async (kind: "copy" | "csv") => {
    if (!menu) return;
    const rows = selectedRows(menu.table);
    const chosen = rows.length ? rows : [menu.row];
    const matrix = rowMatrix(chosen);
    if (kind === "copy") setMessage(await copyText(tsv(matrix)) ? `${chosen.length} row(s) copied.` : "Clipboard access was blocked.");
    else {
      download(`${tableName(menu.table)}.csv`, csv(matrix), "text/csv;charset=utf-8");
      setMessage(`${chosen.length} row(s) exported safely.`);
    }
    setMenu(null);
  };

  const hideColumn = () => {
    if (!menu?.cell) return;
    const index = menu.cell.cellIndex;
    Array.from(menu.table.rows).forEach((row) => row.cells[index]?.setAttribute("data-wb-hidden", "true"));
    setMessage("Column hidden for this view. Use Reset table columns to restore it.");
    setMenu(null);
  };

  const resetColumns = () => {
    if (!menu) return;
    menu.table.querySelectorAll("[data-wb-hidden='true']").forEach((cell) => cell.removeAttribute("data-wb-hidden"));
    setMessage("All table columns restored.");
    setMenu(null);
  };

  return <WorkbenchContext.Provider value={value}>
    {children}
    {message && <div className="rel-wp__workbench-toast" role="status">{message}<button type="button" onClick={() => setMessage("")}>Dismiss</button></div>}
    {menu && <div className="rel-wp__context-menu" role="menu" style={{ left: Math.min(menu.x, window.innerWidth - 250), top: Math.min(menu.y, window.innerHeight - 260) }}>
      <button type="button" role="menuitem" onClick={() => void actOnRows("copy")}>Copy selected rows</button>
      <button type="button" role="menuitem" onClick={() => void actOnRows("csv")}>Export selected CSV</button>
      <button type="button" role="menuitem" onClick={hideColumn}>Hide this column</button>
      <button type="button" role="menuitem" onClick={resetColumns}>Reset table columns</button>
      <button type="button" role="menuitem" onClick={() => { menu.table.querySelectorAll("tbody tr[data-wb-selected]").forEach((row) => row.removeAttribute("data-wb-selected")); setMenu(null); }}>Clear selection</button>
    </div>}
  </WorkbenchContext.Provider>;
}

function useReliabilityWorkbench(): ContextValue {
  const value = useContext(WorkbenchContext);
  if (!value) throw new Error("Reliability workbench controls require ReliabilityWorkbenchProvider.");
  return value;
}

export function WorkbenchPreferenceBar(): React.ReactElement {
  const { density, setDensity, wrapCells, setWrapCells, guidedMode, setGuidedMode, reset } = useReliabilityWorkbench();
  return <div className="rel-wp__preference-bar" aria-label="Reliability workbench display preferences">
    <div className="rel-wp__segmented" aria-label="Table density">
      <button type="button" className={density === "compact" ? "is-active" : ""} aria-pressed={density === "compact"} onClick={() => setDensity("compact")}>Compact</button>
      <button type="button" className={density === "comfortable" ? "is-active" : ""} aria-pressed={density === "comfortable"} onClick={() => setDensity("comfortable")}>Comfortable</button>
    </div>
    <label><input type="checkbox" checked={wrapCells} onChange={(event) => setWrapCells(event.target.checked)} />Wrap cells</label>
    <label><input type="checkbox" checked={guidedMode} onChange={(event) => setGuidedMode(event.target.checked)} />Guided mode</label>
    <details><summary>Shortcuts</summary><div className="rel-wp__shortcut-grid"><kbd>↑ ↓ ← →</kbd><span>Move cells</span><kbd>Ctrl/Cmd + click</kbd><span>Select rows</span><kbd>Right click</kbd><span>Row / column actions</span><kbd>Esc</kbd><span>Close menu</span></div></details>
    <button type="button" className="rel-wp__plain-action" onClick={reset}>Reset view</button>
  </div>;
}

import { useEffect } from "react";

const CELL_SELECTOR = ".wr-drop-cell[role='gridcell']";
const INTERACTIVE_SELECTOR = "button, input, select, textarea, a, [contenteditable='true']";

function asCell(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(CELL_SELECTOR) : null;
}

function bindGridInteractions(grid: HTMLElement) {
  let pointerId: number | null = null;
  let startCell: HTMLElement | null = null;
  let lastCell: HTMLElement | null = null;
  let startX = 0;
  let startY = 0;
  let extendFromExisting = false;
  let dragging = false;
  let suppressClick = false;
  let syntheticSelection = false;
  let suppressFocusUntil = 0;

  const dispatchSelection = (cell: HTMLElement, extend: boolean) => {
    // RosterPlannerV2 schedules focus after updating its authoritative range.
    // Suppress the grid's onFocus reset while that scheduled focus settles.
    suppressFocusUntil = performance.now() + 120;
    syntheticSelection = true;
    try {
      cell.dispatchEvent(new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: window,
        shiftKey: extend,
      }));
    } finally {
      syntheticSelection = false;
    }
  };

  const finishDrag = () => {
    pointerId = null;
    startCell = null;
    lastCell = null;
    extendFromExisting = false;
    dragging = false;
    grid.classList.remove("is-sheet-selecting");
    window.setTimeout(() => { suppressClick = false; }, 0);
  };

  const onPointerDown = (event: PointerEvent) => {
    if (event.button !== 0 || pointerId !== null) return;
    const cell = asCell(event.target);
    if (!cell) return;

    const modifierRange = event.shiftKey || event.ctrlKey || event.metaKey;
    const interactive = event.target instanceof Element
      ? event.target.closest(INTERACTIVE_SELECTOR)
      : null;
    if (interactive && !modifierRange) return;

    pointerId = event.pointerId;
    startCell = cell;
    lastCell = cell;
    startX = event.clientX;
    startY = event.clientY;
    extendFromExisting = modifierRange;

    // Native focus occurs before click and the planner's focus handler resets a
    // range to one cell. Prevent that focus only for explicit modifier ranges;
    // the synthetic selection below will let the planner restore focus safely.
    if (modifierRange) event.preventDefault();
  };

  const onPointerMove = (event: PointerEvent) => {
    if (pointerId === null || event.pointerId !== pointerId || !startCell) return;

    if (!dragging) {
      const moved = Math.hypot(event.clientX - startX, event.clientY - startY);
      if (moved < 5) return;
      dragging = true;
      suppressClick = true;
      grid.classList.add("is-sheet-selecting");
      dispatchSelection(startCell, extendFromExisting);
    }

    const underPointer = document.elementFromPoint(event.clientX, event.clientY);
    const cell = asCell(underPointer);
    if (!cell || cell === lastCell || !grid.contains(cell)) return;
    event.preventDefault();
    lastCell = cell;
    dispatchSelection(cell, true);
  };

  const onPointerUp = (event: PointerEvent) => {
    if (pointerId === null || event.pointerId !== pointerId) return;
    finishDrag();
  };

  const onClickCapture = (event: MouseEvent) => {
    const cell = asCell(event.target);
    if (!cell || syntheticSelection) return;

    if (suppressClick) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    // Normalize Shift and Ctrl/Cmd mouse gestures to the same authoritative
    // rectangular range contract. Keyboard Shift+Arrow remains native to the
    // planner. Ctrl/Cmd is intentionally rectangular rather than a second,
    // disconnected state model so bulk fill/copy/paste always matches the UI.
    if (event.shiftKey || event.ctrlKey || event.metaKey) {
      event.preventDefault();
      event.stopImmediatePropagation();
      dispatchSelection(cell, true);
    }
  };

  const onFocusInCapture = (event: FocusEvent) => {
    if (performance.now() >= suppressFocusUntil) return;
    const cell = asCell(event.target);
    if (!cell) return;
    event.stopPropagation();
  };

  grid.addEventListener("pointerdown", onPointerDown, true);
  grid.addEventListener("click", onClickCapture, true);
  grid.addEventListener("focusin", onFocusInCapture, true);
  window.addEventListener("pointermove", onPointerMove, { passive: false });
  window.addEventListener("pointerup", onPointerUp, true);
  window.addEventListener("pointercancel", onPointerUp, true);

  return () => {
    grid.removeEventListener("pointerdown", onPointerDown, true);
    grid.removeEventListener("click", onClickCapture, true);
    grid.removeEventListener("focusin", onFocusInCapture, true);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp, true);
    window.removeEventListener("pointercancel", onPointerUp, true);
    grid.classList.remove("is-sheet-selecting");
  };
}

/**
 * Adds desktop-spreadsheet selection gestures without creating a second roster
 * state model. RosterPlannerV2 remains authoritative for the selected rectangle;
 * this adapter translates pointer drag and Shift/Ctrl/Cmd range gestures into
 * the same click contract already used by keyboard selection and bulk actions.
 */
export function RosterSpreadsheetInteractions() {
  useEffect(() => {
    const workspace = document.querySelector<HTMLElement>(".wr-planner-workspace");
    if (!workspace) return;

    let boundGrid: HTMLElement | null = null;
    let unbindGrid: (() => void) | null = null;

    const bindCurrentGrid = () => {
      const nextGrid = workspace.querySelector<HTMLElement>(".wr-roster-grid--month");
      if (nextGrid === boundGrid) return;
      unbindGrid?.();
      boundGrid = nextGrid;
      unbindGrid = nextGrid ? bindGridInteractions(nextGrid) : null;
    };

    bindCurrentGrid();
    const observer = new MutationObserver(bindCurrentGrid);
    observer.observe(workspace, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      unbindGrid?.();
    };
  }, []);

  return null;
}

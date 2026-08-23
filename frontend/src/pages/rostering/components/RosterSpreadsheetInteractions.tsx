import { useEffect } from "react";

const CELL_SELECTOR = ".wr-drop-cell[role='gridcell']";
const INTERACTIVE_SELECTOR = "button, input, select, textarea, a, [contenteditable='true']";

function asCell(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(CELL_SELECTOR) : null;
}

function dispatchCellClick(cell: HTMLElement, extend: boolean) {
  cell.dispatchEvent(new MouseEvent("click", {
    bubbles: true,
    cancelable: true,
    view: window,
    shiftKey: extend,
  }));
  cell.focus({ preventScroll: true });
}

/**
 * Adds desktop-spreadsheet selection gestures without creating a second roster
 * state model. RosterPlannerV2 remains authoritative for the selected rectangle;
 * this adapter translates pointer drag and Ctrl/Cmd range gestures into the
 * same click/Shift-click contract already used by keyboard selection and bulk
 * fill operations.
 */
export function RosterSpreadsheetInteractions() {
  useEffect(() => {
    const grid = document.querySelector<HTMLElement>(".wr-planner-workspace .wr-roster-grid--month");
    if (!grid) return;

    let pointerId: number | null = null;
    let startCell: HTMLElement | null = null;
    let lastCell: HTMLElement | null = null;
    let startX = 0;
    let startY = 0;
    let extendFromExisting = false;
    let dragging = false;
    let suppressClick = false;

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
    };

    const onPointerMove = (event: PointerEvent) => {
      if (pointerId === null || event.pointerId !== pointerId || !startCell) return;

      if (!dragging) {
        const moved = Math.hypot(event.clientX - startX, event.clientY - startY);
        if (moved < 5) return;
        dragging = true;
        suppressClick = true;
        grid.classList.add("is-sheet-selecting");
        dispatchCellClick(startCell, extendFromExisting);
      }

      const underPointer = document.elementFromPoint(event.clientX, event.clientY);
      const cell = asCell(underPointer);
      if (!cell || cell === lastCell || !grid.contains(cell)) return;
      event.preventDefault();
      lastCell = cell;
      dispatchCellClick(cell, true);
    };

    const onPointerUp = (event: PointerEvent) => {
      if (pointerId === null || event.pointerId !== pointerId) return;
      finishDrag();
    };

    const onClickCapture = (event: MouseEvent) => {
      const cell = asCell(event.target);
      if (!cell) return;

      if (suppressClick) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }

      // Ctrl/Cmd gives Windows/macOS users the same rectangular range gesture
      // as Shift. The planner's authoritative selection remains one rectangle,
      // so bulk fill/copy/paste always operates on the cells the user sees.
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey) {
        event.preventDefault();
        event.stopImmediatePropagation();
        dispatchCellClick(cell, true);
      }
    };

    grid.addEventListener("pointerdown", onPointerDown, true);
    grid.addEventListener("click", onClickCapture, true);
    window.addEventListener("pointermove", onPointerMove, { passive: false });
    window.addEventListener("pointerup", onPointerUp, true);
    window.addEventListener("pointercancel", onPointerUp, true);

    return () => {
      grid.removeEventListener("pointerdown", onPointerDown, true);
      grid.removeEventListener("click", onClickCapture, true);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp, true);
      window.removeEventListener("pointercancel", onPointerUp, true);
      grid.classList.remove("is-sheet-selecting");
    };
  }, []);

  return null;
}

import React, { useEffect, useMemo, useRef, useState } from "react";
import QmsPlannerPageV2 from "./QmsPlannerPageV2";
import { plannerClockAt } from "./qmsPlannerClock";

const PLANNER_TIMEZONE = "Africa/Nairobi";
const CLOCK_REFRESH_MS = 30_000;
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function isFocusable(element: Element | null): element is HTMLElement {
  if (!(element instanceof HTMLElement) || !element.isConnected) return false;
  if (element.matches(":disabled, [aria-disabled='true']")) return false;
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (!element.getClientRects().length) return false;
  return typeof element.focus === "function";
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(isFocusable);
}

function firstFocusable(...candidates: Array<HTMLElement | null>): HTMLElement | null {
  return candidates.find((candidate) => isFocusable(candidate)) || null;
}

function fallbackTrigger(dialog: HTMLElement): HTMLElement | null {
  if (dialog.matches(".qms-planner-command")) {
    return firstFocusable(document.querySelector<HTMLElement>(".qms-planner-toolbar__search"));
  }
  if (dialog.matches(".qms-planner-create-modal")) {
    return firstFocusable(
      document.querySelector<HTMLElement>(".qms-planner-quick-schedule"),
      document.querySelector<HTMLElement>(".qms-planner-toolbar__controls button:last-child"),
    );
  }
  if (dialog.matches(".qms-planner-shortcuts")) {
    return firstFocusable(
      document.querySelector<HTMLElement>(".qms-planner-shortcut-link"),
      document.querySelector<HTMLElement>(".qms-planner-shortcut-summary button"),
    );
  }
  if (dialog.querySelector("#qms-reschedule-title")) {
    return firstFocusable(
      document.querySelector<HTMLElement>(".qms-planner-inspector__actions button"),
      document.querySelector<HTMLElement>(".qms-planner-event.is-selected"),
    );
  }
  return null;
}

function shortcutTrigger(event: KeyboardEvent): HTMLElement | null {
  const key = event.key.toLowerCase();
  if (event.key === "/" || ((event.ctrlKey || event.metaKey) && key === "k")) {
    return firstFocusable(document.querySelector<HTMLElement>(".qms-planner-toolbar__search"));
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && key === "c") {
    return firstFocusable(
      document.querySelector<HTMLElement>(".qms-planner-quick-schedule"),
      document.querySelector<HTMLElement>(".qms-planner-toolbar__controls button:last-child"),
    );
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key === "?") {
    return firstFocusable(
      document.querySelector<HTMLElement>(".qms-planner-shortcut-link"),
      document.querySelector<HTMLElement>(".qms-planner-shortcut-summary button"),
    );
  }
  return null;
}

function usePlannerDialogFocusManagement(): void {
  const lastOutsideFocusRef = useRef<HTMLElement | null>(null);
  const intendedTriggerRef = useRef<HTMLElement | null>(null);
  const openDialogsRef = useRef(new Map<HTMLElement, HTMLElement | null>());

  useEffect(() => {
    const currentDialogs = (): HTMLElement[] => Array.from(
      document.querySelectorAll<HTMLElement>("[role='dialog'][aria-modal='true']"),
    );

    const rememberOutsideFocus = (event: FocusEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && !target.closest("[role='dialog']")) {
        lastOutsideFocusRef.current = target;
      }
    };

    const rememberPointerTrigger = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>("button, a, [role='button']") : null;
      if (isFocusable(target) && !target.closest("[role='dialog']")) intendedTriggerRef.current = target;
    };

    const manageDialogKeyboard = (event: KeyboardEvent) => {
      const trigger = shortcutTrigger(event);
      if (isFocusable(trigger)) intendedTriggerRef.current = trigger;

      if (event.key !== "Tab") return;
      const dialogs = currentDialogs();
      const topDialog = dialogs[dialogs.length - 1];
      if (!topDialog) return;

      const controls = focusableElements(topDialog);
      if (!controls.length) {
        event.preventDefault();
        topDialog.tabIndex = -1;
        topDialog.focus({ preventScroll: true });
        return;
      }

      const active = document.activeElement as HTMLElement | null;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!active || !topDialog.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
        return;
      }
      if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      }
    };

    const observer = new MutationObserver(() => {
      const dialogs = currentDialogs();
      const currentDialogSet = new Set(dialogs);

      dialogs.forEach((dialog) => {
        if (openDialogsRef.current.has(dialog)) return;
        const intended = intendedTriggerRef.current;
        const outside = lastOutsideFocusRef.current;
        openDialogsRef.current.set(
          dialog,
          firstFocusable(intended, outside, fallbackTrigger(dialog)),
        );
        intendedTriggerRef.current = null;

        window.requestAnimationFrame(() => {
          const active = document.activeElement as HTMLElement | null;
          if (active && dialog.contains(active)) return;
          const autofocus = dialog.querySelector<HTMLElement>("[autofocus]");
          const target = firstFocusable(autofocus, focusableElements(dialog)[0] || null);
          if (target) target.focus({ preventScroll: true });
        });
      });

      const removedTriggers: HTMLElement[] = [];
      for (const [dialog, trigger] of openDialogsRef.current) {
        if (currentDialogSet.has(dialog)) continue;
        openDialogsRef.current.delete(dialog);
        if (isFocusable(trigger)) removedTriggers.push(trigger);
      }

      const restoreTarget = removedTriggers[0] || null;
      if (!dialogs.length && restoreTarget) {
        window.requestAnimationFrame(() => {
          if (isFocusable(restoreTarget)) restoreTarget.focus({ preventScroll: true });
        });
      }
    });

    document.addEventListener("focusin", rememberOutsideFocus, true);
    document.addEventListener("pointerdown", rememberPointerTrigger, true);
    document.addEventListener("keydown", manageDialogKeyboard, true);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      document.removeEventListener("focusin", rememberOutsideFocus, true);
      document.removeEventListener("pointerdown", rememberPointerTrigger, true);
      document.removeEventListener("keydown", manageDialogKeyboard, true);
      openDialogsRef.current.clear();
    };
  }, []);
}

export default function QmsPlannerLivePage(): React.ReactElement {
  const [clockInstant, setClockInstant] = useState(() => new Date());
  usePlannerDialogFocusManagement();

  useEffect(() => {
    const timer = window.setInterval(() => setClockInstant(new Date()), CLOCK_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const plannerClock = useMemo(
    () => plannerClockAt(clockInstant, PLANNER_TIMEZONE),
    [clockInstant],
  );

  // Ordinary timer ticks rerender the existing planner so its current-time marker
  // advances. The key changes only at an EAT date rollover, refreshing Today-based
  // memoized state without resetting the workspace every minute.
  return <QmsPlannerPageV2 key={plannerClock.dateKey} />;
}

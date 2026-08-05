import React, { useEffect, useMemo, useRef, useState } from "react";
import QmsPlannerPageV2 from "./QmsPlannerPageV2";
import { plannerClockAt } from "./qmsPlannerClock";

const PLANNER_TIMEZONE = "Africa/Nairobi";
const CLOCK_REFRESH_MS = 30_000;

function isFocusable(element: Element | null): element is HTMLElement {
  if (!(element instanceof HTMLElement) || !element.isConnected) return false;
  if (element.matches(":disabled, [aria-disabled='true']")) return false;
  return typeof element.focus === "function";
}

function fallbackTrigger(dialog: HTMLElement): HTMLElement | null {
  if (dialog.matches(".qms-planner-command")) {
    return document.querySelector<HTMLElement>(".qms-planner-toolbar__search");
  }
  if (dialog.matches(".qms-planner-create-modal")) {
    return document.querySelector<HTMLElement>(".qms-planner-quick-schedule")
      || document.querySelector<HTMLElement>(".qms-planner-toolbar__controls button:last-child");
  }
  if (dialog.matches(".qms-planner-shortcuts")) {
    return document.querySelector<HTMLElement>(".qms-planner-shortcut-link");
  }
  if (dialog.querySelector("#qms-reschedule-title")) {
    return document.querySelector<HTMLElement>(".qms-planner-inspector__actions button")
      || document.querySelector<HTMLElement>(".qms-planner-event.is-selected");
  }
  return null;
}

function shortcutTrigger(event: KeyboardEvent): HTMLElement | null {
  const key = event.key.toLowerCase();
  if (event.key === "/" || ((event.ctrlKey || event.metaKey) && key === "k")) {
    return document.querySelector<HTMLElement>(".qms-planner-toolbar__search");
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && key === "c") {
    return document.querySelector<HTMLElement>(".qms-planner-quick-schedule")
      || document.querySelector<HTMLElement>(".qms-planner-toolbar__controls button:last-child");
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key === "?") {
    return document.querySelector<HTMLElement>(".qms-planner-shortcut-link");
  }
  return null;
}

function usePlannerDialogFocusRestoration(): void {
  const lastOutsideFocusRef = useRef<HTMLElement | null>(null);
  const intendedTriggerRef = useRef<HTMLElement | null>(null);
  const openDialogsRef = useRef(new Map<HTMLElement, HTMLElement | null>());

  useEffect(() => {
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

    const rememberShortcutTrigger = (event: KeyboardEvent) => {
      const trigger = shortcutTrigger(event);
      if (isFocusable(trigger)) intendedTriggerRef.current = trigger;
    };

    const observer = new MutationObserver(() => {
      const currentDialogs = new Set(
        Array.from(document.querySelectorAll<HTMLElement>("[role='dialog'][aria-modal='true']")),
      );

      currentDialogs.forEach((dialog) => {
        if (openDialogsRef.current.has(dialog)) return;
        const intended = intendedTriggerRef.current;
        const outside = lastOutsideFocusRef.current;
        openDialogsRef.current.set(
          dialog,
          isFocusable(intended) ? intended : isFocusable(outside) ? outside : fallbackTrigger(dialog),
        );
        intendedTriggerRef.current = null;
      });

      let restoreTarget: HTMLElement | null = null;
      openDialogsRef.current.forEach((trigger, dialog) => {
        if (currentDialogs.has(dialog)) return;
        openDialogsRef.current.delete(dialog);
        if (!restoreTarget && isFocusable(trigger)) restoreTarget = trigger;
      });

      if (!currentDialogs.size && restoreTarget) {
        const target = restoreTarget;
        window.requestAnimationFrame(() => {
          if (isFocusable(target)) target.focus({ preventScroll: true });
        });
      }
    });

    document.addEventListener("focusin", rememberOutsideFocus, true);
    document.addEventListener("pointerdown", rememberPointerTrigger, true);
    document.addEventListener("keydown", rememberShortcutTrigger, true);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      document.removeEventListener("focusin", rememberOutsideFocus, true);
      document.removeEventListener("pointerdown", rememberPointerTrigger, true);
      document.removeEventListener("keydown", rememberShortcutTrigger, true);
      openDialogsRef.current.clear();
    };
  }, []);
}

export default function QmsPlannerLivePage(): React.ReactElement {
  const [clockInstant, setClockInstant] = useState(() => new Date());
  usePlannerDialogFocusRestoration();

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

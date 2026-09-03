import React, { useEffect, useRef } from "react";
import QmsPlannerPageV2 from "./QmsPlannerPageV2";

const FOCUS_RESTORE_DELAYS_MS = [0, 40, 120, 240, 500, 1000, 1800];
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function isRendered(element: HTMLElement): boolean {
  if (!element.isConnected || element.closest("[aria-hidden='true']")) return false;
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return false;
  return element.getClientRects().length > 0;
}

function isFocusable(element: Element | null): element is HTMLElement {
  if (!(element instanceof HTMLElement) || !isRendered(element)) return false;
  if (element.matches(":disabled, [aria-disabled='true']")) return false;
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
      document.querySelector<HTMLElement>(".qms-planner-schedule-action"),
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
      Array.from(document.querySelectorAll<HTMLElement>(".qms-planner-inspector__actions button"))
        .find((button) => /^reschedule$/i.test(button.textContent?.trim() || "")) || null,
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
      document.querySelector<HTMLElement>(".qms-planner-schedule-action"),
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
    const openDialogs = openDialogsRef.current;
    const pendingFocusTimers = new Set<number>();
    const scheduledRestoreDialogs = new WeakSet<HTMLElement>();
    const currentDialogs = (): HTMLElement[] => Array.from(
      document.querySelectorAll<HTMLElement>("[role='dialog'][aria-modal='true']"),
    ).filter(isRendered);

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

    const restoreDialogTrigger = (dialog: HTMLElement, rememberedTrigger: HTMLElement | null) => {
      if (scheduledRestoreDialogs.has(dialog)) return;
      scheduledRestoreDialogs.add(dialog);

      let restoredOnce = false;
      let cancelled = false;
      const restore = () => {
        if (cancelled || currentDialogs().length) return;
        const target = firstFocusable(rememberedTrigger, fallbackTrigger(dialog));
        if (!target) return;

        const active = document.activeElement as HTMLElement | null;
        const activeIsMeaningfulOther = Boolean(
          restoredOnce
            && active
            && active !== target
            && active !== document.body
            && active !== document.documentElement
            && isFocusable(active),
        );
        if (activeIsMeaningfulOther) {
          cancelled = true;
          return;
        }

        if (active !== target) target.focus({ preventScroll: true });
        if (document.activeElement === target) restoredOnce = true;
      };

      window.requestAnimationFrame(() => {
        restore();
        FOCUS_RESTORE_DELAYS_MS.forEach((delay) => {
          const timer = window.setTimeout(() => {
            pendingFocusTimers.delete(timer);
            restore();
          }, delay);
          pendingFocusTimers.add(timer);
        });
      });
    };

    const manageDialogKeyboard = (event: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      if (
        (event.key === "Enter" || event.key === " ")
        && isFocusable(active)
        && !active.closest("[role='dialog']")
      ) {
        intendedTriggerRef.current = active;
      }

      const trigger = shortcutTrigger(event);
      if (isFocusable(trigger)) intendedTriggerRef.current = trigger;

      const dialogs = currentDialogs();
      const topDialog = dialogs[dialogs.length - 1];

      if (event.key === "Escape" && topDialog) {
        const rememberedTrigger = openDialogs.get(topDialog) ?? fallbackTrigger(topDialog);
        const timer = window.setTimeout(() => {
          pendingFocusTimers.delete(timer);
          if (!isRendered(topDialog)) restoreDialogTrigger(topDialog, rememberedTrigger);
        }, 0);
        pendingFocusTimers.add(timer);
        return;
      }

      if (event.key !== "Tab" || !topDialog) return;

      const controls = focusableElements(topDialog);
      if (!controls.length) {
        event.preventDefault();
        topDialog.tabIndex = -1;
        topDialog.focus({ preventScroll: true });
        return;
      }

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
        if (openDialogs.has(dialog)) return;
        const intended = intendedTriggerRef.current;
        const outside = lastOutsideFocusRef.current;
        openDialogs.set(
          dialog,
          firstFocusable(intended, fallbackTrigger(dialog), outside),
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

      const removedDialogs: Array<{ dialog: HTMLElement; trigger: HTMLElement | null }> = [];
      for (const [dialog, trigger] of openDialogs) {
        if (currentDialogSet.has(dialog)) continue;
        openDialogs.delete(dialog);
        removedDialogs.push({ dialog, trigger });
      }

      if (!dialogs.length && removedDialogs.length) {
        const removed = removedDialogs[removedDialogs.length - 1];
        restoreDialogTrigger(removed.dialog, removed.trigger);
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
      pendingFocusTimers.forEach((timer) => window.clearTimeout(timer));
      pendingFocusTimers.clear();
      openDialogs.clear();
    };
  }, []);
}

type QmsPlannerLivePageProps = {
  /** When true, omit DepartmentLayout — parent already provides Assurance/QMS shell. */
  embedded?: boolean;
};

// QmsPlannerPageV2 owns the tenant timezone and live clock because those values
// come from the tenant-scoped calendar projection. This wrapper owns only modal
// focus containment and trigger restoration.
export default function QmsPlannerLivePage({ embedded = false }: QmsPlannerLivePageProps): React.ReactElement {
  usePlannerDialogFocusManagement();
  return <QmsPlannerPageV2 embedded={embedded} />;
}

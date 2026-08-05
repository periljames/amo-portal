import { useEffect } from "react";

import "../../styles/modal-top-layer.css";

const MODAL_SELECTOR = '[aria-modal="true"]';
const ACTIVE_BODY_CLASS = "portal-modal-layer-active";
const TOP_LAYER_CLASS = "portal-modal-top-layer";
const SURFACE_CLASS = "portal-modal-top-layer--surface";
const HOST_CLASS = "portal-modal-top-layer--host";
const FALLBACK_HOST_CLASS = "portal-modal-fallback-host";
const FALLBACK_ANCESTOR_CLASS = "portal-modal-fallback-ancestor";

type PopoverElement = HTMLElement & {
  showPopover?: () => void;
  hidePopover?: () => void;
};

type ManagedDialog = {
  host: PopoverElement;
  surface: boolean;
};

function isNativeModalDialog(element: HTMLElement): boolean {
  return typeof HTMLDialogElement !== "undefined"
    && element instanceof HTMLDialogElement
    && element.open;
}

function isVisibleModal(element: HTMLElement): boolean {
  if (!element.isConnected || isNativeModalDialog(element)) return false;

  let current: HTMLElement | null = element;
  while (current && current !== document.body) {
    if (current.hidden || current.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(current);
    if (style.display === "none" || style.visibility === "hidden") return false;
    current = current.parentElement;
  }

  const bounds = element.getBoundingClientRect();
  return bounds.width > 0 && bounds.height > 0;
}

function selectTopLayerHost(dialog: HTMLElement): ManagedDialog {
  const viewportArea = Math.max(window.innerWidth * window.innerHeight, 1);
  let current: HTMLElement | null = dialog;

  while (current && current !== document.body && current !== document.documentElement) {
    const bounds = current.getBoundingClientRect();
    const coverage = (Math.max(bounds.width, 0) * Math.max(bounds.height, 0)) / viewportArea;
    const position = window.getComputedStyle(current).position;
    if ((position === "fixed" || position === "absolute") && coverage >= 0.55) {
      return { host: current as PopoverElement, surface: false };
    }
    current = current.parentElement;
  }

  return { host: dialog as PopoverElement, surface: true };
}

function isPopoverOpen(element: HTMLElement): boolean {
  try {
    return element.matches(":popover-open");
  } catch {
    return false;
  }
}

/**
 * Promotes every visible ARIA modal into the browser top layer. This protects
 * route-level dialogs from app-shell transforms, sticky navigation and local
 * stacking contexts without requiring every feature page to invent a z-index.
 */
export function ModalTopLayerGuard() {
  useEffect(() => {
    const managedDialogs = new Map<HTMLElement, ManagedDialog>();
    const hostReferences = new Map<HTMLElement, number>();
    const fallbackAncestors = new Map<HTMLElement, HTMLElement[]>();
    const ancestorReferences = new Map<HTMLElement, number>();
    const addedPopoverAttribute = new Set<HTMLElement>();
    let animationFrame: number | null = null;

    const addFallbackAncestors = (host: HTMLElement) => {
      const ancestors: HTMLElement[] = [];
      let current = host.parentElement;
      while (current && current !== document.body && current !== document.documentElement) {
        const count = ancestorReferences.get(current) || 0;
        ancestorReferences.set(current, count + 1);
        if (count === 0) current.classList.add(FALLBACK_ANCESTOR_CLASS);
        ancestors.push(current);
        current = current.parentElement;
      }
      fallbackAncestors.set(host, ancestors);
    };

    const removeFallbackAncestors = (host: HTMLElement) => {
      for (const ancestor of fallbackAncestors.get(host) || []) {
        const nextCount = Math.max((ancestorReferences.get(ancestor) || 1) - 1, 0);
        if (nextCount === 0) {
          ancestorReferences.delete(ancestor);
          ancestor.classList.remove(FALLBACK_ANCESTOR_CLASS);
        } else {
          ancestorReferences.set(ancestor, nextCount);
        }
      }
      fallbackAncestors.delete(host);
    };

    const useFallbackLayer = (host: HTMLElement) => {
      host.classList.add(FALLBACK_HOST_CLASS);
      addFallbackAncestors(host);
    };

    const promoteHost = ({ host, surface }: ManagedDialog) => {
      host.classList.add(TOP_LAYER_CLASS, surface ? SURFACE_CLASS : HOST_CLASS);
      host.dataset.portalModalLayer = "true";

      if (typeof host.showPopover !== "function") {
        useFallbackLayer(host);
        return;
      }

      if (!host.hasAttribute("popover")) {
        host.setAttribute("popover", "manual");
        addedPopoverAttribute.add(host);
      }

      try {
        if (!isPopoverOpen(host)) host.showPopover();
      } catch {
        useFallbackLayer(host);
      }
    };

    const demoteHost = (host: PopoverElement) => {
      if (typeof host.hidePopover === "function" && isPopoverOpen(host)) {
        try {
          host.hidePopover();
        } catch {
          // The feature may have removed the host between observation and cleanup.
        }
      }
      if (addedPopoverAttribute.delete(host)) host.removeAttribute("popover");
      removeFallbackAncestors(host);
      host.classList.remove(TOP_LAYER_CLASS, SURFACE_CLASS, HOST_CLASS, FALLBACK_HOST_CLASS);
      delete host.dataset.portalModalLayer;
    };

    const acquire = (dialog: HTMLElement, selection: ManagedDialog) => {
      const count = hostReferences.get(selection.host) || 0;
      hostReferences.set(selection.host, count + 1);
      if (count === 0) promoteHost(selection);
      managedDialogs.set(dialog, selection);
    };

    const release = (dialog: HTMLElement) => {
      const selection = managedDialogs.get(dialog);
      if (!selection) return;
      managedDialogs.delete(dialog);
      const nextCount = Math.max((hostReferences.get(selection.host) || 1) - 1, 0);
      if (nextCount === 0) {
        hostReferences.delete(selection.host);
        demoteHost(selection.host);
      } else {
        hostReferences.set(selection.host, nextCount);
      }
    };

    const sync = () => {
      const modalElements = Array.from(document.querySelectorAll<HTMLElement>(MODAL_SELECTOR));
      const currentModals = new Set(modalElements);

      for (const dialog of managedDialogs.keys()) {
        if (!currentModals.has(dialog) || !isVisibleModal(dialog)) release(dialog);
      }

      for (const dialog of modalElements) {
        if (!isVisibleModal(dialog)) continue;
        const selection = selectTopLayerHost(dialog);
        const current = managedDialogs.get(dialog);
        if (current && current.host === selection.host && current.surface === selection.surface) {
          if (typeof current.host.showPopover === "function" && !isPopoverOpen(current.host)) {
            try {
              current.host.showPopover();
            } catch {
              if (!current.host.classList.contains(FALLBACK_HOST_CLASS)) useFallbackLayer(current.host);
            }
          }
          continue;
        }
        if (current) release(dialog);
        acquire(dialog, selection);
      }

      document.body.classList.toggle(ACTIVE_BODY_CLASS, managedDialogs.size > 0);
    };

    const scheduleSync = () => {
      if (animationFrame !== null) return;
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = null;
        sync();
      });
    };

    const observer = new MutationObserver(scheduleSync);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["aria-hidden", "aria-modal", "class", "hidden", "open", "style"],
    });
    window.addEventListener("resize", scheduleSync);
    scheduleSync();

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", scheduleSync);
      if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
      for (const dialog of [...managedDialogs.keys()]) release(dialog);
      document.body.classList.remove(ACTIVE_BODY_CLASS);
    };
  }, []);

  return null;
}

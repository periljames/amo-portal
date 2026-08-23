import React, { useEffect, useRef } from "react";

type DrawerProps = {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  side?: "left" | "right";
  panelClassName?: string;
  closeDisabled?: boolean;
};

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

const Drawer: React.FC<DrawerProps> = ({
  title,
  isOpen,
  onClose,
  children,
  side = "right",
  panelClassName,
  closeDisabled = false,
}) => {
  const lastActiveRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (isOpen) {
      lastActiveRef.current = document.activeElement as HTMLElement | null;
      wasOpenRef.current = true;
      const frame = window.requestAnimationFrame(() => {
        const panel = panelRef.current;
        if (!panel) return;
        const firstFocusable = panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
        (firstFocusable ?? panel).focus();
      });
      return () => window.cancelAnimationFrame(frame);
    }

    if (wasOpenRef.current) {
      wasOpenRef.current = false;
      const trigger = lastActiveRef.current;
      if (trigger?.isConnected) trigger.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !closeDisabled) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true"
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [closeDisabled, isOpen, onClose]);

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!closeDisabled && event.target === event.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className={`drawer-overlay drawer-overlay--${side}${isOpen ? " drawer-overlay--open" : ""}`}
      onMouseDown={handleBackdropClick}
      aria-hidden={!isOpen}
      aria-busy={closeDisabled || undefined}
    >
      {isOpen ? (
        <aside
          ref={panelRef}
          className={`drawer-panel${panelClassName ? ` ${panelClassName}` : ""}`}
          role="dialog"
          aria-modal="true"
          aria-label={title}
          tabIndex={-1}
        >
          <div className="drawer__header">
            <h3 className="drawer__title">{title}</h3>
            <button type="button" className="drawer__close" onClick={onClose} disabled={closeDisabled} aria-label={`Close ${title}`}>
              ×
            </button>
          </div>
          {children}
        </aside>
      ) : null}
    </div>
  );
};

export default Drawer;

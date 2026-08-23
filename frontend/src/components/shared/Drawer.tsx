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

  useEffect(() => {
    if (isOpen) {
      lastActiveRef.current = document.activeElement as HTMLElement | null;
      return;
    }
    lastActiveRef.current?.focus?.();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || closeDisabled) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
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
        <aside className={`drawer-panel${panelClassName ? ` ${panelClassName}` : ""}`} role="dialog" aria-modal="true">
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

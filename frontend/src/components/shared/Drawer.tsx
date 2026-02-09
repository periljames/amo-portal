import React, { useEffect, useRef } from "react";

type DrawerProps = {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
};

const Drawer: React.FC<DrawerProps> = ({ title, isOpen, onClose, children }) => {
  const lastActiveRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      lastActiveRef.current = document.activeElement as HTMLElement | null;
      return;
    }
    lastActiveRef.current?.focus?.();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className={`drawer-overlay${isOpen ? " drawer-overlay--open" : ""}`}
      onMouseDown={handleBackdropClick}
      aria-hidden={!isOpen}
    >
      <aside className="drawer-panel" role="dialog" aria-modal="true">
        <div className="drawer__header">
          <h3 className="drawer__title">{title}</h3>
          <button type="button" className="drawer__close" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
};

export default Drawer;

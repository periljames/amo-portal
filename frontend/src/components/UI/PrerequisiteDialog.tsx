import { useEffect, useId, useRef, type ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";

import "./contextual-help.css";

export type PrerequisiteItem = {
  id: string;
  title: string;
  detail: string;
  action?: ReactNode;
};

type Props = {
  open: boolean;
  title?: string;
  description?: string;
  items: PrerequisiteItem[];
  onClose: () => void;
  continueLabel?: string;
};

export function PrerequisiteDialog({
  open,
  title = "Complete setup before continuing",
  description = "This page depends on the following tenant configuration.",
  items,
  onClose,
  continueLabel = "Continue in read-only mode",
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="portal-help-backdrop" role="presentation">
      <section className="portal-help-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className="portal-help-dialog__header">
          <div>
            <span className="portal-help-dialog__eyebrow">Setup required</span>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button ref={closeRef} type="button" className="portal-help-dialog__close" onClick={onClose} aria-label="Close setup guidance">
            <X size={19} aria-hidden="true" />
          </button>
        </header>
        <div className="portal-help-dialog__body">
          <p>{description}</p>
          <div className="portal-prerequisite-list">
            {items.map((item) => (
              <article className="portal-prerequisite-item" key={item.id}>
                <AlertTriangle size={18} aria-hidden="true" />
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </div>
                {item.action ? <div className="portal-prerequisite-item__action">{item.action}</div> : null}
              </article>
            ))}
          </div>
        </div>
        <footer className="portal-help-dialog__footer">
          <button type="button" className="portal-help-button portal-help-button--secondary" onClick={onClose}>{continueLabel}</button>
        </footer>
      </section>
    </div>
  );
}

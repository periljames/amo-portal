import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { HelpCircle, X } from "lucide-react";

import { acknowledgeGuidance, guidanceAcknowledged } from "../../services/contextualGuidance";
import "./contextual-help.css";

type Props = {
  topic: string;
  version?: number;
  title: string;
  description: ReactNode;
  checklist?: ReactNode[];
  actions?: ReactNode;
  triggerLabel?: string;
  autoOpen?: boolean;
  className?: string;
};

const FOCUSABLE = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function ContextualHelp({
  topic,
  version = 1,
  title,
  description,
  checklist = [],
  actions,
  triggerLabel = "Open help",
  autoOpen = true,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const titleId = useId();
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let active = true;
    if (!autoOpen) {
      setChecked(true);
      return () => { active = false; };
    }
    void guidanceAcknowledged(topic, version).then((acknowledged) => {
      if (!active) return;
      setChecked(true);
      if (!acknowledged) setOpen(true);
    });
    return () => { active = false; };
  }, [autoOpen, topic, version]);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) || []);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      const target = previousFocusRef.current || triggerRef.current;
      globalThis.setTimeout(() => target?.focus(), 0);
    };
  }, [open]);

  const acknowledge = async () => {
    setOpen(false);
    await acknowledgeGuidance(topic, version);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`portal-help-trigger ${className}`.trim()}
        aria-label={triggerLabel}
        title={triggerLabel}
        onClick={() => setOpen(true)}
        data-guidance-checked={checked ? "true" : "false"}
      >
        <HelpCircle size={17} aria-hidden="true" />
      </button>

      {open ? (
        <div className="portal-help-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setOpen(false);
        }}>
          <section
            ref={dialogRef}
            className="portal-help-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <header className="portal-help-dialog__header">
              <div>
                <span className="portal-help-dialog__eyebrow">Quick guidance</span>
                <h2 id={titleId}>{title}</h2>
              </div>
              <button
                ref={closeRef}
                type="button"
                className="portal-help-dialog__close"
                onClick={() => setOpen(false)}
                aria-label="Close help without acknowledging"
              >
                <X size={19} aria-hidden="true" />
              </button>
            </header>
            <div className="portal-help-dialog__body">
              <div className="portal-help-dialog__description">{description}</div>
              {checklist.length ? <ul>{checklist.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
            </div>
            <footer className="portal-help-dialog__footer">
              {actions}
              <button type="button" className="portal-help-button portal-help-button--primary" onClick={() => void acknowledge()}>Got it</button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

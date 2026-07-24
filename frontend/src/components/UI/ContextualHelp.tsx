import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { HelpCircle, X } from "lucide-react";

import { getCachedUser, getContext } from "../../services/auth";
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

function storageKey(topic: string, version: number): string {
  const user = getCachedUser();
  const context = getContext();
  const userId = user?.id || "anonymous";
  const tenantId = user?.amo_id || context.amoCode || context.amoSlug || "tenant";
  return `amo_portal_help_seen:${tenantId}:${userId}:${topic}:v${version}`;
}

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
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const key = useMemo(() => storageKey(topic, version), [topic, version]);

  useEffect(() => {
    if (!autoOpen || typeof window === "undefined") return;
    try {
      if (!window.localStorage.getItem(key)) setOpen(true);
    } catch {
      // Hardened browsers may block storage; help remains manually available.
    }
  }, [autoOpen, key]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const dismiss = () => {
    try {
      window.localStorage.setItem(key, new Date().toISOString());
    } catch {
      // Best effort only.
    }
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        className={`portal-help-trigger ${className}`.trim()}
        aria-label={triggerLabel}
        title={triggerLabel}
        onClick={() => setOpen(true)}
      >
        <HelpCircle size={17} aria-hidden="true" />
      </button>

      {open ? (
        <div className="portal-help-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) dismiss();
        }}>
          <section
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
                onClick={dismiss}
                aria-label="Close help"
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
              <button type="button" className="portal-help-button portal-help-button--primary" onClick={dismiss}>Got it</button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

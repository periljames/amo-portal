import type { ComponentType, FormEvent, ReactNode } from "react";
import { BadgeCheck, LoaderCircle, X } from "lucide-react";

import "../../styles/procurement-workspace.css";

export function Field({
  label,
  required,
  wide,
  children,
}: {
  label: string;
  required?: boolean;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`proc-field${wide ? " proc-field--wide" : ""}`}>
      <span>{label}{required ? " *" : ""}</span>
      {children}
    </label>
  );
}

export function Empty({
  icon: Icon,
  title,
  text,
  action,
}: {
  icon: ComponentType<{ size?: number }>;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="proc-empty-state">
      <Icon size={28} />
      <strong>{title}</strong>
      <span>{text}</span>
      {action}
    </div>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="proc-table-skeleton" role="status" aria-label="Loading Procurement records">
      {Array.from({ length: rows }).map((_, index) => <span key={index} />)}
    </div>
  );
}

export function ModalShell({
  title,
  busy,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  return (
    <div className="proc-modal" role="dialog" aria-modal="true" aria-labelledby="proc-modal-title">
      <button type="button" className="proc-modal__backdrop" aria-label="Close dialog" onClick={onClose} />
      <div className="proc-modal__panel">
        <header>
          <div>
            <h2 id="proc-modal-title">{title}</h2>
            <p>Required fields and backend controls are validated before the record is committed.</p>
          </div>
          <button type="button" className="proc-icon-button" onClick={onClose} aria-label="Close">
            <X size={17} />
          </button>
        </header>
        <form className="proc-form" onSubmit={onSubmit}>
          {children}
          <footer className="proc-form__footer">
            <button type="button" className="proc-button proc-button--ghost" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="proc-button proc-button--primary" disabled={busy}>
              {busy ? <LoaderCircle className="is-spinning" size={16} /> : <BadgeCheck size={16} />}
              {busy ? "Saving controlled record" : "Save and continue"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

export function RecordActions({ children }: { children: ReactNode }) {
  return <div className="proc-row-actions">{children}</div>;
}

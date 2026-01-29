import React from "react";
import { clsx } from "clsx";

export interface PanelProps {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  compact?: boolean;
}

const Panel: React.FC<PanelProps> = ({
  title,
  subtitle,
  actions,
  children,
  className,
  compact = false,
}) => {
  return (
    <section
      className={clsx("admin-panel", compact && "admin-panel--compact", className)}
    >
      {(title || subtitle || actions) && (
        <div className="admin-panel__header">
          <div>
            {title ? <h2 className="admin-panel__title">{title}</h2> : null}
            {subtitle ? (
              <p className="admin-panel__subtitle">{subtitle}</p>
            ) : null}
          </div>
          {actions ? <div className="admin-panel__actions">{actions}</div> : null}
        </div>
      )}
      <div className="admin-panel__body">{children}</div>
    </section>
  );
};

export default Panel;

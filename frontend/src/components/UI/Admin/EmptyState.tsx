import React from "react";
import { clsx } from "clsx";

export interface EmptyStateProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actions,
  className,
}) => {
  return (
    <div className={clsx("admin-empty-state", className)}>
      <strong className="admin-empty-state__title">{title}</strong>
      {description ? (
        <p className="admin-empty-state__description">{description}</p>
      ) : null}
      {actions ? <div className="admin-empty-state__actions">{actions}</div> : null}
    </div>
  );
};

export default EmptyState;

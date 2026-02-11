import React from "react";

type DashboardCardProps = {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  isLoading?: boolean;
  emptyMessage?: string;
  isEmpty?: boolean;
};

const DashboardCard: React.FC<DashboardCardProps> = ({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  isLoading = false,
  isEmpty = false,
  emptyMessage = "No data available.",
}) => {
  return (
    <article className={`qms-dashboard-card ${className ?? ""}`.trim()}>
      <header className="qms-dashboard-card__header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="qms-dashboard-card__actions">{actions}</div> : null}
      </header>

      <div className={`qms-dashboard-card__body ${bodyClassName ?? ""}`.trim()}>
        {isLoading ? <div className="qms-dashboard-card__state">Loading…</div> : null}
        {!isLoading && isEmpty ? <div className="qms-dashboard-card__state">{emptyMessage}</div> : null}
        {!isLoading && !isEmpty ? children : null}
      </div>
    </article>
  );
};

export default React.memo(DashboardCard);

import React from "react";
import { clsx } from "clsx";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  actions,
  className,
}) => {
  return (
    <div className={clsx("admin-page-header", className)}>
      <div className="admin-page-header__heading">
        <h1 className="admin-page-header__title">{title}</h1>
        {subtitle ? (
          <p className="admin-page-header__subtitle">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="admin-page-header__actions">{actions}</div> : null}
    </div>
  );
};

export default PageHeader;

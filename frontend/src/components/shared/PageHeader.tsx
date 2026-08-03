import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

type Breadcrumb = {
  label: string;
  to?: string;
};

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  breadcrumbs?: Breadcrumb[];
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  compact?: boolean;
};

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  eyebrow,
  breadcrumbs,
  actions,
  meta,
  compact = false,
}) => {
  return (
    <section className={`page-header${compact ? " page-header--compact" : ""}`}>
      <div className="page-header__body">
        {(eyebrow || (breadcrumbs && breadcrumbs.length > 0)) && (
          <div className="page-header__meta-row">
            {eyebrow ? <span className="page-header__eyebrow">{eyebrow}</span> : null}
            {breadcrumbs && breadcrumbs.length > 0 ? (
              <nav className="page-header__breadcrumbs" aria-label="Breadcrumb">
                {breadcrumbs.map((crumb, index) => (
                  <React.Fragment key={`${crumb.label}-${index}`}>
                    {index > 0 ? <ChevronRight size={14} className="page-header__crumb-separator" /> : null}
                    {crumb.to ? (
                      <Link to={crumb.to} className="page-header__crumb-link">
                        {crumb.label}
                      </Link>
                    ) : (
                      <span className="page-header__crumb-current">{crumb.label}</span>
                    )}
                  </React.Fragment>
                ))}
              </nav>
            ) : null}
          </div>
        )}

        <div className="page-header__title-row">
          <div className="page-header__title-block">
            <h1 className="page-header__title">{title}</h1>
            {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
          </div>
          {meta ? <div className="page-header__meta">{meta}</div> : null}
        </div>
      </div>

      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </section>
  );
};

export default PageHeader;

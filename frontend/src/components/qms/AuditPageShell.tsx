import React from "react";
import { clsx } from "clsx";
import { ChevronRight, Ellipsis, type LucideIcon } from "lucide-react";
import QMSLayout from "../QMS/QMSLayout";

export type AuditShellNavItem = {
  id: string;
  label: string;
  shortLabel?: string;
  icon: LucideIcon;
  href: string;
  active: boolean;
  ariaLabel?: string;
};

type Breadcrumb = {
  label: string;
  href?: string;
  onClick?: () => void;
};

type Props = {
  amoCode: string;
  department: string;
  title: string;
  subtitle: string;
  breadcrumbs: Breadcrumb[];
  nav: React.ReactNode;
  toolbar?: React.ReactNode;
  children: React.ReactNode;
};

const AuditPageShell: React.FC<Props> = ({ amoCode, department, title, subtitle, breadcrumbs, nav, toolbar, children }) => {
  const customHeader = (
    <div className="audit-shell-header">
      <div className="audit-shell-header__top-row">
        <div className="audit-shell-header__title-block">
          <nav className="audit-shell-header__breadcrumbs" aria-label="Breadcrumb">
            {breadcrumbs.map((item, index) => (
              <React.Fragment key={`${item.label}-${index}`}>
                {index > 0 ? <ChevronRight className="audit-shell-header__crumb-separator" /> : null}
                {item.href || item.onClick ? (
                  <button
                    type="button"
                    onClick={item.onClick}
                    className="audit-shell-header__crumb-button"
                  >
                    {item.label}
                  </button>
                ) : (
                  <span className="audit-shell-header__crumb-current">{item.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
          <div>
            <h1 className="audit-shell-header__title">{title}</h1>
            <p className="audit-shell-header__subtitle">{subtitle}</p>
          </div>
        </div>
        <div className="audit-shell-header__actions">
          {toolbar}
          <button
            type="button"
            aria-label="More audit page actions"
            className="secondary-chip-btn audit-shell-header__overflow"
          >
            <Ellipsis size={15} />
          </button>
        </div>
      </div>
      <div className="audit-shell-header__nav">{nav}</div>
    </div>
  );

  return (
    <QMSLayout amoCode={amoCode} department={department} title={title} subtitle={subtitle} hideBackButton customHeader={customHeader}>
      <div className={clsx("audit-shell-content")}>{children}</div>
    </QMSLayout>
  );
};

export default AuditPageShell;

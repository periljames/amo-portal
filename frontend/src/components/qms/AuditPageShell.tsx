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
    <div className="space-y-3 rounded-3xl border border-slate-800 bg-slate-900/70 p-4 shadow-[0_20px_60px_rgba(2,6,23,0.25)] backdrop-blur">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <nav className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-slate-400" aria-label="Breadcrumb">
            {breadcrumbs.map((item, index) => (
              <React.Fragment key={`${item.label}-${index}`}>
                {index > 0 ? <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-600" /> : null}
                {item.href || item.onClick ? (
                  <button
                    type="button"
                    onClick={item.onClick}
                    className="truncate rounded-md px-1 py-0.5 transition hover:text-cyan-300"
                  >
                    {item.label}
                  </button>
                ) : (
                  <span className="truncate text-slate-200">{item.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-slate-50">{title}</h1>
            <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:max-w-[52%] lg:justify-end">
          {toolbar}
          <button
            type="button"
            aria-label="More audit page actions"
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-950 text-slate-300 transition hover:border-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            <Ellipsis className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="border-t border-slate-800 pt-3">{nav}</div>
    </div>
  );

  return (
    <QMSLayout amoCode={amoCode} department={department} title={title} subtitle={subtitle} hideBackButton customHeader={customHeader}>
      <div className={clsx("space-y-4")}>{children}</div>
    </QMSLayout>
  );
};

export default AuditPageShell;

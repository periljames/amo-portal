import React from "react";

export type AppShellProps = {
  sidebar: React.ReactNode;
  header: React.ReactNode;
  children: React.ReactNode;
  fluid?: boolean;
  className?: string;
  contentClassName?: string;
};

const AppShell: React.FC<AppShellProps> = ({
  sidebar,
  header,
  children,
  fluid = false,
  className,
  contentClassName,
}) => {
  const contentClass = contentClassName ?? "app-shell__content";
  const fluidClass = contentClassName ? "" : fluid ? " app-shell__content--fluid" : "";
  return (
    <div className={className}>
      {sidebar}
      <div className="app-shell__main">
        {header}
        <div className={`${contentClass}${fluidClass}`}>
          {children}
        </div>
      </div>
    </div>
  );
};

export default AppShell;

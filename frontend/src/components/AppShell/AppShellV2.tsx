import React from "react";

export type AppShellV2Props = {
  sidebar: React.ReactNode;
  header: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  focusMode?: boolean;
};

const AppShellV2: React.FC<AppShellV2Props> = ({
  sidebar,
  header,
  children,
  className,
  contentClassName,
  focusMode = false,
}) => {
  const contentClass = contentClassName ?? "app-shell__content";
  return (
    <div className={`${className ?? ""}${focusMode ? " app-shell--focus" : ""}`}>
      {sidebar}
      <div className="app-shell__main">
        {header}
        <div className="app-shell__scroll">
          <div className={contentClass}>{children}</div>
        </div>
      </div>
    </div>
  );
};

export default AppShellV2;

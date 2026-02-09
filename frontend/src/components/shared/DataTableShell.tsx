import React from "react";

type DataTableShellProps = {
  title?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
};

const DataTableShell: React.FC<DataTableShellProps> = ({
  title,
  actions,
  children,
}) => {
  return (
    <div className="data-table">
      {(title || actions) && (
        <div className="data-table__header">
          {title && <h4 className="data-table__title">{title}</h4>}
          {actions && <div>{actions}</div>}
        </div>
      )}
      <div className="data-table__body">{children}</div>
    </div>
  );
};

export default DataTableShell;

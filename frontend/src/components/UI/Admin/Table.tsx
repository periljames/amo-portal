import React from "react";
import { clsx } from "clsx";

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  wrapperClassName?: string;
}

const Table: React.FC<TableProps> = ({
  wrapperClassName,
  className,
  children,
  ...rest
}) => {
  return (
    <div className={clsx("admin-table", wrapperClassName)}>
      <table className={clsx("admin-table__table", className)} {...rest}>
        {children}
      </table>
    </div>
  );
};

export default Table;

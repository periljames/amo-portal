import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import "../../../styles/qms/workspace.css";

const defaultColumn: ColDef = { sortable: true, filter: true, floatingFilter: true, resizable: true, minWidth: 140, flex: 1 };

export default function QmsWorkspaceGrid<T>({ className = "", columnDefs, ...props }: AgGridReactProps<T>) {
  const columns = useMemo(() => columnDefs?.map((column, index) => "children" in column ? column : { ...column, colId: column.colId || column.field || column.headerName || String(index) }), [columnDefs]);
  return <div className={`qms-workspace-grid ag-theme-alpine ${className}`}>
    <AgGridReact<T>
      defaultColDef={defaultColumn} columnDefs={columns}
      rowHeight={48} headerHeight={38} animateRows={false}
      enableCellTextSelection ensureDomOrder
      {...props}
    />
  </div>;
}

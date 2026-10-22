import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import { useMemo, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import Pagination from "../../../components/shared/Pagination";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import "../../../styles/qms/workspace.css";

const defaultColumn: ColDef = { sortable: true, filter: true, floatingFilter: true, resizable: true, minWidth: 140, flex: 1 };

export default function QmsWorkspaceGrid<T>({ className = "", columnDefs, onGridReady, onPaginationChanged, pagination, paginationPageSize=25, paginationPageSizeSelector, ...props }: AgGridReactProps<T>) {
  const columns = useMemo(() => columnDefs?.map((column, index) => "children" in column ? column : { ...column, colId: column.colId || column.field || column.headerName || String(index) }), [columnDefs]);
  const [api,setApi]=useState<GridApi<T>|null>(null);
  const [paging,setPaging]=useState({page:1,size:paginationPageSize,total:props.rowData?.length || 0});
  const sync=(grid:GridApi<T>)=>{
    if(grid.isDestroyed())return;
    const next={page:grid.paginationGetCurrentPage()+1,size:grid.paginationGetPageSize(),total:grid.paginationGetRowCount()};
    setPaging(current=>current.page===next.page && current.size===next.size && current.total===next.total ? current : next);
  };
  const pageSizes=Array.from(new Set([paging.size,...(Array.isArray(paginationPageSizeSelector) ? paginationPageSizeSelector : [25,50,100])])).sort((a,b)=>a-b);
  return <div className={`qms-workspace-grid ag-theme-alpine ${pagination ? "qms-workspace-grid--paged" : ""} ${className}`}>
    <div className="qms-workspace-grid__surface"><AgGridReact<T>
      defaultColDef={defaultColumn} columnDefs={columns}
      rowHeight={48} headerHeight={38} animateRows={false}
      enableCellTextSelection ensureDomOrder
      {...props}
      pagination={pagination} paginationPageSize={paginationPageSize} paginationPageSizeSelector={paginationPageSizeSelector}
      suppressPaginationPanel={pagination ? true : props.suppressPaginationPanel}
      onGridReady={event=>{setApi(event.api);sync(event.api);onGridReady?.(event);}}
      onPaginationChanged={event=>{sync(event.api);onPaginationChanged?.(event);}}
    /></div>
    {pagination ? <Pagination page={paging.page} pageSize={paging.size} total={paging.total} visibleCount={Math.max(0,Math.min(paging.size,paging.total-(paging.page-1)*paging.size))} onPageChange={value=>api?.paginationGoToPage(value-1)} onPageSizeChange={value=>api?.setGridOption("paginationPageSize",value)} pageSizes={pageSizes} /> : null}
  </div>;
}

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import type { ColDef, ICellRendererParams, ValueGetterParams, ValueFormatterParams } from "ag-grid-community";
import InlineLoading from "./InlineLoading";
import "./recordTable.css";

/** Bounded, server-paginated registers do not need a virtual grid/layout engine. */
export default function RecordTable<T>({ rows, columns, label, loading = false, sort, onSortChange, getRowId = (row: T) => String((row as unknown as { id: unknown }).id), onRowClick, onRowDoubleClick }: {
  sort?: {key:string;direction:"asc"|"desc"}; onSortChange?: (sort:{key:string;direction:"asc"|"desc"})=>void;
  getRowId?: (row:T)=>string; rows: T[]; columns: ColDef<T>[]; label: string; loading?: boolean;
  onRowClick?: (row: T, event: React.MouseEvent) => void;
  onRowDoubleClick?: (row: T, event: React.MouseEvent) => void;
}) {
  const [widths, setWidths] = useState<Record<number, number>>({});
  const drag = useRef<AbortController | null>(null);
  useEffect(() => () => drag.current?.abort(), []);
  const resize = (event: React.PointerEvent, index: number) => {
    event.preventDefault(); event.stopPropagation(); drag.current?.abort();
    const controller = new AbortController(); drag.current = controller;
    const start = event.clientX, width = event.currentTarget.parentElement!.getBoundingClientRect().width;
    window.addEventListener("pointermove", (next) => setWidths((current) => ({ ...current, [index]: Math.max(columns[index].minWidth || 64, Math.min(columns[index].maxWidth || 1200, width + next.clientX - start)) })), { signal: controller.signal });
    window.addEventListener("pointerup", () => controller.abort(), { signal: controller.signal, once: true });
    window.addEventListener("pointercancel", () => controller.abort(), { signal: controller.signal, once: true });
  };
  const keyResize = (event: React.KeyboardEvent, index: number) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const width = event.currentTarget.parentElement!.getBoundingClientRect().width;
    setWidths((current) => ({ ...current, [index]: Math.max(columns[index].minWidth || 64, Math.min(columns[index].maxWidth || 1200, width + (event.key === "ArrowRight" ? 16 : -16))) }));
  };
  const cell = (column: ColDef<T>, row: T) => {
    const fieldValue = String(column.field || "").split(".").filter(Boolean).reduce<unknown>((value, key) => value == null ? undefined : (value as Record<string, unknown>)[key], row);
    const value = typeof column.valueGetter === "function" ? column.valueGetter({ data: row } as ValueGetterParams<T>) : fieldValue;
    const params = { data: row, value } as ICellRendererParams<T>;
    if (typeof column.cellRenderer === "function") return React.createElement(column.cellRenderer, params);
    return typeof column.valueFormatter === "function" ? column.valueFormatter(params as unknown as ValueFormatterParams<T>) : String(value ?? "—");
  };
  return <div className="record-table-scroll" aria-busy={loading}>
    <table className="record-table" aria-label={label} style={{ minWidth: columns.reduce((sum, col) => sum + (col.minWidth || 96), 0) }}>
      <colgroup>{columns.map((column, index) => <col key={index} style={{ width: widths[index] || column.width || `${(column.flex || 1) * 100 / columns.reduce((sum, col) => sum + (col.flex || 1), 0)}%` }} />)}</colgroup>
      <thead><tr>{columns.map((column, index) => <th key={index} scope="col" aria-sort={sort && sort.key===(column.colId || column.field) ? sort.direction==="asc" ? "ascending" : "descending" : undefined} data-pinned={column.pinned || undefined}>
        {onSortChange && column.sortable!==false ? <button type="button" className="record-table-sort" onClick={()=>onSortChange({key:column.colId || String(column.field || index),direction:sort && sort.key===(column.colId || column.field) && sort.direction==="asc" ? "desc" : "asc"})}>{column.headerName}{sort && sort.key===(column.colId || column.field) ? sort.direction==="asc" ? <ArrowUp size={13}/> : <ArrowDown size={13}/> : <ArrowUpDown size={13}/>}</button> : column.headerName || <span className="sr-only">Actions</span>}
        {column.resizable !== false && column.minWidth !== column.maxWidth ? <span className="record-table-resize" role="separator" aria-label={`Resize ${column.headerName || "actions"} column`} aria-orientation="vertical" tabIndex={0} onPointerDown={(event) => resize(event, index)} onKeyDown={(event) => keyResize(event, index)} /> : null}
      </th>)}</tr></thead>
      <tbody>{rows.map((row) => <tr key={getRowId(row)} onClick={(event) => onRowClick?.(row, event)} onDoubleClick={(event) => onRowDoubleClick?.(row, event)}>
        {columns.map((column, index) => <td key={index} data-pinned={column.pinned || undefined} className={typeof column.cellClass === "string" ? column.cellClass : undefined}>{cell(column, row)}</td>)}
      </tr>)}</tbody>
    </table>
    {!rows.length ? <div className="record-table-empty">{loading ? <InlineLoading label={`Loading ${label.toLowerCase()}`} /> : "No records in this view"}</div> : null}
  </div>;
}

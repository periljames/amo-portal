import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

import type { IntegratedLibraryItem, LibraryDiscoveryItem } from "../../services/documentLibrary";

type SharedProps = {
  defaultColDef: ColDef;
};

type Props = SharedProps & (
  | { mode: "integrated"; rowData: IntegratedLibraryItem[]; columnDefs: ColDef<IntegratedLibraryItem>[] }
  | { mode: "discovery"; rowData: LibraryDiscoveryItem[]; columnDefs: ColDef<LibraryDiscoveryItem>[] }
);

export default function DocumentLibraryRegisterGrid({
  mode,
  rowData,
  columnDefs,
  defaultColDef,
}: Props) {
  const height = Math.min(650, Math.max(220, rowData.length * 62 + 44));
  if (mode === "integrated") {
    return (
      <div className="ag-theme-alpine dlibrary__ag-grid" style={{ height }}>
        <AgGridReact<IntegratedLibraryItem>
          rowData={rowData}
          columnDefs={columnDefs as ColDef<IntegratedLibraryItem>[]}
          defaultColDef={defaultColDef}
          rowHeight={62}
          headerHeight={40}
          animateRows={false}
          suppressCellFocus
          getRowId={({ data: item }) => item.id}
          overlayNoRowsTemplate="No controlled documents match this view"
        />
      </div>
    );
  }
  return (
    <div
      className="ag-theme-alpine dlibrary__ag-grid"
      style={{ height }}
    >
      <AgGridReact<LibraryDiscoveryItem>
        rowData={rowData}
        columnDefs={columnDefs as ColDef<LibraryDiscoveryItem>[]}
        defaultColDef={defaultColDef}
        rowHeight={62}
        headerHeight={40}
        animateRows={false}
        suppressCellFocus
        getRowId={({ data: item }) => item.id}
        overlayNoRowsTemplate="No controlled documents match this view"
      />
    </div>
  );
}

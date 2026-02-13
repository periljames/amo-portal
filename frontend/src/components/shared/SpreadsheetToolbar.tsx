import React from "react";

type Density = "compact" | "comfortable";

type ColumnToggle = {
  id: string;
  label: string;
  checked: boolean;
  onToggle: () => void;
};

type Props = {
  density: Density;
  onDensityChange: (density: Density) => void;
  wrapText: boolean;
  onWrapTextChange: (next: boolean) => void;
  showFilters: boolean;
  onShowFiltersChange: (next: boolean) => void;
  columnToggles?: ColumnToggle[];
  actions?: React.ReactNode;
};

const SpreadsheetToolbar: React.FC<Props> = ({
  density,
  onDensityChange,
  wrapText,
  onWrapTextChange,
  showFilters,
  onShowFiltersChange,
  columnToggles,
  actions,
}) => {
  return (
    <div className="spreadsheet-toolbar">
      <div className="qms-segmented" role="tablist" aria-label="Row density">
        <button type="button" className={density === "compact" ? "is-active" : ""} onClick={() => onDensityChange("compact")}>
          Compact
        </button>
        <button type="button" className={density === "comfortable" ? "is-active" : ""} onClick={() => onDensityChange("comfortable")}>
          Comfortable
        </button>
      </div>
      <label className="qms-pill"><input type="checkbox" checked={wrapText} onChange={(e) => onWrapTextChange(e.target.checked)} /> Wrap text</label>
      <label className="qms-pill"><input type="checkbox" checked={showFilters} onChange={(e) => onShowFiltersChange(e.target.checked)} /> Header filters</label>
      {(columnToggles ?? []).map((col) => (
        <label className="qms-pill" key={col.id}><input type="checkbox" checked={col.checked} onChange={col.onToggle} /> {col.label}</label>
      ))}
      {actions}
    </div>
  );
};

export default SpreadsheetToolbar;

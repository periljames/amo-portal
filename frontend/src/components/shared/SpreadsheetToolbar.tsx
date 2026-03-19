import React from "react";
import { Columns3Cog, Rows3, Rows4, UserRound, WrapText } from "lucide-react";

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
  const iconButtonClass =
    "inline-flex h-9 items-center justify-center gap-2 rounded-xl border border-slate-300/80 bg-white px-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50";
  const iconLabelClass = "hidden 2xl:inline";

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <div className="inline-flex items-center rounded-xl border border-slate-300/80 bg-white p-1 shadow-sm" role="tablist" aria-label="Row density">
        <button
          type="button"
          aria-pressed={density === "compact"}
          title="Compact density"
          className={`${iconButtonClass} h-8 border-0 px-2 ${density === "compact" ? "bg-slate-900 text-white hover:bg-slate-900" : "bg-transparent shadow-none"}`}
          onClick={() => onDensityChange("compact")}
        >
          <Rows3 className="h-4 w-4" />
          <span className={iconLabelClass}>Compact</span>
        </button>
        <button
          type="button"
          aria-pressed={density === "comfortable"}
          title="Comfortable density"
          className={`${iconButtonClass} h-8 border-0 px-2 ${density === "comfortable" ? "bg-slate-900 text-white hover:bg-slate-900" : "bg-transparent shadow-none"}`}
          onClick={() => onDensityChange("comfortable")}
        >
          <Rows4 className="h-4 w-4" />
          <span className={iconLabelClass}>Comfortable</span>
        </button>
      </div>

      <button
        type="button"
        aria-pressed={wrapText}
        title="Wrap text"
        className={`${iconButtonClass} ${wrapText ? "border-slate-900 bg-slate-900 text-white hover:bg-slate-900" : ""}`}
        onClick={() => onWrapTextChange(!wrapText)}
      >
        <WrapText className="h-4 w-4" />
        <span className={iconLabelClass}>Wrap text</span>
      </button>

      <button
        type="button"
        aria-pressed={showFilters}
        title="Header filters"
        className={`${iconButtonClass} ${showFilters ? "border-slate-900 bg-slate-900 text-white hover:bg-slate-900" : ""}`}
        onClick={() => onShowFiltersChange(!showFilters)}
      >
        <Columns3Cog className="h-4 w-4" />
        <span className={iconLabelClass}>Header filters</span>
      </button>

      {(columnToggles ?? []).map((col) => (
        <button
          key={col.id}
          type="button"
          aria-pressed={col.checked}
          title={col.label}
          className={`${iconButtonClass} ${col.checked ? "border-slate-900 bg-slate-900 text-white hover:bg-slate-900" : ""}`}
          onClick={col.onToggle}
        >
          <UserRound className="h-4 w-4" />
          <span className={iconLabelClass}>{col.label}</span>
        </button>
      ))}

      {actions}
    </div>
  );
};

export default SpreadsheetToolbar;

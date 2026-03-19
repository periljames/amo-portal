import React from "react";
import { SlidersHorizontal, Text, WrapText } from "lucide-react";
import { ResponsiveSegmentedControl } from "../qms/ResponsiveSegmentedControl";
import type { ViewDensity } from "../../hooks/useDensityPreference";

type ColumnToggle = {
  id: string;
  label: string;
  checked: boolean;
  onToggle: () => void;
};

type Props = {
  density: ViewDensity;
  onDensityChange: (density: ViewDensity) => void;
  wrapText: boolean;
  onWrapTextChange: (next: boolean) => void;
  showFilters: boolean;
  onShowFiltersChange: (next: boolean) => void;
  columnToggles?: ColumnToggle[];
  actions?: React.ReactNode;
};

const toolbarButtonClass =
  "inline-flex h-9 items-center justify-center gap-2 rounded-xl border px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

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
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/70 p-2">
      <ResponsiveSegmentedControl
        label="Row density"
        value={density}
        onChange={onDensityChange}
        options={[
          { value: "compact", label: "Compact", icon: Text },
          { value: "comfortable", label: "Comfortable", icon: SlidersHorizontal },
        ]}
        compactIconsOnMobile
      />

      <button
        type="button"
        aria-pressed={wrapText}
        onClick={() => onWrapTextChange(!wrapText)}
        className={`${toolbarButtonClass} ${wrapText ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700 hover:text-white"}`}
      >
        <WrapText className="h-4 w-4" />
        <span className="hidden sm:inline">Wrap text</span>
      </button>

      <button
        type="button"
        aria-pressed={showFilters}
        onClick={() => onShowFiltersChange(!showFilters)}
        className={`${toolbarButtonClass} ${showFilters ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700 hover:text-white"}`}
      >
        <SlidersHorizontal className="h-4 w-4" />
        <span className="hidden sm:inline">Header filters</span>
      </button>

      {(columnToggles ?? []).map((col) => (
        <button
          key={col.id}
          type="button"
          aria-pressed={col.checked}
          onClick={col.onToggle}
          className={`${toolbarButtonClass} ${col.checked ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700 hover:text-white"}`}
        >
          <span>{col.label}</span>
        </button>
      ))}

      <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
};

export default SpreadsheetToolbar;

import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";

type SegmentOption<T extends string> = {
  value: T;
  label: string;
  shortLabel?: string;
  icon: LucideIcon;
  ariaLabel?: string;
};

type Props<T extends string> = {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  compactIconsOnMobile?: boolean;
};

export function ResponsiveSegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  compactIconsOnMobile = false,
}: Props<T>) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="audit-shell-segmented"
    >
      {options.map((option) => {
        const Icon = option.icon;
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={option.ariaLabel || option.label}
            onClick={() => onChange(option.value)}
            className={clsx("audit-shell-segmented__button", active && "is-active")}
          >
            <Icon className="audit-shell-segmented__icon" />
            <span className={clsx(compactIconsOnMobile ? "audit-shell-segmented__label--mobile" : "audit-shell-segmented__label")}>{option.shortLabel || option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

import { clsx } from "clsx";
import { motion } from "framer-motion";
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
      className="inline-flex min-w-0 flex-wrap items-center gap-1 rounded-2xl border border-slate-800 bg-slate-950/80 p-1"
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
            className={clsx(
              "relative inline-flex h-10 items-center justify-center gap-2 rounded-xl px-3 text-sm font-medium leading-none whitespace-nowrap transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950",
              active ? "text-white" : "text-slate-400 hover:text-slate-100"
            )}
          >
            {active ? (
              <motion.span
                layoutId={`${label}-segment-active`}
                className="absolute inset-0 rounded-xl bg-cyan-500/20 ring-1 ring-cyan-400/40"
                transition={{ type: "spring", stiffness: 320, damping: 28 }}
              />
            ) : null}
            <Icon className="relative z-10 h-4 w-4 shrink-0" />
            <span className={clsx("relative z-10", compactIconsOnMobile ? "hidden sm:inline" : "inline")}>{option.shortLabel || option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

import React from "react";
import { GlassPanel, type GlassPanelProps } from "./GlassPanel";

type GlassCardProps = Omit<GlassPanelProps, "preset"> & {
  preset?: "panel" | "kpiCard" | "loginCard" | "sidebarPanel";
};

const GlassCardComponent: React.FC<GlassCardProps> = ({ preset = "panel", ...props }) => {
  return <GlassPanel preset={preset} {...props} />;
};

export const GlassCard = React.memo(GlassCardComponent);

export type { GlassCardProps };

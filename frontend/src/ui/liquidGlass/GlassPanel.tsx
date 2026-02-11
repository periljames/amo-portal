import React from "react";
import { clsx } from "clsx";
import { LiquidGlassContainer } from "@tinymomentum/liquid-glass-react";
import {
  LIQUID_GLASS_CONTAINER_PRESETS,
  LIQUID_GLASS_PADDING,
  type GlassContainerPresetKey,
  type LiquidGlassVisualProps,
} from "./presets";

type GlassPanelProps = {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  contentClassName?: string;
  preset?: GlassContainerPresetKey;
  padding?: number;
  glassProps?: LiquidGlassVisualProps;
};

const GlassPanelComponent: React.FC<GlassPanelProps> = ({
  children,
  className,
  style,
  contentClassName,
  preset = "panel",
  padding,
  glassProps,
}) => {
  const mergedProps = {
    ...LIQUID_GLASS_CONTAINER_PRESETS[preset],
    ...glassProps,
  };

  return (
    <div className={clsx("glass-panel", className)} style={style}>
      <LiquidGlassContainer className="glass-panel__surface" {...mergedProps}>
        <div
          className={clsx("glass-panel__inner", contentClassName)}
          style={{ padding: padding ?? LIQUID_GLASS_PADDING[preset] }}
        >
          {children}
        </div>
      </LiquidGlassContainer>
    </div>
  );
};

export const GlassPanel = React.memo(GlassPanelComponent);

export type { GlassPanelProps };

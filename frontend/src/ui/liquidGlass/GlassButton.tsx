import React from "react";
import { clsx } from "clsx";
import { LiquidGlassButton } from "@tinymomentum/liquid-glass-react";
import {
  LIQUID_GLASS_BUTTON_PRESETS,
  type GlassButtonPresetKey,
  type LiquidGlassVisualProps,
} from "./presets";

type GlassButtonProps = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "style"> & {
  className?: string;
  style?: React.CSSProperties;
  preset?: GlassButtonPresetKey;
  glassProps?: LiquidGlassVisualProps;
};

const GlassButtonComponent = React.forwardRef<HTMLButtonElement, GlassButtonProps>(
  ({ className, style, preset = "ctaButton", glassProps, children, disabled, type = "button", ...rest }, ref) => {
    const mergedProps = {
      ...LIQUID_GLASS_BUTTON_PRESETS[preset],
      ...glassProps,
    };

    return (
      <LiquidGlassButton
        {...mergedProps}
        {...rest}
        className={clsx("glass-button", className, disabled && "glass-button--disabled")}
        style={style}
        ref={ref as React.Ref<HTMLElement>}
        role="button"
        aria-disabled={disabled}
        type={type}
        tabIndex={disabled ? -1 : 0}
      >
        {children}
      </LiquidGlassButton>
    );
  }
);

GlassButtonComponent.displayName = "GlassButton";

export const GlassButton = React.memo(GlassButtonComponent);

export type { GlassButtonProps };

import React from "react";
import { clsx } from "clsx";
import { LiquidGlassLink } from "@tinymomentum/liquid-glass-react";
import {
  LIQUID_GLASS_LINK_PRESETS,
  type GlassLinkPresetKey,
  type LiquidGlassVisualProps,
} from "./presets";

type GlassLinkProps = {
  href?: string;
  target?: "_self" | "_blank" | "_parent" | "_top";
  rel?: string;
  onClick?: React.MouseEventHandler<HTMLAnchorElement>;
  className?: string;
  style?: React.CSSProperties;
  preset?: GlassLinkPresetKey;
  glassProps?: LiquidGlassVisualProps;
  children: React.ReactNode;
};

const GlassLinkComponent = React.forwardRef<HTMLAnchorElement, GlassLinkProps>(
  ({ href, target, rel, className, style, preset = "link", glassProps, children, ...rest }, ref) => {
    const mergedProps = {
      ...LIQUID_GLASS_LINK_PRESETS[preset],
      ...glassProps,
    };
    const computedRel = target === "_blank" ? rel ?? "noreferrer noopener" : rel;

    return (
      <LiquidGlassLink
        {...mergedProps}
        {...rest}
        href={href}
        target={target}
        rel={computedRel}
        className={clsx("glass-link", className)}
        style={style}
        ref={ref as React.Ref<HTMLElement>}
      >
        {children}
      </LiquidGlassLink>
    );
  }
);

GlassLinkComponent.displayName = "GlassLink";

export const GlassLink = React.memo(GlassLinkComponent);

export type { GlassLinkProps };

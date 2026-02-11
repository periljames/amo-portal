declare module "@tinymomentum/liquid-glass-react" {
  import type * as React from "react";

  export type LiquidGlassBaseProps = {
    elementType?: "div" | "button" | "a" | "span" | "p";
    href?: string;
    target?: "_self" | "_blank" | "_parent" | "_top";
    rel?: string;
    download?: string | boolean;
    width?: number;
    height?: number;
    borderRadius?: number;
    innerShadowColor?: string;
    innerShadowBlur?: number;
    innerShadowSpread?: number;
    glassTintColor?: string;
    glassTintOpacity?: number;
    frostBlurRadius?: number;
    noiseFrequency?: number;
    noiseStrength?: number;
    children?: React.ReactNode;
    style?: React.CSSProperties;
    className?: string;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
  } & React.HTMLAttributes<HTMLElement>;

  export const LiquidGlassContainer: React.ForwardRefExoticComponent<
    Omit<LiquidGlassBaseProps, "elementType"> & React.RefAttributes<HTMLElement>
  >;

  export const LiquidGlassButton: React.ForwardRefExoticComponent<
    Omit<LiquidGlassBaseProps, "elementType"> & React.RefAttributes<HTMLElement>
  >;

  export const LiquidGlassLink: React.ForwardRefExoticComponent<
    Omit<LiquidGlassBaseProps, "elementType"> & {
      href?: string;
      target?: "_self" | "_blank" | "_parent" | "_top";
      rel?: string;
      download?: string | boolean;
    } & React.RefAttributes<HTMLElement>
  >;
}

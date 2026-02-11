export type LiquidGlassVisualProps = {
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
};

export type GlassContainerPresetKey = "panel" | "sidebarPanel" | "kpiCard" | "loginCard";
export type GlassButtonPresetKey = "ctaButton";
export type GlassLinkPresetKey = "link";

export const LIQUID_GLASS_CONTAINER_PRESETS: Record<GlassContainerPresetKey, LiquidGlassVisualProps> = {
  panel: {
    borderRadius: 24,
    innerShadowColor: "rgba(255, 255, 255, 0.55)",
    innerShadowBlur: 18,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 14,
    frostBlurRadius: 2,
    noiseFrequency: 0.009,
    noiseStrength: 78,
  },
  sidebarPanel: {
    borderRadius: 26,
    innerShadowColor: "rgba(255, 255, 255, 0.6)",
    innerShadowBlur: 20,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 18,
    frostBlurRadius: 3,
    noiseFrequency: 0.009,
    noiseStrength: 82,
  },
  kpiCard: {
    borderRadius: 22,
    innerShadowColor: "rgba(255, 255, 255, 0.52)",
    innerShadowBlur: 18,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 12,
    frostBlurRadius: 2,
    noiseFrequency: 0.009,
    noiseStrength: 72,
  },
  loginCard: {
    borderRadius: 28,
    innerShadowColor: "rgba(255, 255, 255, 0.65)",
    innerShadowBlur: 20,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 12,
    frostBlurRadius: 3,
    noiseFrequency: 0.009,
    noiseStrength: 54,
  },
};

export const LIQUID_GLASS_BUTTON_PRESETS: Record<GlassButtonPresetKey, LiquidGlassVisualProps> = {
  ctaButton: {
    borderRadius: 32,
    innerShadowColor: "rgba(255, 255, 255, 0.5)",
    innerShadowBlur: 18,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 34,
    frostBlurRadius: 3,
    noiseFrequency: 0.009,
    noiseStrength: 52,
  },
};

export const LIQUID_GLASS_LINK_PRESETS: Record<GlassLinkPresetKey, LiquidGlassVisualProps> = {
  link: {
    borderRadius: 24,
    innerShadowColor: "rgba(255, 255, 255, 0.5)",
    innerShadowBlur: 16,
    innerShadowSpread: -6,
    glassTintColor: "#ffffff",
    glassTintOpacity: 18,
    frostBlurRadius: 2,
    noiseFrequency: 0.009,
    noiseStrength: 40,
  },
};

export const LIQUID_GLASS_PADDING: Record<GlassContainerPresetKey, number> = {
  panel: 18,
  sidebarPanel: 18,
  kpiCard: 14,
  loginCard: 26,
};

export const outerShellPreset: LiquidGlassVisualProps = {
  borderRadius: 32,
  innerShadowColor: "rgba(255,255,255,0.55)",
  innerShadowBlur: 18,
  innerShadowSpread: -8,
  glassTintColor: "#ffffff",
  glassTintOpacity: 10,
  frostBlurRadius: 1,
  noiseFrequency: 0.009,
  noiseStrength: 42,
};

export const illustrationFramePreset: LiquidGlassVisualProps = {
  borderRadius: 28,
  innerShadowColor: "rgba(255,255,255,0.5)",
  innerShadowBlur: 16,
  innerShadowSpread: -8,
  glassTintColor: "#ffffff",
  glassTintOpacity: 12,
  frostBlurRadius: 1,
  noiseFrequency: 0.009,
  noiseStrength: 56,
};

export const socialButtonPreset: LiquidGlassVisualProps = {
  borderRadius: 15,
  innerShadowColor: "rgba(255,255,255,0.52)",
  innerShadowBlur: 12,
  innerShadowSpread: -5,
  glassTintColor: "#ffffff",
  glassTintOpacity: 14,
  frostBlurRadius: 1,
  noiseFrequency: 0.009,
  noiseStrength: 64,
};

export const primaryButtonPreset: LiquidGlassVisualProps = {
  borderRadius: 13,
  innerShadowColor: "rgba(255,255,255,0.35)",
  innerShadowBlur: 14,
  innerShadowSpread: -6,
  glassTintColor: "#a27384",
  glassTintOpacity: 64,
  frostBlurRadius: 1,
  noiseFrequency: 0.0085,
  noiseStrength: 32,
};

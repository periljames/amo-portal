export const resolveLoaderContrast = ({
  requested = "normal",
  prefersContrastMore = false,
  forcedColors = false,
  rootHighContrastClass = false,
}) => {
  if (requested === "high") return "high";
  if (requested === "normal") {
    if (prefersContrastMore || forcedColors || rootHighContrastClass) return "high";
    return "normal";
  }
  return "normal";
};

export const detectSystemContrastPreference = () => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return { prefersContrastMore: false, forcedColors: false };
  }
  const prefersContrastMore = window.matchMedia("(prefers-contrast: more)").matches;
  const forcedColors = window.matchMedia("(forced-colors: active)").matches;
  return { prefersContrastMore, forcedColors };
};

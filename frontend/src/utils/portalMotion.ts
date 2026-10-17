/** Use the same explicit/system preference as the appearance settings. */
export function portalScrollBehavior(): ScrollBehavior {
  if (typeof document === "undefined") return "auto";
  const mode = document.documentElement.dataset.portalMotion || document.body.dataset.portalMotion;
  const reduced = mode === "reduced" || (mode !== "full" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  return reduced ? "instant" : "smooth";
}

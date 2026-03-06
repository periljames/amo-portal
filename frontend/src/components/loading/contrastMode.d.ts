export function resolveLoaderContrast(input: {
  requested?: "normal" | "high";
  prefersContrastMore?: boolean;
  forcedColors?: boolean;
  rootHighContrastClass?: boolean;
}): "normal" | "high";

export function detectSystemContrastPreference(): {
  prefersContrastMore: boolean;
  forcedColors: boolean;
};

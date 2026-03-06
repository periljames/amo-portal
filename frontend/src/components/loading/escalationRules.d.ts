import type { LoadingTask } from "./GlobalLoadingProvider";

export const LOADER_ESCALATION: {
  inlineMs: number;
  shortMs: number;
  sectionMs: number;
  overlayMs: number;
  longWaitMs: number;
};

export function pickLoaderPresentation(
  task: Pick<LoadingTask, "allow_overlay" | "mode_preference" | "affects_route">,
  elapsedMs: number
): {
  mode: "inline" | "section" | "page" | "overlay" | "auto";
  showDock: boolean;
  showOverlay: boolean;
  showLongWaitHint: boolean;
};

export function shouldClearTaskOnRouteChange(task: Pick<LoadingTask, "persistent">): boolean;

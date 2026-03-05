export const LOADER_ESCALATION = {
  inlineMs: 0,
  shortMs: 250,
  sectionMs: 700,
  overlayMs: 2500,
  longWaitMs: 9000,
};

export const pickLoaderPresentation = (task, elapsedMs) => {
  const modePreference = task.mode_preference || "auto";
  const base = {
    mode: "inline",
    showDock: elapsedMs >= LOADER_ESCALATION.shortMs,
    showOverlay: false,
    showLongWaitHint: elapsedMs >= LOADER_ESCALATION.longWaitMs,
  };

  if (modePreference !== "auto") {
    return {
      ...base,
      mode: modePreference,
      showOverlay: modePreference === "overlay" && elapsedMs >= LOADER_ESCALATION.overlayMs,
      showDock: modePreference !== "page",
    };
  }

  if (task.affects_route) {
    if (elapsedMs >= LOADER_ESCALATION.overlayMs && task.allow_overlay) {
      return { ...base, mode: "overlay", showDock: true, showOverlay: true };
    }
    return { ...base, mode: "page", showDock: elapsedMs >= LOADER_ESCALATION.sectionMs, showOverlay: false };
  }

  if (elapsedMs >= LOADER_ESCALATION.overlayMs && task.allow_overlay) {
    return { ...base, mode: "overlay", showDock: true, showOverlay: true };
  }

  if (elapsedMs >= LOADER_ESCALATION.sectionMs) {
    return { ...base, mode: "section", showDock: true, showOverlay: false };
  }

  if (elapsedMs >= LOADER_ESCALATION.shortMs) {
    return { ...base, mode: "inline", showDock: true, showOverlay: false };
  }

  return { ...base, mode: "inline", showDock: false, showOverlay: false };
};


export const shouldClearTaskOnRouteChange = (task) => !task.persistent;

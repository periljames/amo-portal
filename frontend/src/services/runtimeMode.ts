export const LS_PORTAL_GO_LIVE = "amodb_portal_go_live";
export const PORTAL_RUNTIME_MODE_EVENT = "amodb:runtime-mode";

const readFlag = (): boolean => {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(LS_PORTAL_GO_LIVE) === "1";
};

const writeFlag = (enabled: boolean) => {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_PORTAL_GO_LIVE, enabled ? "1" : "0");
  window.dispatchEvent(new Event(PORTAL_RUNTIME_MODE_EVENT));
};

export const isPortalGoLive = (): boolean => readFlag();

export const setPortalGoLive = (enabled: boolean) => {
  writeFlag(enabled);
};

export const shouldUseMockData = (): boolean => !readFlag();

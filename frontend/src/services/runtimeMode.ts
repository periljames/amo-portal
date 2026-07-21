export const LS_PORTAL_GO_LIVE = "amodb_portal_go_live";
export const LS_PORTAL_DATA_MODE = "amodb_portal_data_mode";
export const PORTAL_RUNTIME_MODE_EVENT = "amodb:runtime-mode";

export type PortalDataMode = "REAL" | "DEMO";

const normaliseDataMode = (value: string | null | undefined): PortalDataMode | null => {
  const clean = (value || "").trim().toUpperCase();
  if (clean === "DEMO") return "DEMO";
  if (clean === "REAL" || clean === "LIVE") return "REAL";
  return null;
};

const dispatchModeEvent = () => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(PORTAL_RUNTIME_MODE_EVENT));
};

const readDataMode = (): PortalDataMode => {
  if (typeof window === "undefined") return "REAL";
  const explicit = normaliseDataMode(localStorage.getItem(LS_PORTAL_DATA_MODE));
  if (explicit) return explicit;

  // Earlier frontend builds treated a missing go-live flag as DEMO. That caused
  // live tenants to show DEMO after login. The safe default is now REAL unless
  // the authenticated AMO context explicitly says DEMO.
  const legacyGoLive = localStorage.getItem(LS_PORTAL_GO_LIVE);
  if (legacyGoLive === "0") return "REAL";
  return "REAL";
};

const writeDataMode = (mode: PortalDataMode) => {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_PORTAL_DATA_MODE, mode);
  localStorage.setItem(LS_PORTAL_GO_LIVE, mode === "DEMO" ? "0" : "1");
  dispatchModeEvent();
};

export const getPortalDataMode = (): PortalDataMode => readDataMode();

export const isPortalDemoMode = (): boolean => readDataMode() === "DEMO";

export const isPortalGoLive = (): boolean => !isPortalDemoMode();

export const setPortalDataMode = (mode: PortalDataMode | "LIVE") => {
  writeDataMode(mode === "DEMO" ? "DEMO" : "REAL");
};

export const setPortalGoLive = (enabled: boolean) => {
  writeDataMode(enabled ? "REAL" : "DEMO");
};

export const shouldUseMockData = (): boolean => isPortalDemoMode();

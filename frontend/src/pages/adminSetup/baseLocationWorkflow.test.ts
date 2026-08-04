import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { AirportCatalogItem, BaseStationRead } from "../../types/foundations";
import {
  airportMatch,
  uniqueFacilityCode,
} from "./BaseStationEditorDialogV2";

const routedEditor = readFileSync(new URL("./BaseStationEditorDialog.tsx", import.meta.url), "utf8");
const editorSource = readFileSync(new URL("./BaseStationEditorDialogV2.tsx", import.meta.url), "utf8");
const compatSource = readFileSync(new URL("./BaseStationEditorDialogCompat.tsx", import.meta.url), "utf8");
const mapSource = readFileSync(new URL("./GoogleBaseLocationPicker.tsx", import.meta.url), "utf8");
const navigatorSource = readFileSync(new URL("./AdminSetupWorkflowNavigator.tsx", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../../styles/admin-setup-location-v2.css", import.meta.url), "utf8");

const jkia: AirportCatalogItem = {
  ident: "HKJK",
  name: "Jomo Kenyatta International Airport",
  municipality: "Nairobi",
  iso_country: "KE",
  icao_code: "HKJK",
  iata_code: "NBO",
  latitude: -1.319167,
  longitude: 36.927778,
  source: "OURAIRPORTS",
};

function base(overrides: Partial<BaseStationRead>): BaseStationRead {
  return {
    id: "base-1",
    amo_id: "amo-1",
    code: "NBO",
    name: "Existing Nairobi Base",
    base_type: "MAIN_BASE",
    location_configured: false,
    geofence_radius_m: 250,
    checkin_prompt_enabled: false,
    checkout_reminder_enabled: false,
    suspicious_location_review_enabled: false,
    is_active: true,
    aliases: [],
    created_at: "2026-08-04T00:00:00Z",
    updated_at: "2026-08-04T00:00:00Z",
    ...overrides,
  };
}

describe("base identity and location workflow", () => {
  it("keeps aerodrome codes separate from the unique facility code", () => {
    expect(uniqueFacilityCode(jkia, "MAIN_BASE", [base({ code: "NBO" })])).toBe("NBO-HQ");
    expect(uniqueFacilityCode(jkia, "HANGAR", [base({ code: "NBO-HGR" })])).toBe("NBO-HGR-2");
    expect(editorSource).not.toContain("draft.code.trim() || item.iata_code");
    expect(editorSource).toContain("ICAO/IATA identify the aerodrome");
  });

  it("recognises and updates an existing base at the selected aerodrome", () => {
    expect(airportMatch(jkia, base({ icao_code: "HKJK", iata_code: "NBO" }))).toBe(true);
    expect(editorSource).toContain("onEditExisting(matchingBase)");
    expect(compatSource).toContain("updateBaseStation(selectedExisting.id");
    expect(compatSource).toContain("listBaseStations({ include_inactive: true })");
  });

  it("restores the captured superuser tenant before the existing-base PUT", () => {
    expect(compatSource).toContain("tenantContextRef.current = context");
    expect(compatSource).toContain("await setAdminContext({");
    const syncIndex = compatSource.lastIndexOf("await setAdminContext({");
    const updateIndex = compatSource.indexOf("await updateBaseStation(selectedExisting.id");
    expect(syncIndex).toBeGreaterThan(-1);
    expect(updateIndex).toBeGreaterThan(syncIndex);
  });

  it("routes the existing setup page through the location-first editor", () => {
    expect(routedEditor).toContain('from "./BaseStationEditorDialogCompat"');
    expect(routedEditor).not.toContain("const code = draft.code.trim()");
  });

  it("keeps the base stage active until the loaded summary confirms all bases are located", () => {
    expect(navigatorSource).toContain('"needs-location"');
    expect(navigatorSource).toContain("summary.match");
    expect(navigatorSource).toContain('params.set("section", "bases")');
    expect(navigatorSource).toContain('params.set("section", "departments")');
  });

  it("keeps the navigation portal mounted while observing its host", () => {
    expect(navigatorSource).toContain("setPortalTarget((current) => current === body ? current : body)");
    expect(navigatorSource).not.toContain('body?.querySelector(".setup-resend__step-navigation") ? null : body');
  });

  it("moves each opened stage into view and provides skip and continue controls", () => {
    expect(navigatorSource).toContain("scrollIntoView");
    expect(navigatorSource).toContain("Skip for now");
    expect(navigatorSource).toContain("Continue");
    expect(navigatorSource).toContain("createPortal");
  });

  it("supports Google place selection and an accessible draggable pin", () => {
    expect(mapSource).toContain("VITE_GOOGLE_MAPS_API_KEY");
    expect(mapSource).toContain("PlaceAutocompleteElement");
    expect(mapSource).toContain('addEventListener("gmp-select"');
    expect(mapSource).toContain("gmpDraggable: true");
    expect(mapSource).toContain('addListener("dragend"');
    expect(mapSource).toContain('addListener("click"');
  });

  it("shows a marker only after the draft has a real position", () => {
    expect(mapSource).toContain("...(configuredPosition ? { map, position: configuredPosition } : {})");
    expect(mapSource).toContain("marker.map = map");
    expect(mapSource).toContain("markerRef.current.map = null");
    expect(mapSource).not.toContain("position: initialPosition,");
  });

  it("keeps placeholders subordinate and notifications above the modal", () => {
    expect(cssSource).toContain("opacity: 0.42 !important");
    expect(cssSource).toContain("font-style: italic");
    expect(cssSource).toContain("z-index: 15100 !important");
    expect(cssSource).toContain("min-height: clamp(310px, 42vh, 430px)");
  });
});

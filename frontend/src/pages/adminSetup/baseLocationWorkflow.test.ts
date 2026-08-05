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
const pageSource = readFileSync(new URL("../AdminSetupCentreResendPage.tsx", import.meta.url), "utf8");
const v2PageSource = readFileSync(new URL("../AdminSetupCentreV2Page.tsx", import.meta.url), "utf8");
const foundationServiceSource = readFileSync(new URL("../../services/foundations.ts", import.meta.url), "utf8");
const pageScopeSource = readFileSync(new URL("../../services/adminPageTenantScope.ts", import.meta.url), "utf8");
const httpSource = readFileSync(new URL("../../services/crs.ts", import.meta.url), "utf8");
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

  it("uses an authoritative live register and never substitutes stale setup data", () => {
    expect(httpSource).toContain('cache: offline?.cache ?? method === "GET"');
    expect(foundationServiceSource).toContain("cache: false");
    expect(foundationServiceSource).toContain("allowStaleFallback: false");
    expect(foundationServiceSource).toContain("requiredBaseIdentityScope");
    expect(foundationServiceSource).toContain("No base change was sent");
    expect(foundationServiceSource).not.toContain("if (bases) assertIdentityAvailable");
  });

  it("binds every base request to the latest page-selected AMO for this browser tab", () => {
    expect(pageScopeSource).toContain("window.sessionStorage");
    expect(pageScopeSource).toContain("user_id");
    expect(pageScopeSource).toContain("active_amo_id");
    expect(pageScopeSource).toContain("latestAttemptSequence");
    expect(pageScopeSource).toContain("beginAdminPageTenantScope");
    expect(pageScopeSource).toContain("completeAdminPageTenantScope");
    expect(httpSource).toContain('path === "/accounts/admin/context"');
    expect(httpSource).toContain("beginAdminPageTenantScope(body)");
    expect(httpSource).toContain("completeAdminPageTenantScope(contextAttempt, result)");
    for (const source of [pageSource, v2PageSource]) {
      expect(source).toContain("setAdminContext({");
      expect(source).toContain("active_amo_id: selected.id");
    }
    expect(foundationServiceSource).toContain('const AMO_CONTEXT_HEADER = "X-AMO-Context-Id"');
    expect(foundationServiceSource).toContain("readAdminPageTenantScope");
    expect(foundationServiceSource).toContain("captureBaseStationRequestScope");
    expect(foundationServiceSource).toContain("validateBaseStationRequestScope");
    expect(foundationServiceSource).toContain("const requestScope = resolvedRequestScope");
    expect(foundationServiceSource).toContain("assertRegisterTenant(items, requestScope)");
    expect(foundationServiceSource).toContain("baseWriteKey(\"create\", null, payload, requestScope)");
    expect(foundationServiceSource).toContain("assertResponseTenant(created, requestScope)");
    expect(foundationServiceSource).not.toContain("knownBaseAmoScopes");
    expect(foundationServiceSource).not.toContain("resolvedUpdateScope");
    expect(compatSource).toContain("tenantScopeRef");
    expect(compatSource).toContain("captureBaseStationRequestScope()");
    expect(compatSource).toContain("validateBaseStationRequestScope(tenantScopeRef.current)");
    expect(compatSource).not.toContain("getAdminContext");
    expect(compatSource).not.toContain("setAdminContext");
  });

  it("rechecks the live register on every save and recovers write-time conflicts", () => {
    expect(compatSource).toContain("const liveBases = await loadLiveBaseRegister()");
    expect(compatSource).toContain("identityConflictFromError(cause)");
    expect(compatSource).toContain("await openConflictOwner(writeConflict)");
    expect(compatSource).toContain("setSelectedExisting(existing)");
    expect(compatSource).toContain("onChange(draftFromBase(existing))");
  });

  it("opens the complete existing record for full modification", () => {
    for (const field of [
      "code: base.code",
      "name: base.name",
      "icao_code: base.icao_code",
      "iata_code: base.iata_code",
      "base_type: base.base_type",
      "time_zone: base.time_zone",
      "description: base.description",
      "aliases: (base.aliases",
      "latitude: base.latitude",
      "longitude: base.longitude",
      "coordinate_accuracy_m: base.coordinate_accuracy_m",
      "location_source: base.location_source",
      "airport_reference_ident: base.airport_reference_ident",
      "geofence_radius_m: String(base.geofence_radius_m",
      "checkin_prompt_enabled: base.checkin_prompt_enabled",
      "checkout_reminder_enabled: base.checkout_reminder_enabled",
      "suspicious_location_review_enabled: base.suspicious_location_review_enabled",
      "is_active: base.is_active",
    ]) {
      expect(compatSource).toContain(field);
    }
    expect(compatSource).toContain("await updateBaseStation(current.id, payload, scope)");
    expect(pageSource).toContain("startBase(base)");
    expect(pageSource).toContain("Deactivate");
    expect(pageSource).toContain("Reactivate");
  });

  it("recognises and updates an existing base at the selected aerodrome", () => {
    expect(airportMatch(jkia, base({ icao_code: "HKJK", iata_code: "NBO" }))).toBe(true);
    expect(editorSource).toContain("onEditExisting(matchingBase)");
    expect(compatSource).toContain("updateBaseStation(current.id");
    expect(compatSource).toContain("listBaseStations({");
    expect(compatSource).toContain("include_inactive: true");
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

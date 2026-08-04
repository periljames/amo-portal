import { describe, expect, it } from "vitest";

import {
  baseStationIdentityConflictMessage,
  findBaseStationIdentityConflict,
} from "./foundationBaseIdentity";
import type { BaseStationRead } from "../types/foundations";

function base(overrides: Partial<BaseStationRead> = {}): BaseStationRead {
  return {
    id: "base-nbo",
    amo_id: "amo-1",
    code: "NBO-HQ",
    name: "Nairobi Main Base",
    base_type: "MAIN_BASE",
    location_configured: false,
    geofence_radius_m: 250,
    checkin_prompt_enabled: false,
    checkout_reminder_enabled: false,
    suspicious_location_review_enabled: false,
    is_active: true,
    aliases: [{
      id: "alias-hq",
      amo_id: "amo-1",
      base_station_id: "base-nbo",
      alias: "HQ",
      created_at: "2026-08-04T00:00:00Z",
    }],
    created_at: "2026-08-04T00:00:00Z",
    updated_at: "2026-08-04T00:00:00Z",
    ...overrides,
  };
}

describe("base station identity conflicts", () => {
  it("detects base codes case-insensitively", () => {
    const conflict = findBaseStationIdentityConflict(
      [base()],
      { code: " nbo-hq ", aliases: [] },
    );

    expect(conflict).toMatchObject({
      field: "code",
      requestedValue: "nbo-hq",
      existingKind: "code",
      existingValue: "NBO-HQ",
    });
    expect(baseStationIdentityConflictMessage(conflict!)).toContain("NBO-HQ · Nairobi Main Base");
  });

  it("detects an alias that collides with another base code", () => {
    const conflict = findBaseStationIdentityConflict(
      [base()],
      { code: "NBO-HGR", aliases: ["nbo-hq"] },
    );

    expect(conflict).toMatchObject({
      field: "aliases",
      requestedValue: "nbo-hq",
      existingKind: "code",
    });
  });

  it("detects a code that collides with an existing alias", () => {
    const conflict = findBaseStationIdentityConflict(
      [base()],
      { code: "hq", aliases: [] },
    );

    expect(conflict).toMatchObject({
      field: "code",
      existingKind: "alias",
      existingValue: "HQ",
    });
  });

  it("points users to inactive records instead of creating duplicates", () => {
    const conflict = findBaseStationIdentityConflict(
      [base({ is_active: false })],
      { code: "NBO-HQ", aliases: [] },
    );

    expect(baseStationIdentityConflictMessage(conflict!)).toContain("inactive");
    expect(baseStationIdentityConflictMessage(conflict!)).toContain("reactivate or edit");
  });

  it("excludes the record currently being edited", () => {
    const conflict = findBaseStationIdentityConflict(
      [base()],
      { code: "NBO-HQ", aliases: ["HQ"] },
      "base-nbo",
    );

    expect(conflict).toBeNull();
  });

  it("does not treat shared airport codes as base identity collisions", () => {
    const conflict = findBaseStationIdentityConflict(
      [base({ icao_code: "HKJK", iata_code: "NBO" })],
      { code: "NBO-HGR", aliases: ["Hangar 2"] },
    );

    expect(conflict).toBeNull();
  });
});

import { describe, expect, it } from "vitest";

import {
  fieldHistoryAreaFromEntity,
  fieldHistoryStorageKey,
  historyEntriesFromValue,
  mergeFieldHistory,
  rankHistoryByFrequency,
} from "./useTextFieldHistory";

describe("useTextFieldHistory helpers", () => {
  it("splits multi-line values into history entries", () => {
    expect(
      historyEntriesFromValue("Plan assurance audits.\n\nCover hangar and line."),
    ).toEqual(["Plan assurance audits.", "Cover hangar and line."]);
  });

  it("merges newest entries first without case duplicates", () => {
    expect(
      mergeFieldHistory(
        ["Older line", "Shared line"],
        ["Shared line", "Newest line"],
        3,
      ),
    ).toEqual(["Shared line", "Newest line", "Older line"]);
  });

  it("scopes storage keys by tenant first, then audit area", () => {
    const aircraft = fieldHistoryStorageKey("safarilink", "audit-scope", "AIRCRAFT");
    const station = fieldHistoryStorageKey("safarilink", "audit-scope", "STATION");
    const otherTenant = fieldHistoryStorageKey("other", "audit-scope", "AIRCRAFT");
    expect(aircraft).toContain(":SAFARILINK:");
    expect(aircraft).toContain(":AIRCRAFT:");
    expect(aircraft).not.toBe(station);
    expect(aircraft).not.toBe(otherTenant);
    expect(fieldHistoryAreaFromEntity("STATION")).toBe("STATION");
    expect(fieldHistoryAreaFromEntity("AIRCRAFT_TYPE")).toBe("AIRCRAFT_TYPE");
  });

  it("ranks often-used area lines ahead of one-offs", () => {
    expect(
      rankHistoryByFrequency(
        ["Hangar scope", "Line station scope", "Hangar scope", "Hangar scope"],
        2,
      ),
    ).toEqual(["Hangar scope", "Line station scope"]);
  });
});

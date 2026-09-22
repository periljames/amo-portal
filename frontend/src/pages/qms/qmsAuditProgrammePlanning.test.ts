import { describe, expect, it } from "vitest";

import {
  aircraftRegistrationSuffix,
  auditMonthPlanningMode,
  auditTypeForEntity,
  findAuditorScheduleCollisions,
  ordinalDayLabel,
  programmeLeadAuditorOptions,
  programmeMatrixSlotLabel,
  resolveAircraftRegistration,
  suggestedLocationCode,
  uniqueAuditorInitials,
  withoutLeadAuditor,
  workingDayCount,
} from "./qmsAuditProgrammePlanning";

describe("audit programme planning rules", () => {
  it("derives immutable audit types from the selected audit area", () => {
    expect(auditTypeForEntity("FACILITY")).toBe("FACILITY");
    expect(auditTypeForEntity("STATION")).toBe("FACILITY");
    expect(auditTypeForEntity("AIRCRAFT")).toBe("PRODUCT");
    expect(auditTypeForEntity("CONTRACTOR")).toBe("CONTRACTED_FUNCTION");
  });

  it("derives working-day duration from the planned date range", () => {
    expect(workingDayCount("2026-09-08", "2026-09-09")).toBe(2);
    expect(workingDayCount("2026-09-11", "2026-09-14")).toBe(2);
    expect(workingDayCount("2026-09-12", "2026-09-12")).toBe(1);
  });

  it("prefers lead auditors and falls back to auditors when none exist", () => {
    const people = [
      { id: "a", auditor_roles: ["AUDITOR"] },
      { id: "b", auditor_roles: ["LEAD_AUDITOR"] },
      { id: "c", auditor_roles: [] },
    ];
    expect(programmeLeadAuditorOptions(people).map((row) => row.id)).toEqual([
      "b",
    ]);
    expect(
      programmeLeadAuditorOptions([
        { id: "a", auditor_roles: ["AUDITOR"] },
        { id: "c", auditor_roles: ["OBSERVER_AUDITOR"] },
      ]).map((row) => row.id),
    ).toEqual(["a", "c"]);
    expect(programmeLeadAuditorOptions([{ id: "c", auditor_roles: [] }])).toEqual(
      [],
    );
  });

  it("preserves an existing one-time audit when another month is selected", () => {
    expect(
      auditMonthPlanningMode(
        {
          recurrence: "ONE_TIME",
          fixed_dates: [],
          target_start: "2026-09-08",
        },
        11,
      ),
    ).toBe("create");
    expect(
      auditMonthPlanningMode(
        {
          recurrence: "ONE_TIME",
          fixed_dates: [],
          target_start: "2026-09-08",
        },
        9,
      ),
    ).toBe("update");
    expect(
      auditMonthPlanningMode(
        {
          recurrence: "FIXED_DATES",
          fixed_dates: ["09-08"],
          target_start: "2026-09-08",
        },
        11,
      ),
    ).toBe("update");
    expect(
      auditMonthPlanningMode(
        {
          recurrence: "MONTHLY",
          fixed_dates: [],
          target_start: "2026-09-08",
        },
        11,
      ),
    ).toBe("update");
  });

  it("suggests a tenant location that matches the selected area", () => {
    const locations = [
      {
        id: "base",
        code: "NBO",
        name: "Nairobi Base",
        location_type: "MAIN_BASE",
      },
      {
        id: "hangar",
        code: "HGR-1",
        name: "Main Hangar",
        location_type: "HANGAR",
      },
      {
        id: "line",
        code: "MBA",
        name: "Mombasa Line Station",
        location_type: "LINE_STATION",
      },
    ];
    expect(
      suggestedLocationCode(
        { entity_type: "FACILITY", display_label: "Hangar" } as never,
        locations,
      ),
    ).toBe("HGR-1");
    expect(
      suggestedLocationCode(
        { entity_type: "STATION", display_label: "Line stations" } as never,
        locations,
      ),
    ).toBe("MBA");
  });

  it("keeps the lead and observer out of the supporting team", () => {
    expect(
      withoutLeadAuditor(
        ["lead", "observer", "second", "second"],
        "lead",
        "observer",
      ),
    ).toEqual(["second"]);
  });

  it("creates stable unique initials and advances on collisions", () => {
    const initials = uniqueAuditorInitials([
      { id: "james", fullName: "James Muisyo" },
      { id: "elvin", fullName: "Elvin Kinanga" },
      { id: "francis", fullName: "Francis Muriuki" },
      { id: "joseph", fullName: "Joseph Maina" },
      { id: "john", fullName: "John Mugo" },
    ]);

    expect(initials.get("elvin")).toBe("EK");
    expect(initials.get("francis")).toBe("FM");
    expect(initials.get("james")).toBe("JM");
    expect(initials.get("john")).toBe("MJ");
    expect(initials.get("joseph")).toBe("JA");
    expect(new Set(initials.values()).size).toBe(5);
  });

  it("uses the compact aircraft tail suffix and ordinal date label", () => {
    expect(aircraftRegistrationSuffix("5Y-SLN")).toBe("SLN");
    expect(aircraftRegistrationSuffix(" 5y sln ")).toBe("SLN");
    expect(ordinalDayLabel("1–2")).toBe("1st–2nd");
    expect(ordinalDayLabel("11→13")).toBe("11th→13th");
  });

  it("shows aircraft registration on product matrix chips instead of dates", () => {
    expect(
      resolveAircraftRegistration({
        title: "5Y-SLL",
        scope: null,
        audit_type: "PRODUCT",
        auditable_entity: {
          entity_type: "AIRCRAFT_TYPE",
          display_label: "Aircraft / product audits",
          aircraft: { tail_number: null },
        } as never,
      }),
    ).toBe("SLL");

    expect(
      programmeMatrixSlotLabel(
        {
          title: "5Y-SLE",
          scope: null,
          audit_type: "PRODUCT",
          auditable_entity: {
            entity_type: "AIRCRAFT_TYPE",
            display_label: "Aircraft / product audits",
            aircraft: null,
          } as never,
        },
        "15-16",
      ),
    ).toBe("SLE");

    expect(
      programmeMatrixSlotLabel(
        {
          title: "Hangar audit",
          scope: null,
          audit_type: "FACILITY",
          auditable_entity: {
            entity_type: "FACILITY",
            display_label: "Hangar",
            aircraft: null,
          } as never,
        },
        "8-9",
      ),
    ).toBe("8-9");
  });

  it("finds overlapping internal and external auditor allocations", () => {
    const collisions = findAuditorScheduleCollisions([
      {
        key: "internal:september",
        itemId: "internal-item",
        programmeId: "internal-programme",
        title: "Hangar audit",
        startDate: "2026-09-08",
        endDate: "2026-09-09",
        auditorUserIds: ["james", "elvin"],
      },
      {
        key: "external:september",
        itemId: "external-item",
        programmeId: "external-programme",
        title: "Regulatory audit",
        startDate: "2026-09-09",
        endDate: "2026-09-10",
        auditorUserIds: ["james", "francis"],
      },
      {
        key: "clear:september",
        itemId: "clear-item",
        programmeId: "internal-programme",
        title: "Stores audit",
        startDate: "2026-09-09",
        endDate: "2026-09-09",
        auditorUserIds: ["unassigned-elsewhere"],
      },
    ]);

    expect(collisions.get("internal:september")).toEqual([
      expect.objectContaining({
        otherItemId: "external-item",
        conflictingUserIds: ["james"],
      }),
    ]);
    expect(collisions.get("external:september")).toEqual([
      expect.objectContaining({
        otherItemId: "internal-item",
        conflictingUserIds: ["james"],
      }),
    ]);
    expect(collisions.has("clear:september")).toBe(false);
  });
});

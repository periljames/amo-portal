import { describe, expect, it } from "vitest";
import { validateCarRcaProjection, validateCarInviteAccess, validateCarParetoSnapshots } from "./qmsCarRcaContracts";

describe("CAR controlled response contracts", () => {
  const genericFallback = { module: "cars", view: "default", record_id: "car-a", items: [] };
  it("rejects successful HTTP generic-register fallbacks instead of inventing an empty RCA", () => {
    expect(() => validateCarRcaProjection(genericFallback)).toThrow("invalid CAR investigation response");
    expect(() => validateCarInviteAccess(genericFallback)).toThrow("invalid invitation access response");
    expect(() => validateCarParetoSnapshots(genericFallback)).toThrow("invalid Pareto snapshots response");
  });
  it("accepts an authoritative empty investigation and preserves the original response", () => {
    const row = { car_id: "car-a", revision: 0,
      draft: { form: {}, investigation: { version: 1, problem_statement: "Finding", investigations: [],
        conclusion: "", supported_cause_ids: [], conclusion_evidence_references: [] } },
      submitted_revision: null, submitted_snapshot: null, submitted_at: null,
      actions: [], action_events: [], retained_responses: [], history: [],
    };
    expect(validateCarRcaProjection(row)).toBe(row);
    expect(() => validateCarRcaProjection({ ...row, actions: {} })).toThrow();
    expect(() => validateCarRcaProjection({ ...row, draft: { form: {}, investigation: {} } })).toThrow();
  });
  it("distinguishes no retained Pareto snapshots from malformed categories", () => {
    expect(validateCarParetoSnapshots([])).toEqual([]);
    expect(() => validateCarParetoSnapshots([{ id: "snapshot", categories: null }])).toThrow();
  });
  it("requires explicit invitation access fields rather than assuming active access", () => {
    const row = { expires_at: null, revoked_at: null, reason: "" };
    expect(validateCarInviteAccess(row)).toBe(row);
    expect(() => validateCarInviteAccess({ expires_at: null })).toThrow();
  });
});

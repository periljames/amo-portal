import { describe, expect, it } from "vitest";

import { assertOfflineReplayAllowed, classifyOfflineMutation, offlineCommandRouteKey } from "./offlineCapabilities";
import { OFFLINE_CREATE_ROUTES } from "./offlineCreateRoutes";

describe("offline controlled-write policy", () => {
  it("queues observations with approved source answers while nonconformities require a negative decision", () => {
    const path = "/api/maintenance/amo/quality/audits/a/checklist-items/i/fieldwork-findings";
    const payload = { client_mutation_id: "observation-device-1", device_id: "auditor-device-1", device_sequence: 1,
      client_timestamp: new Date().toISOString(), base_version: 1, operation: "CREATE_FINDING", reason: "Synthetic offline observation",
      canonical_response_status: "COMPLIANT", response_value: "YES", level: "LEVEL_4", severity: "MINOR", description: "Synthetic observation" };
    expect(() => assertOfflineReplayAllowed(path, "POST", JSON.stringify(payload))).not.toThrow();
    expect(() => assertOfflineReplayAllowed(path, "POST", JSON.stringify({ ...payload, level: "LEVEL_2" }))).toThrow();
  });
  it.each(OFFLINE_CREATE_ROUTES)("automatically queues $id with its concrete server receipt key", (route) => {
    const path = route.path.replace(/\{[^}]+\}/g, "test-id");
    const rule = classifyOfflineMutation(path, "POST");
    expect(rule.autoQueue).toBe(true);
    expect(rule.module).toBe(route.module);
    expect(offlineCommandRouteKey(path, "POST")).toBe(`portal.create:${path}`);
    expect(classifyOfflineMutation(`https://portal.test${path}/?v=1`, "POST").id).toBe(rule.id);
    expect(() => assertOfflineReplayAllowed(path, "POST", JSON.stringify({ title: "Offline record" }))).not.toThrow();
  });
  it("allows only guarded draft operations", () => {
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/assignments",
      "POST",
      JSON.stringify({ source_reference_id: "offline-source-1" }),
    )).not.toThrow();
    expect(() => assertOfflineReplayAllowed(
      "/rostering/assignments/ID-ASSIGNMENT",
      "PATCH",
      JSON.stringify({ expected_state_revision: 4 }),
    )).not.toThrow();
    expect(() => assertOfflineReplayAllowed(
      "/workforce/attendance-events",
      "POST",
      JSON.stringify({ idempotency_key: "attendance-device-1" }),
    )).not.toThrow();
  });

  it("rejects unguarded, destructive and authoritative operations", () => {
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/assignments",
      "POST",
      JSON.stringify({}),
    )).toThrow(/missing its idempotency or revision guard/i);
    expect(() => assertOfflineReplayAllowed(
      "/rostering/assignments/ID-ASSIGNMENT",
      "DELETE",
    )).toThrow(/requires a live server/i);
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/publish",
      "POST",
      JSON.stringify({}),
    )).toThrow(/requires a live server/i);
    expect(() => assertOfflineReplayAllowed(
      "/workforce/payroll/post",
      "POST",
      JSON.stringify({}),
    )).toThrow(/requires a live server/i);
  });

  it("classifies every mutation and exposes durable command route keys", () => {
    expect(classifyOfflineMutation("/unknown/new-endpoint", "POST").capability).toBe("unsupported");
    expect(classifyOfflineMutation("/anything/42", "DELETE").capability).toBe("live-only");
    expect(offlineCommandRouteKey("/rostering/versions/ID-V/assignments", "POST"))
      .toBe("rostering.version.assignment.create:ID-V");
  });

  it.each([null, "", "4", -1, 1.5, undefined])("rejects an invalid roster revision %s", (revision) => {
    expect(() => assertOfflineReplayAllowed("/rostering/assignments/id", "PATCH",
      JSON.stringify({ expected_state_revision: revision }))).toThrow();
  });
});

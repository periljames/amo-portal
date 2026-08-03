import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const pageSource = readFileSync(new URL("./WorkforceRosteringPagesV2.tsx", import.meta.url), "utf8");
const assistantSource = readFileSync(new URL("./components/DutyLocationAssistant.tsx", import.meta.url), "utf8");
const foundationService = readFileSync(new URL("../../services/foundations.ts", import.meta.url), "utf8");

describe("private duty-location guidance", () => {
  it("loads as a separate lazy employee self-service surface", () => {
    expect(pageSource).toContain("LazyDutyLocationAssistant");
    expect(pageSource).toContain("Checking private duty-location guidance");
    expect(pageSource).toContain("<LazyMyRosterWorkspace />");
  });

  it("derives prompts from roster and attendance state", () => {
    expect(assistantSource).toContain("Duty is active and attendance has not started");
    expect(assistantSource).toContain("Duty has ended and attendance is still open");
    expect(assistantSource).toContain("getMyRoster");
    expect(assistantSource).toContain("getAttendanceSummary");
  });

  it("requests one-time location only after a user action", () => {
    expect(assistantSource).toContain("Check my location once");
    expect(assistantSource).toContain("navigator.geolocation.getCurrentPosition");
    expect(assistantSource).toContain("window.isSecureContext");
    expect(assistantSource).not.toContain("watchPosition");
    expect(assistantSource).not.toContain("setInterval");
  });

  it("uses transient evaluation and private consensus contracts", () => {
    expect(assistantSource).toContain("evaluateBaseLocation");
    expect(assistantSource).toContain("contributeBaseLocation");
    expect(assistantSource).toContain("No background tracking is used");
    expect(assistantSource).toContain("location alone is never treated as misconduct");
    expect(foundationService).toContain("/foundations/location/evaluate");
    expect(foundationService).not.toContain("listBaseLocationObservations");
  });
});

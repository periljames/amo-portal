import { describe, expect, it } from "vitest";
import { departureLabel, departurePhaseForPercent } from "./loginDepartureWarmup";

describe("login departure phases", () => {
  it("maps takeoff progress to aviation phases", () => {
    expect(departurePhaseForPercent(0)).toBe("taxi");
    expect(departurePhaseForPercent(25)).toBe("roll");
    expect(departurePhaseForPercent(50)).toBe("rotate");
    expect(departurePhaseForPercent(75)).toBe("climb");
    expect(departurePhaseForPercent(95)).toBe("cruise");
    expect(departurePhaseForPercent(100)).toBe("cruise");
  });

  it("uses short airborne labels", () => {
    expect(departureLabel("roll")).toBe("Takeoff roll");
    expect(departureLabel("cruise")).toBe("Airborne");
  });
});

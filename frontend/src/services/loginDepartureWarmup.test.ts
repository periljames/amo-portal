import { describe, expect, it, vi } from "vitest";
import { departureLabel, departurePhaseForPercent, waitForLoginPreloads, runLoginDepartureWarmup } from "./loginDepartureWarmup";

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

describe("authenticated landing warmup", () => {
  it("does not keep an authenticated user on login when a preload stalls", async () => {
    vi.useFakeTimers();
    try {
      const neverSettles = new Promise<void>(() => undefined);
      const completion = waitForLoginPreloads([neverSettles], 250);
      await vi.advanceTimersByTimeAsync(250);
      await expect(completion).resolves.toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it("treats failed optional prefetch as nonfatal", async () => {
    await expect(
      waitForLoginPreloads([Promise.reject(new Error("optional prefetch failed"))], 250),
    ).resolves.toBeUndefined();
  });
});

vi.mock("../app/routePreload", () => ({ preloadRoute: vi.fn(() => new Promise(() => {})) }));
vi.mock("./auth", () => ({ getContext: () => ({}) }));
vi.mock("./loginHomeHint", () => ({ rememberLoginHome: vi.fn() }));
it("returns the authenticated destination while its module download is still pending", async () => {
 const path = "/maintenance/test/quality";
 const pending = runLoginDepartureWarmup({ user: {} as import("./auth").PortalUser, amoSlug: "test", landingPath: path, onProgress: vi.fn(), takeoffStartedAt: 0 });
 expect(await Promise.race([pending, Promise.resolve("blocked")])).toBe(path);
});

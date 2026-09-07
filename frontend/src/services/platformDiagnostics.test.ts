import { describe, expect, it } from "vitest";

import { isThroughputStable } from "./platformDiagnostics";

describe("adaptive platform network diagnostics", () => {
  it("does not call a test stable before enough samples exist", () => {
    expect(isThroughputStable([100, 101, 100])).toBe(false);
  });

  it("accepts a settled recent throughput window", () => {
    expect(isThroughputStable([42, 90, 101, 99, 102, 100])).toBe(true);
  });

  it("keeps sampling when recent throughput is still moving", () => {
    expect(isThroughputStable([100, 160, 90, 145])).toBe(false);
  });
});

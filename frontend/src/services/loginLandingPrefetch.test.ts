import { describe, expect, it } from "vitest";

import { qmsAmoQueryKey } from "./loginLandingPrefetch";

describe("qmsAmoQueryKey", () => {
  it("normalises tenant casing for cache hits", () => {
    expect(qmsAmoQueryKey("SAFARILINK")).toBe("safarilink");
    expect(qmsAmoQueryKey("safarilink")).toBe("safarilink");
  });
});

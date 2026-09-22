import { describe, expect, it } from "vitest";

import { isActionFlashing } from "./useActionFlash";

describe("useActionFlash helpers", () => {
  it("matches only the active flash key", () => {
    expect(isActionFlashing("SUSPEND", "SUSPEND")).toBe(true);
    expect(isActionFlashing("SUSPEND", "REVOKE")).toBe(false);
    expect(isActionFlashing(null, "SUSPEND")).toBe(false);
  });
});

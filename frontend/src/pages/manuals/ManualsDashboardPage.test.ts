import { describe, expect, it } from "vitest";
import { resolveNextRevisionId } from "./ManualsDashboardPage";

describe("resolveNextRevisionId", () => {
  it("falls back to first revision when previous is from another manual", () => {
    const next = resolveNextRevisionId("rev-old", [{ id: "rev-1" }, { id: "rev-2" }]);
    expect(next).toBe("rev-1");
  });

  it("keeps previous revision when it exists in current list", () => {
    const next = resolveNextRevisionId("rev-2", [{ id: "rev-1" }, { id: "rev-2" }]);
    expect(next).toBe("rev-2");
  });
});

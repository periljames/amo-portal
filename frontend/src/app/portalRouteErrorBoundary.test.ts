import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const source = readFileSync(fileURLToPath(new URL("../portalRoutes.tsx", import.meta.url)), "utf8");

describe("portal route error boundary", () => {
  it("keeps internal exception details out of the operator screen and supports an in-place retry", () => {
    expect(source).toContain("reportPortalError(error");
    expect(source).toContain("Your saved records are safe.");
    expect(source).toContain("onClick={this.retry}");
    expect(source).not.toContain("{this.state.message}");
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { qmsAmoQueryKey } from "./loginLandingPrefetch";

describe("qmsAmoQueryKey", () => {
  it("normalises tenant casing for cache hits", () => {
    expect(qmsAmoQueryKey("SAFARILINK")).toBe("safarilink");
    expect(qmsAmoQueryKey("safarilink")).toBe("safarilink");
  });
});


describe("Training background warmup contract", () => {
  it("does not request the protected control room for self-service or denied Training access", () => {
    const source = readFileSync(fileURLToPath(new URL("./loginLandingPrefetch.ts", import.meta.url)), "utf8");
    const start = source.indexOf("async function warmTrainingHttp");
    const end = source.indexOf("/**\n * Prefetch the authenticated landing surface", start);
    const warmTraining = source.slice(start, end);
    expect(warmTraining).toContain("const access = await getTrainingAccess()");
    expect(warmTraining).toContain("!access.can_open_operating_system || access.self_service_only");
    expect(warmTraining.indexOf("can_open_operating_system")).toBeLessThan(warmTraining.indexOf("getTrainingControlRoom()"));
  });
});

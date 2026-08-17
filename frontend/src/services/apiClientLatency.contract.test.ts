import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  fileURLToPath(new URL("./apiClient.ts", import.meta.url)),
  "utf-8",
);

describe("API client latency retry policy", () => {
  it("does not replay valid HTTP failures against a second localhost alias", () => {
    expect(source).toContain("if (error instanceof ApiClientError) return false;");
    expect(source).not.toContain("if (error instanceof ApiClientError) return error.status >= 500;");
  });

  it("keeps alternate-backend fallback for transport failures only", () => {
    expect(source).toContain('message.includes("failed to fetch")');
    expect(source).toContain('message.includes("networkerror")');
    expect(source).toContain('message.includes("request timed out")');
  });
});

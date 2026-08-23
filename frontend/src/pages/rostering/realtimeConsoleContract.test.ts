/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const realtimeSource = readFileSync(
  new URL("../../components/realtime/RealtimeProvider.tsx", import.meta.url),
  "utf8",
);

describe("rostering realtime console hygiene", () => {
  it("stops presence heartbeats after an authorization rejection", () => {
    expect(realtimeSource).toContain("presenceAuthRejectedRef");
    expect(realtimeSource).toContain("response.status === 401 || response.status === 403");
    expect(realtimeSource).toContain("presenceAuthRejectedRef.current = true");
  });

  it("re-enables presence only after an authenticated session event", () => {
    const authenticated = realtimeSource.indexOf('detail.type === "authenticated"');
    const reset = realtimeSource.indexOf("presenceAuthRejectedRef.current = false", authenticated);
    expect(authenticated).toBeGreaterThan(-1);
    expect(reset).toBeGreaterThan(authenticated);
  });
});

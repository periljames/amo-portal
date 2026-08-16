import { describe, expect, it } from "vitest";

import {
  resolveDevProxyTargets,
  shouldProxyDevApi,
  shouldProxyPlatformOps,
  shouldServePlatformSpa,
} from "./devProxyRouting";

describe("development proxy routing", () => {
  it("keeps Platform Operations on the dedicated gateway", () => {
    expect(shouldProxyPlatformOps("/ops/v1/bootstrap?data_mode=REAL")).toBe(true);
    expect(shouldProxyPlatformOps("/ops/v1/live?data_mode=REAL")).toBe(true);
    expect(shouldProxyPlatformOps("/ops/v1/infrastructure/summary")).toBe(true);
    expect(shouldProxyPlatformOps("/platform/operations")).toBe(false);
    expect(shouldProxyDevApi("/ops/v1/bootstrap?data_mode=REAL")).toBe(false);
  });

  it("preserves the normal API proxy contract", () => {
    expect(shouldProxyDevApi("/quality/audits")).toBe(true);
    expect(shouldProxyDevApi("/platform/settings")).toBe(true);
    expect(shouldProxyDevApi("/healthz")).toBe(true);
    expect(shouldProxyDevApi("/livez")).toBe(true);
    expect(shouldProxyDevApi("/readyz")).toBe(true);
  });

  it("uses separate default targets and accepts deployment-local overrides", () => {
    expect(resolveDevProxyTargets({})).toEqual({
      apiTarget: "http://127.0.0.1:8080",
      platformOpsTarget: "http://127.0.0.1:8090",
    });
    expect(
      resolveDevProxyTargets({
        VITE_API_PROXY_TARGET: "http://api.internal:18080",
        VITE_PLATFORM_OPS_PROXY_TARGET: "http://ops.internal:18090",
      }),
    ).toEqual({
      apiTarget: "http://api.internal:18080",
      platformOpsTarget: "http://ops.internal:18090",
    });
  });

  it("serves SPA-owned HTML navigation before overlapping API proxies", () => {
    expect(shouldServePlatformSpa("GET", "/platform/operations", "text/html")).toBe(true);
    expect(shouldServePlatformSpa("GET", "/qms/audit-access/signed-token", "text/html,application/xhtml+xml")).toBe(true);
    expect(shouldServePlatformSpa("HEAD", "/qms/car-access/signed-token", "text/html")).toBe(true);

    expect(shouldServePlatformSpa("GET", "/ops/v1/bootstrap", "text/html")).toBe(false);
    expect(shouldServePlatformSpa("GET", "/qms/internal-api", "text/html")).toBe(false);
    expect(shouldServePlatformSpa("GET", "/qms/audit-access/signed-token", "application/json")).toBe(false);
    expect(shouldServePlatformSpa("POST", "/qms/audit-access/signed-token", "text/html")).toBe(false);
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const apiClientSource = readFileSync(
  fileURLToPath(new URL("./apiClient.ts", import.meta.url)),
  "utf-8",
);
const offlineHttpSource = readFileSync(
  fileURLToPath(new URL("./offlineHttp.ts", import.meta.url)),
  "utf-8",
);
const connectivitySource = readFileSync(
  fileURLToPath(new URL("./portalConnectivity.ts", import.meta.url)),
  "utf-8",
);
const viteConfigSource = readFileSync(
  fileURLToPath(new URL("../../vite.config.ts", import.meta.url)),
  "utf-8",
);

describe("API client latency retry policy", () => {
  it("does not replay genuine backend HTTP failures against a second localhost alias", () => {
    expect(apiClientSource).toContain("if (error instanceof ApiClientError) return error.transportFailure;");
    expect(apiClientSource).not.toContain("if (error instanceof ApiClientError) return error.status >= 500;");
  });

  it("keeps alternate-backend fallback for genuine transport failures", () => {
    expect(apiClientSource).toContain('message.includes("failed to fetch")');
    expect(apiClientSource).toContain('message.includes("networkerror")');
    expect(apiClientSource).toContain('message.includes("request timed out")');
  });

  it("marks Vite proxy connection failures so direct API fallback remains functional", () => {
    expect(viteConfigSource).toContain("X-AMO-Proxy-Transport-Error");
    expect(viteConfigSource).toContain("configure: markProxyTransportFailure");
    expect(offlineHttpSource).toContain("if (proxyTransportFailure) return response;");
    expect(apiClientSource).toContain("isProxyTransportFailureResponse(response)");
  });

  it("does not gate ordinary GET/navigation requests behind connectivity recovery", () => {
    expect(offlineHttpSource).toContain('if (connectivityState === "RECOVERING") {');
    expect(offlineHttpSource).toContain("if (isGet) void probePortalReadiness();");
    expect(offlineHttpSource).toContain("else await waitForPortalReadiness();");
    expect(offlineHttpSource).toContain("return isPortalRequestNetworkEligible(");
    expect(offlineHttpSource).not.toContain('if (getPortalConnectivity().state === "RECOVERING") {\n    await waitForPortalReadiness();');
  });

  it("uses lightweight liveness for interactive connectivity instead of dependency readiness", () => {
    expect(connectivitySource).toContain('fetch(apiUrl("/livez"), init)');
    expect(connectivitySource).toContain('fetch(apiUrl("/health"), init)');
    expect(connectivitySource).not.toContain('apiUrl("/readyz")');
    expect(connectivitySource).toContain("CONNECTIVITY_PROBE_TIMEOUT_MS");
  });

  it("can bypass a stale cross-tab leader lease when a protected request must recover", () => {
    expect(connectivitySource).toContain("const forced = await probePortalReadiness(true);");
  });

  it("does not broadcast a connectivity event for every successful API response", () => {
    expect(connectivitySource).toContain('const changed = snapshot.state !== "ONLINE" || snapshot.reason !== null;');
    expect(connectivitySource).toContain('if (snapshot.state !== "ONLINE") {');
    expect(connectivitySource).toContain("if (changed) window.dispatchEvent");
  });
});

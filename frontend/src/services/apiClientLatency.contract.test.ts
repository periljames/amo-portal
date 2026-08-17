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

  it("does not broadcast a connectivity event for every successful API response", () => {
    expect(connectivitySource).toContain('const changed = snapshot.state !== "ONLINE" || snapshot.reason !== null;');
    expect(connectivitySource).toContain('if (snapshot.state !== "ONLINE") {');
    expect(connectivitySource).toContain("if (changed) window.dispatchEvent");
  });
});

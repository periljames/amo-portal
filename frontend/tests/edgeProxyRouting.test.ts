import { afterEach, describe, expect, it, vi } from "vitest";
import { onRequest, resolveEdgeRoute } from "../functions/[[path]]";

const env = {
  API_UPSTREAM: "https://private-api.venspera.com",
  OPS_UPSTREAM: "https://private-ops.venspera.com",
  ASSETS: { fetch: vi.fn(async () => new Response("SPA index", { status: 200 })) },
};

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("Venspera production same-origin edge", () => {
  it("keeps SPA navigations local while forwarding API and private ops routes", () => {
    expect(resolveEdgeRoute("GET", "/platform/billing", "text/html")).toBe("assets");
    expect(resolveEdgeRoute("GET", "/qms/audit-access/token", "text/html")).toBe("assets");
    expect(resolveEdgeRoute("GET", "/auth/me", "application/json")).toBe("api");
    expect(resolveEdgeRoute("POST", "/platform/tenants", "application/json")).toBe("api");
    expect(resolveEdgeRoute("GET", "/ops/events", "text/event-stream")).toBe("ops");
    expect(resolveEdgeRoute("GET", "/assets/runtime.js", "*/*")).toBe("assets");
  });

  it("rejects cross-origin mutations before contacting the backend", async () => {
    const fetcher = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetcher);
    const request = new Request("https://app.venspera.com/platform/billing/maintenance/run", {
      method: "POST", headers: { origin: "https://evil.invalid" },
    });
    const response = await onRequest({ request, env });
    expect(response.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refuses absent or insecure upstreams", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const request = new Request("https://app.venspera.com/auth/me");
    expect((await onRequest({ request, env: { ...env, API_UPSTREAM: "http://127.0.0.1:8080" } })).status).toBe(503);
    expect((await onRequest({ request, env: { ...env, API_UPSTREAM: "https://app.venspera.com" } })).status).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("preserves signed session headers and streams responses", async () => {
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      expect(url).toBe("https://private-api.venspera.com/auth/me?check=1");
      expect(new Headers(init.headers).get("cookie")).toBe("refresh=abc");
      expect(new Headers(init.headers).get("x-forwarded-host")).toBe("app.venspera.com");
      expect(new Headers(init.headers).get("x-forwarded-proto")).toBe("https");
      return new Response(JSON.stringify({ ok: true }), { headers: { "content-type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetcher);
    const request = new Request("https://app.venspera.com/auth/me?check=1", {
      headers: { cookie: "refresh=abc", accept: "application/json" },
    });
    const result = await onRequest({ request, env });
    expect(result.status).toBe(200);
    expect(result.headers.get("cache-control")).toBe("private, no-store");
    expect(await result.json()).toEqual({ ok: true });
  });
  it("rewrites an upstream login redirect to the public edge origin", async () => {
    const fetcher = vi.fn(async () => new Response(null, {
      status: 302,
      headers: { location: "https://private-api.venspera.com/auth/login?next=%2Fquality" },
    }));
    vi.stubGlobal("fetch", fetcher);
    const request = new Request("https://app.venspera.com/auth/session", {
      headers: { accept: "application/json" },
    });
    const response = await onRequest({ request, env });
    expect(response.status).toBe(302);
    expect(response.headers.get("location"))
      .toBe("https://app.venspera.com/auth/login?next=%2Fquality");
    expect(fetcher).toHaveBeenCalledOnce();
  });

});

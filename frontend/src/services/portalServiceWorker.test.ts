import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

const source = readFileSync(new URL("../../public/portal-sw.js", import.meta.url), "utf8");

const workerVersion = /const VERSION = "([^"]+)"/.exec(source)![1];

function worker(fetch: typeof globalThis.fetch) {
  const stores = new Map<string, Map<string, Response>>();
  const handlers = new Map<string, (event: unknown) => void>();
  const background: Promise<unknown>[] = [];
  const caches = {
    open: async (name: string) => {
      if (!stores.has(name)) stores.set(name, new Map());
      const store = stores.get(name)!;
      return {
        match: async (key: string) => store.get(key)?.clone(),
        put: async (key: string, response: Response) => {
          store.set(key, response);
        },
      };
    },
  };
  const context = {
    fetch,
    caches,
    Response,
    URL,
    setTimeout,
    clearTimeout,
    self: {
      location: { origin: "https://portal.test" },
      addEventListener: (name: string, handler: (event: unknown) => void) => handlers.set(name, handler),
    },
  };
  runInNewContext(source, context);
  const waitUntil = (promise: Promise<unknown>) => {
    background.push(Promise.resolve(promise).then(() => undefined, () => undefined));
  };
  return { context, handlers, stores, background, waitUntil };
}

describe("QMS service-worker caching", () => {
  it("serves content-addressed chunks without re-downloading them on a weak link", async () => {
    const fetch = vi.fn(() => new Promise<Response>(() => {}));
    const { context } = worker(fetch);
    context.caches.open = vi.fn().mockResolvedValue({ match: vi.fn(async () => new Response("cached immutable code")), put: vi.fn() });
    const sandbox = { ...context, request: new Request("https://portal.test/assets/workspace-Ab12_Cd3.js") };
    const result = await runInNewContext("cacheFirstAsset(request)", sandbox) as Response;
    expect(await result.text()).toBe("cached immutable code");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("serves precached public code when a module reload adds an Origin header", async () => {
    const { context } = worker(vi.fn().mockRejectedValue(new TypeError("Offline")));
    const response = new Response("cached module", { headers: { Vary: "Origin" } });
    const match = vi.fn(async (_request: Request, options?: CacheQueryOptions) =>
      options?.ignoreVary ? response.clone() : undefined);
    context.caches.open = vi.fn().mockResolvedValue({ match, put: vi.fn() });
    const sandbox = { ...context, request: new Request("https://portal.test/assets/app.js", {
      headers: { Origin: "https://portal.test" }, mode: "cors",
    }) };
    const result = await runInNewContext("cacheFirstAsset(request)", sandbox) as Response;
    expect(await result.text()).toBe("cached module");
    expect(match).toHaveBeenCalledWith(sandbox.request, { ignoreVary: true });
  });

  it("warms all module code with bounded concurrency and excludes authenticated data", async () => {
    const assets: string[] = [];
    let active = 0;
    let peak = 0;
    const { context } = worker(vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/portal-precache.json") return Response.json({ portalUrls: [
        "/assets/training.js", "/assets/procurement.js", "/assets/records.css", "/accounts/me", "/api/private", "/documents/controlled.pdf",
      ] });
      assets.push(url);
      peak = Math.max(peak, ++active);
      await new Promise((resolve) => setTimeout(resolve, 1));
      active--;
      return new Response("code");
    }));
    await runInNewContext("Promise.all([precachePortal(), precachePortal()])", context);
    expect(peak).toBe(2);
    expect(assets.sort()).toEqual(["/assets/procurement.js", "/assets/records.css", "/assets/training.js"]);
    await runInNewContext("precachePortal()", context);
    expect(assets).toHaveLength(3);
  });
  it("coalesces warmups, limits downloads to two, and never precaches API payloads", async () => {
    let active = 0;
    let peak = 0;
    const assets: string[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/portal-precache.json") {
        return Response.json({
          qmsUrls: ["/assets/a.js", "/assets/b.js", "/assets/c.js", "/auth/me", "/api/quality/audits"],
        });
      }
      assets.push(url);
      active++;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, 1));
      active--;
      return new Response("code");
    });
    const { context } = worker(fetch);
    await runInNewContext("Promise.all([precacheQms(), precacheQms()])", context);
    expect(peak).toBe(2);
    expect(assets.sort()).toEqual(["/assets/a.js", "/assets/b.js", "/assets/c.js"]);
    await runInNewContext("precacheQms()", context);
    expect(assets).toHaveLength(3);
  });

  it("serves the cached shell during a deployment 503 without caching the error", async () => {
    const { context, stores, background, waitUntil } = worker(
      vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })),
    );
    stores.set(
      `amo-portal-shell-${workerVersion}`,
      new Map([["/", new Response("offline shell", { headers: { "Content-Type": "text/html" } })]]),
    );
    const sandbox = { ...context, waitUntil };
    const result = (await runInNewContext(
      "cachedShellNavigation('/maintenance/t/quality', null, { waitUntil })",
      sandbox,
    )) as Response;
    expect(await result.text()).toBe("offline shell");
    await Promise.all(background);
    expect(await stores.get(`amo-portal-shell-${workerVersion}`)!.get("/")!.clone().text()).toBe("offline shell");
  });

  it("acknowledges browser-only audit readiness only after QMS chunks are cached", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/portal-precache.json") {
        return Response.json({ urls: ["/", "/index.html"], qmsUrls: ["/assets/fieldwork.js"] });
      }
      return new Response("asset", { status: 200, headers: { "Content-Type": url === "/" ? "text/html" : "application/javascript" } });
    });
    const { handlers, background, waitUntil } = worker(fetch);
    const sent: Array<{ ok: boolean; assets?: number; reason?: string }> = [];
    handlers.get("message")!({
      data: { type: "PREPARE_AUDIT_SHELL" },
      ports: [{ postMessage: (message: { ok: boolean; assets?: number; reason?: string }) => sent.push(message) }],
      waitUntil,
    });
    await Promise.all(background);
    expect(sent).toEqual([{ ok: true, assets: 1 }]);
    expect(fetch).not.toHaveBeenCalledWith("/api/maintenance/a/quality", expect.anything());
  });

  it("leaves authenticated API and document requests outside Cache Storage", () => {
    const { handlers } = worker(vi.fn());
    for (const path of ["/auth/refresh", "/api/maintenance/t/quality/audits", "/accounts/me", "/documents/private.pdf"]) {
      const respondWith = vi.fn();
      handlers.get("fetch")!({
        request: { method: "GET", url: `https://portal.test${path}`, mode: "cors" },
        respondWith,
      });
      expect(respondWith).not.toHaveBeenCalled();
    }
  });

  it("prefers current HTML over a saved shell when the server responds promptly", async () => {
    const { context, stores, waitUntil } = worker(vi.fn(async () => new Response("current shell", { headers: { "Content-Type": "text/html" } })));
    stores.set(`amo-portal-shell-${workerVersion}`, new Map([["/", new Response("old shell")]]));
    const response = await runInNewContext("cachedShellNavigation('/maintenance/t/quality', null, { waitUntil })", { ...context, waitUntil }) as Response;
    expect(await response.text()).toBe("current shell");
  });
  it("uses the updated root shell rather than an older route warmup when offline", async () => {
    const { context, stores, waitUntil } = worker(vi.fn().mockRejectedValue(new TypeError("Offline")));
    stores.set(`amo-portal-shell-${workerVersion}`, new Map([
      ["/", new Response("current release")],
      ["/maintenance/t/quality/settings/general", new Response("previous release")],
    ]));
    const response = await runInNewContext("cachedShellNavigation('/maintenance/t/quality/settings/general', null, { waitUntil })", { ...context, waitUntil }) as Response;
    expect(await response.text()).toBe("current release");
  });
  it("returns the cached shell without waiting for a slow network refresh", async () => {
    vi.useFakeTimers();
    try {
      let finish!: (response: Response) => void;
      const pending = new Promise<Response>((resolve) => {
        finish = resolve;
      });
      const { context, stores, background, waitUntil } = worker(vi.fn().mockReturnValue(pending));
      stores.set(`amo-portal-shell-${workerVersion}`, new Map([["/", new Response("saved shell")]]));
      const sandbox = { ...context, waitUntil };
      const result = runInNewContext(
        "cachedShellNavigation('/maintenance/t/quality', null, { waitUntil })",
        sandbox,
      ) as Promise<Response>;
      // The stale-shell fallback is bounded, even if the server never responds.
      await vi.advanceTimersByTimeAsync(350);
      expect(await (await result).text()).toBe("saved shell");
      finish(new Response("fresh shell", { headers: { "Content-Type": "text/html" } }));
      await Promise.all(background);
      expect(await stores.get(`amo-portal-shell-${workerVersion}`)!.get("/")!.clone().text()).toBe("fresh shell");
    } finally {
      vi.useRealTimers();
    }
  });
});

import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

const source = readFileSync(new URL("../../public/portal-sw.js", import.meta.url), "utf8");

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
      "amo-portal-shell-v10",
      new Map([["/", new Response("offline shell", { headers: { "Content-Type": "text/html" } })]]),
    );
    const sandbox = { ...context, waitUntil };
    const result = (await runInNewContext(
      "cachedShellNavigation('/maintenance/t/quality', null, { waitUntil })",
      sandbox,
    )) as Response;
    expect(await result.text()).toBe("offline shell");
    await Promise.all(background);
    expect(await stores.get("amo-portal-shell-v10")!.get("/")!.clone().text()).toBe("offline shell");
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

  it("returns the cached shell without waiting for a slow network refresh", async () => {
    vi.useFakeTimers();
    try {
      let finish!: (response: Response) => void;
      const pending = new Promise<Response>((resolve) => {
        finish = resolve;
      });
      const { context, stores, background, waitUntil } = worker(vi.fn().mockReturnValue(pending));
      stores.set("amo-portal-shell-v10", new Map([["/", new Response("saved shell")]]));
      const sandbox = { ...context, waitUntil };
      const result = runInNewContext(
        "cachedShellNavigation('/maintenance/t/quality', null, { waitUntil })",
        sandbox,
      ) as Promise<Response>;
      // No timers or network completion are needed for a cached navigation.
      expect(await (await result).text()).toBe("saved shell");
      finish(new Response("fresh shell", { headers: { "Content-Type": "text/html" } }));
      await Promise.all(background);
      expect(await stores.get("amo-portal-shell-v10")!.get("/")!.clone().text()).toBe("fresh shell");
    } finally {
      vi.useRealTimers();
    }
  });
});

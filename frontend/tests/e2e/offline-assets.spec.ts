import { expect, test } from "@playwright/test";

test("production shell and all module assets remain available with the network disabled", async ({ page, context }) => {
  await page.route("**/__asset_harness__", (route) => route.fulfill({ contentType: "text/html", body: "<html><body>Asset readiness</body></html>" }));
  await page.goto("/__asset_harness__");
  const urls = await page.evaluate(async () => {
    await navigator.serviceWorker.register("/portal-sw.js", { scope: "/" });
    const ready = await navigator.serviceWorker.ready;
    const manifest = await (await fetch("/portal-precache.json")).json();
    ready.active!.postMessage({ type: "PRECACHE_PORTAL" });
    return manifest.portalUrls as string[];
  });
  expect(urls.length).toBeGreaterThan(100);
  for (const module of ["Training", "Procurement", "TechnicalRecords", "Reliability"]) {
    expect(urls.some((url) => url.includes(module))).toBe(true);
  }
  await expect.poll(async () => page.evaluate(async (urls) => {
    let missing = 0;
    for (const url of urls) if (!await caches.match(url)) missing++;
    return missing;
  }, urls), { timeout: 60_000 }).toBe(0);
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await context.setOffline(true);
  const navigation = await page.goto("/maintenance/test/training");
  expect(navigation?.status()).toBe(200);
  const failed = await page.evaluate(async (urls) => {
    const results = await Promise.all(urls.map(async (url) => {
      try { return (await fetch(url)).ok ? null : url; } catch { return url; }
    }));
    return results.filter(Boolean);
  }, urls);
  expect(failed).toEqual([]);
});

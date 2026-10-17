import { expect, test } from "@playwright/test";

test("live events replace cached answers, batch bursts, isolate audits and catch up after reconnect", async ({ page }) => {
  const values: Record<string, number> = { "audit-a": 1, "audit-b": 10, fleet: 20 };
  const calls: Record<string, number> = {};
  await page.route("**/readyz", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/__realtime_fixture__/*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/").pop()!;
    calls[id] = (calls[id] || 0) + 1;
    return route.fulfill({ json: { id, value: values[id] } });
  });
  await page.route("**/__quality_realtime__", (route) => route.fulfill({ contentType: "text/html", body: '<html><body><div id="root"></div></body></html>' }));
  await page.goto("/__quality_realtime__");
  await page.evaluate(async () => {
    const { default: refresh } = await import(/* @vite-ignore */ "/@react-refresh"); refresh.injectIntoGlobalHook(window);
    Object.assign(window, { $RefreshReg$: () => {}, $RefreshSig$: () => (type: unknown) => type, __vite_plugin_react_preamble_installed__: true });
    const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/qualityRealtimeHarness.tsx"); fixture.mount();
  });
  await expect(page.getByTestId("audit-a")).toHaveText("1");
  await expect(page.getByTestId("audit-b")).toHaveText("10");
  values["audit-a"] = 2;
  await page.evaluate(async () => { const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/qualityRealtimeHarness.tsx"); for (let i = 0; i < 12; i++) fixture.event("audit-a"); });
  await expect(page.getByTestId("audit-a")).toHaveText("2");
  expect(calls["audit-a"]).toBe(2);
  expect(calls["audit-b"]).toBe(1); expect(calls.fleet).toBe(1);
  values["audit-a"] = 3; values["audit-b"] = 11;
  await page.evaluate(async () => { const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/qualityRealtimeHarness.tsx"); fixture.event("audit-b"); fixture.state("offline"); fixture.state("connected"); });
  await expect(page.getByTestId("audit-a")).toHaveText("3");
  await expect(page.getByTestId("audit-b")).toHaveText("10");
  values["audit-a"] = 4;
  await page.evaluate(async () => { const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/qualityRealtimeHarness.tsx"); fixture.event(undefined, true); });
  await expect(page.getByTestId("audit-a")).toHaveText("4");
  expect(calls["audit-b"]).toBe(1); expect(calls.fleet).toBe(1);
});

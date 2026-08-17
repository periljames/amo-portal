import { expect, test } from "@playwright/test";

const user = {
  id: "ID-TEST-USER", amo_id: "ID-TEST-AMO", department_id: "ID-TEST-DEPT", staff_code: "TEST01",
  email: "test@example.com", first_name: "Test", last_name: "User", full_name: "Test User",
  role: "USER", position_title: null, phone: null, regulatory_authority: null,
  licence_number: null, licence_state_or_country: null, licence_expires_on: null,
  is_active: true, is_superuser: false, is_amo_admin: false, must_change_password: false,
  last_login_at: null, last_login_ip: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const loginResponse = {
  access_token: "test-access-token", token_type: "bearer", expires_in: 900, user,
  amo: { id: "ID-TEST-AMO", amo_code: "TEST", name: "Test AMO", login_slug: "test", data_mode: "REAL" },
  department: { id: "ID-TEST-DEPT", code: "engineering", name: "Engineering" },
};

test("precache manifest keeps the application shell usable offline", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    const registration = await navigator.serviceWorker.getRegistration();
    registration?.active?.postMessage({ type: "PRECACHE_RELEASE" });
  });
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL || "")).toContain("portal-sw.js");
  await context.setOffline(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("body")).not.toBeEmpty();
  await context.setOffline(false);
});

test("one login securely authenticates another same-origin tab without localStorage tokens", async ({ context }) => {
  await context.route("**/auth/login-context?**", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ login_slug: "test", amo_code: "TEST", amo_name: "Test AMO", is_platform: false }),
  }));
  await context.route("**/auth/login", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(loginResponse) }));
  await context.route("**/readyz", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ready", ready: true }) }));
  const first = await context.newPage();
  const second = await context.newPage();
  await Promise.all([first.goto("/login"), second.goto("/login")]);
  await first.locator("#identifier").fill("test@example.com");
  await first.getByRole("button", { name: "Continue" }).click();
  await first.locator("#password").fill("Secure-Test-Password-1");
  await first.getByRole("button", { name: "Sign In" }).click();
  await expect.poll(() => second.evaluate(() => sessionStorage.getItem("amo_portal_token"))).toBe("test-access-token");
  expect(await second.evaluate(() => localStorage.getItem("amo_portal_token"))).toBeNull();
});

test("dependency outage enters degraded mode without a request storm and recovers on focus", async ({ page }) => {
  let ready = false;
  let probes = 0;
  await page.route("**/readyz", (route) => {
    probes += 1;
    return route.fulfill({
      status: ready ? 200 : 503,
      headers: ready ? {} : { "Retry-After": "2", "X-Error-Code": "DATABASE_UNAVAILABLE" },
      contentType: "application/json",
      body: JSON.stringify(ready ? { status: "ready", ready: true } : { status: "degraded", ready: false }),
    });
  });
  await page.goto("/");
  await expect(page.getByText(/Server dependencies are recovering|Checking the server/i)).toBeVisible();
  await page.waitForTimeout(1_000);
  expect(probes).toBeLessThanOrEqual(2);
  ready = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => probes).toBeGreaterThan(1);
  await expect(page.getByText(/Server dependencies are recovering/i)).toHaveCount(0);
});

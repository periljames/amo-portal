import type { Page } from "@playwright/test";

/** Keep mocked workflow browsers from sending synthetic sessions to the live API. */
export async function mockPortalBackgroundRequests(page: Page): Promise<void> {
  await page.route("**/auth/me", async route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(await page.evaluate(() => JSON.parse(localStorage.getItem("amo_current_user") || "{}"))) }));
  await page.route("**/auth/refresh", async route => {
    const session = await page.evaluate(() => ({
      user: JSON.parse(localStorage.getItem("amo_current_user") || "{}"),
      access_token: sessionStorage.getItem("amo_portal_token") || localStorage.getItem("amo_portal_token"),
      amo_code: localStorage.getItem("amo_code"), amo_slug: localStorage.getItem("amo_slug"),
    }));
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      user: session.user, access_token: session.access_token, token_type: "bearer", expires_in: 3600,
      amo: { id: session.user.amo_id, amo_code: session.amo_code, name: "Tenant A", login_slug: session.amo_slug },
      department: { id: session.user.department_id, code: "quality", name: "Quality" },
    }) });
  });
  await page.route(/\/(readyz|livez|healthz|health)(\?.*)?$/, route => route.fulfill({ status: 200, contentType: "application/json", body: '{"ready":true,"status":"alive","live":true,"process":true}' }));
  await page.route("**/api/realtime/**", route => route.fulfill({ status: 200, contentType: "application/json", body: '{}' }));
  await page.route(/\/accounts\/amo-assets\/logo(?:\?.*)?$/, route => route.fulfill({ status: 204, body: "" }));
  await page.route("**/accounts/onboarding/status", route => route.fulfill({ status: 200, contentType: "application/json", body: '{"is_complete":true,"missing":[]}' }));
  await page.route("**/accounts/admin/admin-profile/**", route => route.fulfill({ status: 200, contentType: "application/json", body: '{"eligible":false,"active":false}' }));
  await page.route("**/time", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ epoch_ms: Date.now() }) }));
  await page.route("**/platform/product-events", (route) => route.fulfill({ status: 200, contentType: "application/json", body: '{"accepted":true}' }));
  await page.route("**/api/events?*", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: ": fixture connected\n\n" }));
  await page.route("**/api/events", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: ": fixture connected\n\n" }));
  await page.route(/\/api\/(notifications|chat)\//, (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/unread-count")
      ? { notifications: 0, messages: 0, total: 0 }
      : path.endsWith("/preferences") ? { in_app_enabled: true, email_enabled: false } : [];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

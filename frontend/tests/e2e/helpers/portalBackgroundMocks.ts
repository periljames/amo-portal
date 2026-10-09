import type { Page } from "@playwright/test";

/** Keep mocked workflow browsers from sending synthetic sessions to the live API. */
export async function mockPortalBackgroundRequests(page: Page): Promise<void> {
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

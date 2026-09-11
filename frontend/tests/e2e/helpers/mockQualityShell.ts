import type { Page } from "@playwright/test";

export async function mockQualityShell(page: Page): Promise<void> {
  await page.route("**/*", async route => {
    const request = route.request();
    if (["document", "stylesheet", "script", "image", "font", "media", "manifest"].includes(request.resourceType())) return route.continue();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/auth/me")) return json(await page.evaluate(() => JSON.parse(localStorage.getItem("amo_current_user") || "{}")));
    if (path.endsWith("/auth/refresh")) {
      const session = await page.evaluate(() => ({ user: JSON.parse(localStorage.getItem("amo_current_user") || "{}"), access_token: sessionStorage.getItem("amo_portal_token") || localStorage.getItem("amo_portal_token") }));
      return json({ ...session, token_type: "bearer", expires_in: 3600, amo: { id: "amo-a", amo_code: "AMO-A", name: "Tenant A", login_slug: "tenant-a" }, department: { id: "department-quality", code: "quality", name: "Quality" } });
    }
    if (path === "/time") return json({ epoch_ms: Date.now() });
    if (["/readyz", "/livez", "/healthz", "/health"].includes(path)) return json({ status: "alive", ready: true, live: true });
    if (path.includes("/accounts/onboarding/status")) return json({ is_complete: true, missing: [] });
    if (path.startsWith("/api/chat/threads") || path.endsWith("/tasks/my")) return json([]);
    if (path.includes("/api/notifications/me/unread-count")) return json({ notifications: 0, messages: 0, total: 0 });
    return json({});
  });
}

import { expect, test, type Request } from "@playwright/test";
import { QMS_ROUTE_REGISTRY, qmsModulePath } from "../../src/pages/qms/routes/qmsRouteRegistry";
import { writeFile } from "node:fs/promises";

// Explicitly opt in. This suite signs in to the real tenant but never submits
// business forms or manufactures audit / review / calibration evidence.
test("Safarilink admin can reach QMS pages through the live application", async ({ page }, testInfo) => {
  test.skip(!process.env.QMS_LIVE_EMAIL || !process.env.QMS_LIVE_PASSWORD, "Set authorized live credentials to run the read-only tenant audit.");
  test.setTimeout(20 * 60_000);
  const response = await page.request.post("/auth/login", { data: { amo_slug: "safarilink", email: process.env.QMS_LIVE_EMAIL, password: process.env.QMS_LIVE_PASSWORD }, timeout: 60_000 });
  expect(response.status()).toBe(200);
  const auth = await response.json();
  await page.addInitScript(data => {
    sessionStorage.setItem("amo_portal_token", data.access_token);
    sessionStorage.setItem("amo_portal_token_expiry_v1", String(Date.now() + data.expires_in * 1000));
    localStorage.setItem("amo_current_user", JSON.stringify(data.user));
    localStorage.setItem("amo_code", data.amo.amo_code); localStorage.setItem("amo_slug", data.amo.login_slug);
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
  }, auth);
  const moduleIds = new Set(["management-review", "risk", "system", "equipment-calibration", "external-interface"]);
  const paths = QMS_ROUTE_REGISTRY.filter(module => !["documents", "aerodoc"].includes(module.id)).flatMap(module =>
    module.validViews.filter(view => view !== "new").map(view => ({ module: module.id, view, path: qmsModulePath(auth.amo.amo_code, module.id, view) })));
  const root = `/maintenance/${auth.amo.amo_code}/quality`;
  for (const hub of ["readiness", "controls", "evidence", "intelligence"]) paths.push({ module: "assurance-hub", view: hub, path: `${root}?hub=${hub}` });
  for (const workspace of ["missions", "intelligence", "assurance"]) paths.push({ module: "workspaces", view: workspace, path: `${root}?workspace=${workspace}` });
  for (const tab of ["overview", "people", "cases", "reviews", "administration"]) paths.push({ module: "people", view: tab, path: `${root}?workspace=people&tab=${tab}` });
  const auditPaths = process.env.QMS_LIVE_SCOPE === "workspaces"
    ? paths.filter(entry => ["assurance-hub", "workspaces", "people"].includes(entry.module)) : paths;
  const outcomes: { module: string; view: string; path: string; headings: string[]; alerts: string[]; failures: string[] }[] = [];
  const pending = new Set<Request>();
  let failures: string[] = [];
  const isSource = (url: string) => {
    const path = new URL(url).pathname;
    return path.includes("/api/maintenance/") || path.startsWith("/quality/");
  };
  page.on("pageerror", error => failures.push(`Runtime error: ${error.message}`));
  page.on("request", request => { if (isSource(request.url())) pending.add(request); });
  page.on("requestfinished", request => pending.delete(request));
  page.on("requestfailed", request => { if (isSource(request.url())) {
    pending.delete(request);
    // Leaving a page deliberately cancels its in-flight background refreshes.
    // Retain real transport failures, including their browser error reason.
    const reason = request.failure()?.errorText || "Unknown transport failure";
    if (reason !== "net::ERR_ABORTED") failures.push(`Request failed: ${new URL(request.url()).pathname}: ${reason}`);
  } });
  page.on("response", response => { if (isSource(response.url()) && response.status() >= 400) failures.push(`${response.status()} ${new URL(response.url()).pathname}`); });
  for (const entry of auditPaths) {
    failures = [];
    await page.goto(entry.path, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await expect(page.getByRole("navigation", { name: "QMS page menus", exact: true })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".tenant-shell__main")).toContainText(/\S{4}/, { timeout: 60_000 });
    if (moduleIds.has(entry.module)) await expect(page.locator(".qms-review__stats").first()).toBeVisible({ timeout: 30_000 });
    await expect.poll(async () => page.locator('.tenant-shell__main [role="status"]').filter({ hasText: /Loading|Opening|Preparing/ }).count(), { timeout: 30_000 }).toBe(0);
    await expect.poll(() => pending.size, { timeout: 30_000 }).toBe(0);
    await page.waitForTimeout(500);
    await expect.poll(() => pending.size, { timeout: 30_000 }).toBe(0);
    await expect(page.getByText("Creation belongs to the governed source workflow", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /Quality page not found|Something went wrong/i })).toHaveCount(0);
    if (entry.module === "findings") {
      const names: Record<string, string> = { register: "Findings Register", "by-process": "Findings by process", "by-severity": "Findings by severity", trends: "Finding trends", "linked-cars": "Findings linked to CARs" };
      await expect(page.getByRole("heading", { name: names[entry.view], exact: true })).toBeVisible();
    }
    const headings = await page.locator(".tenant-shell__main h1,.tenant-shell__main h2").allTextContents();
    const alerts = await page.getByRole("alert").allTextContents();
    outcomes.push({ ...entry, headings, alerts, failures: [...failures] });
    await writeFile(testInfo.outputPath("live-navigation-audit.json"), JSON.stringify(outcomes, null, 2));
    if (["management-review", "risk", "equipment-calibration"].includes(entry.module) && entry.view === QMS_ROUTE_REGISTRY.find(module => module.id === entry.module)?.defaultView) {
      await page.screenshot({ path: testInfo.outputPath(`${entry.module}-live.png`), fullPage: true });
    }
  }
  await testInfo.attach("live-navigation-audit", { body: JSON.stringify(outcomes, null, 2), contentType: "application/json" });
  expect(outcomes).toHaveLength(auditPaths.length);
  expect(outcomes.filter(item => item.failures.length || item.alerts.length)).toEqual([]);
});

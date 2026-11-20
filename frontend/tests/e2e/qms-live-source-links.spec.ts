import { expect, test, type Page } from "@playwright/test";

// Real tenant reads only: no fabricated minutes, evidence, cases or approvals.
async function signIn(page: Page) {
  test.skip(!process.env.QMS_LIVE_EMAIL || !process.env.QMS_LIVE_PASSWORD, "Authorized live credentials are required.");
  const response = await page.request.post("/auth/login", { data: {
    amo_slug: "safarilink", email: process.env.QMS_LIVE_EMAIL, password: process.env.QMS_LIVE_PASSWORD,
  } });
  expect(response.status()).toBe(200);
  const auth = await response.json();
  await page.addInitScript(data => {
    sessionStorage.setItem("amo_portal_token", data.access_token);
    sessionStorage.setItem("amo_portal_token_expiry_v1", String(Date.now() + data.expires_in * 1000));
    localStorage.setItem("amo_current_user", JSON.stringify(data.user));
    localStorage.setItem("amo_code", data.amo.amo_code);
    localStorage.setItem("amo_slug", data.amo.login_slug);
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
  }, auth);
  return auth;
}

test("live page search opens the review form and equipment evidence workflow", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const auth = await signIn(page);
  const base = `/maintenance/${auth.amo.amo_code}/quality`;
  const dashboardResponse = page.waitForResponse(response => response.url().includes("/quality/dashboard-v2") && response.status() === 200);
  await page.goto(base);
  const dashboard = await (await dashboardResponse).json();
  expect(dashboard.source_errors || []).toEqual([]);
  await expect(page.getByRole("heading", { name: "Control Room", exact: true })).toBeVisible();
  await expect.poll(async () => page.locator('.tenant-shell__main [role="status"]').filter({ hasText: /Loading|Opening|Preparing/ }).count(), { timeout: 30_000 }).toBe(0);
  await page.screenshot({ path: testInfo.outputPath("control-room-live.png"), fullPage: true });
  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByRole("searchbox", { name: "Find any Quality page" }).fill("minutes");
  await page.getByRole("navigation", { name: "Quality page search results" }).getByRole("link", { name: /Meetings/ }).click();
  await expect(page).toHaveURL(/management-review\/meetings/);
  await page.getByRole("link", { name: "Plan a review", exact: true }).click();
  await expect(page).toHaveURL(/management-review\/new/);
  await expect(page.getByLabel("Review title", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Chair", { exact: true }).locator("option")).not.toHaveCount(1);
  await expect(page.getByLabel("Agenda", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByRole("searchbox", { name: "Find any Quality page" }).fill("calibration history");
  await page.getByRole("navigation", { name: "Quality page search results" }).getByRole("link", { name: /Calibration history/ }).click();
  await expect(page).toHaveURL(/equipment-calibration\/calibration-history/);
  await page.getByRole("button", { name: "Add calibration", exact: true }).click();
  await expect(page.getByLabel("Calibration date", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Calibration result", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Results and evidence reference", { exact: false })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("navigation", { name: "Equipment & Calibration views", exact: true }).getByRole("link", { name: "Reports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Calibration assurance report", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Calibration report measures", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("calibration-report-live.png"), fullPage: true });
});

test("real assigned work opens its retained source record", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  const auth = await signIn(page);
  const response = await page.request.get(`/api/maintenance/${auth.amo.amo_code}/quality/work-inbox/assigned-to-me`, {
    headers: { Authorization: `Bearer ${auth.access_token}` },
  });
  expect(response.status()).toBe(200);
  const assignments = await response.json();
  expect(assignments.source_errors).toEqual([]);
  expect(assignments.items.length).toBeGreaterThan(0);
  let inspected = 0;
  for (const item of assignments.items.slice(0, 5)) {
    const sourceRead = page.waitForResponse(response => response.url().includes(item.record_id) && response.status() === 200, { timeout: 60_000 });
    await page.goto(item.route);
    await sourceRead;
    await expect(page.getByRole("navigation", { name: "QMS page menus", exact: true })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: /not found|Something went wrong/i })).toHaveCount(0);
    await expect.poll(async () => page.locator('.tenant-shell__main [role="status"]').filter({ hasText: /Loading|Opening|Preparing/ }).count(), { timeout: 30_000 }).toBe(0);
    expect(await page.locator(".tenant-shell__main").evaluate((element, title) => {
      const values = Array.from(element.querySelectorAll("input,textarea")).map(field => (field as HTMLInputElement).value);
      return element.textContent?.includes(title) || values.includes(title);
    }, item.title), item.route).toBeTruthy();
    if (inspected++ === 0) {
      await page.screenshot({ path: testInfo.outputPath("assigned-audit-desktop.png"), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(page.getByRole("button", { name: "Find a page", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("assigned-audit-mobile.png"), fullPage: true });
      await page.setViewportSize({ width: 1280, height: 720 });
    }
  }
});

test("live finding classifications drill into the matching retained cohort", async ({ page }) => {
  test.setTimeout(240_000);
  const auth = await signIn(page);
  const base = `/maintenance/${auth.amo.amo_code}/quality`;
  const classifications = page.waitForResponse(response => response.url().includes("/findings/insights?") && new URL(response.url()).searchParams.get("view") === "by-severity" && response.status() === 200);
  await page.goto(`${base}/findings/by-severity`);
  const severity = await (await classifications).json();
  const group = severity.groups.find((item: { key: string }) => ["MINOR", "MAJOR", "CRITICAL"].includes(item.key));
  expect(group).toBeTruthy();
  const retained = page.waitForResponse(response => response.url().includes("/audits/register/paged?") && new URL(response.url()).searchParams.get("severity") === group.key && response.status() === 200);
  await page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: group.key, exact: true }) }).getByRole("link", { name: "Inspect findings", exact: true }).click();
  const records = await (await retained).json();
  expect(records.total).toBe(group.total);
  expect(records.rows.every((row: { finding: { severity: string } }) => row.finding.severity === group.key)).toBe(true);
  const mappingResponse = page.waitForResponse(response => response.url().includes("/findings/insights?") && new URL(response.url()).searchParams.get("view") === "by-process" && response.status() === 200);
  await page.getByRole("navigation", { name: "Findings views", exact: true }).getByRole("link", { name: "By process", exact: true }).click();
  const mappings = await (await mappingResponse).json();
  const unmappedResponse = page.waitForResponse(response => response.url().includes("/audits/register/paged?") && new URL(response.url()).searchParams.get("process_unmapped") === "true" && response.status() === 200);
  await page.getByRole("link", { name: "Inspect unmapped findings", exact: true }).click();
  const unmapped = await (await unmappedResponse).json();
  expect(unmapped.total).toBe(mappings.unmapped);
});

test("tenant slug and trailing-slash entries retain working finding navigation", async ({ page }) => {
  test.setTimeout(180_000);
  const auth = await signIn(page);
  const root = `/maintenance/${encodeURIComponent(auth.amo.login_slug)}/quality`;
  await page.goto(`${root}/findings/register`);
  const tabs = page.getByRole("navigation", { name: "Findings views", exact: true });
  await expect(tabs).toBeVisible({ timeout: 60_000 });
  const source = page.waitForResponse(response => response.url().includes(`/api/maintenance/${encodeURIComponent(auth.amo.login_slug)}/quality/findings/insights?`) && response.status() === 200);
  await tabs.getByRole("link", { name: "By severity", exact: true }).click(); await source;
  await expect(page).toHaveURL(new URL(`${root}/findings/by-severity`, page.url()).href);
  await expect(page.getByRole("heading", { name: "Recorded severity", exact: true })).toBeVisible();
  const linked = page.waitForResponse(response => response.url().includes("/audits/register/paged?") && new URL(response.url()).searchParams.get("only_with_cars") === "true" && response.status() === 200);
  await page.goto(`${root}/findings/linked-cars/`); await linked;
  await expect(page.getByRole("heading", { name: "Findings linked to CARs", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Findings views", exact: true })).toBeVisible();
});

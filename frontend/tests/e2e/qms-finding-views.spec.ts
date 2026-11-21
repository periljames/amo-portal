import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

test.setTimeout(120_000);
async function prepare(page: Page) {
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "auditor", amo_id: "amo-a", role: "AUDITOR", full_name: "Assigned Auditor", is_active: true, is_amo_admin: false }));
  });
  await page.route("**/quality/findings/insights?*", route => {
    const query = new URL(route.request().url()).searchParams;
    const view = query.get("view");
    const year = Number(query.get("year"));
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ year, total: 12, open: 5, unmapped: 3,
      groups: view === "by-process" ? [{ key: "Engineering", total: 7, open: 3 }, { key: "Flight operations", total: 4, open: 2 }, { key: "Supply chain", total: 2, open: 0 }]
        : [{ key: "MINOR", total: 3, open: 0 }, { key: "MAJOR", total: 7, open: 3 }, { key: "CRITICAL", total: 2, open: 2 }],
      months: Array.from({ length: 12 }, (_, i) => ({ month: `${year}-${String(i + 1).padStart(2, "0")}`, raised: i === 0 ? 12 : 0, closed: i === 2 ? 14 : 0 })),
    }) });
  });
  await page.route("**/quality/audits/register/paged?*", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ rows: [], total: 0, limit: 25, offset: 0, has_more: false, car_linked_findings: 0, open_car_count: 0 }) }));
  await page.route("**/api/maintenance/tenant-a/quality/audits?*", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ id: "audit-1", audit_ref: "QAR-2026-01", title: "Personnel control audit", status: "IN_PROGRESS" }], total: 1, limit: 25, offset: 0 }) }));
}

test("severity analysis drills into a server-filtered retained finding register", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/by-severity");
  await expect(page.getByRole("heading", { name: "Findings by severity", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("list", { name: "Severity distribution" }).getByRole("link").first()).toHaveAccessibleName("Inspect Critical findings");
  const filtered = page.waitForRequest(request => new URL(request.url()).searchParams.get("severity") === "MAJOR");
  await page.getByRole("link", { name: "Inspect Major findings", exact: true }).click();
  await filtered;
  await expect(page).toHaveURL(/findings\/register\?.*severity=MAJOR/);
  await expect(page.getByRole("navigation", { name: "Findings views", exact: true })).toBeVisible();
});

test("process coverage keeps unmapped findings visible and linked CARs use their own filter", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/by-process");
  await expect(page.getByRole("heading", { name: "Findings by process area", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("9 of 12 total findings mapped to a process", { exact: true })).toBeVisible();
  const unmapped = page.waitForRequest(request => new URL(request.url()).searchParams.get("process_unmapped") === "true");
  await page.getByRole("link", { name: "3 unmapped", exact: true }).click(); await unmapped;
  await expect(page.getByText("No current verified process mapping", { exact: true })).toBeVisible();
  const linked = page.waitForRequest(request => new URL(request.url()).searchParams.get("only_with_cars") === "true");
  await page.getByRole("navigation", { name: "Findings views", exact: true }).getByRole("link", { name: "Linked cars", exact: true }).click(); await linked;
  await expect(page.getByRole("heading", { name: "Findings linked to CARs", exact: true })).toBeVisible();
});

test("auditors can discover source-based finding capture and inspect monthly event trends", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/trends");
  await expect(page.getByRole("heading", { name: "Raised and closed by month", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("img", { name: /Monthly finding events/ })).toBeVisible();
  await page.getByText("Monthly figures", { exact: true }).click();
  await expect(page.getByRole("row", { name: "Mar 0 14", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByLabel("Find any Quality page").fill("findings create");
  const directory = page.getByRole("navigation", { name: "Quality page search results", exact: true });
  await expect(directory.getByRole("link")).toHaveCount(1); await directory.getByRole("link").click();
  await expect(page.getByRole("heading", { name: "Record a finding", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open fieldwork", exact: true })).toHaveAttribute("href", "/maintenance/tenant-a/quality/audits/audit-1/live#findings");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("process filters preserve year and status when drilling into source records", async ({ page }, info) => {
  await prepare(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/maintenance/tenant-a/quality/findings/by-process?period=2025");
  const distribution = page.getByRole("list", { name: "Process distribution" });
  await expect(distribution.getByRole("link")).toHaveCount(3, { timeout: 60_000 });
  await page.screenshot({ path: info.outputPath("process-desktop.png"), fullPage: true });
  await page.getByLabel("Finding year", { exact: true }).fill("2024");
  const changedYear = page.waitForRequest(request => request.url().includes("/findings/insights") && new URL(request.url()).searchParams.get("year") === "2024");
  await page.getByRole("button", { name: "Apply year", exact: true }).click(); await changedYear;
  await page.getByLabel("Finding status", { exact: true }).selectOption("open");
  await expect(distribution.getByRole("link")).toHaveCount(2);
  await page.getByRole("searchbox", { name: "Filter process areas" }).fill("flight");
  const flight = distribution.getByRole("link", { name: "Inspect Flight operations findings, open only", exact: true });
  await expect(distribution.getByRole("link")).toHaveCount(1);
  await expect(flight).toContainText("40%");
  await expect(flight).toHaveAttribute("href", /period=2024&process=Flight\+operations&status=open/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: info.outputPath("process-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const filtered = page.waitForRequest(request => new URL(request.url()).searchParams.get("process") === "Flight operations");
  await flight.click(); await filtered;
  await expect(page.getByRole("button", { name: "Clear process filter" })).toBeVisible();
  await page.getByRole("button", { name: "Show filters", exact: true }).click();
  await page.getByRole("searchbox", { name: "Process area", exact: true }).fill("Engineering");
  const edited = page.waitForRequest(request => new URL(request.url()).searchParams.get("process") === "Engineering");
  await page.getByRole("searchbox", { name: "Process area", exact: true }).press("Enter"); await edited;
  await expect(page.getByRole("button", { name: "Clear process filter" })).toContainText("Engineering");
  const cleared = page.waitForRequest(request => request.url().includes("register/paged") && !new URL(request.url()).searchParams.has("process") && new URL(request.url()).searchParams.get("finding_status") === "open");
  await page.getByRole("button", { name: "Clear process filter" }).click(); await cleared;
  const views = page.getByRole("navigation", { name: "Findings views", exact: true });
  await expect(views.getByRole("link", { name: "By severity", exact: true })).toHaveAttribute("href", /by-severity\?period=2024$/);
});

test("severity and trends stay legible in light and dark layouts without duplicate tables", async ({ page }, info) => {
  await prepare(page);
  await page.addInitScript(() => localStorage.setItem("amo_color_scheme", "light"));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/maintenance/tenant-a/quality/findings/by-severity?period=2026");
  await expect(page.getByRole("list", { name: "Severity distribution" })).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: info.outputPath("severity-light.png"), fullPage: true });
  await page.getByRole("navigation", { name: "Findings views", exact: true }).getByRole("link", { name: "Trends", exact: true }).click();
  await expect(page.getByRole("img", { name: /Monthly finding events/ })).toBeVisible();
  await expect(page.getByRole("table", { name: "Monthly finding events for 2026" })).not.toBeVisible();
  await page.screenshot({ path: info.outputPath("trends-light.png"), fullPage: true });
  await page.evaluate(() => { localStorage.setItem("amo_color_scheme", "dark"); window.dispatchEvent(new CustomEvent("amo:color-scheme-changed", { detail: "dark" })); });
  await page.screenshot({ path: info.outputPath("trends-dark.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: info.outputPath("trends-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("empty cohorts show an honest empty state instead of fabricated chart data", async ({ page }) => {
  await prepare(page);
  await page.route("**/quality/findings/insights?*", route => route.fulfill({ json: { year: 2026, total: 0, open: 0, unmapped: 0, groups: [], months: [] } }));
  await page.goto("/maintenance/tenant-a/quality/findings/trends?period=2026");
  await expect(page.getByText("No findings raised or closed in 2026.", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("img", { name: /Monthly finding events/ })).toHaveCount(0);
});

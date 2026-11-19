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
    const view = new URL(route.request().url()).searchParams.get("view");
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ year: 2026, total: 3, open: 2, unmapped: 2,
      groups: [{ key: view === "by-process" ? "Engineering" : "MAJOR", total: 1, open: 0 }],
      months: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, "0")}`, raised: i === 0 ? 3 : 0, closed: i === 2 ? 2 : 0 })),
    }) });
  });
  await page.route("**/quality/audits/register/paged?*", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ rows: [], total: 0, limit: 25, offset: 0, has_more: false, car_linked_findings: 0, open_car_count: 0 }) }));
  await page.route("**/api/maintenance/tenant-a/quality/audits?*", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ id: "audit-1", audit_ref: "QAR-2026-01", title: "Personnel control audit", status: "IN_PROGRESS" }], total: 1, limit: 25, offset: 0 }) }));
}

test("severity analysis drills into a server-filtered retained finding register", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/by-severity");
  await expect(page.getByRole("heading", { name: "Findings by severity", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("cell", { name: "1", exact: true })).toBeVisible();
  const filtered = page.waitForRequest(request => new URL(request.url()).searchParams.get("severity") === "MAJOR");
  await page.getByRole("link", { name: "Inspect findings", exact: true }).click();
  await filtered;
  await expect(page).toHaveURL(/findings\/register\?.*severity=MAJOR/);
  await expect(page.getByRole("navigation", { name: "Findings views", exact: true })).toBeVisible();
});

test("process coverage keeps unmapped findings visible and linked CARs use their own filter", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/by-process");
  await expect(page.getByRole("heading", { name: "Verified control process areas", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/2 finding\(s\) have no qualifying process mapping/)).toBeVisible();
  const unmapped = page.waitForRequest(request => new URL(request.url()).searchParams.get("process_unmapped") === "true");
  await page.getByRole("link", { name: "Inspect unmapped findings", exact: true }).click(); await unmapped;
  await expect(page.getByText("No current verified process mapping", { exact: true })).toBeVisible();
  const linked = page.waitForRequest(request => new URL(request.url()).searchParams.get("only_with_cars") === "true");
  await page.getByRole("navigation", { name: "Findings views", exact: true }).getByRole("link", { name: "Linked cars", exact: true }).click(); await linked;
  await expect(page.getByRole("heading", { name: "Findings linked to CARs", exact: true })).toBeVisible();
});

test("auditors can discover source-based finding capture and inspect monthly event trends", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/findings/trends");
  await expect(page.getByRole("heading", { name: "Monthly finding events", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("row", { name: "2026-03 0 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByLabel("Find any Quality page").fill("findings create");
  const directory = page.getByRole("navigation", { name: "Quality page search results", exact: true });
  await expect(directory.getByRole("link")).toHaveCount(1); await directory.getByRole("link").click();
  await expect(page.getByRole("heading", { name: "Record a finding", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open fieldwork", exact: true })).toHaveAttribute("href", "/maintenance/tenant-a/quality/audits/audit-1/live#findings");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

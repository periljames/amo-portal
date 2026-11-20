import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";
import { readFile } from "node:fs/promises";

test.setTimeout(120_000);
async function prepare(page: Page) {
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "chair", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: "QUALITY_MANAGER", full_name: "Quality Chair", is_active: true, is_amo_admin: true }));
  });
  let record: Record<string, unknown> | null = null;
  const fields = [{ key: "likelihood", label: "Likelihood (1–5)", type: "number", required: true, options: [] }, { key: "consequence", label: "Consequence (1–5)", type: "number", required: true, options: [] }, { key: "rating", label: "Assessed risk level", type: "select", required: true, options: ["LOW", "MEDIUM", "HIGH", "CRITICAL"] }];
  await page.route("**/quality/register-workspace/**", async route => {
    const request = route.request(); if (request.resourceType() === "document") return route.fallback();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/export")) return route.fulfill({ contentType: "text/csv", headers: { "Content-Disposition": "attachment; filename=QMS-risk-register.csv" }, body: "Title,Status\r\nRisk assessment,OPEN\r\n" });
    if (request.method() === "POST") { const body = request.postDataJSON(); record = { ...body, id: "risk-123", version: 1, payload: { ...body.fields, version: 1, history: [] } }; return json(record, 201); }
    if (request.method() === "PUT") { const body = request.postDataJSON(); expect(body.expected_version).toBe(1); record = { ...record, ...body, version: 2, payload: { ...body.fields, version: 2, history: [] } }; return json(record); }
    if (path.endsWith("/risk-123")) return json(record);
    return json({ items: record ? [record] : [], total: record ? 1 : 0, offset: 0, limit: 30, source: "risks", label: "Risk register", fields, statuses: ["OPEN", "IN_PROGRESS", "CLOSED"], members: [{ id: "chair", first_name: "Quality", last_name: "Chair", email: "chair@example.test" }], equipment: [], status_counts: [], risk_matrix: [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], unassessed: 0, immutable: false });
  });
}

test("risk forms create and edit retained assessments, and matrix reads assessed records", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/risk/register");
  await expect(page.getByRole("heading", { name: "Risk and Opportunities", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Add record", exact: true }).click();
  await page.getByLabel("Record title", { exact: true }).fill("Risk assessment");
  await page.getByLabel("Record owner", { exact: true }).selectOption("chair");
  await page.getByLabel("Likelihood (1–5)", { exact: false }).fill("3");
  await page.getByLabel("Consequence (1–5)", { exact: false }).fill("4");
  await page.getByLabel("Assessed risk level", { exact: false }).selectOption("HIGH");
  await page.getByRole("button", { name: "Create record", exact: true }).click();
  await expect(page).toHaveURL(/record=risk-123/);
  await expect(page.getByRole("status").filter({ hasText: "Record saved" })).toBeVisible();
  await page.getByLabel("Record title", { exact: true }).fill("Updated risk assessment");
  await page.getByRole("button", { name: "Save record changes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Updated risk assessment", exact: true })).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download complete CSV", exact: true }).click()]);
  expect(await download.failure()).toBeNull();
  await page.getByRole("navigation", { name: "Risk & Opportunities views", exact: true }).getByRole("link", { name: "Risk matrix", exact: true }).click();
  await expect(page.getByRole("table", { name: "Risk likelihood and consequence matrix", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/risk-matrix-mobile.png", fullPage: true });
});

test("calibration reports expose inventory gaps and retained results and download both sections", async ({ page }) => {
  await prepare(page);
  await page.route("**/quality/register-workspace/equipment-calibration/reports**", async route => {
    if (route.request().resourceType() === "document") return route.fallback();
    if (new URL(route.request().url()).pathname.endsWith("/export")) return route.fulfill({ contentType: "text/csv", headers: { "Content-Disposition": "attachment; filename=QMS-equipment-calibration-reports.csv" }, body: "Tenant totals (unfiltered),Value\r\nActive missing due date,1\r\nPassed,3\r\nFailed,1\r\n" });
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({
      items: [], total: 0, offset: 0, limit: 30, source: "calibrations", label: "Calibration reports", fields: [], statuses: ["COMPLETE"], members: [], equipment: [], status_counts: [], immutable: true,
      equipment_report: { equipment_total: 6, active: 4, active_within_due_date: 2, active_overdue: 1, active_missing_due_date: 1, out_of_service: 1, open_tolerance_cases: 2, retained_calibrations: 4, passed: 3, failed: 1 },
    }) });
  });
  await page.goto("/maintenance/tenant-a/quality/equipment-calibration/reports");
  await expect(page.getByRole("heading", { name: "Calibration assurance report", exact: true })).toBeVisible();
  const measures = page.getByRole("table", { name: "Calibration report measures", exact: true });
  await expect(measures.getByRole("row", { name: "Active equipment missing a due date 1", exact: true })).toBeVisible();
  await expect(measures.getByRole("row", { name: "Recorded calibration failures 1", exact: true })).toBeVisible();
  await expect(measures.getByRole("row", { name: "Retained results without PASS / FAIL classification 0", exact: true })).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download complete CSV", exact: true }).click()]);
  expect(await readFile((await download.path())!, "utf8")).toContain("Active missing due date,1");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

import { expect, test } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

test("Quality work tabs show distinct assignment queues and personal watches", async ({ page }) => {
  test.setTimeout(120_000);
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "chair", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: "QUALITY_MANAGER", full_name: "Quality Chair", is_active: true, is_amo_admin: true }));
  });
  let watching = false;
  await page.route("**/quality/work-inbox/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST") watching = true;
    if (route.request().method() === "DELETE") watching = false;
    const view = path.split("/").at(-1);
    const item = { id: "risks:risk-1", record_id: "risk-1", source: "risks", source_label: "Risk assessment", title: view === "completed" ? "Completed assessment" : view === "approvals" ? "Review awaiting approval" : "Assigned risk assessment", status: view === "completed" ? "CLOSED" : "OPEN", due_date: "2026-11-15", route: "/maintenance/tenant-a/quality/risk/register?record=risk-1", watching };
    const items = view === "watching" && !watching ? [] : [item];
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items, total: items.length, offset: 0, limit: 30, source_errors: [] }) });
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me");
  await expect(page.getByRole("heading", { name: "My Quality Work", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("cell", { name: "Assigned risk assessment", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Watch", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop watching", exact: true })).toBeVisible();
  const tabs = page.getByRole("navigation", { name: "My Quality Work views", exact: true });
  await tabs.getByRole("link", { name: "Watching", exact: true }).click();
  await page.getByRole("button", { name: "Stop watching", exact: true }).click();
  await expect(page.getByText("No records match this view.", { exact: false })).toBeVisible();
  await tabs.getByRole("link", { name: "Completed", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Completed assessment", exact: true })).toBeVisible();
  await tabs.getByRole("link", { name: "Approvals", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Review awaiting approval", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open work", exact: true })).toHaveAttribute("href", /risk\/register\?record=risk-1$/);
});

test("Quality history exposes retained before and after values through registered navigation", async ({ page }) => {
  test.setTimeout(120_000);
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "chair", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: "QUALITY_MANAGER", full_name: "Quality Chair", is_active: true, is_amo_admin: true }));
  });
  await page.route("**/quality/activity-log?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ id: "event-1", actor_name: "Quality Chair", action: "REVIEW_APPROVED", module: "management-review", entity_type: "qms_management_reviews", entity_id: "review-1", previous_value: { status: "PENDING_APPROVAL" }, new_value: { status: "APPROVED" }, created_at: "2026-11-18T06:00:00Z" }], total: 1, offset: 0, limit: 30, modules: ["management-review"] }) }));
  await page.goto("/maintenance/tenant-a/quality/settings/audit-log");
  await expect(page.getByRole("heading", { name: "Quality activity log", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Inspect change", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Retained change: review approved", exact: true })).toBeVisible();
  await expect(page.locator("pre").first()).toContainText("PENDING_APPROVAL");
  await expect(page.locator("pre").last()).toContainText("APPROVED");
  await page.getByLabel("Search action or record", { exact: true }).fill("review-1");
  await expect(page).toHaveURL(/q=review-1/);
});

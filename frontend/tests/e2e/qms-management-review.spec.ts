import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";
import { readFile } from "node:fs/promises";
import type { ReviewRecord } from "../../src/services/qmsManagementReview";

test.setTimeout(120_000);

async function prepare(page: Page, readOnly = false) {
  await mockQualityShell(page);
  await page.addInitScript(({ readOnly }) => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "chair", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: readOnly ? "VIEW_ONLY" : "QUALITY_MANAGER", full_name: "Quality Chair", is_active: true, is_amo_admin: !readOnly }));
  }, { readOnly });
  let row: ReviewRecord = { id: "review-123", title: "Quarterly management review", status: "DRAFT", owner_user_id: "chair", due_date: "2026-11-20", version: 1,
    payload: { agenda: "Audit results and resources", review_date: "2026-11-20", chair_user_id: "chair", attendee_user_ids: [], inputs: [], minutes: "", decisions: [], history: [] }, actions: [] };
  await page.route("**/quality/management-review/workspace**", async route => {
    if (route.request().resourceType() === "document") return route.fallback();
    const path = new URL(route.request().url()).pathname;
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path.endsWith("/members")) return json({ items: [{ id: "chair", first_name: "Quality", last_name: "Chair", email: "chair@example.test" }] });
    if (path.endsWith("/meetings/review-123/actions") && route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      const action: ReviewRecord = { ...body, id: "action-123", status: "OPEN", version: 1, payload: { review_id: row.id, decision_id: body.decision_id, completion_evidence: "" } };
      row.actions = [action]; return json(action, 201);
    }
    if (path.includes("/actions/action-123")) {
      let action = row.actions![0];
      if (route.request().method() === "PUT") { const body = route.request().postDataJSON(); action = { ...action, ...body, version: action.version + 1, payload: { ...action.payload, completion_evidence: body.completion_evidence } }; }
      if (path.endsWith("/transition")) { const body = route.request().postDataJSON(); expect(body.expected_version).toBe(action.version); action = { ...action, status: body.status, version: action.version + 1 }; }
      row.actions = [action]; return json(action);
    }
    if (route.request().method() === "POST" && path.endsWith("/meetings")) {
      const body = route.request().postDataJSON();
      row = { ...row, ...body, payload: { ...row.payload, ...body } };
      return json(row, 201);
    }
    if (path.endsWith("/transition")) {
      const body = route.request().postDataJSON();
      expect(body.expected_version).toBe(row.version);
      expect(body.reason).toBeTruthy();
      row = { ...row, status: body.status, version: row.version + 1, payload: { ...row.payload, history: [...(row.payload.history || []), { event: `REVIEW_${body.status}`, at: new Date().toISOString(), by: "chair", status: body.status, reason: body.reason }] } };
      return json(row);
    }
    if (path.endsWith("/meetings/review-123")) {
      if (route.request().method() === "PUT") { const body = route.request().postDataJSON(); row = { ...row, ...body, payload: { ...row.payload, ...body }, version: row.version + 1 }; }
      return json(row);
    }
    const actions = new URL(route.request().url()).searchParams.get("view")?.includes("actions");
    return json({ items: actions ? [] : [row], total: actions ? 0 : 1, offset: 0, limit: 30, summary: { meetings: 1, awaiting_approval: 0, open_actions: 0, overdue_actions: 0 } });
  });
  await page.route("**/quality/excellence/management-review-pack", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ generated_at: new Date().toISOString(), executive_summary: ["Source-backed review briefing"], decisions_required: [] }) }));
}

test("management review is reachable through page search and has a real draft form", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/management-review/dashboard");
  await expect(page.getByRole("heading", { name: "Management Review", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByLabel("Find any Quality page").fill("management create");
  const directory = page.getByRole("navigation", { name: "Quality page search results" });
  await expect(directory.getByRole("link")).toHaveCount(1);
  await directory.getByRole("link").click();
  await expect(page.getByRole("heading", { name: "Plan a management review", exact: true })).toBeVisible();
  await page.getByLabel("Review title", { exact: true }).fill("Quarterly management review");
  await page.getByLabel("Meeting date", { exact: true }).fill("2026-11-20");
  await page.getByLabel("Chair", { exact: true }).selectOption("chair");
  await page.getByLabel("Agenda", { exact: true }).fill("Audit results and resources");
  await page.getByRole("button", { name: "Create draft review", exact: true }).click();
  await expect(page).toHaveURL(/management-review\/review-123\/overview$/);
  await expect(page.getByRole("heading", { name: "Quarterly management review", exact: true })).toBeVisible();
  const schedule = page.getByRole("button", { name: "Schedule review", exact: true });
  await expect(schedule).toBeDisabled();
  await page.getByLabel("Decision / transition reason", { exact: true }).fill("Chair and agenda confirmed.");
  await schedule.click();
  await expect(page.getByRole("button", { name: "Start review", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review history", exact: true }).locator("..")).toContainText("Chair and agenda confirmed.");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download meeting record", exact: true }).click()]);
  expect(await download.failure()).toBeNull();
  expect(await readFile((await download.path())!, "utf8")).toContain("Reason: Chair and agenda confirmed.");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/management-review-mobile.png", fullPage: true });
});

test("read-only review users get records without workflow mutation controls", async ({ page }) => {
  await prepare(page, true); await page.goto("/maintenance/tenant-a/quality/management-review/review-123/overview");
  await expect(page.getByRole("heading", { name: "Retained meeting record", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Save meeting record", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Schedule review", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Plan a review", exact: true })).toHaveCount(0);
});

test("review minutes, decisions, action evidence and verification remain usable through closeout", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/management-review/review-123/overview");
  await page.getByRole("button", { name: "Add review input", exact: true }).click();
  await page.getByLabel("Input topic", { exact: true }).fill("Audit results");
  await page.getByLabel("Input summary", { exact: true }).fill("Reviewed retained audit findings and outstanding actions.");
  await page.getByRole("button", { name: "Add decision", exact: true }).click();
  await page.getByLabel("Decision title", { exact: true }).fill("Improve the follow-up control");
  await page.getByLabel("Decision rationale", { exact: true }).fill("The retained findings show the need for a stronger control.");
  await page.getByLabel("Minutes", { exact: true }).fill("Management reviewed effectiveness and agreed a corrective improvement.");
  await page.getByRole("button", { name: "Save meeting record", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Meeting record saved" })).toBeVisible();
  async function meetingStep(button: string) {
    await page.getByLabel("Decision / transition reason", { exact: true }).first().fill("Evidence and retained record checked.");
    await page.getByRole("button", { name: button, exact: true }).click();
  }
  await meetingStep("Schedule review"); await expect(page.getByRole("button", { name: "Start review", exact: true })).toBeVisible();
  await meetingStep("Start review");
  await page.getByLabel("Action title", { exact: true }).fill("Implement and verify the control");
  await page.getByLabel("Action owner", { exact: true }).selectOption("chair");
  await page.getByLabel("Action due date", { exact: true }).fill("2026-11-30");
  await page.getByRole("button", { name: "Assign action", exact: true }).click();
  const action = page.locator("#action-action-123");
  await expect(action).toBeVisible();
  await action.getByLabel("Decision / transition reason", { exact: true }).fill("Assigned work accepted.");
  await action.getByRole("button", { name: "Start action", exact: true }).click();
  await action.getByLabel("Completion evidence", { exact: true }).fill("Control implemented and evidence retained under the agreed reference.");
  await action.getByRole("button", { name: "Save action", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Action updated" })).toBeVisible();
  await action.getByLabel("Decision / transition reason", { exact: true }).fill("Completion evidence submitted for review.");
  await action.getByRole("button", { name: "Submit for verification", exact: true }).click();
  await action.getByLabel("Decision / transition reason", { exact: true }).fill("Objective evidence independently checked.");
  await action.getByRole("button", { name: "Verify & close", exact: true }).click();
  await meetingStep("Submit minutes for approval");
  await expect(page.getByRole("heading", { name: "Retained meeting record", exact: true })).toBeVisible();
  await meetingStep("Approve minutes & decisions"); await expect(page.getByRole("button", { name: "Close review", exact: true })).toBeVisible();
  await meetingStep("Close review");
  await expect(page.locator(".qms-review__section").first().locator(".qms-review__status")).toHaveText("closed");
});

test("section menus expose direct views and preserve escape-key navigation", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/management-review/dashboard");
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  const menu = page.getByRole("navigation", { name: "Reports pages", exact: true });
  await expect(menu.getByRole("link", { name: "Open actions", exact: true })).toHaveAttribute("href", "/maintenance/tenant-a/quality/management-review/open-actions");
  await menu.getByRole("link", { name: "Open actions", exact: true }).click();
  await expect(page).toHaveURL(/management-review\/open-actions$/);
  await expect(page.getByRole("heading", { name: "Follow-up actions", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Find a page", exact: true }).click();
  await page.getByLabel("Find any Quality page").fill("mail");
  await expect(page.getByRole("navigation", { name: "Quality page search results" }).getByRole("link")).not.toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Quality page directory" })).toHaveCount(0);
});

import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "admin-test", amo_id: "tenant-a", amo_code: "TENANT-A", amo_slug: "tenant-a",
  department_id: "maintenance-dept", department_code: "maintenance", role: "TECHNICIAN",
  staff_code: "ADM", email: "admin@example.test", first_name: "Tenant", last_name: "Admin", full_name: "Tenant Admin",
  is_active: true, is_superuser: false, is_amo_admin: true, must_change_password: false,
};
const organisation = { id: "tenant-a", amo_code: "TENANT-A", login_slug: "tenant-a", name: "Tenant Aviation", is_active: true,
  country: "Kenya", icao_code: "TEST", contact_email: "office@example.test", contact_phone: "", time_zone: "Africa/Nairobi" };
async function prepare(page: Page) {
  await page.addInitScript((identity) => {
    localStorage.setItem("amo_portal_token", "administration-e2e-token");
    localStorage.setItem("amo_current_user", JSON.stringify(identity));
    localStorage.setItem("amo_code", "TENANT-A"); localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
  }, user);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!/^\/(auth|accounts|workforce|foundations|notifications|quality|billing|api|realtime|training|platform|readyz|livez|time)(\/|$)/.test(url.pathname)) return route.continue();
    let data: unknown = [];
    if (["/readyz", "/livez"].includes(url.pathname)) data = { status: "ok" };
    else if (url.pathname === "/time") data = { utc: new Date().toISOString() };
    else if (url.pathname.includes("/admin-profile/")) data = { eligible: true, active: true, grant_type: "PERMANENT" };
    else if (url.pathname.endsWith("/organisation")) data = route.request().method() === "PUT" ? { ...organisation, ...route.request().postDataJSON() } : organisation;
    else if (url.pathname === "/auth/me") data = user;
    else if (url.pathname.includes("onboarding")) data = { is_complete: true, missing: [] };
    else if (url.pathname.endsWith("/access-framework")) data = { initialized: true, source: "test", profiles: [], modules: [] };
    else if (url.pathname.includes("amo-assets")) data = { crs_logo_filename: null, crs_template_filename: null };
    else if (url.pathname.includes("identity-health")) data = { active_users_without_profile: 0, active_profiles_without_user: 0, issues: [] };
    else if (url.pathname.includes("dashboard")) data = { employees_without_contract_count: 0, employees_without_base_count: 0, employees_without_pattern_count: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
  });
}

test("tenant admin edits their organisation and follows the reporting-structure link", async ({ page }, testInfo) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/admin/amos");
  await expect(page.getByRole("heading", { name: "AMO Management", exact: true })).toBeVisible();
  await expect(page.getByLabel("Organisation name", { exact: true })).toHaveValue("Tenant Aviation");
  await page.getByLabel("Organisation name", { exact: true }).fill("Tenant Aviation Updated");
  const saved = page.waitForRequest((request) => request.url().endsWith("/accounts/admin/organisation") && request.method() === "PUT");
  await page.getByRole("button", { name: "Save organisation" }).click();
  expect((await saved).postDataJSON()).not.toHaveProperty("amo_id");
  await expect(page.getByText("Your AMO details have been updated.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Organisation structure/ })).toHaveAttribute("href", "/maintenance/tenant-a/rostering/settings?section=workforce&workforce_view=governance");
  await page.screenshot({ path: testInfo.outputPath("organisation.png"), fullPage: true });
});

test("release-assets deep link stays selected and supports forward and backward navigation", async ({ page }, testInfo) => {
  await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/maintenance/tenant-a/admin/amo-assets?section=assets");
  await expect(page.getByRole("heading", { name: "AMO Assets & Setup" })).toBeVisible();
  await expect(page.getByText("No approved logo uploaded")).toBeVisible();
  await expect(page).toHaveURL(/section=assets/);
  await page.getByRole("button", { name: "Next: Module setup" }).click();
  await expect(page).toHaveURL(/section=modules/);
  await page.getByRole("button", { name: "Back: CRS release assets" }).click();
  await expect(page.getByText("No approved logo uploaded")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath("assets-mobile.png"), fullPage: true });
});

test("foreign tenant URL returns to the assigned department despite stale department storage", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-b/admin/amos");
  await expect(page).toHaveURL(/\/maintenance\/tenant-a\/maintenance$/);
});


test("user management exposes frontend access-role administration and governed appointments", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/admin/users?tab=roles");
  await expect(page.getByRole("link", { name: "Open Workforce structure and appointments" })).toHaveAttribute("href", "/maintenance/tenant-a/rostering/settings?section=workforce&workforce_view=governance");
  await expect(page.getByRole("heading", { name: "Access Roles", exact: true })).toBeVisible();
  await expect(page.getByText(/Supporting access roles.*editable by AMO administrators/i)).toBeVisible();
  await expect(page.getByText(/Create and edit tenant access profiles/i)).toBeVisible();
  await page.goto("/maintenance/tenant-a/admin/users?tab=lifecycle");
  await expect(page.getByRole("heading", { name: "Employment lifecycle", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Workforce appointments" })).toHaveAttribute("href", "/maintenance/tenant-a/rostering/settings?section=workforce&workforce_view=governance");
});

test("failed group retrieval shows a retry instead of an empty directory", async ({ page }) => {
  await prepare(page);
  await page.route("**/accounts/admin/groups*", (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Permission denied" }) }));
  await page.goto("/maintenance/tenant-a/admin/users?tab=groups");
  await expect(page.getByRole("button", { name: "Retry groups" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("No groups configured.", { exact: true })).toHaveCount(0);
});
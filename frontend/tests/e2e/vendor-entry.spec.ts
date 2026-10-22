import { expect, test } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

test("vendor entry retains tenant context and ignores employee session expiry", async ({ page }) => {
  await page.goto("/vendor/login?amo=safarilink");
  await expect(page.getByRole("heading", { name: "Vendor access" })).toBeVisible();
  await expect(page.getByLabel("AMO tenant code")).toHaveValue("safarilink");
  await expect(page.getByRole("link", { name: "Staff / QMS sign in" })).toHaveAttribute("href", "/maintenance/safarilink/login");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("amo_session_event", {
    detail: { type: "expired", at: Date.now() },
  })));
  await expect(page.getByRole("heading", { name: "Vendor access" })).toBeVisible();
  await expect(page).toHaveURL(/\/vendor\/login\?amo=safarilink$/);
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await page.screenshot({ path: "../.artifacts/vendor-login-interface.png", fullPage: true });
});

test("staff login exposes a vendor entry before credentials", async ({ page }) => {
  await page.goto("/login");
  const options = page.getByRole("navigation", { name: "Sign in options" });
  await expect(options.getByRole("link", { name: "Vendor sign in" })).toBeVisible();
  await options.getByRole("link", { name: "Vendor sign in" }).click();
  await expect(page.getByRole("heading", { name: "Vendor access" })).toBeVisible();
});

test("Quality account governance keeps the tenant navigation and invitation controls", async ({ page }) => {
  await mockQualityShell(page);
  await page.route("**/quality/external-accounts**", route => {
    if (route.request().resourceType() === "document") return route.continue();
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], has_more: false }) });
  });
  await page.addInitScript(() => {
    const token = `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`;
    sessionStorage.setItem("amo_portal_token", token);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a", amo_id: "amo-a", amo_code: "AMO-A", amo_slug: "tenant-a",
      role: "QUALITY_MANAGER", first_name: "Quality", last_name: "Manager",
      full_name: "Quality Manager", is_active: true, is_superuser: false, is_amo_admin: false,
    }));
  });
  await page.goto("/maintenance/tenant-a/quality/external-accounts");
  await expect(page.getByRole("heading", { name: "External provider access" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Invite provider representative" })).toBeVisible();
  await expect(page.locator(".tenant-shell")).toBeVisible();
  await expect(page.getByRole("link", { name: "External Providers register", exact: true })).toHaveAttribute("href", "/maintenance/tenant-a/quality/suppliers/register");
  await page.screenshot({ path: "../.artifacts/qms-vendor-accounts-interface.png", fullPage: true });
  await page.goto("/maintenance/tenant-a/quality/external-accounts/register");
  await expect(page.getByRole("heading", { name: "External provider access" })).toBeVisible();
});

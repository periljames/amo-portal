import { test, expect } from "@playwright/test";

test("public verify shows instrument loader before valid response", async ({ page }) => {
  await page.route("**/api/v1/esign/verify/test-valid.json", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        title: "Demo verification",
        storage_integrity_valid: true,
        cryptographic_signature_applied: false,
        cryptographically_valid: false,
        timestamp_present: false,
        document_sha256: "abc",
        artifact_sha256: "def",
      }),
    });
  });

  await page.route("**/api/v1/esign/verify/test-valid/artifact-access", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        artifact_available: true,
        public_download_allowed: false,
      }),
    });
  });

  await page.goto("/verify/test-valid");
  await expect(page.getByText("Loading verification record")).toBeVisible();
  await expect(page.locator(".instrument-loader").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Demo verification" })).toBeVisible();
});

test("public verify loader clears on service error", async ({ page }) => {
  await page.route("**/api/v1/esign/verify/test-error.json", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({ status: 503, body: "{\"detail\":\"temporary\"}" });
  });

  await page.goto("/verify/test-error");
  await expect(page.getByText("Loading verification record")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verification service temporarily unavailable" })).toBeVisible();
});

test("instrument loader honors reduced motion", async ({ page }) => {
  await page.route("**/api/v1/esign/verify/test-reduced.json", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ status: 503, body: "{\"detail\":\"temporary\"}" });
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/verify/test-reduced");
  await expect(page.locator(".instrument-loader").first()).toBeVisible();
  const animation = await page.locator(".instrument-loader__orbit").first().evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toBe("none");
});

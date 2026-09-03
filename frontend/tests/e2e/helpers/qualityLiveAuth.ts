import { expect, type Page } from "@playwright/test";

/**
 * Canonical live Quality e2e auth (same contract as qms-calendar-live /
 * qms-modern-planner-live): UI login against a connected AMO, producing a real
 * sessionStorage JWT + HttpOnly refresh cookie via the Vite same-origin proxy.
 */
export const QUALITY_LIVE_ENABLED = process.env.E2E_LIVE_QUALITY === "1";
export const QUALITY_LIVE_AMO_CODE = process.env.E2E_AMO_CODE || "demo-amo";
export const QUALITY_LIVE_ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
export const QUALITY_LIVE_ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";

export function requireQualityLiveCredentials(): void {
  if (!QUALITY_LIVE_ADMIN_EMAIL || !QUALITY_LIVE_ADMIN_PASSWORD) {
    throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD for live Quality browser tests.");
  }
}

export async function signInQualityLive(page: Page, amoCode = QUALITY_LIVE_AMO_CODE): Promise<void> {
  requireQualityLiveCredentials();

  await page.goto(`/maintenance/${encodeURIComponent(amoCode)}/login`);
  await page.getByLabel("Email").fill(QUALITY_LIVE_ADMIN_EMAIL);

  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) {
    await continueButton.click();
  }

  const password = page.locator("#password");
  if (await password.count()) {
    await password.fill(QUALITY_LIVE_ADMIN_PASSWORD);
  } else {
    await page.getByLabel("Password").fill(QUALITY_LIVE_ADMIN_PASSWORD);
  }

  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

export async function assertAuthenticatedSession(page: Page, amoCode = QUALITY_LIVE_AMO_CODE): Promise<void> {
  const tokenPresent = await page.evaluate(() => Boolean(sessionStorage.getItem("amo_portal_token")));
  expect(tokenPresent, "expected sessionStorage access token after live sign-in").toBe(true);

  const me = await page.evaluate(async () => {
    const token = sessionStorage.getItem("amo_portal_token");
    const response = await fetch("/auth/me", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "include",
    });
    return { status: response.status, ok: response.ok };
  });
  expect(me.status, "/auth/me must succeed with the live session").toBe(200);

  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await expect(page.getByText(/secure session expired/i)).toHaveCount(0);
  await expect(page.getByText(/Portal connection unavailable/i)).toHaveCount(0);

  // Confirm tenant shell can render a Quality route for this AMO.
  await page.goto(`/maintenance/${encodeURIComponent(amoCode)}/quality`);
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await expect(page.getByText(/secure session expired/i)).toHaveCount(0);
}

import { expect, test, type Page } from "@playwright/test";

import {
  assertAuthenticatedSession,
  QUALITY_LIVE_AMO_CODE,
  QUALITY_LIVE_ENABLED,
  signInQualityLive,
} from "./helpers/qualityLiveAuth";

const amo = QUALITY_LIVE_AMO_CODE;
const qualityRoot = `/maintenance/${encodeURIComponent(amo)}/quality`;

/**
 * Live Audit Assurance journeys against a connected Vite+API runtime.
 * Gated by E2E_LIVE_QUALITY=1 — uses real UI login (no injected JWTs).
 */
test.use({
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "only-on-failure",
  video: "retain-on-failure",
});

test.describe("Audit Assurance live browser journeys", () => {
  test.skip(!QUALITY_LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected AMO environment.");

  test("auth smoke: live sign-in establishes session and Quality tenant route", async ({ page }) => {
    await signInQualityLive(page, amo);
    await assertAuthenticatedSession(page, amo);
  });

  test("Overview → Programme and Assurance Cases remain separate", async ({ page }) => {
    await signInQualityLive(page, amo);

    await page.goto(`${qualityRoot}/audits/dashboard`);
    await expect(page.getByLabel("Assurance workspace sections")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/secure session expired/i)).toHaveCount(0);
    await expect(page.getByText(/Portal connection unavailable/i)).toHaveCount(0);

    await page.getByRole("link", { name: /^Programme$/i }).first().click();
    await expect(page).toHaveURL(new RegExp(`${amo}/quality/audits/program`));
    await expect(page.getByRole("navigation", { name: "Programme workspace sections" })).toBeVisible({ timeout: 30_000 });

    await page.goto(`${qualityRoot}?workspace=assurance`);
    await expect(page).toHaveURL(/workspace=assurance/);
    await expect(page.getByText(/Assurance Cases|Cases/i).first()).toBeVisible();
  });

  test("Programme create drawer and schedule drawer / deep-link chrome", async ({ page }) => {
    await signInQualityLive(page, amo);
    await page.goto(`${qualityRoot}/audits/program`);
    await expect(page.getByRole("navigation", { name: "Programme workspace sections" })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: /New programme/i }).click();
    await expect(page.getByText(/Create continuous assurance programme/i)).toBeVisible();
    await page.getByRole("button", { name: /Cancel/i }).click();

    const queueButton = page.getByRole("region", { name: "Programme scheduling queue" }).getByRole("button").first();
    if (await queueButton.count()) {
      await queueButton.click();
      await expect(page.getByRole("heading", { name: "Schedule programme requirement", exact: true })).toBeVisible({ timeout: 15_000 });
    }

    const deeplink = page.locator("a.qms-audit-programme-flow__deeplink").first();
    if (await deeplink.count()) {
      const href = await deeplink.getAttribute("href");
      expect(href).toMatch(/\/audits\/program\/.+\/items\/.+\/schedule/);
      await page.goto(href!);
      await expect(page.getByLabel("Assurance workspace sections")).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("heading", { name: "Audit Programme", exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Schedule programme requirement", exact: true })).toBeVisible();
    }
  });

  test("Calendar/Planner CTAs resolve to Planner V2; plan?view=calendar redirects", async ({ page }) => {
    await signInQualityLive(page, amo);

    await page.goto(`${qualityRoot}/audits/dashboard`);
    await expect(page.getByLabel("Assurance workspace sections")).toBeVisible({ timeout: 30_000 });

    const plannerLink = page.getByRole("link", { name: /^Planner$/i }).first();
    await expect(plannerLink).toHaveAttribute("href", new RegExp(`${amo}/quality/calendar`));
    await plannerLink.click();
    await expect(page).toHaveURL(new RegExp(`${amo}/quality/calendar`));
    await expect(page.locator(".qms-modern-planner-v2, .qms-modern-planner")).toBeVisible({ timeout: 30_000 });

    await page.goto(`${qualityRoot}/audits/plan?view=calendar`);
    await expect(page).toHaveURL(new RegExp(`${amo}/quality/calendar`), { timeout: 15_000 });
  });

  test("Planner audit event links use canonical /setup when present", async ({ page }) => {
    await signInQualityLive(page, amo);
    await page.goto(`${qualityRoot}/calendar/week`);
    await expect(page.locator(".qms-modern-planner-v2, .qms-modern-planner")).toBeVisible({ timeout: 30_000 });

    const setupOrOverview = await page.evaluate(async () => {
      const token = sessionStorage.getItem("amo_portal_token");
      const amoSlug = localStorage.getItem("amo_slug") || "";
      const response = await fetch(`/api/maintenance/${encodeURIComponent(amoSlug)}/quality/integrations/calendar?view=week`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
      });
      if (!response.ok) return { status: response.status, links: [] as string[] };
      const body = (await response.json()) as { items?: Array<{ link?: string | null; module?: string }> };
      const links = (body.items || [])
        .filter((item) => item.module === "audits" && item.link)
        .map((item) => String(item.link));
      return { status: response.status, links };
    });

    expect(setupOrOverview.status).toBeLessThan(400);
    const auditLinks = setupOrOverview.links.filter((link) => /\/quality\/audits\//.test(link));
    for (const link of auditLinks) {
      expect(link, `audit calendar link must not use /overview: ${link}`).not.toMatch(/\/overview(?:\?|$)/);
    }
  });
});

async function collectFailedPrimaryRequests(page: Page): Promise<string[]> {
  const failed: string[] = [];
  page.on("response", (response) => {
    const url = response.url();
    if (!/\/(api\/maintenance|quality\/|auth\/)/.test(url)) return;
    if (response.status() >= 500) failed.push(`${response.status()} ${url}`);
    if (response.status() === 404 && /\/quality\/(audits|calendar|audit-programmes)/.test(url)) {
      failed.push(`${response.status()} ${url}`);
    }
  });
  return failed;
}

test.describe("Audit Assurance live console/network hygiene", () => {
  test.skip(!QUALITY_LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected AMO environment.");

  test("primary Assurance surfaces have no unexplained console errors or 5xx", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    const failed = await collectFailedPrimaryRequests(page);

    await signInQualityLive(page, amo);
    await page.goto(`${qualityRoot}/audits/dashboard`);
    await expect(page.getByLabel("Assurance workspace sections")).toBeVisible({ timeout: 30_000 });
    await page.goto(`${qualityRoot}/audits/program`);
    await expect(page.getByRole("navigation", { name: "Programme workspace sections" })).toBeVisible({ timeout: 30_000 });
    await page.goto(`${qualityRoot}/calendar/week`);
    await expect(page.locator(".qms-modern-planner-v2, .qms-modern-planner")).toBeVisible({ timeout: 30_000 });

    expect(failed, failed.join("\n")).toEqual([]);
    const unexplained = consoleErrors.filter((text) => !/ResizeObserver|favicon|sse|EventSource|aborted/i.test(text));
    expect(unexplained, unexplained.join("\n")).toEqual([]);
  });
});

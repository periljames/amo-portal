import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";
async function prepare(page: Page, readOnly = false) {
  await mockQualityShell(page);
  const settings = { numbering_rules: {}, retention_rules: {} };
  let follow = { report_due_days: 7, report_reminder_days: [7,3,1], car_reminder_percentages: [75,50,25], final_reminder_days_before_due: 2, auto_escalation_enabled: true };
  const writes: Record<string, unknown>[] = [];
  await page.route("**/quality/settings**", async route => {
    if (route.request().resourceType() === "document") return route.fallback();
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/numbering/reset")) {
      const data = route.request().postDataJSON(); writes.push(data);
      return data.prefix === "QAR" ? json({ detail: "This series already contains issued references through 12. Choose a new prefix to restart at zero; existing records are preserved." }, 409) : json({ next_value: data.last_value + 1 });
    }
    if (path.endsWith("/numbering")) return json({ rules: { audit_prefix: "QAR", car_prefix: "CAR", reliability_car_prefix: "RCAR", finding_prefix: "F", sequence_digits: 3, date_format: "YY" }, server_date: "2026-10-26", server_period: "2026", counter_year: 26, audit_scopes: [{code:"MO",name:"Maintenance organisation"}], car_unit_code:"MO", series: [{ id: "existing", prefix: "QAR", scope: "MO", year: 26, last_value: 12, next_value: 13 }] });
    if (path.endsWith("/follow-up")) { if (route.request().method() === "PATCH") { const data = route.request().postDataJSON(); writes.push(data); follow = { ...follow, ...data }; } return json({ settings: follow }); }
    if (route.request().method() === "PATCH") { const data = route.request().postDataJSON(); writes.push(data); Object.assign(settings, data); }
    return json({ tenant: { amo_code: "tenant-a" }, settings });
  });
  await page.addInitScript(({ readOnly }) => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now()/1000)+3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "manager", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: readOnly ? "VIEW_ONLY" : "QUALITY_MANAGER", full_name: "Quality User", is_amo_admin: !readOnly, is_active: true, capability_codes: readOnly ? ["qms.settings.view", "qms.dashboard.view"] : undefined }));
  }, { readOnly });
  return writes;
}
test("tenant tabs, reference previews and inline validation save real formats", async ({ page }) => {
  const writes = await prepare(page); await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await expect(page.getByRole("navigation", { name: "Settings sections" })).toBeVisible();
  await expect(page.locator(".qms-settings__scope")).toContainText("tenant-a");
  const field = page.getByLabel("Finding Prefix", { exact: true }); await field.fill("FIND");
  await expect(page.locator(".qms-settings__preview")).toContainText("-FIND-001");
  await page.getByLabel("CAR Prefix", { exact: true }).fill("QAR");
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
  await page.getByLabel("CAR Prefix", { exact: true }).fill("CAP");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved and recorded in Quality activity history.", { exact: true })).toBeVisible();
  expect(writes[0]).toMatchObject({ numbering_rules: { finding_prefix: "FIND", car_prefix: "CAP" }, expected_settings: { numbering_rules: {} } });
});
test("series controls retain a rejected reset and initialise a fresh prefix", async ({ page }) => {
  await prepare(page); await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await page.getByLabel("Reference series", { exact: true }).selectOption("existing");
  await page.getByRole("button", { name: "Adjust or initialise a series" }).click();
  await expect(page.getByRole("spinbutton", { name: /Reference year/ })).toHaveCount(0);
  await expect(page.getByLabel("Reference period")).toContainText("2026");
  await page.getByLabel("Last issued number", { exact: true }).fill("0");
  await page.getByLabel("Reason for series change").fill("Begin a fresh reporting series.");
  await page.getByRole("checkbox", { name: /^I confirm/ }).check();
  await page.getByRole("button", { name: "Apply series change" }).click();
  await expect(page.locator(".qms-settings__card").getByRole("alert")).toContainText("already contains issued references");
  await expect(page.getByRole("alert")).toHaveCount(1);
  await expect(page.getByLabel("Reason for series change")).toHaveValue("Begin a fresh reporting series.");
  await page.getByRole("combobox", { name: "Series prefix", exact: true }).selectOption("CAR");
  await page.getByRole("checkbox", { name: /^I confirm/ }).check();
  await page.getByRole("button", { name: "Apply series change" }).click();
  await expect(page.getByText("Series updated. The next number is 1.")).toBeVisible();
});
test("follow-up uses separate reminder inputs and validates before saving", async ({ page }) => {
  const writes = await prepare(page); await page.goto("/maintenance/tenant-a/quality/settings/workflows");
  const due = page.getByLabel("Report due after fieldwork (days)"); await due.fill("0");
  await expect(page.getByRole("button", { name: "Save follow-up" })).toBeDisabled();
  await due.fill("10"); await page.getByRole("button", { name: "Save follow-up" }).click();
  await expect(page.getByText("Follow-up settings saved.")).toBeVisible();
  expect(writes[0]).toMatchObject({ report_due_days: 10, expected_settings: { report_due_days: 7 } });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const tray = page.locator(".qms-settings__save");
  const feedbackBounds = await tray.getByRole("status").boundingBox();
  expect(feedbackBounds?.height).toBeLessThan(200);
  expect((await tray.locator(".qms-settings__feedback>div").boundingBox())?.width).toBeGreaterThan(150);
});

test("read-only capability exposes configuration without edit or reset controls", async ({ page }) => {
  const writes = await prepare(page, true); await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await expect(page.getByLabel("Audit Prefix", { exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Adjust or initialise a series" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

test("reference dates use the server clock and configurable ISO presentation", async ({ page }) => {
  const writes = await prepare(page);
  await page.addInitScript(() => { Date.prototype.getFullYear = () => 1999; });
  await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await expect(page.getByLabel("Server reference date")).toHaveText("2026-10-26");
  await page.getByRole("combobox", { name: "Reference date format", exact: true }).selectOption("YYYY-MM");
  await expect(page.locator(".qms-settings__preview")).toContainText("QAR/MO/2026-10/001");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved and recorded in Quality activity history.")).toBeVisible();
  expect(writes[0]).toMatchObject({ numbering_rules: { date_format: "YYYY-MM" } });
});

test("save feedback stays by the action, retains failed drafts and honours muted chimes", async ({ page }) => {
  await prepare(page);
  await page.addInitScript(() => {
    const tones: number[] = [];
    Object.assign(window, { settingsTestTones: tones });
    const original = AudioContext.prototype.createOscillator;
    AudioContext.prototype.createOscillator = function () {
      const oscillator = original.call(this);
      const setFrequency = oscillator.frequency.setValueAtTime.bind(oscillator.frequency);
      oscillator.frequency.setValueAtTime = (value, time) => { tones.push(value); return setFrequency(value, time); };
      return oscillator;
    };
  });
  await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await page.getByLabel("Finding Prefix", { exact: true }).fill("FN");
  let fail = true;
  let release: () => void = () => undefined;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/quality/settings", async route => {
    if (route.request().method() !== "PATCH") return route.fallback();
    if (fail) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Temporary outage" }) });
    await pending;
    return route.fallback();
  });
  const save = page.getByRole("button", { name: "Save changes", exact: true });
  await save.click();
  const tray = page.locator(".qms-settings__save");
  await expect(tray.getByRole("alert")).toContainText("Your entries are retained");
  await expect(page.getByRole("alert")).toHaveCount(1);
  await expect(page.getByLabel("Finding Prefix", { exact: true })).toHaveValue("FN");
  expect(await page.evaluate(() => (window as Window & { settingsTestTones: number[] }).settingsTestTones)).toEqual([]);
  fail = false;
  await save.click();
  await expect(tray.locator("button[aria-busy=true]")).toBeDisabled();
  await expect(tray.locator(".qms-settings__spinner")).toBeVisible();
  release();
  await expect(tray.getByRole("status")).toContainText("Saved successfully");
  await expect(save).toHaveAttribute("data-state", "saved");
  await expect.poll(() => page.evaluate(() => (window as Window & { settingsTestTones: number[] }).settingsTestTones)).toEqual([660,880]);
  await page.getByRole("button", { name: "Dismiss confirmation" }).click();
  await expect(tray.getByRole("status")).toHaveCount(0);
  await page.getByRole("button", { name: "Notification sounds", exact: true }).click();
  await expect(page.getByRole("button", { name: "Notification sounds", exact: true })).toHaveAttribute("aria-pressed", "false");
  await page.getByLabel("Finding Prefix", { exact: true }).fill("FIND");
  await save.click();
  await expect(tray.getByRole("status")).toContainText("Saved successfully");
  expect(await page.evaluate(() => (window as Window & { settingsTestTones: number[] }).settingsTestTones)).toEqual([660,880]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect((await tray.getByRole("status").boundingBox())?.height).toBeLessThan(200);
  expect((await tray.locator(".qms-settings__feedback>div").boundingBox())?.width).toBeGreaterThan(150);
  expect(await save.evaluate(el => parseFloat(getComputedStyle(el).transitionDuration))).toBeLessThanOrEqual(0.001);
});

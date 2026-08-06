import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure" });
test.setTimeout(60_000);

const DATASETS = ["AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "STRUCTURES", "RECURRING", "ECTM", "ADD"] as const;

const fields: Record<string, Array<Record<string, unknown>>> = {
  AU: [{ key: "flight_hours", label: "Aircraft flight hours", data_type: "decimal", required: true, unit: "FH", options: [] }],
  AI: [{ key: "incident_number", label: "Incident number", data_type: "text", required: true, options: [] }],
  FI: [{ key: "interruption_type", label: "Interruption type", data_type: "select", required: true, options: ["TECHNICAL_DELAY", "TECHNICAL_CANCELLATION"] }],
  PM: [{ key: "defect_description", label: "Defect / report", data_type: "textarea", required: true, options: [] }],
  OOS: [{ key: "start_at", label: "Out-of-service start", data_type: "datetime", required: true, options: [] }],
  RM: [{ key: "off_part_number", label: "Removed part number", data_type: "text", required: true, options: [] }],
  SM: [{ key: "workpack_reference", label: "Workpack reference", data_type: "text", required: true, options: [] }],
  SR: [{ key: "shop_visit_reference", label: "Shop visit reference", data_type: "text", required: true, options: [] }],
  STRUCTURES: [{ key: "damage_reference", label: "Damage reference", data_type: "text", required: true, options: [] }],
  RECURRING: [{ key: "repeat_key", label: "Controlled repeat key", data_type: "text", required: true, options: [] }],
  ECTM: [{ key: "trend_status", label: "Trend status", data_type: "select", required: true, options: ["NORMAL", "WATCH", "ALERT"] }],
  ADD: [{ key: "deferral_type", label: "Deferral type", data_type: "select", required: true, options: ["MEL", "CDL"] }],
};

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function catalog() {
  return DATASETS.map((code) => ({
    code,
    name: {
      AU: "Aircraft utilisation",
      AI: "Aircraft incidents",
      FI: "Flight interruptions",
      PM: "Pilot and maintenance reports",
      OOS: "Aircraft out of service",
      RM: "Component removals",
      SM: "Scheduled maintenance findings",
      SR: "Shop reports",
      STRUCTURES: "Aircraft structures",
      RECURRING: "Recurring defects",
      ECTM: "Engine condition and trend monitoring",
      ADD: "Deferred defects / MEL / CDL",
    }[code],
    workbook_sheet_names: [code],
    description: `${code} representative tenant source register`,
    fields: fields[code],
  }));
}

async function fulfilApi(route: Route): Promise<void> {
  const url = new URL(route.request().url());
  const path = url.pathname;
  const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  if (path.includes("/reliability/workbook-parity")) {
    if (path.endsWith("/catalog")) return json(catalog());
    if (path.endsWith("/records")) return json([]);
    if (path.endsWith("/oos-metrics")) return json({ records: 3, downtime_hours: 18.5, scheduled_available_hours: 720, available_hours: 701.5, availability_pct: 97.43, mttr_hours: 6.17 });
    if (path.endsWith("/statistical-alerts")) return json([]);
    if (path.endsWith("/mappings")) return json([]);
    if (path.endsWith("/parity")) return json(DATASETS.map((code) => ({ dataset_code: code, dataset_name: code, required_fields: [], optional_fields: [], mapped_required_fields: [], missing_required_fields: [], coverage_pct: 100, record_count: 0 })));
    if (path.endsWith("/contracts")) return json({ mapping: { profiles: { "SAFARILINK-C208B-RP": {}, "SAFARILINK-DHC8-RP": {}, "GENERIC-ANALYSIS-TEMPLATE": {} }, datasets: {} }, report_layouts: { required_datasets: DATASETS, layouts: {} } });
    if (path.endsWith("/imports")) return json({ total: 0, offset: 0, limit: 50, items: [] });
    if (path.endsWith("/report-layouts")) return json([
      { id: 1, code: "C208B-RP", name: "Cessna 208B Reliability Programme Report", aircraft_family: "C208B", revision: 1, active: true, sections: [], page_settings: {} },
      { id: 2, code: "DHC8-RP", name: "DHC8 Reliability Programme Report", aircraft_family: "DHC8", revision: 1, active: true, sections: [], page_settings: {} },
    ]);
    if (path.endsWith("/reports")) return json([]);
    return json({});
  }

  if (url.origin === "http://127.0.0.1:8080") {
    if (path.includes("/accounts/admin/admin-profile/")) return json({ eligible: false, active: false });
    if (path.endsWith("/auth/onboarding-status")) return json({ is_complete: true, missing: [] });
    return json({ detail: "Not configured in Reliability render UAT" }, 404);
  }

  return route.continue();
}

async function openWorkspace(page: Page): Promise<void> {
  const token = futureToken();
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.addInitScript(({ storedToken }) => {
    const onboarding = JSON.stringify({ is_complete: true, missing: [] });
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "SAFARILINK");
    localStorage.setItem("amo_slug", "safarilink");
    localStorage.setItem("amo_department", "reliability");
    localStorage.setItem("amo_onboarding_status", onboarding);
    sessionStorage.setItem("amo_onboarding_status", onboarding);
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "uat-user", amo_id: "uat-amo", department_id: "uat-rel", staff_code: "REL-UAT",
      email: "uat@example.invalid", first_name: "Reliability", last_name: "UAT", full_name: "Reliability UAT",
      role: "QUALITY_MANAGER", position_title: "Reliability Manager", phone: null,
      regulatory_authority: "KCAA", licence_number: null, licence_state_or_country: null, licence_expires_on: null,
      is_active: true, is_superuser: false, is_amo_admin: false, must_change_password: false,
      last_login_at: null, last_login_ip: null, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    }));
  }, { storedToken: token });
  await page.route("**/*", fulfilApi);
  await page.goto("/maintenance/safarilink/reliability/workbook-parity", { waitUntil: "domcontentloaded" });

  try {
    await expect(page.getByTestId("reliability-workbook-parity"), `Expected workbook parity workspace at ${page.url()}`).toBeVisible({ timeout: 30_000 });
  } catch (error) {
    const body = (await page.locator("body").innerText().catch(() => "<body unavailable>")).slice(0, 4000);
    throw new Error(`Workbook parity workspace did not render. URL: ${page.url()}\nBody: ${body}\nBrowser errors: ${consoleErrors.join(" | ") || "none"}\n${String(error)}`);
  }
}

test.describe("Reliability workbook parity representative-tenant UAT", () => {
  test("wires every workbook register, governance view and controlled report surface", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openWorkspace(page);

    for (const code of DATASETS) await expect(page.getByRole("button", { name: new RegExp(`^${code}\\b`) })).toBeVisible();
    await page.getByRole("button", { name: /^OOS\b/ }).click();
    await expect(page.getByRole("heading", { name: "Aircraft out of service" })).toBeVisible();
    await expect(page.getByText("97.43%")).toBeVisible();
    await expect(page.getByText("6.17 h")).toBeVisible();

    await page.getByRole("button", { name: /Statistical alerts/ }).click();
    await expect(page.getByRole("heading", { name: "Statistical alert calculation" })).toBeVisible();
    await page.getByRole("button", { name: /Mapping & imports/ }).click();
    await expect(page.getByRole("heading", { name: "Field mapping and parity" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Controlled workbook import" })).toBeVisible();
    await page.getByRole("button", { name: /Report layouts/ }).click();
    await expect(page.getByRole("heading", { name: "Report layouts" })).toBeVisible();
    await expect(page.getByText("Cessna 208B Reliability Programme Report")).toBeVisible();
    await expect(page.getByText("DHC8 Reliability Programme Report")).toBeVisible();

    const widths = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport + 2);
  });

  test("keeps the parity workspace usable on a narrow operational screen", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openWorkspace(page);
    const widths = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport + 2);
    await expect(page.getByRole("button", { name: /^AU\b/ })).toBeVisible();
  });
});

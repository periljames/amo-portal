import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure" });
test.setTimeout(60_000);

const DATASETS = [
  "AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR",
  "SB", "CS", "AS", "UR", "STRUCTURES", "RECURRING", "ECTM", "ADD",
] as const;

const names: Record<string, string> = {
  AU: "Aircraft utilisation",
  AI: "Aircraft incidents",
  FI: "Flight interruptions",
  PM: "Pilot and maintenance reports",
  OOS: "Aircraft out of service",
  RM: "Component removals",
  SM: "Scheduled maintenance findings",
  SR: "Shop reports",
  SB: "Service bulletins and modifications",
  CS: "Maintenance cost",
  AS: "Aircraft change status",
  UR: "Component removal-rate analysis",
  STRUCTURES: "Aircraft structures",
  RECURRING: "Recurring defects",
  ECTM: "Engine condition and trend monitoring",
  ADD: "Deferred defects / MEL / CDL",
};

const fields: Record<string, Array<Record<string, unknown>>> = {
  AU: [{ key: "flight_hours", label: "Aircraft flight hours", data_type: "decimal", required: true, unit: "FH", options: [] }],
  AI: [{ key: "incident_number", label: "Incident number", data_type: "text", required: true, options: [] }],
  FI: [{ key: "interruption_type", label: "Interruption type", data_type: "select", required: true, options: ["TECHNICAL_DELAY", "TECHNICAL_CANCELLATION"] }],
  PM: [{ key: "defect_description", label: "Defect / report", data_type: "textarea", required: true, options: [] }],
  OOS: [{ key: "start_at", label: "Out-of-service start", data_type: "datetime", required: true, options: [] }],
  RM: [{ key: "off_part_number", label: "Removed part number", data_type: "text", required: true, options: [] }],
  SM: [{ key: "workpack_reference", label: "Workpack reference", data_type: "text", required: true, options: [] }],
  SR: [{ key: "shop_visit_reference", label: "Shop visit reference", data_type: "text", required: true, options: [] }],
  SB: [{ key: "service_bulletin_number", label: "Service bulletin number", data_type: "text", required: false, options: [] }],
  CS: [{ key: "total_cost", label: "Total cost", data_type: "decimal", required: false, options: [] }],
  AS: [{ key: "effective_change_date", label: "Effective change date", data_type: "date", required: true, options: [] }],
  UR: [{ key: "unit_hours", label: "Fleet unit-hours", data_type: "decimal", required: true, options: [] }],
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
    name: names[code],
    workbook_sheet_names: [code],
    description: `${code} representative tenant source register`,
    fields: fields[code],
  }));
}

function csvPreview() {
  return {
    id: 501,
    profile_code: "STRUCTURED-CSV",
    dataset_code: "AU",
    original_filename: "daily-au.csv",
    sanitized_filename: "daily-au.csv",
    file_extension: ".csv",
    file_size_bytes: 96,
    source_hash: "a".repeat(64),
    status: "PREVIEW_READY",
    detected_sheets: [{ name: "CSV", state: "visible", max_row: 2, max_column: 4 }],
    selected_sheet: "CSV-AU",
    header_row: 1,
    header_map: { "1": "event_date", "2": "aircraft_serial_number", "3": "title", "4": "flight_hours" },
    total_rows: 1,
    valid_rows: 1,
    invalid_rows: 0,
    committed_rows: 0,
    failed_rows: 0,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    completed_at: null,
    preview_truncated: false,
    preview_rows: [{
      id: 9001,
      row_number: 2,
      status: "VALID",
      raw_values: { "1": "2026-08-07", "2": "5Y-SLK", "3": "Daily utilisation", "4": "6.25" },
      mapped_values: { dataset_code: "AU", event_date: "2026-08-07", aircraft_serial_number: "5Y-SLK", title: "Daily utilisation", payload: { flight_hours: "6.25" } },
      errors: [],
      row_source_hash: "b".repeat(64),
    }],
  };
}

async function fulfilApi(route: Route): Promise<void> {
  const url = new URL(route.request().url());
  const path = url.pathname;
  const json = (body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  // apiClient intentionally uses same-origin first on Vite preview surfaces. Mock
  // the Reliability API before the preview-origin pass-through so Vite's SPA
  // fallback cannot return index.html for an API request and hide the fixture.
  if (path.includes("/reliability/workbook-parity")) {
    if (path.endsWith("/catalog")) return json(catalog());
    if (path.endsWith("/imports/csv-preview") && route.request().method() === "POST") return json(csvPreview(), 201);
    if (path.endsWith("/imports/501/commit") && route.request().method() === "POST") {
      return json({ ...csvPreview(), status: "COMPLETED", valid_rows: 0, committed_rows: 1, processed: 1, remaining_valid_rows: 0, completed_at: "2026-08-07T09:01:00Z" });
    }
    if (path.endsWith("/management-reports/render") && route.request().method() === "POST") {
      return json({
        id: 42,
        layout_id: 7,
        layout_code: "MANAGEMENT-PERIOD",
        layout_name: "Reliability Management Period Report",
        period_start: "2026-01-01",
        period_end: "2026-03-31",
        aircraft: [],
        sha256_hash: "c".repeat(64),
        generated_at: "2026-08-07T09:02:00Z",
        download_url: "/reliability/workbook-parity/reports/42/html",
        view_url: "/reliability/workbook-parity/reports/42/view",
        pdf_url: "/reliability/workbook-parity/reports/42/pdf",
        data_url: "/reliability/workbook-parity/reports/42/data",
      }, 201);
    }
    if (path.endsWith("/reports/42/view")) {
      return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><html><body><h1>Q1 Reliability Management Report</h1><p>1,250.0 FH · 1,840 FC</p></body></html>" });
    }
    if (path.endsWith("/reports/42/data")) {
      return json({ id: 42, layout_code: "MANAGEMENT-PERIOD", layout_name: "Reliability Management Period Report", period_start: "2026-01-01", period_end: "2026-03-31", aircraft: [], sha256_hash: "c".repeat(64), generated_at: "2026-08-07T09:02:00Z", rendered_data: {} });
    }
    if (path.endsWith("/records")) return json([]);
    if (path.endsWith("/oos-metrics")) {
      return json({ records: 3, downtime_hours: 18.5, scheduled_available_hours: 720, available_hours: 701.5, availability_pct: 97.43, mttr_hours: 6.17 });
    }
    if (path.endsWith("/statistical-alerts")) return json([]);
    if (path.endsWith("/mappings")) return json([]);
    if (path.endsWith("/parity")) {
      return json(DATASETS.map((code) => ({ dataset_code: code, dataset_name: names[code], required_fields: [], optional_fields: [], mapped_required_fields: [], missing_required_fields: [], coverage_pct: 100, record_count: 0 })));
    }
    if (path.endsWith("/contracts")) {
      return json({ mapping: { profiles: { "SAFARILINK-C208B-RP": {}, "SAFARILINK-DHC8-RP": {}, "GENERIC-ANALYSIS-TEMPLATE": {} }, datasets: {} }, report_layouts: { required_datasets: DATASETS, layouts: {} } });
    }
    if (path.endsWith("/imports")) return json({ total: 0, offset: 0, limit: 50, items: [] });
    if (path.endsWith("/report-layouts")) {
      return json([
        { id: 1, code: "C208B-RP", name: "Cessna 208B Reliability Programme Report", aircraft_family: "C208B", revision: 1, active: true, sections: [], page_settings: {} },
        { id: 2, code: "DHC8-RP", name: "DHC8 Reliability Programme Report", aircraft_family: "DHC8", revision: 1, active: true, sections: [], page_settings: {} },
      ]);
    }
    if (path.endsWith("/reports")) return json([]);
    return json({});
  }

  if (url.origin === "http://127.0.0.1:4173") {
    if (path === "/api/realtime/presence" && route.request().method() === "POST") {
      return json({ state: "online" });
    }
    await route.continue();
    return;
  }

  if (url.origin === "http://127.0.0.1:8080") {
    if (path.includes("/accounts/admin/admin-profile/")) return json({ eligible: false, active: false });
    if (path.endsWith("/auth/onboarding-status")) return json({ is_complete: true, missing: [] });
    return json({ detail: "Not configured in Reliability render UAT" }, 404);
  }

  await route.continue();
}

async function openWorkspace(page: Page): Promise<void> {
  const token = futureToken();
  const consoleErrors: string[] = [];

  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
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
      id: "uat-user", amo_id: "uat-amo", department_id: "uat-rel", staff_code: "REL-UAT", email: "uat@example.invalid",
      first_name: "Reliability", last_name: "UAT", full_name: "Reliability UAT", role: "QUALITY_MANAGER", position_title: "Reliability Manager",
      phone: null, regulatory_authority: "KCAA", licence_number: null, licence_state_or_country: null, licence_expires_on: null,
      is_active: true, is_superuser: false, is_amo_admin: false, must_change_password: false, last_login_at: null, last_login_ip: null,
      created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
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
  test("wires every register, governed CSV, analysis and retained reports", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openWorkspace(page);

    for (const code of DATASETS) await expect(page.getByRole("button", { name: new RegExp(`^${code}\\b`) })).toBeVisible();

    await page.getByRole("button", { name: /^OOS\b/ }).click();
    await expect(page.getByRole("heading", { name: "Aircraft out of service" })).toBeVisible();
    await page.getByLabel("From", { exact: true }).fill("2026-07-01");
    await page.getByLabel("To", { exact: true }).fill("2026-07-31");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByText("97.43%")).toBeVisible();
    await expect(page.getByText("6.17 h")).toBeVisible();

    await page.getByRole("button", { name: /Statistical alerts/ }).click();
    await expect(page.getByRole("heading", { name: "Statistical alert calculation" })).toBeVisible();
    await expect(page.getByLabel("Analysis method")).toBeVisible();

    await page.getByRole("button", { name: /Mapping & imports/ }).click();
    await expect(page.getByRole("heading", { name: "Structured CSV / TSV import" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Field mapping and parity" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Controlled workbook import" })).toBeVisible();
    await page.getByLabel("CSV / TSV file").setInputFiles({ name: "daily-au.csv", mimeType: "text/csv", buffer: Buffer.from("event_date,aircraft_serial_number,title,flight_hours\n2026-08-07,5Y-SLK,Daily utilisation,6.25\n") });
    await page.getByRole("button", { name: "Audit and preview CSV" }).click();
    await expect(page.getByText("1 row(s) passed validation")).toBeVisible();
    await page.getByRole("button", { name: "Commit next 100 controlled drafts" }).click();
    await expect(page.getByText("1 row(s) were committed as controlled DRAFT records")).toBeVisible();

    await page.getByRole("button", { name: /Report layouts/ }).click();
    await expect(page.getByRole("heading", { name: "Reliability management period report" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Report layouts" })).toBeVisible();
    await expect(page.getByRole("button", { name: /C208B-RP Cessna 208B Reliability Programme Report/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /DHC8-RP DHC8 Reliability Programme Report/ })).toBeVisible();
    await page.getByRole("button", { name: "Q1" }).click();
    await page.getByRole("button", { name: "Full programme" }).click();
    await page.getByRole("button", { name: "Generate and retain management report" }).click();
    await expect(page.getByRole("heading", { name: "Snapshot 42" })).toBeVisible();
    await expect(page).toHaveURL(/snapshot=42/);
    await expect(page.getByRole("button", { name: "Copy manager link" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Download controlled PDF" })).toBeVisible();

    const widths = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport + 2);
  });

  test("keeps the workspace usable on a narrow operational screen", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openWorkspace(page);
    const widths = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport + 2);
    await expect(page.getByRole("button", { name: /^AU\b/ })).toBeVisible();
  });
});
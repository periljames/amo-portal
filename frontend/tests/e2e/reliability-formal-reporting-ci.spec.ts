import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure" });
test.setTimeout(90_000);

type ReportStatus = "DRAFT" | "DATA_REVIEW" | "TECHNICAL_REVIEW" | "QUALITY_REVIEW" | "APPROVAL_PENDING" | "APPROVED" | "PUBLISHED" | "SUPERSEDED" | "WITHDRAWN";
type MockReport = ReturnType<typeof reportFixture>;

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function profileFixture() {
  return {
    id: "profile-kcaa",
    code: "KCAA",
    version: "2026-08-07.1",
    name: "KCAA Reliability Programme baseline",
    authority: "KCAA",
    jurisdiction: "Kenya",
    status: "ACTIVE",
    required_sections: [{ code: "executive_assessment", title: "Executive assessment", required: true }],
    mandatory_kpis: ["event_rate_per_100_fh"],
    historical_windows: [12, 24, 36],
    approval_workflow: {},
    publication_rules: {},
    source_manifest: [{ code: "AU" }, { code: "FI" }],
  };
}

function reportFixture(id: string, number: string, periodType: "HALF_YEAR" | "ANNUAL", start: string, end: string) {
  return {
    id,
    report_number: number,
    revision: 0,
    title: periodType === "ANNUAL" ? "Annual Reliability Programme Report" : "Half-year Reliability Programme Review",
    period_type: periodType,
    period_start: start,
    period_end: end,
    status: "DRAFT" as ReportStatus,
    profile_id: "profile-kcaa",
    profile_code: "KCAA",
    profile_version: "2026-08-07.1",
    data_cutoff_at: null as string | null,
    effectivity: {},
    effectivity_frozen_at: null as string | null,
    html_sha256: null as string | null,
    pdf_sha256: null as string | null,
    published_at: null as string | null,
    supersedes_report_id: null as string | null,
    created_at: "2026-08-07T10:00:00Z",
    regulatory_manifest: [],
    source_population: {},
    formula_revisions: [{ code: "event_rate_per_100_fh", version: "1.0" }],
    data_quality: {},
    completeness: { passed: false, checks: [], blocking_failures: ["MANDATORY_SECTIONS", "REQUIREMENT:req-1", "HTML_HASH", "PDF_HASH"], override_count: 0 },
    sections: [{
      id: `${id}-section-1`, code: "executive_assessment", sequence: 1, title: "Executive assessment", required: true,
      status: "DRAFT" as "DRAFT" | "READY" | "WITHHELD" | "NOT_APPLICABLE",
      computed_data: {
        event_rate_per_100_fh: { value: null, quality: "WITHHELD_NO_FLIGHT_HOURS", denominator: 0 },
        long_term_history: { configured_windows: [12, 24, 36] },
      },
      commentary: [] as Array<Record<string, unknown>>, evidence_refs: [], warnings: [],
    }],
    requirements: [{
      id: `${id}-assessment-1`, requirement_id: "req-1", section_code: "executive_assessment", applicable: true,
      status: "GAP" as "SATISFIED" | "NOT_APPLICABLE" | "WITHHELD" | "GAP" | "SUPERSEDED",
      requirement: {
        requirement_key: "KCAA-CURRENT-REGULATORY-MAPPING", authority: "KCAA", source_reference: "KCARs 2025",
        paragraph_reference: "Operator applicability", controlled_summary: "Current controlling KCAA basis must be evidenced before publication.", obligation_status: "MANDATORY",
      },
      evidence_refs: [] as Array<Record<string, unknown>>, calculation_refs: [] as Array<Record<string, unknown>>, source_refs: [] as Array<Record<string, unknown>>, reviewer_note: null as string | null,
    }],
  };
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function createMockApi() {
  const reports = new Map<string, MockReport>();
  let sequence = 1;
  let denyTransition = false;
  let crossTenantFailure = false;
  let postCutoffMutationCount = 0;

  const list = () => Array.from(reports.values()).map(clone);
  const report = (id: string) => reports.get(id);
  const ready = (row: MockReport) => {
    const sectionReady = row.sections.every((item) => item.status === "READY" || item.status === "NOT_APPLICABLE");
    const requirementsReady = row.requirements.every((item) => item.status !== "GAP" && item.status !== "WITHHELD");
    const artifactReady = Boolean(row.html_sha256 && row.pdf_sha256);
    return sectionReady && requirementsReady && artifactReady;
  };

  async function handle(route: Route): Promise<void> {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (url.origin === "http://127.0.0.1:4173") {
      if (path === "/api/realtime/presence" && method === "POST") return json({ state: "online" });
      await route.continue();
      return;
    }

    if (url.origin !== "http://127.0.0.1:8080") {
      await route.continue();
      return;
    }

    if (path.includes("/accounts/admin/admin-profile/")) return json({ eligible: false, active: false });
    if (path.endsWith("/auth/onboarding-status")) return json({ is_complete: true, missing: [] });

    const root = "/reliability/formal-reporting";
    if (!path.startsWith(root)) return json({ detail: "Not configured in formal Reliability UAT" }, 404);
    const suffix = path.slice(root.length);

    if (suffix === "/profiles" && method === "GET") return json({ profiles: [profileFixture()] });
    if (suffix === "/reports" && method === "GET") return json({ total: reports.size, limit: 100, offset: 0, reports: list() });
    if (suffix === "/reports" && method === "POST") {
      const body = route.request().postDataJSON() as { report_number: string; title: string; period_type: "HALF_YEAR" | "ANNUAL"; period_start: string; period_end: string };
      const id = `formal-${sequence++}`;
      const row = reportFixture(id, body.report_number, body.period_type, body.period_start, body.period_end);
      row.title = body.title;
      reports.set(id, row);
      return json(clone(row), 201);
    }

    const match = suffix.match(/^\/reports\/([^/]+)(.*)$/);
    if (!match) {
      if (suffix.startsWith("/schedule")) return json({ total: 0, limit: 500, offset: 0, items: [] });
      if (suffix.startsWith("/amp-recommendations")) return json({ total: 0, limit: 500, offset: 0, items: [] });
      return json({ detail: "Unknown formal Reliability endpoint" }, 404);
    }

    const id = decodeURIComponent(match[1]);
    const action = match[2];
    if (crossTenantFailure && id === "other-tenant") return json({ detail: "Formal Reliability report not found." }, 404);
    const row = report(id);
    if (!row) return json({ detail: "Formal Reliability report not found." }, 404);

    if (!action && method === "GET") return json(clone(row));
    if (action === "/freeze" && method === "POST") {
      row.status = "DATA_REVIEW";
      row.data_cutoff_at = "2026-08-07T10:30:00Z";
      row.effectivity_frozen_at = row.data_cutoff_at;
      row.effectivity = { scope: "TENANT_FLEET", aircraft_serial_numbers: [] };
      row.source_population = { source_identity_sha256: "a".repeat(64), canonical_event_count: 12, post_cutoff_mutations_ignored: postCutoffMutationCount };
      return json(clone(row));
    }
    if (action.startsWith("/sections/") && method === "PUT") {
      const body = route.request().postDataJSON() as { status: "DRAFT" | "READY" | "WITHHELD" | "NOT_APPLICABLE"; commentary: Array<Record<string, unknown>> };
      row.sections[0].status = body.status;
      row.sections[0].commentary = body.commentary;
      return json(clone(row));
    }
    if (action.startsWith("/requirements/") && method === "PUT") {
      const body = route.request().postDataJSON() as { status: "SATISFIED" | "NOT_APPLICABLE" | "WITHHELD" | "GAP" | "SUPERSEDED"; reviewer_note?: string | null; source_refs?: Array<Record<string, unknown>> };
      row.requirements[0].status = body.status;
      row.requirements[0].reviewer_note = body.reviewer_note || null;
      row.requirements[0].source_refs = body.source_refs || [];
      return json(clone(row));
    }
    if (action === "/render" && method === "POST") {
      row.html_sha256 = "b".repeat(64);
      row.pdf_sha256 = "c".repeat(64);
      return json(clone(row));
    }
    if (action === "/completeness" && method === "POST") {
      const passed = ready(row);
      const failures: string[] = [];
      if (!row.sections.every((item) => item.status === "READY" || item.status === "NOT_APPLICABLE")) failures.push("MANDATORY_SECTIONS");
      if (row.requirements.some((item) => item.status === "GAP")) failures.push("REQUIREMENT:req-1");
      if (!row.html_sha256) failures.push("HTML_HASH");
      if (!row.pdf_sha256) failures.push("PDF_HASH");
      row.completeness = {
        passed,
        checks: failures.map((code) => ({ code, passed: false, raw_passed: false, overridden: false, blocking: true, message: code.includes("REQUIREMENT") ? "Applicable mandatory KCAA requirement remains GAP." : `${code} incomplete.` })),
        blocking_failures: failures,
        override_count: 0,
      };
      return json(clone(row.completeness));
    }
    if (action === "/transition" && method === "POST") {
      if (denyTransition) return json({ detail: "Your role cannot perform this formal Reliability transition." }, 403);
      const body = route.request().postDataJSON() as { to_status: ReportStatus };
      if (["APPROVAL_PENDING", "APPROVED", "PUBLISHED"].includes(body.to_status) && !ready(row)) {
        return json({ detail: { message: "Formal Reliability report completeness gate failed.", blocking_failures: ["REQUIREMENT:req-1"] } }, 409);
      }
      row.status = body.to_status;
      if (body.to_status === "PUBLISHED") row.published_at = "2026-08-07T11:00:00Z";
      return json(clone(row));
    }
    if (action === "/view" && method === "GET") {
      const warning = row.status === "SUPERSEDED" ? "SUPERSEDED — retained historical revision" : "CURRENT CONTROLLED REVISION";
      return route.fulfill({ status: 200, contentType: "text/html", headers: { ETag: row.html_sha256 || "" }, body: `<!doctype html><html><body><div>${warning}</div><h1>${row.report_number}</h1><p>${row.html_sha256}</p></body></html>` });
    }
    if (action === "/pdf" && method === "GET") return route.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.4 mock" });
    return json({ detail: "Unknown report action" }, 404);
  }

  return {
    handle,
    reports,
    denyTransitions(value: boolean) { denyTransition = value; },
    setCrossTenantFailure(value: boolean) { crossTenantFailure = value; },
    recordPostCutoffMutation() { postCutoffMutationCount += 1; },
  };
}

async function authenticate(page: Page): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken }) => {
    const onboarding = JSON.stringify({ is_complete: true, missing: [] });
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "SAFARILINK");
    localStorage.setItem("amo_slug", "safarilink");
    localStorage.setItem("amo_department", "reliability");
    localStorage.setItem("amo_onboarding_status", onboarding);
    sessionStorage.setItem("amo_onboarding_status", onboarding);
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user", amo_id: "uat-amo", department_id: "uat-rel", staff_code: "REL-QM", email: "quality@example.invalid",
      first_name: "Quality", last_name: "Manager", full_name: "Quality Manager", role: "QUALITY_MANAGER", position_title: "Quality Manager",
      phone: null, regulatory_authority: "KCAA", licence_number: null, licence_state_or_country: null, licence_expires_on: null,
      is_active: true, is_superuser: false, is_amo_admin: false, must_change_password: false, last_login_at: null, last_login_ip: null,
      created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    }));
  }, { storedToken: token });
}

async function openReview(page: Page, api: ReturnType<typeof createMockApi>): Promise<void> {
  await authenticate(page);
  await page.route("**/*", api.handle);
  await page.goto("/maintenance/safarilink/reliability/formal-review", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Formal review workspace" })).toBeVisible({ timeout: 30_000 });
}

async function createAndPublish(page: Page, period: "HALF_YEAR" | "ANNUAL", number: string, start: string, end: string): Promise<string> {
  await page.getByLabel("Period", { exact: true }).selectOption(period);
  await page.getByLabel("Start", { exact: true }).fill(start);
  await page.getByLabel("End", { exact: true }).fill(end);
  await page.getByLabel("Report number").fill(number);
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page.getByText("Draft formal report created.")).toBeVisible();

  await page.getByRole("button", { name: "Freeze cutoff & effectivity" }).click();
  await expect(page.getByText("Data cutoff and fleet effectivity frozen.")).toBeVisible();

  await page.getByRole("combobox").filter({ has: page.locator("option[value='READY']") }).selectOption("READY");
  await page.getByPlaceholder(/Add traceable engineering interpretation/).fill("Observed rate is withheld because the frozen population contains no valid FH denominator; no zero value is inferred.");
  await page.getByRole("button", { name: "Save controlled section" }).click();

  await page.getByRole("button", { name: "Review requirement" }).click();
  const requirementEditor = page.locator(".rfw-requirement-editor");
  await requirementEditor.getByRole("combobox").selectOption("SATISFIED");
  await requirementEditor.getByPlaceholder("Reviewer note / applicability rationale").fill("Current operator-controlled KCAA mapping reviewed against the approved programme basis.");
  await requirementEditor.getByPlaceholder("Controlled source/calculation reference").fill("QAM-REL-MAP-2026-01");
  await requirementEditor.getByRole("button", { name: "Save assessment" }).click();

  await page.getByRole("button", { name: "Generate retained report" }).click();
  await expect(page.getByText("Formal HTML/PDF regenerated from the frozen snapshot.")).toBeVisible();
  await page.getByRole("button", { name: "Run completeness" }).click();
  await expect(page.getByText("Completeness gate passed.")).toBeVisible();

  for (const label of ["Submit technical review", "Submit quality review", "Submit for approval", "Approve revision", "Publish controlled revision"]) {
    await page.getByRole("button", { name: label }).click();
  }
  await expect(page.getByText("PUBLISHED", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Open retained view" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open PDF" })).toBeVisible();
  return number;
}

test.describe("Formal Reliability Programme publication", () => {
  test("publishes deterministic half-year and annual controlled reports", async ({ page }) => {
    const api = createMockApi();
    await openReview(page, api);
    await createAndPublish(page, "HALF_YEAR", "REL-2026-H1-UAT", "2026-01-01", "2026-06-30");
    await createAndPublish(page, "ANNUAL", "REL-2026-ANNUAL-UAT", "2026-01-01", "2026-12-31");

    const published = Array.from(api.reports.values()).filter((row) => row.status === "PUBLISHED");
    expect(published).toHaveLength(2);
    for (const row of published) {
      expect(row.data_cutoff_at).toBeTruthy();
      expect(row.html_sha256).toHaveLength(64);
      expect(row.pdf_sha256).toHaveLength(64);
      expect(row.requirements[0].status).toBe("SATISFIED");
      expect(row.sections[0].status).toBe("READY");
    }
  });

  test("surfaces mandatory GAP, RBAC, zero-denominator, immutability and tenant controls", async ({ page }) => {
    const api = createMockApi();
    const base = reportFixture("negative-1", "REL-NEGATIVE-UAT", "HALF_YEAR", "2026-01-01", "2026-06-30");
    api.reports.set(base.id, base);
    await openReview(page, api);

    await page.getByRole("button", { name: "Freeze cutoff & effectivity" }).click();
    await page.getByRole("button", { name: "Generate retained report" }).click();
    await page.getByRole("button", { name: "Run completeness" }).click();
    await expect(page.getByText("Applicable mandatory KCAA requirement remains GAP.")).toBeVisible();
    await expect(page.getByText(/WITHHELD_NO_FLIGHT_HOURS/)).toBeVisible();

    api.denyTransitions(true);
    await page.getByRole("button", { name: "Submit technical review" }).click();
    await expect(page.getByRole("alert")).toContainText("cannot perform this formal Reliability transition");
    api.denyTransitions(false);

    const frozenHash = (api.reports.get(base.id)?.source_population as { source_identity_sha256?: string }).source_identity_sha256;
    api.recordPostCutoffMutation();
    await page.getByRole("button", { name: "Run completeness" }).click();
    expect((api.reports.get(base.id)?.source_population as { source_identity_sha256?: string }).source_identity_sha256).toBe(frozenHash);

    const published = api.reports.get(base.id)!;
    published.status = "SUPERSEDED";
    published.html_sha256 = "b".repeat(64);
    published.pdf_sha256 = "c".repeat(64);
    published.published_at = "2026-08-07T11:00:00Z";
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByText("SUPERSEDED", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Review requirement" })).toBeDisabled();

    const retained = await page.goto("http://127.0.0.1:8080/reliability/formal-reporting/reports/negative-1/view", { waitUntil: "domcontentloaded" });
    expect(retained?.status()).toBe(200);
    await expect(page.locator("body")).toContainText("SUPERSEDED — retained historical revision");

    api.setCrossTenantFailure(true);
    const crossTenant = await page.goto("http://127.0.0.1:8080/reliability/formal-reporting/reports/other-tenant", { waitUntil: "domcontentloaded" });
    expect(crossTenant?.status()).toBe(404);
  });
});
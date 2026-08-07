import { expect, test, type Route } from "@playwright/test";

const auditRows = Array.from({ length: 5 }, (_, index) => ({
  id: `audit-${index + 1}`,
  amo_id: "amo-1",
  domain: "AMO",
  kind: "INTERNAL",
  status: "CAP_OPEN",
  audit_ref: `QAR/AMODEMO/26/00${index + 1}`,
  reference_family: "QAR",
  unit_code: "AMODEMO",
  ref_year: 26,
  ref_sequence: index + 1,
  title: `Audit ${index + 1}`,
  scope: "Scope",
  criteria: "Criteria",
  auditee: null,
  auditee_email: null,
  auditee_user_id: null,
  lead_auditor_user_id: "user-1",
  observer_auditor_user_id: null,
  assistant_auditor_user_id: null,
  planned_start: "2026-03-19",
  planned_end: "2026-03-20",
  actual_start: null,
  actual_end: null,
  report_file_ref: null,
  checklist_file_ref: null,
  retention_until: null,
  upcoming_notice_sent_at: null,
  day_of_notice_sent_at: null,
  created_by_user_id: "user-1",
  created_at: "2026-03-19T00:00:00Z",
}));

const registerRows = auditRows.map((audit, index) => ({
  audit,
  finding: {
    id: `finding-${index + 1}`,
    amo_id: "amo-1",
    audit_id: audit.id,
    finding_ref: `F-${index + 1}`,
    finding_type: "NON_CONFORMITY",
    severity: "MAJOR",
    level: "LEVEL_2",
    requirement_ref: null,
    description: `Finding ${index + 1}`,
    objective_evidence: "Evidence",
    safety_sensitive: false,
    target_close_date: "2026-03-25",
    closed_at: null,
    verified_at: null,
    verified_by_user_id: null,
    acknowledged_at: null,
    acknowledged_by_user_id: null,
    acknowledged_by_name: null,
    acknowledged_by_email: null,
    created_at: "2026-03-19T00:00:00Z",
  },
  linked_cars: [
    {
      id: `car-${index + 1}`,
      program: "QUALITY",
      car_number: `CAR-${index + 1}`,
      title: `CAR ${index + 1}`,
      summary: "Summary",
      priority: "HIGH",
      status: "IN_PROGRESS",
      due_date: "2026-03-26",
      target_closure_date: "2026-03-27",
      closed_at: null,
      escalated_at: null,
      finding_id: `finding-${index + 1}`,
      requested_by_user_id: "user-1",
      assigned_to_user_id: "user-1",
      invite_token: `tok-${index + 1}`,
      reminder_interval_days: 7,
      next_reminder_at: null,
      containment_action: null,
      root_cause: null,
      corrective_action: null,
      preventive_action: null,
      evidence_ref: null,
      submitted_by_name: null,
      submitted_by_email: null,
      submitted_at: null,
      root_cause_text: null,
      root_cause_status: "PENDING",
      root_cause_review_note: null,
      capa_text: null,
      capa_status: "PENDING",
      capa_review_note: null,
      evidence_required: true,
      evidence_received_at: null,
      evidence_verified_at: null,
      created_at: "2026-03-19T00:00:00Z",
      updated_at: "2026-03-19T00:00:00Z",
    },
  ],
}));

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function seedSession(storedToken: string) {
  localStorage.setItem("amo_portal_token", storedToken);
  localStorage.setItem("amo_code", "demo");
  localStorage.setItem("amo_slug", "demo");
  localStorage.setItem("amo_department", "quality");
  localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
  localStorage.setItem("amo_current_user", JSON.stringify({
    id: "user-1",
    amo_id: "amo-1",
    department_id: null,
    staff_code: "QUAL01",
    email: "quality@example.com",
    first_name: "Quality",
    last_name: "Manager",
    full_name: "Quality Manager",
    role: "QUALITY_MANAGER",
    position_title: "Quality Manager",
    phone: null,
    regulatory_authority: null,
    licence_number: null,
    licence_state_or_country: null,
    licence_expires_on: null,
    is_active: true,
    is_superuser: false,
    is_amo_admin: true,
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2026-03-19T00:00:00Z",
    updated_at: "2026-03-19T00:00:00Z",
  }));
}

function isTenantApi(url: URL): boolean {
  return url.pathname.startsWith("/api/maintenance/");
}

async function fulfilShellRequest(route: Route, url: URL): Promise<boolean> {
  if (url.pathname === "/auth/portal-preferences/" || url.pathname === "/auth/portal-preferences") {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "user-1",
        amo_id: "amo-1",
        text_scale: "standard",
        density: "comfortable",
        motion: "system",
        color_scheme: "light",
        accent: "tenant",
        version: 1,
        updated_at: "2026-03-19T00:00:00Z",
      }),
    });
    return true;
  }
  if (url.pathname.includes("/accounts/admin/admin-profile/")) {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
    return true;
  }
  if (url.pathname === "/accounts/onboarding/status" || url.pathname === "/accounts/onboarding/status/") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ is_complete: true, missing: [] }) });
    return true;
  }
  if (url.pathname === "/billing/entitlements" || url.pathname === "/billing/entitlements/") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ modules: ["quality"] }) });
    return true;
  }
  if (url.pathname === "/time" || url.pathname === "/time/") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ utc: "2026-03-19T00:00:00Z" }) });
    return true;
  }
  if (url.pathname === "/healthz") {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    return true;
  }
  if (url.pathname.includes("/amo-assets/logo")) {
    await route.fulfill({ status: 404, body: "" });
    return true;
  }
  return false;
}

test("audit register uses the paged closeout contract without per-audit fan-out", async ({ page }) => {
  let pagedRegisterRequests = 0;
  let legacyRegisterRequests = 0;
  let legacyFindingRequests = 0;

  await page.addInitScript(seedSession, futureToken());
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (await fulfilShellRequest(route, url)) return;
    if (isTenantApi(url) && url.pathname.endsWith("/quality/audits/register/paged")) {
      pagedRegisterRequests += 1;
      expect(url.searchParams.get("limit")).toBe("25");
      expect(url.searchParams.get("offset")).toBe("0");
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rows: registerRows,
          total: registerRows.length,
          limit: 25,
          offset: 0,
          has_more: false,
          car_linked_findings: registerRows.length,
          open_car_count: registerRows.length,
        }),
      });
    }
    if (isTenantApi(url) && url.pathname.endsWith("/quality/audits/register")) {
      legacyRegisterRequests += 1;
      return route.fulfill({ status: 500, body: "legacy register should not be called" });
    }
    if (isTenantApi(url) && /\/quality\/audits\/[^/]+\/findings$/.test(url.pathname)) {
      legacyFindingRequests += 1;
      return route.fulfill({ status: 500, body: "per-audit finding fan-out should not be called" });
    }
    return route.continue();
  });

  await page.goto("/maintenance/demo/quality/audits/register", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Closeout register" })).toBeVisible({ timeout: 30_000 });
  expect(pagedRegisterRequests).toBe(1);
  expect(legacyRegisterRequests).toBe(0);
  expect(legacyFindingRequests).toBe(0);
});

test("evidence vault search uses one bounded canonical register request", async ({ page }) => {
  let boundedEvidenceRequests = 0;
  let legacyBulkFindingRequests = 0;
  let legacyBulkAttachmentRequests = 0;
  let legacyPerCarAttachmentRequests = 0;

  await page.addInitScript(seedSession, futureToken());
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (await fulfilShellRequest(route, url)) return;
    if (isTenantApi(url) && url.pathname.endsWith("/quality/evidence-vault/search")) {
      boundedEvidenceRequests += 1;
      expect(url.searchParams.get("limit")).toBe("30");
      expect(url.searchParams.get("offset")).toBe("0");
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          module: "evidence-vault",
          view: "search",
          table: "qms_evidence_records",
          items: [{
            id: "evidence-1",
            reference: "EVD-001",
            title: "Audit closeout evidence",
            status: "ACTIVE",
            created_at: "2026-03-19T00:00:00Z",
          }],
          columns: ["reference", "title", "status", "created_at"],
          limit: 30,
          offset: 0,
          next_offset: null,
          has_more: false,
          source_errors: [],
          trace_id: "evidence-test",
          elapsed_ms: 5,
        }),
      });
    }
    if (isTenantApi(url) && url.pathname.endsWith("/quality/audits/findings")) {
      legacyBulkFindingRequests += 1;
      return route.fulfill({ status: 500, body: "legacy bulk findings should not be called" });
    }
    if (isTenantApi(url) && url.pathname.endsWith("/quality/cars/attachments/bulk")) {
      legacyBulkAttachmentRequests += 1;
      return route.fulfill({ status: 500, body: "legacy bulk attachments should not be called" });
    }
    if (isTenantApi(url) && /\/quality\/cars\/[^/]+\/attachments$/.test(url.pathname)) {
      legacyPerCarAttachmentRequests += 1;
      return route.fulfill({ status: 500, body: "per-CAR attachment fan-out should not be called" });
    }
    return route.continue();
  });

  await page.goto("/maintenance/demo/quality/evidence-vault/search", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Evidence Vault" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Audit closeout evidence", { exact: true })).toBeVisible();
  expect(boundedEvidenceRequests).toBe(1);
  expect(legacyBulkFindingRequests).toBe(0);
  expect(legacyBulkAttachmentRequests).toBe(0);
  expect(legacyPerCarAttachmentRequests).toBe(0);
});

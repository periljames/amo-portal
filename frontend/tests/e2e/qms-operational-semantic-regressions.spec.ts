import { mockQualityShell } from "./helpers/mockQualityShell";
import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function localDateKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

async function prepare(page: Page, qualityHandler: (route: Route, url: URL) => Promise<void>): Promise<void> {
  await mockQualityShell(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const token = futureToken();
  await page.addInitScript(({ storedToken }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a", amo_id: "amo-a", department_id: "department-quality", staff_code: "QMS-001",
      email: "quality@tenant-a.test", first_name: "Quality", last_name: "Manager", full_name: "Quality Manager",
      role: "QUALITY_MANAGER", position_title: "Quality Manager", is_active: true, is_superuser: false,
      is_amo_admin: false, must_change_password: false,
    }));
  }, { storedToken: token });

  await page.route("**/auth/portal-preferences/", (route) => json(route, {
    user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system",
    color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-10T03:00:00Z",
  }));
  await page.route("**/accounts/admin/admin-profile/**", (route) => json(route, { eligible: false, active: false }));
  await page.route("**/api/maintenance/tenant-a/quality/**", async (route) => qualityHandler(route, new URL(route.request().url())));
  await page.route("http://127.0.0.1:8080/api/maintenance/tenant-a/quality/**", async (route) => qualityHandler(route, new URL(route.request().url())));
}

function emptyRegister(route: Route) {
  return json(route, { items: [], columns: [], limit: 30, offset: 0, next_offset: null, has_more: false });
}

test("People authorization cases keep preparation and final decision in the governed workflow", async ({ page }) => {
  const decisionBodies: Array<Record<string, unknown>> = [];
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/people/authorization-control/overview")) return json(route, {
      permissions: {
        can_view: true, can_prepare: true, can_approve: true, can_review: true,
        can_approve_exemption: true, can_manage_policy: true, can_oversight: true, self_service_only: false,
      },
      metrics: {
        active_authorizations: 0, suspended_authorizations: 0, expiring_within_60_days: 0,
        open_authorization_cases: 1, reviews_due: 0, active_controlled_exemptions: 0,
      },
      attention: [],
    });
    if (path.endsWith("/quality/people/authorization-control/people")) return json(route, { items: [], total: 0 });
    if (path.endsWith("/quality/people/authorization-control/cases") && route.request().method() === "GET") return json(route, {
      items: [{
        id: "auth-case-1", person: "Amina Wanjiku", home_role: "QUALITY_INSPECTOR", department: "Quality",
        authorization: "Auditor", case_type: "CHANGE_AUTHORIZATION", status: "READY_FOR_DECISION",
        nomination_date: localDateKey(), nominator: "Quality Officer", recommendation: "Promote based on verified competence.",
        updated_at: new Date().toISOString(), next_action: "Decision required",
      }],
      total: 1,
    });
    if (path.endsWith("/quality/people/authorization-control/cases/auth-case-1") && route.request().method() === "GET") return json(route, {
      case: {
        id: "auth-case-1", person: { name: "Amina Wanjiku", home_role: "QUALITY_INSPECTOR", department: "Quality", active: true },
        home_role: "QUALITY_INSPECTOR", department: "Quality", authorization: "Auditor", case_type: "CHANGE_AUTHORIZATION",
        status: "READY_FOR_DECISION", nomination_date: localDateKey(), nominator: "Quality Officer",
        recommendation: "Promote based on verified competence.", next_action: "Decision required",
        current_authorization: { authorization: "Observer / Trainee Auditor", status: "ACTIVE", scope: "Global" },
        requested_authorization: { authorization: "Auditor", scope: "Global" },
      },
      readiness: {
        authorization: "Auditor", as_of: localDateKey(), status: "Ready for decision", hard_blockers: [],
        training: { status: "Current", current: true, developmental_exception: false, courses: [{ course: "QMS-INIT", status: "Current" }], required: ["QMS-INIT"], missing: [] },
        development: { observed_audits: 3, target: 3, progress_label: "3 / 3", target_is_hard_gate: false, supervision_required: false, audit_participation: [] },
        annual_review: null, controlled_exemption: null, affected_assignments: [],
      },
      evidence: [{
        id: "evidence-1", type: "COMPETENCE_ASSESSMENT", label: "Competence assessment",
        source_module: "QUALITY", source_reference: {}, has_file: false, created_at: new Date().toISOString(),
      }],
      authorization_reviews: [],
      controlled_exemption: null,
      history: [{ action: "SUBMITTED_FOR_DECISION", from: "UNDER_REVIEW", to: "READY_FOR_DECISION", reason: "Prepared.", actor: "Quality Officer", occurred_at: new Date().toISOString() }],
      permissions: {
        can_view: true, can_prepare: true, can_approve: true, can_review: true,
        can_approve_exemption: true, can_manage_policy: true, can_oversight: true, self_service_only: false,
      },
    });
    if (path.endsWith("/quality/people/authorization-control/cases/auth-case-1/decision") && route.request().method() === "POST") {
      decisionBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      return json(route, { status: "APPROVED", authorization: { key: "auth-1", authorization: "Auditor", status: "ACTIVE", scope: "Global" } });
    }
    if (path.endsWith("/quality/people/authorization-control/reviews")) return json(route, { items: [] });
    if (path.endsWith("/quality/people/authorization-control/authorizations")) return json(route, { items: [] });
    if (path.endsWith("/quality/people/rules")) return json(route, { items: [] });
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Authorization Cases", exact: true }).click();
  await page.getByRole("button", { name: /Amina Wanjiku/ }).click();
  await expect(page.getByRole("heading", { name: "Final authorization decision", exact: true })).toBeVisible();
  await expect(page.getByText("3 / 3", { exact: true })).toBeVisible();
  await page.locator(".qms-authz-workflow--decision textarea").first().fill("Competence evidence reviewed and authorization approved.");
  await page.getByLabel(/Competence assessment · Competence Assessment/).check();
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Record final decision", exact: true }).click();

  await expect.poll(() => decisionBodies.length).toBe(1);
  expect(decisionBodies[0]).toMatchObject({
    decision: "APPROVE",
    reason: "Competence evidence reviewed and authorization approved.",
    source_references: [{
      type: "AUTHORIZATION_EVIDENCE",
      evidence_id: "evidence-1",
      evidence_type: "COMPETENCE_ASSESSMENT",
      label: "Competence assessment",
    }],
    confirmed: true,
  });
  await expect(page.getByRole("button", { name: /Check audit assignment/i })).toHaveCount(0);
});

test("Intelligence keeps authoritative source-warning provenance available to the operator", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/intelligence/overview")) return json(route, {
      as_of: "2026-08-10T03:00:00Z", programme: { states: {}, completion: { numerator: 0, denominator: 0, value: null }, deferral_rate: { numerator: 0, denominator: 0, value: null }, calculation: "deterministic" },
      assurance: { open_cases: 0, overdue_cases: 0, ineffective_or_inconclusive_reviews: 0 }, people: { active_privileges: 0, expiring_within_60_days: 0 },
      controls: { overdue_control_tests: 0, failed_or_partial_test_records: 0, stale_or_expired_evidence_links: 0, proposed_human_reviews: 0 }, targeted_surveillance: [],
      method: { type: "DETERMINISTIC_RULES", statement: "Source-backed rules only." },
    });
    if (path.endsWith("/quality/audit-programmes/risk-context")) return json(route, {
      as_of: "2026-08-10T03:00:00Z", items: [], global_factors: [], authoritative_metrics: {}, reliability: {},
      source_warnings: [{ source: "reliability_feed", message: "Reliability source timed out; priorities are incomplete.", type: "UPSTREAM_TIMEOUT" }],
      method: { type: "DETERMINISTIC_SOURCE_ATTRIBUTION", statement: "Incomplete authoritative inputs remain explicit." },
    });
    if (path.endsWith("/quality/intelligence/signal-rules")) return json(route, { items: [] });
    if (path.endsWith("/quality/intelligence/signals")) return json(route, { items: [] });
    if (path.endsWith("/quality/intelligence/approval-digital-twin")) return json(route, { as_of: "2026-08-10T03:00:00Z", assurance_state: "UNRESOLVED", is_compliance_declaration: false, state_counts: {}, blockers: [], explanation: "Not a compliance declaration." });
    if (path.endsWith("/quality/intelligence/approval-graph")) return json(route, { nodes: [], links: [] });
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=intelligence", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("1 authoritative source warning(s)", { exact: true })).toBeVisible();
  await page.getByText("Review affected authoritative sources", { exact: true }).click();
  await expect(page.getByText("Reliability Feed", { exact: true })).toBeVisible();
  await expect(page.getByText("Reliability source timed out; priorities are incomplete.", { exact: true })).toBeVisible();
  await expect(page.getByText("Upstream Timeout", { exact: true })).toBeVisible();
});

test("My Quality Work treats a date-only deadline due today as due today, exposes source failures, and refreshes from the network", async ({ page }) => {
  let revision = 0;
  const today = localDateKey();
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/quality/inbox/assigned-to-me")) return json(route, {
      module: "inbox", view: "assigned-to-me", table: "quality_inbox",
      items: [{ id: "task-1", message: revision === 0 ? "Initial source-backed task" : "Refreshed source-backed task", severity: "INFO", due_date: today, route: "/maintenance/tenant-a/quality?workspace=assurance" }],
      columns: ["message", "severity", "due_date"], limit: 30, offset: 0, next_offset: null, has_more: false,
      source_errors: [{ label: "Training register", message: "Training source was unavailable for one enrichment read.", type: "UPSTREAM_TIMEOUT" }],
      trace_id: "trace-inbox-1", elapsed_ms: 12,
    });
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Initial source-backed task", { exact: true })).toBeVisible();
  const marker = page.locator('.qms-register-workspace .ag-cell[col-id="due"]').first();
  await expect(marker).toHaveClass(/is-warning/);
  await expect(marker).not.toHaveClass(/is-danger/);
  await page.getByText("Review 1 affected authoritative source", { exact: true }).click();
  const sourceFailure = page.locator(".qms-register-warning details li").filter({ hasText: "Training register" });
  await expect(sourceFailure).toContainText("Training source was unavailable for one enrichment read.");

  revision = 1;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Refreshed source-backed task", { exact: true })).toBeVisible();
});

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
  await page.setViewportSize({ width: 1920, height: 1080 });
  const token = futureToken();
  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
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

function auditorAssessment(options: { scopeMatches: boolean }) {
  return {
    rule_id: "rule-auditor",
    privilege_code: "AUDITOR_INTERNAL",
    privilege_type: "AUDITOR",
    hard_gates: {
      workforce_active: true,
      active_privilege: options.scopeMatches,
      scope_authorized: options.scopeMatches,
      training_current_verified: true,
      capacity: true,
      independence: true,
    },
    active_privilege: options.scopeMatches ? { id: "priv-hangar-b", scope_key: "HANGAR_B", effective_from: "2026-01-01", expires_on: "2026-12-31" } : null,
    training: { required: ["QMS-AUD"], satisfied: ["QMS-AUD"], missing: [], records: [], passed: true },
    capacity: { active_assignments: 0, max_concurrent_assignments: 3, assignments: [], passed: true },
    independence: { required: true, passed: true, pending: false, declaration: "INDEPENDENT" },
    eligible: options.scopeMatches,
  };
}

test("People uses the governed Planner preflight and never borrows assignment scope from another authorization", async ({ page }) => {
  const preflightBodies: Array<Record<string, unknown>> = [];
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/people/summary")) return json(route, { active_privileges: 1, expiring_within_60_days: 0, suspended_privileges: 1, independence_exceptions: 0 });
    if (path.endsWith("/quality/people/rules")) return json(route, { items: [{
      id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR",
      required_training_course_codes: ["QMS-AUD"], independence_required: true, max_concurrent_assignments: 3,
      scope_schema: {}, is_active: true, updated_at: "2026-08-09T10:00:00Z",
    }] });
    if (path.endsWith("/quality/people/privileges")) return json(route, { items: [
      { id: "priv-hangar-a", rule_id: "rule-auditor", user_id: "auditor-1", privilege_code: "AUDITOR_INTERNAL", scope_key: "HANGAR_A", scope: {}, limitations: [], status: "SUSPENDED", effective_from: "2026-01-01", expires_on: "2026-12-31", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-08-09T10:00:00Z", decisions: [] },
      { id: "priv-hangar-b", rule_id: "rule-auditor", user_id: "auditor-1", privilege_code: "AUDITOR_INTERNAL", scope_key: "HANGAR_B", scope: {}, limitations: [], status: "ACTIVE", effective_from: "2026-01-01", expires_on: "2026-12-31", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-08-09T10:00:00Z", decisions: [] },
    ] });
    if (path.endsWith("/quality/people/eligibility")) return json(route, {
      eligible: true, as_of: localDateKey(),
      person: { user_id: "auditor-1", full_name: "Amina Wanjiku", email: "amina@tenant-a.test", role: "QUALITY_INSPECTOR" },
      rule: { id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR" },
      hard_gates: { workforce_active: true, training_current_verified: true, independence: true, capacity: true, active_privilege: true },
      training: { required: ["QMS-AUD"], satisfied: ["QMS-AUD"], missing: [], records: [], passed: true },
      independence: { required: true, passed: true, pending: true }, workload: { passed: true },
      active_privilege: { id: "priv-hangar-b", status: "ACTIVE", effective_from: "2026-01-01", expires_on: "2026-12-31" },
    });
    if (path.endsWith("/quality/integrations/calendar/auditor-eligibility") && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      preflightBodies.push(body);
      const scopeMatches = body.assignment_scope_key === "HANGAR_B";
      const assessment = auditorAssessment({ scopeMatches });
      return json(route, {
        eligible: scopeMatches,
        governance_configured: true,
        mode: "GOVERNED",
        assignment_role: body.assignment_role,
        user_id: "auditor-1",
        reason: scopeMatches ? undefined : "No configured Quality privilege rule passes every hard eligibility gate for this assignment.",
        rule_id: scopeMatches ? "rule-auditor" : undefined,
        privilege_code: scopeMatches ? "AUDITOR_INTERNAL" : undefined,
        independence_pending: false,
        assessment: scopeMatches ? assessment : undefined,
        assessments: [assessment],
      });
    }
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  const readiness = page.locator(".qms-people__eligibility-summary h3");
  await expect(readiness).toHaveText("Blocked");
  await expect(page.locator(".qms-people__gate-grid")).toContainText("Selected Privilege Active");

  await page.locator(".qms-people__register tbody tr").nth(1).click();
  await expect(readiness).toHaveText("Ready");
  await page.getByRole("button", { name: "Check audit assignment" }).click();
  await expect(page.locator(".qms-people__context-card")).toContainText("Hangar B");

  const preflight = page.getByRole("button", { name: "Run governed assignment preflight" });
  await expect(preflight).toBeDisabled();
  await page.getByLabel("Assignment scope code").fill("HANGAR_A");
  await page.getByLabel("Assignment context").selectOption("AUDIT_SCHEDULE");
  await page.getByLabel("Context ID").fill("audit-schedule-44");
  await expect(preflight).toBeEnabled();
  await preflight.click();
  await expect(page.locator(".qms-people__eligibility > strong")).toHaveText("Blocked for this assignment");
  await expect(page.locator(".qms-people__eligibility")).toContainText("Scope Authorized");

  await page.getByLabel("Assignment scope code").fill("HANGAR_B");
  await preflight.click();
  await expect(page.locator(".qms-people__eligibility > strong")).toHaveText("Eligible for this assignment");
  await expect(preflightBodies).toHaveLength(2);
  expect(preflightBodies[0]).toMatchObject({ assignment_role: "OBSERVER_AUDITOR", assignment_scope_key: "HANGAR_A", context_type: "AUDIT_SCHEDULE", context_id: "audit-schedule-44", enforce_independence: true });
  expect(preflightBodies[1]).toMatchObject({ assignment_scope_key: "HANGAR_B" });
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
  const marker = page.locator(".qms-register-task__marker").first();
  await expect(marker).toHaveClass(/is-warning/);
  await expect(marker).not.toHaveClass(/is-danger/);
  await page.getByText("Review 1 affected authoritative source", { exact: true }).click();
  const sourceFailure = page.locator(".qms-register-warning details li").filter({ hasText: "Training register" });
  await expect(sourceFailure).toContainText("Training source was unavailable for one enrichment read.");

  revision = 1;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Refreshed source-backed task", { exact: true })).toBeVisible();
});

test("Assurance refresh re-reads the selected case detail instead of retaining a stale object", async ({ page }) => {
  let revision = 0;
  const listCase = {
    id: "case-refresh-1", case_ref: "ASC-26-099", case_type: "INVESTIGATION", title: "Refresh-sensitive assurance case", description: "Portfolio summary",
    severity: "HIGH", status: "INVESTIGATING", source_references: [], regulatory_basis: [], owner_user_id: "quality-user-a", due_date: "2026-08-31",
    opened_at: "2026-08-09T10:00:00Z", closed_at: null, closed_by_user_id: null, closure_rationale: null,
    created_at: "2026-08-09T10:00:00Z", updated_at: "2026-08-09T10:00:00Z",
  };
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/assurance-cases") && route.request().method() === "GET") return json(route, { items: [listCase], total: 1, limit: 150, offset: 0, has_more: false });
    if (path.endsWith("/quality/assurance-cases/case-refresh-1") && route.request().method() === "GET") return json(route, {
      ...listCase,
      description: revision === 0 ? "Initial authoritative detail" : "Updated authoritative detail after external change",
      updated_at: revision === 0 ? "2026-08-09T10:00:00Z" : "2026-08-10T03:15:00Z",
      investigation_entries: revision === 0 ? [] : [{ id: "entry-new", method: "FIVE_WHYS", entry_type: "FACT", sequence_no: 1, statement: "Externally recorded fact", evidence_references: [], created_at: "2026-08-10T03:15:00Z" }],
      effectiveness_plans: [], events: [],
    });
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /ASC-26-099/ }).click();
  await expect(page.getByText("Initial authoritative detail", { exact: true })).toBeVisible();
  await expect(page.getByText("0 investigation statements", { exact: false })).toBeVisible();
  revision = 1;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Updated authoritative detail after external change", { exact: true })).toBeVisible();
  await expect(page.getByText("1 investigation statements", { exact: false })).toBeVisible();
});

test("Assurance exposes only backend-allowed transitions and blocks evidence-free causal conclusions", async ({ page }) => {
  const assuranceCase = {
    id: "case-governed-1", case_ref: "ASC-26-100", case_type: "INVESTIGATION", title: "Governed lifecycle case", description: "Lifecycle contract",
    severity: "MEDIUM", status: "INVESTIGATING", source_references: [], regulatory_basis: [], owner_user_id: "quality-user-a", due_date: "2026-08-31",
    opened_at: "2026-08-09T10:00:00Z", closed_at: null, closed_by_user_id: null, closure_rationale: null,
    created_at: "2026-08-09T10:00:00Z", updated_at: "2026-08-09T10:00:00Z",
  };
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/quality/assurance-cases") && route.request().method() === "GET") return json(route, { items: [assuranceCase], total: 1, limit: 150, offset: 0, has_more: false });
    if (url.pathname.endsWith("/quality/assurance-cases/case-governed-1") && route.request().method() === "GET") return json(route, { ...assuranceCase, investigation_entries: [], effectiveness_plans: [], events: [] });
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /ASC-26-100/ }).click();
  const nextState = page.getByLabel("Next state");
  await expect(nextState.locator("option")).toHaveText(["Action Pending", "Effectiveness Review", "Cancelled"]);
  await expect(nextState.locator('option[value="OPEN"]')).toHaveCount(0);
  await expect(nextState.locator('option[value="CLOSED"]')).toHaveCount(0);

  await page.locator("#investigation-type").selectOption("CAUSAL_CONCLUSION");
  await page.locator("#investigation-statement").fill("The root cause is proposed only after verified facts.");
  const recordStatement = page.getByRole("button", { name: "Record immutable statement" });
  await expect(recordStatement).toBeDisabled();
  await expect(page.getByText("Record at least one FACT before promoting a statement to a causal conclusion.", { exact: true })).toBeVisible();
  await page.getByLabel(/Authoritative evidence reference/).first().fill("evidence-record-1");
  await expect(recordStatement).toBeDisabled();
});

test("Assurance requires an evidence-backed effectiveness conclusion before closure becomes available", async ({ page }) => {
  let concluded = false;
  let conclusionBody: Record<string, unknown> | null = null;
  const today = localDateKey();
  const listCase = {
    id: "case-effectiveness-1", case_ref: "ASC-26-101", case_type: "EFFECTIVENESS", title: "Effectiveness closure case", description: "Effectiveness contract",
    severity: "HIGH", status: "EFFECTIVENESS_REVIEW", source_references: [], regulatory_basis: [], owner_user_id: "quality-user-a", due_date: "2026-08-31",
    opened_at: "2026-08-09T10:00:00Z", closed_at: null, closed_by_user_id: null, closure_rationale: null,
    created_at: "2026-08-09T10:00:00Z", updated_at: "2026-08-09T10:00:00Z",
  };
  const plan = {
    id: "plan-1", source_type: null, source_id: null, source_route: null, expected_outcome: "Repeat finding rate remains at zero",
    effectiveness_measure: "No repeat finding across the observation window", verification_method: "Review audit and CAR records",
    observation_window: null, source_indicators: [], responsible_reviewer_user_id: "quality-user-a", planned_review_date: today,
    status: concluded ? "CONCLUDED" : "PLANNED", conclusion: concluded ? "EFFECTIVE" : null,
    conclusion_rationale: concluded ? "Verified evidence demonstrates the corrective action remains effective." : null,
    conclusion_evidence: concluded ? [{ source_ref: "evidence-review-1", source_type: "AUTHORITATIVE_REFERENCE" }] : [],
    concluded_by_user_id: concluded ? "quality-user-a" : null, concluded_at: concluded ? "2026-08-10T03:30:00Z" : null,
    created_at: "2026-08-09T10:00:00Z", updated_at: "2026-08-10T03:30:00Z",
  };
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/assurance-cases") && route.request().method() === "GET") return json(route, { items: [listCase], total: 1, limit: 150, offset: 0, has_more: false });
    if (path.endsWith("/quality/assurance-cases/case-effectiveness-1") && route.request().method() === "GET") return json(route, { ...listCase, investigation_entries: [], effectiveness_plans: [{ ...plan, status: concluded ? "CONCLUDED" : "PLANNED", conclusion: concluded ? "EFFECTIVE" : null, conclusion_rationale: concluded ? "Verified evidence demonstrates the corrective action remains effective." : null }], events: [] });
    if (path.endsWith("/quality/assurance-cases/case-effectiveness-1/effectiveness-plans/plan-1/conclusion") && route.request().method() === "POST") {
      conclusionBody = route.request().postDataJSON() as Record<string, unknown>;
      concluded = true;
      return json(route, { plan: { ...plan, status: "CONCLUDED", conclusion: "EFFECTIVE" }, case: { ...listCase, status: "EFFECTIVENESS_REVIEW" } });
    }
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /ASC-26-101/ }).click();
  const nextState = page.getByLabel("Next state");
  await expect(nextState.locator('option[value="CLOSED"]')).toHaveCount(0);
  await expect(page.getByText(/Closure gate: Conclude every effectiveness plan/)).toBeVisible();

  await page.getByLabel("Evidence-backed rationale").fill("Verified evidence demonstrates the corrective action remains effective.");
  await page.getByLabel("Authoritative evidence reference").last().fill("evidence-review-1");
  await page.getByRole("button", { name: "Record immutable effectiveness conclusion" }).click();
  await expect.poll(() => conclusionBody).not.toBeNull();
  expect(conclusionBody).toMatchObject({ conclusion: "EFFECTIVE", rationale: "Verified evidence demonstrates the corrective action remains effective." });
  expect((conclusionBody?.evidence_references as Array<Record<string, unknown>>)[0]).toMatchObject({ source_ref: "evidence-review-1", source_type: "AUTHORITATIVE_REFERENCE" });
  await expect(nextState.locator('option[value="CLOSED"]')).toHaveCount(1);
});

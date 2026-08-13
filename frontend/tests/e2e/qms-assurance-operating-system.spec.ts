import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function expectFontAtLeast(locator: Locator, pixels: number): Promise<void> {
  await expect(locator).toBeVisible();
  const actual = await locator.evaluate((element) => Number.parseFloat(window.getComputedStyle(element).fontSize));
  expect(actual).toBeGreaterThanOrEqual(pixels);
}

async function expectMinHeightAtLeast(locator: Locator, pixels: number): Promise<void> {
  await expect(locator).toBeVisible();
  const actual = await locator.evaluate((element) => element.getBoundingClientRect().height);
  expect(actual).toBeGreaterThanOrEqual(pixels);
}

const assuranceCase = {
  id: "case-1",
  case_ref: "ASC-26-001",
  case_type: "RECURRING_FINDING",
  title: "Repeat tooling-control finding",
  description: "Repeated calibration evidence weakness across two audits.",
  severity: "HIGH",
  status: "INVESTIGATING",
  source_references: [{ source_type: "QMS_AUDIT_FINDING", source_id: "finding-44" }],
  regulatory_basis: ["KCAR Part 145 tooling controls"],
  owner_user_id: "quality-user-a",
  due_date: "2026-08-31",
  opened_at: "2026-08-08T10:00:00Z",
  closed_at: null,
  closed_by_user_id: null,
  closure_rationale: null,
  created_at: "2026-08-08T10:00:00Z",
  updated_at: "2026-08-08T12:00:00Z",
  investigation_entries: [{
    id: "entry-1",
    method: "FIVE_WHYS",
    entry_type: "FACT",
    sequence_no: 1,
    category: "Evidence",
    prompt: null,
    statement: "Calibration certificates were unavailable at point of use during both sampled audits.",
    confidence: 100,
    evidence_references: [{ source_type: "QMS_AUDIT_FINDING", source_id: "finding-44" }],
    parent_entry_id: null,
    created_by_user_id: "quality-user-a",
    created_at: "2026-08-08T11:00:00Z",
  }],
  effectiveness_plans: [{
    id: "plan-1",
    source_type: "QUALITY_CAR",
    source_id: "car-1",
    source_route: "/quality/cars/car-1",
    expected_outcome: "No repeat missing-calibration evidence during the observation window.",
    effectiveness_measure: "Zero repeat findings in the next targeted tooling sample.",
    verification_method: "Targeted follow-up audit and evidence review.",
    observation_window: "90 days",
    source_indicators: [],
    responsible_reviewer_user_id: "quality-user-a",
    planned_review_date: "2026-11-30",
    status: "PLANNED",
    conclusion: null,
    conclusion_rationale: null,
    conclusion_evidence: [],
    concluded_by_user_id: null,
    concluded_at: null,
    created_at: "2026-08-08T11:30:00Z",
    updated_at: "2026-08-08T11:30:00Z",
  }],
  events: [{
    id: "event-1",
    event_type: "CREATED",
    reason: "Recurring finding escalated into an assurance case.",
    before_snapshot: null,
    after_snapshot: { status: "OPEN" },
    actor_user_id: "quality-user-a",
    created_at: "2026-08-08T10:00:00Z",
  }],
};

async function prepare(page: Page): Promise<void> {
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
      id: "quality-user-a",
      amo_id: "amo-a",
      department_id: "department-quality",
      staff_code: "QMS-001",
      email: "quality@tenant-a.test",
      first_name: "Quality",
      last_name: "Manager",
      full_name: "Quality Manager",
      role: "QUALITY_MANAGER",
      position_title: "Quality Manager",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/auth/portal-preferences/") {
      return json(route, {
        user_id: "quality-user-a",
        amo_id: "amo-a",
        text_scale: "standard",
        density: "comfortable",
        motion: "system",
        color_scheme: "light",
        accent: "tenant",
        version: 1,
        updated_at: "2026-08-09T10:00:00Z",
      });
    }
    if (path.includes("/accounts/admin/admin-profile/")) return json(route, { eligible: false, active: false });

    if (path.endsWith("/quality/people/summary")) {
      return json(route, { active_privileges: 4, expiring_within_60_days: 1, suspended_privileges: 0, independence_exceptions: 1 });
    }
    if (path.endsWith("/quality/people/rules")) {
      return json(route, { items: [{
        id: "rule-1",
        privilege_code: "AUDITOR_INTERNAL",
        title: "Internal Auditor",
        privilege_type: "AUDITOR",
        required_training_course_codes: ["QMS-AUD"],
        independence_required: true,
        max_concurrent_assignments: 2,
        scope_schema: {},
        is_active: true,
        updated_at: "2026-08-08T12:00:00Z",
      }] });
    }
    if (path.endsWith("/quality/people/privileges")) {
      return json(route, { items: [{
        id: "priv-1",
        rule_id: "rule-1",
        user_id: "auditor-user-a",
        privilege_code: "AUDITOR_INTERNAL",
        scope_key: "GLOBAL",
        scope: {},
        limitations: [],
        status: "ACTIVE",
        effective_from: "2026-01-01",
        expires_on: "2026-12-31",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-08-08T12:00:00Z",
        decisions: [],
      }] });
    }
    if (path.endsWith("/quality/people/eligibility")) {
      return json(route, {
        eligible: true,
        as_of: "2026-08-09T10:00:00Z",
        person: { user_id: "auditor-user-a", full_name: "Amina Wanjiku", email: "amina@tenant-a.test", role: "QUALITY_INSPECTOR" },
        rule: { id: "rule-1", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR" },
        hard_gates: { active_privilege: true, training_current: true, independence_clear: true, workload_available: true },
        training: { required: ["QMS-AUD"], satisfied: ["QMS-AUD"], missing: [], records: [], passed: true },
        independence: { passed: true },
        workload: { passed: true },
        active_privilege: { id: "priv-1" },
      });
    }

    if (path.endsWith("/quality/assurance-cases") && request.method() === "GET") {
      return json(route, { items: [assuranceCase], total: 1, limit: 150, offset: 0, has_more: false });
    }
    if (path.endsWith("/quality/assurance-cases/case-1") && request.method() === "GET") return json(route, assuranceCase);

    if (path.endsWith("/quality/intelligence/overview")) {
      return json(route, {
        as_of: "2026-08-09T10:00:00Z",
        programme: {
          states: { SCHEDULED: 8, COMPLETED: 12 },
          completion: { numerator: 12, denominator: 20, value: 0.6 },
          deferral_rate: { numerator: 1, denominator: 20, value: 0.05 },
          calculation: "deterministic",
        },
        assurance: { open_cases: 2, overdue_cases: 1, ineffective_or_inconclusive_reviews: 0 },
        people: { active_privileges: 4, expiring_within_60_days: 1 },
        controls: { overdue_control_tests: 0, failed_or_partial_test_records: 0, stale_or_expired_evidence_links: 1, proposed_human_reviews: 0 },
        targeted_surveillance: [],
        method: { type: "DETERMINISTIC_RULES", statement: "Deterministic source rules order human review; they do not declare compliance or calculate a predictive probability." },
      });
    }
    if (path.endsWith("/quality/audit-programmes/risk-context")) {
      return json(route, {
        as_of: "2026-08-09T10:00:00Z",
        items: [{
          universe_item_id: "univ-1",
          label: "Maintenance Department",
          entity_type: "DEPARTMENT",
          source_owner_module: "workforce",
          source_type: "DEPARTMENT",
          source_id: "maintenance",
          source_route: "/maintenance/tenant-a/workforce",
          mandatory_surveillance: true,
          risk_classification: "HIGH",
          regulatory_criticality: "HIGH",
          programme_states: ["SCHEDULED"],
          planning_order: 13301,
          factors: [
            { code: "MANDATORY_SURVEILLANCE", label: "Mandatory surveillance", value: true, source: "audit-universe", source_record: "Audit Universe / Maintenance Department", source_date: "2026-08-01", hard_requirement: true, rationale: "Mandatory surveillance remains a hard requirement.", planning_weight: 10000 },
            { code: "OVERDUE_CARS", label: "Overdue corrective actions", value: 1, source: "quality", source_record: "CAR-26-014", source_date: "2026-08-06", hard_requirement: false, rationale: "Overdue corrective actions increase assurance demand.", planning_weight: 350 },
          ],
          method: "Deterministic ordering from governed universe properties plus attributable authoritative-source pressures; not a probability or automated compliance conclusion.",
        }],
        global_factors: [{ code: "OVERDUE_CARS", label: "Overdue corrective actions", value: 1, source: "quality", source_record: "CAR register", source_date: "2026-08-09", hard_requirement: false, rationale: "Overdue corrective actions are an explicit assurance exposure.", planning_weight: 350 }],
        authoritative_metrics: { overdue_cars: 1, open_findings: 2 },
        reliability: { high_critical_events_90d: 1, repeat_events_90d: 0, recurring_findings: 0, open_high_recommendations: 0 },
        source_warnings: [],
        method: { type: "DETERMINISTIC_SOURCE_ATTRIBUTION", statement: "Mandatory surveillance remains a hard obligation. Other factors order planning attention only; they do not declare compliance or calculate a predictive probability." },
      });
    }
    if (path.endsWith("/quality/intelligence/signal-rules")) {
      return json(route, { items: [{ id: "rule-sig-1", rule_code: "OVERDUE_CARS_PRESENT", title: "Overdue CARs", metric: "OVERDUE_CAR_COUNT", operator: "GT", threshold: 0, severity: "WARNING", explanation: "Open overdue CAR exists.", source_contract: {}, is_active: true }] });
    }
    if (path.endsWith("/quality/intelligence/signals")) {
      return json(route, { items: [{ id: "signal-1", metric: "OVERDUE_CAR_COUNT", observed_value: 1, threshold: 0, operator: "GT", triggered: true, severity: "WARNING", explanation: "Observed one overdue CAR.", source_snapshot: {}, as_of: "2026-08-09T10:00:00Z" }] });
    }
    if (path.endsWith("/quality/intelligence/approval-digital-twin")) {
      return json(route, {
        as_of: "2026-08-09T10:00:00Z",
        assurance_state: "STALE",
        is_compliance_declaration: false,
        state_counts: { SUPPORTED: 6, UNSUPPORTED: 0, STALE: 1, UNRESOLVED: 0, BLOCKED: 0 },
        blockers: [{ id: "node-2", node_type: "PROCEDURE", title: "Tool calibration procedure", support_state: "STALE", state_reason: "Controlled revision changed after evidence snapshot.", source_route: "/documents/procedure-2" }],
        explanation: "Evidence-support/readiness view; not a compliance declaration.",
      });
    }
    if (path.endsWith("/quality/intelligence/approval-graph")) {
      return json(route, {
        nodes: [{ id: "node-2", node_type: "PROCEDURE", title: "Tool calibration procedure", source_owner_module: "document-control", source_type: "CONTROLLED_DOCUMENT", source_id: "procedure-2", source_route: "/documents/procedure-2", support_state: "STALE", state_reason: "Controlled revision changed after evidence snapshot.", source_snapshot: {}, evidence_as_of: "2026-08-01T11:00:00Z", updated_at: "2026-08-08T11:00:00Z" }],
        links: [],
      });
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) return json(route, { items: [], columns: [], limit: 30, offset: 0, has_more: false });
    return json(route, { detail: "Not mocked" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("People is person-first, contextual and readable at native 1080p", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });

  await expectFontAtLeast(page.getByRole("heading", { name: "Quality authorization board", exact: true }), 28);
  await expect(page.getByText("Amina Wanjiku", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "People and current privileges", exact: true })).toBeVisible();
  await expect(page.getByText("Current authorization readiness", { exact: true })).toBeVisible();
  await expectFontAtLeast(page.locator(".qms-people__row-button strong").first(), 13.5);

  await page.getByRole("button", { name: /Check audit assignment/i }).click();
  await expect(page.getByRole("heading", { name: "Check governed audit assignment", exact: true })).toBeVisible();
  const input = page.locator(".qms-people__drawer input").first();
  await expectFontAtLeast(input, 14);
  await expectMinHeightAtLeast(input, 42);
});

test("Assurance keeps case triage primary and opens creation as a readable governed drawer", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });

  await expectFontAtLeast(page.getByRole("heading", { name: "Cases, investigation & effectiveness", exact: true }), 28);
  await expect(page.getByRole("heading", { name: "Governed assurance work", exact: true })).toBeVisible();
  await expect(page.getByText("Repeat tooling-control finding", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /New case/i }).click();
  const createHeading = page.getByRole("heading", { name: "Source-backed assurance problem", exact: true });
  await expect(createHeading).toBeVisible();
  const createPanel = createHeading.locator("xpath=ancestor::section[contains(@class,'qms-assurance-cases__panel')]").first();
  expect(await createPanel.evaluate((element) => window.getComputedStyle(element).position)).toBe("fixed");
  await expectFontAtLeast(page.locator("#case-title"), 14);
  await expectMinHeightAtLeast(page.locator("#case-title"), 42);

  await page.getByRole("button", { name: /Close create assurance case/i }).click();
  await expect(createHeading).toHaveCount(0);
  await page.getByText("Repeat tooling-control finding", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Fact → hypothesis → causal conclusion", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Define, observe & conclude effectiveness", exact: true })).toBeVisible();
});

test("Intelligence leads with ranked deterministic surveillance and source provenance at 1080p", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=intelligence", { waitUntil: "domcontentloaded" });

  await expectFontAtLeast(page.getByRole("heading", { name: "Surveillance priorities & assurance impact", exact: true }), 28);
  await expect(page.getByRole("heading", { name: "Surveillance priorities", exact: true })).toBeVisible();
  await expect(page.getByText("Maintenance Department", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Mandatory", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/no predictive compliance probability is generated/i)).toBeVisible();
  await expectFontAtLeast(page.locator(".qms-intelligence__priority h3").first(), 16);

  await page.getByText(/Review 2 source-attributed factors/i).click();
  await expect(page.getByText("Audit Universe / Maintenance Department", { exact: true })).toBeVisible();
  await expect(page.getByText("CAR-26-014", { exact: true })).toBeVisible();
  await expect(page.getByText("Weight 10000", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Stale", exact: true })).toBeVisible();
});

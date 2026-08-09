import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
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
    id: "entry-1", method: "FIVE_WHYS", entry_type: "FACT", sequence_no: 1,
    category: "Evidence", prompt: null,
    statement: "Calibration certificates were unavailable at point of use during both sampled audits.",
    confidence: 100, evidence_references: [{ source_type: "QMS_AUDIT_FINDING", source_id: "finding-44" }],
    parent_entry_id: null, created_by_user_id: "quality-user-a", created_at: "2026-08-08T11:00:00Z",
  }],
  effectiveness_plans: [{
    id: "plan-1", source_type: "QUALITY_CAR", source_id: "car-1", source_route: "/quality/cars/car-1",
    expected_outcome: "No repeat missing-calibration evidence during the observation window.",
    effectiveness_measure: "Zero repeat findings in the next targeted tooling sample.",
    verification_method: "Targeted follow-up audit and evidence review.", observation_window: "90 days",
    source_indicators: [], responsible_reviewer_user_id: "quality-user-a", planned_review_date: "2026-11-30",
    status: "PLANNED", conclusion: null, conclusion_rationale: null, conclusion_evidence: [],
    concluded_by_user_id: null, concluded_at: null, created_at: "2026-08-08T11:30:00Z", updated_at: "2026-08-08T11:30:00Z",
  }],
  events: [{
    id: "event-1", event_type: "CREATED", reason: "Recurring finding escalated into an assurance case.",
    before_snapshot: null, after_snapshot: { status: "OPEN" }, actor_user_id: "quality-user-a", created_at: "2026-08-08T10:00:00Z",
  }],
};

async function prepare(page: Page): Promise<void> {
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

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/auth/portal-preferences/") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable",
        motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-08T12:00:00Z",
      }) });
      return;
    }
    if (path.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }

    if (path.endsWith("/quality/people/summary")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ active_privileges: 4, expiring_within_60_days: 1, suspended_privileges: 0, independence_exceptions: 1 }) });
      return;
    }
    if (path.endsWith("/quality/people/rules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{
        id: "rule-1", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR",
        required_training_course_codes: ["QMS-AUD"], independence_required: true, max_concurrent_assignments: 2,
        scope_schema: {}, is_active: true, updated_at: "2026-08-08T12:00:00Z",
      }] }) });
      return;
    }
    if (path.endsWith("/quality/people/privileges")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{
        id: "priv-1", rule_id: "rule-1", user_id: "auditor-user-a", privilege_code: "AUDITOR_INTERNAL",
        scope_key: "GLOBAL", scope: {}, limitations: [], status: "ACTIVE", effective_from: "2026-01-01",
        expires_on: "2026-12-31", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-08-08T12:00:00Z", decisions: [],
      }] }) });
      return;
    }

    if (path.endsWith("/quality/assurance-cases") && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [assuranceCase], total: 1, limit: 150, offset: 0, has_more: false }) });
      return;
    }
    if (path.endsWith("/quality/assurance-cases/case-1") && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(assuranceCase) });
      return;
    }

    if (path.endsWith("/quality/intelligence/overview")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        as_of: "2026-08-08T12:00:00Z",
        programme: { states: { SCHEDULED: 8, COMPLETED: 12 }, completion: { numerator: 12, denominator: 20, value: 0.6 }, deferral_rate: { numerator: 1, denominator: 20, value: 0.05 }, calculation: "deterministic" },
        assurance: { open_cases: 2, overdue_cases: 1, ineffective_or_inconclusive_reviews: 0 },
        people: { active_privileges: 4, expiring_within_60_days: 1 },
        controls: { overdue_control_tests: 0, failed_or_partial_test_records: 0, stale_or_expired_evidence_links: 1, proposed_human_reviews: 0 },
        targeted_surveillance: [{
          universe_item_id: "univ-1", label: "Maintenance Department", entity_type: "DEPARTMENT",
          source_owner_module: "workforce", source_type: "DEPARTMENT", source_id: "maintenance",
          source_route: "/maintenance/tenant-a/workforce", mandatory_surveillance: true,
          risk_classification: "HIGH", regulatory_criticality: "HIGH", surveillance_interval_days: 365,
          programme_states: ["SCHEDULED"], priority_order: 1,
          factors: [{ code: "MANDATORY", label: "Mandatory surveillance", value: true, hard_requirement: true, source: "audit universe", rule: "must remain scheduled" }],
          explanation: "Deterministic ordering only. This is not a predictive probability or automated compliance conclusion.",
        }],
        method: { type: "DETERMINISTIC_RULES", statement: "Deterministic source rules order human review; they do not declare compliance or calculate a predictive probability." },
      }) });
      return;
    }
    if (path.endsWith("/quality/audit-programmes/risk-context")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        as_of: "2026-08-08T12:00:00Z",
        items: [{
          universe_item_id: "univ-1", label: "Maintenance Department", entity_type: "DEPARTMENT",
          source_owner_module: "workforce", source_type: "DEPARTMENT", source_id: "maintenance",
          source_route: "/maintenance/tenant-a/workforce", mandatory_surveillance: true,
          risk_classification: "HIGH", regulatory_criticality: "HIGH", programme_states: ["SCHEDULED"], planning_order: 13301,
          factors: [
            { code: "MANDATORY_SURVEILLANCE", label: "Mandatory surveillance", value: true, source: "audit-universe", hard_requirement: true, rationale: "Mandatory surveillance remains a hard requirement." },
            { code: "OVERDUE_CARS", label: "Overdue corrective actions", value: 1, source: "quality", hard_requirement: false, rationale: "Overdue corrective actions increase assurance demand." },
          ],
          method: "Deterministic ordering from governed universe properties plus attributable authoritative-source pressures; not a probability or automated compliance conclusion.",
        }],
        global_factors: [{ code: "OVERDUE_CARS", label: "Overdue corrective actions", value: 1, source: "quality", hard_requirement: false, rationale: "Overdue corrective actions are an explicit assurance exposure." }],
        authoritative_metrics: { overdue_cars: 1, open_findings: 2 },
        reliability: { high_critical_events_90d: 1, repeat_events_90d: 0, recurring_findings: 0, open_high_recommendations: 0 },
        source_warnings: [],
        method: { type: "DETERMINISTIC_SOURCE_ATTRIBUTION", statement: "Mandatory surveillance remains a hard obligation. Other factors order planning attention only; they do not declare compliance or calculate a predictive probability." },
      }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/signal-rules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{
        id: "sig-rule-1", rule_code: "OVERDUE_CARS_PRESENT", title: "Overdue corrective actions present",
        metric: "OVERDUE_CAR_COUNT", operator: "GT", threshold: 0, severity: "WARNING",
        explanation: "At least one open CAR is past its due date.", source_contract: { authoritative: true }, is_active: true,
      }] }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/signals")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{
        id: "signal-1", rule_id: "sig-rule-1", metric: "OVERDUE_CAR_COUNT", observed_value: 1, threshold: 0,
        operator: "GT", triggered: true, severity: "WARNING", explanation: "Observed one overdue CAR from the authoritative CAR register.",
        source_snapshot: { overdue_cars: 1 }, source_references: [{ source_type: "QUALITY_CAR", count: 1 }],
        as_of: "2026-08-08T12:00:00Z", state: "OPEN",
      }] }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/approval-digital-twin")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        as_of: "2026-08-08T12:00:00Z", assurance_state: "STALE", is_compliance_declaration: false,
        state_counts: { SUPPORTED: 6, UNSUPPORTED: 0, STALE: 1, UNRESOLVED: 0, BLOCKED: 0 },
        blockers: [{ id: "node-2", node_type: "PROCEDURE", title: "Tool calibration procedure", support_state: "STALE", state_reason: "Controlled revision changed after the evidence snapshot.", source_route: "/documents/procedure-2" }],
        explanation: "This is an evidence-support/readiness view. It does not declare regulatory compliance.",
      }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/approval-graph")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ nodes: [{
        id: "node-1", node_type: "REQUIREMENT", title: "Tool calibration requirement",
        source_owner_module: "document-control", source_type: "CONTROLLED_REQUIREMENT", source_id: "req-1",
        source_route: "/documents/req-1", support_state: "SUPPORTED", state_reason: "Current controlled evidence linked.",
        source_snapshot: {}, evidence_as_of: "2026-08-08T11:00:00Z", updated_at: "2026-08-08T11:00:00Z",
      }, {
        id: "node-2", node_type: "PROCEDURE", title: "Tool calibration procedure",
        source_owner_module: "document-control", source_type: "CONTROLLED_DOCUMENT", source_id: "procedure-2",
        source_route: "/documents/procedure-2", support_state: "STALE", state_reason: "Controlled revision changed after the evidence snapshot.",
        source_snapshot: {}, evidence_as_of: "2026-08-01T11:00:00Z", updated_at: "2026-08-08T11:00:00Z",
      }], links: [{ id: "link-1", from_node_id: "node-1", to_node_id: "node-2", relationship: "IMPLEMENTS" }] }) });
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], columns: [], limit: 25, offset: 0, has_more: false }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in assurance OS browser test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("People workspace exposes governed privileges and hard eligibility controls", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Authorization board" })).toBeVisible();
  await expect(page.getByText("AUDITOR_INTERNAL", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Check task eligibility" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Declare assignment conflict state" })).toBeVisible();
  await expect(page.getByText(/Training, Workforce and Rostering remain the authoritative sources/i)).toBeVisible();
});

test("Assurance workspace exposes investigation and effectiveness engineering", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Cases, investigation & effectiveness" })).toBeVisible();
  await page.getByText("Repeat tooling-control finding", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Fact → hypothesis → causal conclusion" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Define success before closure" })).toBeVisible();
  await expect(page.getByText("Calibration certificates were unavailable at point of use during both sampled audits.", { exact: true })).toBeVisible();
  await expect(page.getByText(/without replacing the source audit, CAR, supplier or maintenance records/i)).toBeVisible();
});

test("Intelligence workspace is deterministic and exposes the approval evidence twin", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=intelligence", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Assurance signals & approval impact" })).toBeVisible();
  await expect(page.getByText(/No predictive compliance score is generated/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cross-source assurance pressure" })).toBeVisible();
  await expect(page.getByText(/do not declare compliance or calculate a predictive probability/i)).toBeVisible();
  await expect(page.getByText("Approval Digital Twin", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "STALE" })).toBeVisible();
  await expect(page.getByText("Maintenance Department", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Tool calibration procedure", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/does not declare regulatory compliance/i)).toBeVisible();
});

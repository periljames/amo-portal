import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

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
    const url = new URL(route.request().url());
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
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ id: "rule-1", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR", required_training_course_codes: ["QMS-AUD"], independence_required: true, max_concurrent_assignments: 2, scope_schema: {}, is_active: true, updated_at: "2026-08-08T12:00:00Z" }] }) });
      return;
    }
    if (path.endsWith("/quality/people/privileges")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ id: "priv-1", rule_id: "rule-1", user_id: "auditor-user-a", privilege_code: "AUDITOR_INTERNAL", scope_key: "GLOBAL", scope: {}, limitations: [], status: "ACTIVE", effective_from: "2026-01-01", expires_on: "2026-12-31", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-08-08T12:00:00Z", decisions: [] }] }) });
      return;
    }

    if (path.endsWith("/quality/assurance-cases")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ id: "case-1", case_ref: "ASC-26-001", case_type: "INVESTIGATION", title: "Repeat work-card finding", severity: "HIGH", status: "INVESTIGATING", source_references: [], regulatory_basis: [], opened_at: "2026-08-08T12:00:00Z", created_at: "2026-08-08T12:00:00Z", updated_at: "2026-08-08T12:00:00Z" }], total: 1, limit: 150, offset: 0, has_more: false }) });
      return;
    }

    if (path.endsWith("/quality/intelligence/overview")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        as_of: "2026-08-08T12:00:00Z",
        programme: { states: { SCHEDULED: 8, COMPLETED: 12 }, completion: { numerator: 12, denominator: 20, value: 0.6 }, deferral_rate: { numerator: 1, denominator: 20, value: 0.05 }, calculation: "deterministic" },
        assurance: { open_cases: 2, overdue_cases: 1, ineffective_or_inconclusive_reviews: 0 },
        people: { active_privileges: 4, expiring_within_60_days: 1 },
        controls: { overdue_control_tests: 0, failed_or_partial_test_records: 0, stale_or_expired_evidence_links: 1, proposed_human_reviews: 0 },
        targeted_surveillance: [{ universe_item_id: "univ-1", label: "Maintenance Department", entity_type: "DEPARTMENT", source_owner_module: "workforce", source_type: "DEPARTMENT", source_id: "maintenance", source_route: "/maintenance/tenant-a/workforce", mandatory_surveillance: true, risk_classification: "HIGH", regulatory_criticality: "HIGH", surveillance_interval_days: 365, programme_states: ["SCHEDULED"], priority_order: 1, factors: [{ code: "MANDATORY", label: "Mandatory surveillance", value: true, hard_requirement: true, source: "audit universe", rule: "must remain scheduled" }], explanation: "Mandatory surveillance is an explicit hard requirement." }],
        method: { type: "deterministic", statement: "No predictive compliance score." },
      }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/signal-rules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/signals")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/approval-digital-twin")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ as_of: "2026-08-08T12:00:00Z", assurance_state: "UNRESOLVED", is_compliance_declaration: false, state_counts: { SUPPORTED: 2, UNRESOLVED: 1 }, blockers: [{ id: "node-1", node_type: "MANUAL", title: "MPM procedure", support_state: "UNRESOLVED", state_reason: "Evidence link not yet verified." }], explanation: "Evidence-support/readiness view only; not a regulatory compliance declaration." }) });
      return;
    }
    if (path.endsWith("/quality/intelligence/approval-graph")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ nodes: [{ id: "node-1", node_type: "MANUAL", title: "MPM procedure", source_owner_module: "document-control", source_type: "CONTROLLED_DOCUMENT", source_id: "MPM-1", support_state: "UNRESOLVED", state_reason: "Evidence link not yet verified.", updated_at: "2026-08-08T12:00:00Z" }], links: [] }) });
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], columns: [], limit: 25, offset: 0, has_more: false }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in assurance operating system browser test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("People, Assurance and Intelligence are real permanent workspaces", async ({ page }) => {
  await prepare(page);

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Authorization board" })).toBeVisible();
  await expect(page.getByText("Internal Auditor · AUDITOR_INTERNAL")).toBeVisible();
  await expect(page.getByText("ACTIVE", { exact: true })).toBeVisible();

  await page.goto("/maintenance/tenant-a/quality?workspace=assurance", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Cases, investigation & effectiveness" })).toBeVisible();
  await expect(page.getByText("Repeat work-card finding", { exact: true })).toBeVisible();
  await expect(page.getByText("Fact → hypothesis → causal conclusion", { exact: true })).toHaveCount(0);

  await page.goto("/maintenance/tenant-a/quality?workspace=intelligence", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Explainable surveillance and approval readiness" })).toBeVisible();
  await expect(page.getByText("60.0%", { exact: true })).toBeVisible();
  await expect(page.getByText("Mandatory surveillance is an explicit hard requirement.", { exact: true })).toBeVisible();
  await expect(page.getByText(/not a compliance declaration/i)).toBeVisible();
  await expect(page.getByText("MPM procedure", { exact: true })).toBeVisible();
});

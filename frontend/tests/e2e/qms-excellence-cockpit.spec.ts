import { expect, test, type Page, type Route } from "@playwright/test";


function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function prepare(page: Page, role = "QUALITY_MANAGER"): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken, storedRole }) => {
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
      role: storedRole,
      position_title: storedRole === "QUALITY_MANAGER" ? "Quality Manager" : "Auditor",
      phone: null,
      regulatory_authority: "KCAA",
      licence_number: null,
      licence_state_or_country: "Kenya",
      licence_expires_on: null,
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
      last_login_at: null,
      last_login_ip: null,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    }));
  }, { storedToken: token, storedRole: role });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/auth/portal-preferences/") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "quality-user-a",
          amo_id: "amo-a",
          text_scale: "standard",
          density: "comfortable",
          motion: "system",
          color_scheme: "light",
          accent: "tenant",
          version: 1,
          updated_at: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }

    if (path.endsWith("/quality/excellence/overview")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant: { amo_code: "tenant-a", amo_id: "amo-a" },
          as_of: "2026-08-04T04:00:00Z",
          readiness: {
            score: 78,
            band: "WATCH",
            dimensions: [
              { id: "audit_programme", label: "Audit Programme", score: 82, weight: 0.2 },
              { id: "capa_discipline", label: "Capa Discipline", score: 68, weight: 0.25 },
              { id: "finding_control", label: "Finding Control", score: 76, weight: 0.15 },
              { id: "document_currency", label: "Document Currency", score: 90, weight: 0.15 },
              { id: "competence", label: "Competence", score: 80, weight: 0.15 },
              { id: "continuous_controls", label: "Continuous Controls", score: 72, weight: 0.1 },
            ],
            method: "transparent_weighted_operational_pressure_v1",
            disclaimer: "Readiness is an operational indicator, not a regulatory compliance declaration.",
          },
          metrics: {
            overdue_audits: 1,
            audits_due_30: 3,
            open_cars: 5,
            overdue_cars: 2,
            cars_due_30: 2,
            open_findings: 4,
            active_documents: 26,
            draft_documents: 2,
            expired_training: 1,
            active_controls: 8,
            controls_due: 2,
            verified_controls: 6,
            proposed_insights: 2,
          },
          priority_queue: [
            { id: "overdue-cars", label: "Overdue corrective actions", count: 2, severity: "CRITICAL", why: "Closure dates have passed while the CAR remains open.", path: "/maintenance/tenant-a/quality/cars/overdue" },
            { id: "overdue-audits", label: "Overdue audit commitments", count: 1, severity: "HIGH", why: "The approved audit programme contains dates that have passed.", path: "/maintenance/tenant-a/quality/audits/plan?view=calendar" },
          ],
          forecast: { commitments_due_30_days: 7, band: "ELEVATED", explanation: "Audit dates, CAR due dates and assurance-control test dates falling within 30 days." },
          capabilities: [
            { id: "control-twin", label: "Control twin", description: "Durable control record.", path: "/maintenance/tenant-a/quality?hub=controls" },
            { id: "evidence-graph", label: "Evidence graph", description: "Trace controls to evidence.", path: "/maintenance/tenant-a/quality?hub=evidence" },
            { id: "human-governed-intelligence", label: "Human-governed intelligence", description: "Review every recommendation.", path: "/maintenance/tenant-a/quality?hub=intelligence" },
          ],
          warnings: [],
        }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/controls")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{
            id: "control-1",
            control_code: "145.A.65-C01",
            title: "Independent quality audit programme",
            description: "Verify the complete maintenance system on a planned cycle.",
            framework: "KCAR PART 145",
            clause_reference: "145.A.65(c)",
            process_area: "Quality assurance",
            owner_user_id: "quality-user-a",
            criticality: "CRITICAL",
            status: "ACTIVE",
            test_frequency_days: 365,
            evidence_expectation: "Programme, reports and closure evidence",
            last_tested_at: null,
            next_test_due: "2026-08-20",
            due_state: "DUE_SOON",
            evidence_count: 2,
            verified_evidence_count: 1,
            created_at: "2026-08-04T04:00:00Z",
            updated_at: "2026-08-04T04:00:00Z",
          }],
          total: 1,
          as_of: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/evidence-graph")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          nodes: [
            { id: "control:control-1", kind: "control", label: "145.A.65-C01 · Independent quality audit programme", framework: "KCAR PART 145", process_area: "Quality assurance", criticality: "CRITICAL", status: "ACTIVE" },
            { id: "source:DOCUMENT:doc-1", kind: "evidence", type: "DOCUMENT", label: "MOE 3.2 Quality audit procedure", status: "VERIFIED" },
          ],
          edges: [{ id: "edge-1", from: "control:control-1", to: "source:DOCUMENT:doc-1", relationship: "IMPLEMENTS", status: "VERIFIED", valid_until: null }],
          summary: { controls: 1, evidence_records: 1, relationships: 1, controls_without_evidence: 0 },
          as_of: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/insights")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{
            id: "insight-1",
            insight_type: "CAPA_ESCALATION",
            title: "Escalate overdue corrective-action exposure",
            rationale: "Two CAR records are beyond their target closure date.",
            recommendation: "Review owners and containment sufficiency.",
            payload: { count: 2, module: "cars" },
            source_fingerprint: "rule:overdue-cars:2026-08-04:2",
            risk_level: "HIGH",
            status: "PROPOSED",
            created_by: "RULE_ENGINE",
            human_decision_by_user_id: null,
            human_decision_note: null,
            decision_at: null,
            created_at: "2026-08-04T04:00:00Z",
          }],
          total: 1,
          as_of: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.includes("/quality/excellence/controls/") && path.endsWith("/evidence") && request.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "edge-new" }) });
      return;
    }

    if (path.endsWith("/quality/dashboard")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tenant: { amo_code: "tenant-a", amo_id: "amo-a" }, counters: {}, source_errors: [] }) });
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ module: "overview", view: "dashboard", items: [], columns: [], limit: 15, offset: 0, has_more: false, source_errors: [] }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in QMS excellence test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("QMS root is refactored into a continuous assurance control centre", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 950 });
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality", { waitUntil: "domcontentloaded" });

  const cockpit = page.locator(".qe-cockpit");
  await expect(cockpit).toBeVisible();
  await expect(cockpit.getByRole("heading", { name: "Quality Control Centre" })).toBeVisible();
  await expect(cockpit.getByLabel(/Operational readiness 78 percent/)).toBeVisible();
  await expect(cockpit.getByText("Overdue corrective actions")).toBeVisible();
  await expect(cockpit.getByRole("button", { name: /Control library/ })).toBeVisible();
  await expect(page.locator("html")).toHaveClass(/quality-excellence-active/);
});

test("Quality management can create controls and link evidence from one workspace", async ({ page }) => {
  await prepare(page, "QUALITY_MANAGER");
  await page.goto("/maintenance/tenant-a/quality?hub=controls", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Control library" })).toBeVisible();
  await expect(page.getByText("145.A.65-C01")).toBeVisible();
  await expect(page.getByRole("button", { name: "New control" })).toBeVisible();
  await page.getByRole("button", { name: "Link evidence" }).click();
  await expect(page.getByRole("complementary", { name: "Link control evidence" })).toBeVisible();
  await page.getByLabel("Record ID or reference").fill("doc-2");
  await page.getByLabel("Display label").fill("MOE 3.2 audit procedure");
  await page.getByRole("button", { name: "Add evidence relationship" }).click();
  await expect(page.getByText(/Evidence relationship linked/)).toBeVisible();
});

test("auditors see intelligence but cannot decide or generate recommendations", async ({ page }) => {
  await prepare(page, "AUDITOR");
  await page.goto("/maintenance/tenant-a/quality?hub=intelligence", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Quality intelligence review" })).toBeVisible();
  await expect(page.getByText("Escalate overdue corrective-action exposure")).toBeVisible();
  await expect(page.getByText(/only Quality management can create or decide/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Rebuild recommendations" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Accept for action" })).toHaveCount(0);
});

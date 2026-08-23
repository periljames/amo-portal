import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function futureDateOnly(daysAhead = 7): string {
  const value = new Date();
  value.setDate(value.getDate() + daysAhead);
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

function controlRecord(approvalStatus: "PENDING_APPROVAL" | "APPROVED" = "PENDING_APPROVAL") {
  return {
    id: "control-1",
    control_code: "145.A.65-C01",
    title: "Independent quality audit programme",
    description: "Verify the complete maintenance system on a planned cycle.",
    control_objective: "Confirm independent surveillance covers the approved maintenance system.",
    test_method: "Inspect programme coverage, independence, reports and follow-up.",
    framework: "KCAR PART 145",
    clause_reference: "145.A.65(c)",
    process_area: "Quality assurance",
    owner_user_id: "quality-user-a",
    criticality: "CRITICAL",
    status: "ACTIVE",
    approval_status: approvalStatus,
    version_no: 1,
    test_frequency_days: 365,
    evidence_expectation: "Programme, independent reports and closure evidence",
    last_tested_at: null,
    next_test_due: "2026-08-20",
    due_state: "DUE_SOON",
    evidence_count: 2,
    verified_evidence_count: 1,
    latest_test_result: null,
    latest_tested_at: null,
    approved_by_user_id: approvalStatus === "APPROVED" ? "quality-user-a" : null,
    approved_at: approvalStatus === "APPROVED" ? "2026-08-04T04:00:00Z" : null,
    created_at: "2026-08-04T04:00:00Z",
    updated_at: "2026-08-04T04:00:00Z",
  };
}

function operationalDashboard() {
  return {
    contract: "qms-operational-dashboard.v2",
    tenant: { amo_code: "tenant-a", amo_id: "amo-a" },
    as_of: "2026-08-07T07:30:00Z",
    action_queue: [
      {
        id: "overdue-cars",
        label: "Overdue corrective actions",
        count: 2,
        oldest_age_days: 18,
        owner_status: "assigned",
        next_action: "Review containment and closure plan",
        route: "/maintenance/tenant-a/quality/cars/overdue",
        tone: "danger",
        priority: 100,
        regulatory_consequence: "corrective_action_overdue",
      },
      {
        id: "audit-due",
        label: "Audits due within 30 days",
        count: 3,
        oldest_age_days: 0,
        owner_status: "audit_programme",
        next_action: "Confirm audit plan",
        route: "/maintenance/tenant-a/quality/audits/schedule",
        tone: "warning",
        priority: 70,
        regulatory_consequence: "planned_surveillance_due",
      },
    ],
    my_work: [
      {
        id: "work-1",
        title: "Review CAR QMS-CAR-026",
        severity: "MAJOR",
        created_at: "2026-08-07T06:30:00Z",
        route: "/maintenance/tenant-a/quality/cars/register",
      },
    ],
    upcoming_obligations: [
      {
        id: "obligation-1",
        module: "audits",
        entity_type: "audit",
        entity_id: "audit-1",
        title: "Base maintenance audit",
        date: futureDateOnly(),
        event_type: "AUDIT_DUE",
        link: "/maintenance/tenant-a/quality/audits/schedule",
        due_state: "upcoming",
        actionable: true,
        subtitle: "Nairobi base",
      },
    ],
    performance_kpis: [
      {
        id: "capa-on-time",
        label: "CAR closure on time",
        current: 86,
        target: 95,
        previous: 82,
        direction: "improving",
        unit: "%",
        route: "/maintenance/tenant-a/quality/reports/executive-dashboard",
        data_status: "available",
      },
    ],
    aging_buckets: {},
    unassigned_counts: {},
    severity_breakdown: {},
    period_comparisons: { status: "available", note: "Current and previous periods available." },
    data_freshness: { generated_at: "2026-08-07T07:30:00Z", counter_source: "live", counter_as_of: "2026-08-07T07:30:00Z" },
    source_health: { status: "healthy", error_count: 0, errors_by_source: {}, errors: [] },
    counters: { overdue_cars: 2, audits_due_30: 3 },
    trace_id: "qms-dashboard-v2-test",
    elapsed_ms: 18,
  };
}

function assuranceOverview() {
  return {
    tenant: { amo_code: "tenant-a", amo_id: "amo-a" },
    as_of: "2026-08-04T04:00:00Z",
    readiness: {
      score: 78,
      band: "WATCH",
      dimensions: [
        { id: "audit_programme", label: "Audit Programme", score: 82, weight: 0.15 },
        { id: "capa_discipline", label: "Capa Discipline", score: 68, weight: 0.15 },
        { id: "finding_control", label: "Finding Control", score: 76, weight: 0.08 },
        { id: "document_currency", label: "Document Currency", score: 90, weight: 0.08 },
        { id: "competence", label: "Competence", score: 80, weight: 0.08 },
        { id: "supplier_calibration", label: "Supplier Calibration", score: 74, weight: 0.1 },
        { id: "risk_change", label: "Risk Change", score: 72, weight: 0.1 },
        { id: "continuous_controls", label: "Continuous Controls", score: 70, weight: 0.16 },
        { id: "external_commitments", label: "External Commitments", score: 85, weight: 0.05 },
        { id: "management_review", label: "Management Review", score: 88, weight: 0.05 },
      ],
      method: "cross_module_continuous_assurance_v2",
      disclaimer: "Readiness is a transparent operational indicator, not a regulatory compliance declaration.",
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
      expired_supplier_approvals: 1,
      supplier_approvals_due_30: 2,
      overdue_calibrations: 1,
      calibrations_due_30: 2,
      out_of_tolerance: 0,
      critical_risks: 1,
      pending_changes: 2,
      open_regulator_findings: 1,
      overdue_review_actions: 1,
      active_controls: 8,
      controls_due: 2,
      verified_controls: 6,
      invalid_evidence: 1,
      pending_assurance_events: 1,
      proposed_insights: 2,
    },
    priority_queue: [
      { id: "overdue-cars", label: "Overdue corrective actions", count: 2, severity: "CRITICAL", why: "Closure dates have passed while CAR records remain open.", path: "/maintenance/tenant-a/quality/cars/overdue" },
      { id: "regulator-findings", label: "Open regulator findings", count: 1, severity: "CRITICAL", why: "Authority findings remain open.", path: "/maintenance/tenant-a/quality/external-interface/regulator-findings" },
    ],
    forecast: { commitments_due_30_days: 11, band: "ELEVATED", explanation: "Audit, CAR, control-test, supplier-approval and calibration commitments falling within 30 days." },
    capabilities: [
      { id: "control-twin", label: "Approved control twin", description: "Versioned controls.", path: "/maintenance/tenant-a/quality?hub=controls" },
      { id: "evidence-graph", label: "Validated evidence graph", description: "Tenant-validated evidence.", path: "/maintenance/tenant-a/quality?hub=evidence" },
      { id: "management-pack", label: "Management-review pack", description: "Decision-ready inputs.", path: "/maintenance/tenant-a/quality/management-review/dashboard" },
      { id: "human-intelligence", label: "Human-governed intelligence", description: "Advisory recommendations.", path: "/maintenance/tenant-a/quality?hub=intelligence" },
    ],
    source_coverage: { available: 17, warnings: 0 },
    warnings: [],
  };
}

async function prepare(page: Page, role = "QUALITY_MANAGER"): Promise<void> {
  const token = futureToken();
  let approvalStatus: "PENDING_APPROVAL" | "APPROVED" = "PENDING_APPROVAL";

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

    if (path.endsWith("/quality/dashboard-v2")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(operationalDashboard()) });
      return;
    }

    if (path.endsWith("/quality/excellence/overview/full")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(assuranceOverview()) });
      return;
    }

    if (path.endsWith("/quality/excellence/management-review-pack")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          generated_at: "2026-08-04T04:00:00Z",
          tenant: { amo_code: "tenant-a", amo_id: "amo-a" },
          readiness: { score: 78, band: "WATCH", dimensions: [], method: "cross_module_continuous_assurance_v2", disclaimer: "Not a compliance declaration." },
          executive_summary: ["Operational readiness is 78% (watch).", "Two corrective actions are overdue."],
          decisions_required: [{ title: "Overdue corrective actions", reason: "Closure dates have passed.", severity: "CRITICAL", count: 2, path: "/maintenance/tenant-a/quality/cars/overdue" }],
          metrics: {},
          evidence_gaps: { invalid_evidence: 1, controls_due: 2, pending_events: 1 },
          source_warnings: [],
        }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/controls") && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [controlRecord(approvalStatus)], total: 1, as_of: "2026-08-04T04:00:00Z" }) });
      return;
    }

    if (path.endsWith("/quality/excellence/source-catalog")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [
          { source_type: "DOCUMENT", label: "Controlled document", table: "qms_documents", available: true, description: "Approved controlled procedure, manual, form or work instruction." },
          { source_type: "AUDIT", label: "Audit", table: "qms_audits", available: true, description: "Approved audit scope, fieldwork, report and closeout record." },
          { source_type: "CALIBRATION", label: "Calibration record", table: "qms_calibration_records", available: true, description: "Traceable calibration result." },
        ] }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/source-search")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          source_type: url.searchParams.get("source_type") || "DOCUMENT",
          items: [{
            id: "doc-2",
            label: "MOE-3.2 · Quality audit procedure",
            status: "ACTIVE",
            valid_until: "2027-08-04",
            route: "/maintenance/tenant-a/quality/documents/library/doc-2",
            snapshot: { id: "doc-2", doc_code: "MOE-3.2", title: "Quality audit procedure", status: "ACTIVE" },
          }],
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
            { id: "control:control-1", kind: "control", label: "145.A.65-C01 · Independent quality audit programme", framework: "KCAR PART 145", process_area: "Quality assurance", criticality: "CRITICAL", status: "ACTIVE", approval_status: approvalStatus, version_no: 1 },
            { id: "source:DOCUMENT:doc-1", kind: "evidence", type: "DOCUMENT", label: "MOE 3.2 Quality audit procedure", status: "VERIFIED", route: "/maintenance/tenant-a/quality/documents/library/doc-1", last_synced_at: "2026-08-04T04:00:00Z", invalidation_reason: null },
          ],
          edges: [{ id: "edge-1", from: "control:control-1", to: "source:DOCUMENT:doc-1", relationship: "IMPLEMENTS", status: "VERIFIED", valid_until: null, source_route: "/maintenance/tenant-a/quality/documents/library/doc-1", last_synced_at: "2026-08-04T04:00:00Z", invalidation_reason: null }],
          summary: { controls: 1, evidence_records: 1, relationships: 1, controls_without_evidence: 0, invalid_relationships: 0, verified_relationships: 1 },
          as_of: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.endsWith("/quality/excellence/events")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ id: "event-1", source_table: "qms_documents", source_type: "DOCUMENT", source_id: "doc-1", event_type: "UPDATE", changed_fields: ["title"], processing_status: "PENDING", processing_error: null, actor_user_id: "quality-user-a", occurred_at: "2026-08-04T04:00:00Z", processed_at: null }], total: 1 }) });
      return;
    }

    if (path.endsWith("/quality/excellence/insights")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{ id: "insight-1", insight_type: "CAPA_ESCALATION", title: "Escalate overdue corrective-action exposure", rationale: "Two CAR records are beyond their target closure date.", recommendation: "Review owners and containment sufficiency.", payload: { count: 2, module: "cars" }, source_fingerprint: "rule:overdue-cars:2026-08-04:2", risk_level: "HIGH", status: "PROPOSED", created_by: "RULE_ENGINE", human_decision_by_user_id: null, human_decision_note: null, decision_at: null, created_at: "2026-08-04T04:00:00Z" }],
          total: 1,
          as_of: "2026-08-04T04:00:00Z",
        }),
      });
      return;
    }

    if (path.includes("/quality/excellence/controls/") && path.endsWith("/evidence") && request.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "edge-new", control_id: "control-1", source_type: "DOCUMENT", source_id: "doc-2", source_table: "qms_documents", source_route: "/maintenance/tenant-a/quality/documents/library/doc-2", source_label: "MOE-3.2 · Quality audit procedure", source_snapshot: {}, relationship: "EVIDENCES", label: "MOE-3.2 · Quality audit procedure", evidence_status: "VERIFIED", valid_until: "2027-08-04", notes: null, verified_at: "2026-08-04T04:00:00Z", source_verified_at: "2026-08-04T04:00:00Z", last_synced_at: "2026-08-04T04:00:00Z", invalidated_at: null, invalidation_reason: null, created_at: "2026-08-04T04:00:00Z" }) });
      return;
    }

    if (path.includes("/quality/excellence/controls/") && path.endsWith("/approval") && request.method() === "POST") {
      approvalStatus = "APPROVED";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(controlRecord(approvalStatus)) });
      return;
    }

    if (path.includes("/quality/excellence/controls/") && path.endsWith("/tests") && request.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "test-1", control_id: "control-1", result: "PASS", tested_at: "2026-08-04T04:00:00Z", tested_by_user_id: "quality-user-a", method: "Inspect programme", notes: "Effective", evidence_summary: {}, next_test_due: "2027-08-04", created_at: "2026-08-04T04:00:00Z" }) });
      return;
    }

    if (path.endsWith("/quality/excellence/reconcile") && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ reviewed: 1, changed: 1, rejected: 0, events_processed: 1, errors: [], as_of: "2026-08-04T04:00:00Z" }) });
      return;
    }

    if (path.endsWith("/quality/dashboard")) {
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Legacy root dashboard must not be requested" }) });
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ module: "overview", view: "dashboard", items: [], columns: [], limit: 15, offset: 0, has_more: false, source_errors: [] }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in QMS assurance test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("QMS root presents the assurance Control Room and six-workspace operating model", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 950 });
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality", { waitUntil: "domcontentloaded" });

  const controlRoom = page.locator(".qms-assurance-room");
  await expect(controlRoom).toBeVisible();
  await expect(controlRoom.getByRole("heading", { name: "Control Room" })).toBeVisible();
  await expect(controlRoom.getByText("My decisions & work", { exact: true })).toBeVisible();
  await expect(controlRoom.getByText("Priority signals", { exact: true })).toBeVisible();
  await expect(controlRoom.getByText("Regulatory consequence", { exact: true })).toBeVisible();
  await expect(controlRoom.getByRole("heading", { name: "Needs action" })).toBeVisible();
  await expect(controlRoom.getByText("Overdue corrective actions", { exact: true })).toBeVisible();
  await expect(controlRoom.getByRole("heading", { name: "My work" })).toBeVisible();
  await expect(controlRoom.getByText("Review CAR QMS-CAR-026")).toBeVisible();
  await expect(controlRoom.getByText("Base maintenance audit")).toBeVisible();
  await expect(controlRoom.getByText("CAR closure on time")).toBeVisible();

  const contextBar = page.locator(".quality-context-bar");
  for (const label of ["Control Room", "Planner", "Missions", "People", "Assurance", "Intelligence"]) {
    await expect(contextBar.getByRole("button", { name: label, exact: true })).toBeVisible();
  }

  const diagnostics = controlRoom.locator("details.qms-assurance-room__diagnostics");
  await expect(diagnostics).not.toHaveAttribute("open", "");

  await contextBar.getByRole("button", { name: "Assurance", exact: true }).click();
  await expect(page).toHaveURL(/\?workspace=assurance$/);
  await expect(page.getByRole("heading", { name: "Cases, investigation & effectiveness" })).toBeVisible();
  await expect(page.getByText(/source audit, CAR, supplier or maintenance records/i)).toBeVisible();
});

test("Quality management selects and links a validated tenant source record", async ({ page }) => {
  await prepare(page, "QUALITY_MANAGER");
  await page.goto("/maintenance/tenant-a/quality?hub=controls", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Versioned control library" })).toBeVisible();
  await expect(page.getByText("145.A.65-C01 · v1")).toBeVisible();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Link authoritative evidence" })).toBeVisible();
  await page.getByPlaceholder("Search controlled document").fill("MOE");
  await page.getByRole("button", { name: /MOE-3.2 · Quality audit procedure/ }).click();
  await page.getByLabel("Initial state").selectOption("VERIFIED");
  await page.getByRole("button", { name: "Validate and link evidence" }).click();
  await expect(page.getByText(/Authoritative evidence linked and validated/)).toBeVisible();
});

test("Quality management blocks testing until authorized approval is recorded", async ({ page }) => {
  await prepare(page, "QUALITY_MANAGER");
  await page.goto("/maintenance/tenant-a/quality?hub=controls", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Approve before testing")).toBeVisible();
  await expect(page.getByRole("button", { name: "Test" })).toHaveCount(0);

  const approvalRecorded = await page.evaluate(async () => {
    const response = await fetch("/api/maintenance/tenant-a/quality/excellence/controls/control-1/approval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "APPROVED" }),
    });
    return response.ok;
  });
  expect(approvalRecorded).toBe(true);

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "Test" })).toBeVisible();
  await page.getByRole("button", { name: "Test" }).click();
  await expect(page.getByRole("dialog", { name: "Record control test" })).toBeVisible();
  await page.getByLabel("Test conclusion").fill("The sampled programme and reports were effective.");
  await page.getByRole("button", { name: "Record test result" }).click();
  await expect(page.getByText(/Operating-effectiveness test recorded/)).toBeVisible();
});

test("auditors see intelligence and evidence events without management actions", async ({ page }) => {
  await prepare(page, "AUDITOR");
  await page.goto("/maintenance/tenant-a/quality?hub=intelligence", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Human-governed intelligence" })).toBeVisible();
  await expect(page.getByText("Escalate overdue corrective-action exposure")).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rebuild recommendations" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Accept" })).toHaveCount(0);
});
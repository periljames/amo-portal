import { expect, test } from "@playwright/test";

const auditRows = Array.from({ length: 5 }, (_, index) => ({
  id: `audit-${index + 1}`,
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

const registerPayload = {
  rows: auditRows.map((audit, index) => ({
    audit,
    finding: {
      id: `finding-${index + 1}`,
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
  })),
};

function seedSession() {
  localStorage.setItem("amo_portal_token", "fake-token");
  localStorage.setItem("amo_code", "demo");
  localStorage.setItem("amo_slug", "demo");
  localStorage.setItem("amo_department", "quality");
  localStorage.setItem(
    "amo_current_user",
    JSON.stringify({
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
    }),
  );
}

test("register loads through a bounded query shape without per-audit findings fan-out", async ({ page }) => {
  let registerRequests = 0;
  let legacyFindingRequests = 0;

  await page.addInitScript(seedSession);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/accounts/onboarding/status") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ is_complete: true, missing: [] }) });
    if (url.pathname === "/billing/entitlements") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ modules: ["quality"] }) });
    if (url.pathname === "/time") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ utc: "2026-03-19T00:00:00Z" }) });
    if (url.pathname === "/healthz") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    if (url.pathname === "/quality/audits/register") {
      registerRequests += 1;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(registerPayload) });
    }
    if (/\/quality\/audits\/[^/]+\/findings$/.test(url.pathname)) {
      legacyFindingRequests += 1;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    }
    if (url.pathname.includes("/amo-assets/logo")) return route.fulfill({ status: 404, body: "" });
    return route.continue();
  });

  await page.goto("/maintenance/demo/quality/qms/audits/register");
  await expect(page.getByRole("heading", { name: "Closeout register" })).toBeVisible();
  expect(registerRequests).toBe(1);
  expect(legacyFindingRequests).toBe(0);
});

test("evidence library uses bulk findings and bulk attachment requests instead of N+1 calls", async ({ page }) => {
  let bulkFindingRequests = 0;
  let bulkAttachmentRequests = 0;
  let legacyFindingRequests = 0;
  let legacyAttachmentRequests = 0;

  await page.addInitScript(seedSession);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/accounts/onboarding/status") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ is_complete: true, missing: [] }) });
    if (url.pathname === "/billing/entitlements") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ modules: ["quality"] }) });
    if (url.pathname === "/time") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ utc: "2026-03-19T00:00:00Z" }) });
    if (url.pathname === "/healthz") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    if (url.pathname === "/quality/audits") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(auditRows) });
    if (url.pathname === "/quality/audits/findings") {
      bulkFindingRequests += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(registerPayload.rows.map((row) => row.finding)),
      });
    }
    if (url.pathname === "/quality/cars") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(registerPayload.rows.flatMap((row) => row.linked_cars)),
      });
    }
    if (url.pathname === "/quality/cars/attachments/bulk") {
      bulkAttachmentRequests += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          registerPayload.rows.flatMap((row, index) =>
            row.linked_cars.map((car) => ({
              id: `att-${index + 1}`,
              car_id: car.id,
              filename: `evidence-${index + 1}.pdf`,
              content_type: "application/pdf",
              size_bytes: 1024,
              sha256: null,
              uploaded_at: "2026-03-19T00:00:00Z",
              download_url: `/quality/cars/${car.id}/attachments/att-${index + 1}/download`,
            })),
          ),
        ),
      });
    }
    if (/\/quality\/audits\/[^/]+\/findings$/.test(url.pathname)) {
      legacyFindingRequests += 1;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    }
    if (/\/quality\/cars\/[^/]+\/attachments$/.test(url.pathname)) {
      legacyAttachmentRequests += 1;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    }
    if (url.pathname.includes("/amo-assets/logo")) return route.fulfill({ status: 404, body: "" });
    return route.continue();
  });

  await page.goto("/maintenance/demo/quality/qms/evidence");
  await expect(page.getByRole("heading", { name: "Evidence browser" })).toBeVisible();
  expect(bulkFindingRequests).toBe(1);
  expect(bulkAttachmentRequests).toBe(1);
  expect(legacyFindingRequests).toBe(0);
  expect(legacyAttachmentRequests).toBe(0);
});

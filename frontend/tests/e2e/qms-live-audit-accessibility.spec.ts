import { expect, test, type Route } from "@playwright/test";

const FINDING_ID = "11111111-1111-4111-8111-111111111111";

async function respond(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function session() {
  return {
    participant: {
      display_name: "Auditee Representative",
      organisation: "Example AMO",
      participant_type: "AUDITEE_GUEST",
      role: "AUDITEE",
      expires_at: "2026-08-20T18:00:00Z",
    },
    permissions: ["audit:read_summary", "audit:read_progress", "audit:read_released_findings", "audit:acknowledge"],
    audit: {
      id: "33333333-3333-4333-8333-333333333333",
      audit_ref: "QAR-MO-26-021",
      title: "Quality system audit",
      scope: "Quality management system and controlled processes.",
      criteria: "Approved QMS manual and applicable regulatory requirements.",
      planned_start: "2026-08-19T05:00:00Z",
      planned_end: "2026-08-19T13:00:00Z",
      actual_start: "2026-08-19T05:03:00Z",
      actual_end: null,
    },
    progress: { total: 48, completed: 21, percent: 44 },
    released_findings: [{
      id: FINDING_ID,
      finding_ref: "QAR-MO-26-021-F-001",
      finding_type: "NON_CONFORMITY",
      severity: "MAJOR",
      level: "LEVEL_2",
      requirement_ref: "QMSM 4.2.3",
      description: "An obsolete controlled procedure revision was available at a sampled point of use.",
      objective_evidence: null,
      released_evidence_refs: [],
      acknowledged_at: null,
    }],
    document_requests: [],
    issued_report_available: false,
  };
}

test.beforeEach(async ({ page }) => {
  let model = session();
  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/exchange") && request.method() === "POST") return respond(route, model);
    if (path.endsWith("/session") && request.method() === "GET") return respond(route, model);
    if (path.endsWith(`/findings/${FINDING_ID}/acknowledge`) && request.method() === "POST") {
      model = {
        ...model,
        released_findings: model.released_findings.map((item) => ({ ...item, acknowledged_at: "2026-08-19T09:30:00Z" })),
      };
      return respond(route, { finding_id: FINDING_ID, acknowledged_at: "2026-08-19T09:30:00Z" });
    }
    return respond(route, { detail: "Not configured in accessibility fixture." }, 404);
  });
});

test("auditee live view remains usable at phone width with reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const startedAt = Date.now();
  await page.goto("/qms/audit-access/accessibility-test-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /QAR-MO-26-021 · Quality system audit/i })).toBeVisible();
  const firstUsableMs = Date.now() - startedAt;
  expect(firstUsableMs).toBeLessThan(5_000);

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  }));
  expect(dimensions.reducedMotion).toBe(true);
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
});

test("released finding acknowledgement is keyboard operable and announces its result", async ({ page }) => {
  await page.goto("/qms/audit-access/keyboard-test-token", { waitUntil: "domcontentloaded" });
  const acknowledge = page.getByRole("button", { name: "Acknowledge finding" });
  await expect(acknowledge).toBeVisible();
  await acknowledge.focus();
  await expect(acknowledge).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Acknowledged/)).toBeVisible();
});

import { expect, test, type Route } from "@playwright/test";

const FINDING_ID = "11111111-1111-4111-8111-111111111111";
const WIDTHS = [360, 390, 430, 768, 1024, 1280, 1440] as const;
const LONG_REF = "QAR-MO-26-021-EXTRA-LONG-REFERENCE-WITHOUT-LOSS-OF-IDENTITY";
const LONG_FINDING = "A deliberately long released finding description verifies that the auditee workspace wraps operational text, preserves actionable controls, and does not force a horizontally scrolling desktop table onto phone, tablet, foldable, or desktop layouts.";

async function respond(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function session() {
  return {
    participant: {
      display_name: "Auditee Representative With A Long Display Name",
      organisation: "Example Aviation Maintenance Organisation With Long Branding",
      participant_type: "AUDITEE_GUEST",
      role: "AUDITEE",
      expires_at: "2026-08-20T18:00:00Z",
    },
    permissions: ["audit:read_summary", "audit:read_progress", "audit:read_released_findings", "audit:acknowledge"],
    audit: {
      id: "33333333-3333-4333-8333-333333333333",
      audit_ref: LONG_REF,
      title: "Quality system audit with deliberately long responsive acceptance content",
      scope: "Quality management system and controlled processes across a deliberately long operational scope that must wrap safely on small displays.",
      criteria: "Approved QMS manual, applicable regulatory requirements, controlled procedures and the frozen audit checklist revision.",
      planned_start: "2026-08-19T05:00:00Z",
      planned_end: "2026-08-19T13:00:00Z",
      actual_start: "2026-08-19T05:03:00Z",
      actual_end: null,
    },
    progress: { total: 48, completed: 21, percent: 44 },
    released_findings: [{
      id: FINDING_ID,
      finding_ref: `${LONG_REF}-F-001`,
      finding_type: "NON_CONFORMITY",
      severity: "MAJOR",
      level: "LEVEL_2",
      requirement_ref: "QMSM 4.2.3 / CONTROLLED-DOCUMENT-LONG-REFERENCE",
      description: LONG_FINDING,
      objective_evidence: "A long objective-evidence statement remains wrapped and readable without exposing internal auditor notes or creating unintended horizontal overflow.",
      released_evidence_refs: [],
      acknowledged_at: null,
    }],
    document_requests: [],
    issued_report_available: false,
  };
}

async function installSessionFixture(page: import("@playwright/test").Page, mode: "ok" | "expired" | "revoked" = "ok") {
  let model = session();
  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/passkey/status") && request.method() === "POST") {
      return respond(route, { detail: "Passkey assurance is only available to an assigned external auditor identity." }, 403);
    }
    if (path.endsWith("/exchange") && request.method() === "POST") {
      if (mode === "expired") return respond(route, { detail: "Audit access grant has expired." }, 401);
      if (mode === "revoked") return respond(route, { detail: "Audit access grant is revoked." }, 403);
      return respond(route, model);
    }
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
}

for (const width of WIDTHS) {
  test(`auditee workspace has no unintended horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await installSessionFixture(page);
    const startedAt = Date.now();
    await page.goto(`/qms/audit-access/responsive-${width}-token`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: new RegExp(LONG_REF) })).toBeVisible();
    await expect(page.getByText(LONG_FINDING)).toBeVisible();
    expect(Date.now() - startedAt).toBeLessThan(5_000);

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    }));
    expect(dimensions.reducedMotion).toBe(true);
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
    expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport + 1);

    const acknowledge = page.getByRole("button", { name: "Acknowledge finding" });
    const box = await acknowledge.boundingBox();
    expect(box).not.toBeNull();
    if (width <= 430 && box) {
      expect(box.height).toBeGreaterThanOrEqual(40);
      expect(box.width).toBeGreaterThanOrEqual(40);
    }
  });
}

test("released finding acknowledgement is keyboard operable, visibly focused and announces its result", async ({ page }) => {
  await installSessionFixture(page);
  await page.goto("/qms/audit-access/keyboard-test-token", { waitUntil: "domcontentloaded" });
  const acknowledge = page.getByRole("button", { name: "Acknowledge finding" });
  await acknowledge.focus();
  await expect(acknowledge).toBeFocused();
  const focusStyle = await acknowledge.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow };
  });
  expect(focusStyle.outlineStyle !== "none" || focusStyle.outlineWidth !== "0px" || focusStyle.boxShadow !== "none").toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Acknowledged/)).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Finding receipt recorded/i);
});

test("critical public workspace exposes semantic heading, main content, accessible controls and non-color status", async ({ page }) => {
  await installSessionFixture(page);
  await page.goto("/qms/audit-access/semantics-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(LONG_REF);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Acknowledge finding" })).toBeVisible();
  await expect(page.getByText(/MAJOR/i)).toBeVisible();
  await expect(page.getByText(/Released findings/i)).toBeVisible();
});

test("expired access fails closed with an actionable public error and no audit projection", async ({ page }) => {
  await installSessionFixture(page, "expired");
  await page.goto("/qms/audit-access/expired-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("alert")).toContainText(/expired/i);
  await expect(page.getByText(LONG_FINDING)).toHaveCount(0);
});

test("revoked access fails closed with an actionable public error and no audit projection", async ({ page }) => {
  await installSessionFixture(page, "revoked");
  await page.goto("/qms/audit-access/revoked-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("alert")).toContainText(/revoked/i);
  await expect(page.getByText(LONG_FINDING)).toHaveCount(0);
});

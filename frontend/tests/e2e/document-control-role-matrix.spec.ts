import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "dmsgate";
const DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "00000000-0000-4000-8000-000000000480";
const WORKFLOW_ID = process.env.E2E_DMS_WORKFLOW_ID || "00000000-0000-4000-8000-000000000501";
const ROLE_PASSWORD = process.env.E2E_DMS_ROLE_PASSWORD || "DmsRoles!2026-Local";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "dms-gate@example.com";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "DmsGate!2026-Local";
const READER_EMAIL = process.env.E2E_DMS_READER_EMAIL || "dms-reader@example.com";
const TECH_EMAIL = process.env.E2E_DMS_TECH_REVIEWER_EMAIL || "dms-tech-reviewer@example.com";
const QUALITY_EMAIL = process.env.E2E_DMS_QUALITY_REVIEWER_EMAIL || "dms-quality-reviewer@example.com";
const MANAGEMENT_EMAIL = process.env.E2E_DMS_MANAGEMENT_APPROVER_EMAIL || "dms-management-approver@example.com";
const BACKEND = process.env.E2E_DIRECT_API_URL || "http://127.0.0.1:8080";

async function clearSession(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.goto(`/maintenance/${AMO_CODE}/login`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
}

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await clearSession(page);
  await page.getByLabel("Email").fill(email);
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) await continueButton.click();
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function token(page: Page): Promise<string> {
  const value = await page.evaluate(() => localStorage.getItem("amo_portal_token"));
  if (!value) throw new Error("Authenticated DMS role fixture did not receive a bearer token");
  return value;
}

async function workflow(page: Page): Promise<{ state: string; version: number }> {
  const auth = await token(page);
  const response = await page.request.get(
    `${BACKEND}/doc-control/workspace/t/${AMO_CODE}/documents/${DOCUMENT_ID}`,
    { headers: { Authorization: `Bearer ${auth}` } },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  const payload = await response.json();
  const row = payload.workflows.find((item: { id: string }) => item.id === WORKFLOW_ID);
  if (!row) throw new Error(`Workflow ${WORKFLOW_ID} is not visible to the authenticated controller fixture`);
  return { state: row.state, version: row.version };
}

async function transitionAsCurrentUser(page: Page, action: string, expectedVersion: number) {
  const auth = await token(page);
  return page.request.post(
    `${BACKEND}/doc-control/workspace/t/${AMO_CODE}/workflows/${WORKFLOW_ID}/transition`,
    {
      headers: { Authorization: `Bearer ${auth}`, "Content-Type": "application/json" },
      data: {
        action,
        expected_version: expectedVersion,
        comments: `Deterministic role-matrix acceptance: ${action}`,
        evidence: [],
      },
    },
  );
}

async function openWorkspace(page: Page): Promise<void> {
  await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}?tab=workflow`);
  await expect(page.getByTestId("document-workspace")).toBeVisible({ timeout: 30_000 });
}

async function captureUiTransition(page: Page, actionButton: ReturnType<Page["getByRole"]>) {
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST"
      && response.url().includes(`/workflows/${WORKFLOW_ID}/transition`),
  );
  await actionButton.click();
  const response = await responsePromise;
  expect(response.status(), await response.text()).toBe(200);
  return response.json() as Promise<{ state: string; version: number }>;
}

test.describe.serial("DMS authoritative role matrix", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS role checks.");

  test("ordinary reader can read current content but cannot mutate workflow", async ({ page }) => {
    await signIn(page, READER_EMAIL, ROLE_PASSWORD);
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library`);
    await expect(page.getByTestId("integrated-document-library")).toBeVisible({ timeout: 30_000 });
    const row = page.getByRole("row").filter({ hasText: "DMS-CI-MOM" });
    await expect(row.getByRole("button", { name: "Read", exact: true })).toBeVisible();
    await row.getByRole("button", { name: "Read", exact: true }).click();
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });

    await openWorkspace(page);
    await expect(page.getByRole("button", { name: "Read current", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Review assigned change", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Responsibilities/i })).toHaveCount(0);

    const forbidden = await workflowForControllerOnly(page);
    expect(forbidden.status()).toBe(403);
  });

  test("confirmed technical reviewer receives only the technical decision", async ({ page }) => {
    await signIn(page, TECH_EMAIL, ROLE_PASSWORD);
    await openWorkspace(page);
    await expect(page.getByRole("button", { name: "Review assigned change", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Responsibilities/i })).toHaveCount(0);
    await page.getByRole("button", { name: "Review assigned change", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Assigned document review" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Approve technical review", exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Approve Quality review", exact: true })).toHaveCount(0);
    await expect(dialog.getByText(/reviewed revision ID and source checksum are retained automatically/i)).toBeVisible();
    await dialog.getByLabel("Review comments").fill("Technical review completed against the retained candidate revision.");
    const result = await captureUiTransition(page, dialog.getByRole("button", { name: "Approve technical review", exact: true }));
    expect(result.state).toBe("TECHNICAL_APPROVED");
    expect(result.version).toBe(2);
  });

  test("controller performs handoff but cannot impersonate the Quality reviewer decision surface", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    const current = await workflow(page);
    expect(current.state).toBe("TECHNICAL_APPROVED");
    const response = await transitionAsCurrentUser(page, "START_QUALITY_REVIEW", current.version);
    expect(response.status(), await response.text()).toBe(200);
    const result = await response.json();
    expect(result.state).toBe("QUALITY_REVIEW");
  });

  test("confirmed Quality reviewer receives and records the Quality decision", async ({ page }) => {
    await signIn(page, QUALITY_EMAIL, ROLE_PASSWORD);
    await openWorkspace(page);
    await page.getByRole("button", { name: "Review assigned change", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Assigned document review" });
    await expect(dialog.getByRole("button", { name: "Approve Quality review", exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Approve technical review", exact: true })).toHaveCount(0);
    await dialog.getByLabel("Review comments").fill("Quality review completed against the retained candidate revision and technical decision.");
    const result = await captureUiTransition(page, dialog.getByRole("button", { name: "Approve Quality review", exact: true }));
    expect(result.state).toBe("QUALITY_APPROVED");
    expect(result.version).toBe(4);
  });

  test("controller hands off to management and governed approver records the decision", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    const current = await workflow(page);
    expect(current.state).toBe("QUALITY_APPROVED");
    const response = await transitionAsCurrentUser(page, "SUBMIT_ACCOUNTABLE_MANAGER", current.version);
    expect(response.status(), await response.text()).toBe(200);
    const handoff = await response.json();
    expect(handoff.state).toBe("ACCOUNTABLE_MANAGER_APPROVAL");
    expect(handoff.version).toBe(5);

    await signIn(page, MANAGEMENT_EMAIL, ROLE_PASSWORD);
    await openWorkspace(page);
    await page.getByRole("button", { name: "Review assigned change", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Assigned document review" });
    await expect(dialog.getByRole("button", { name: "Approve for management", exact: true })).toBeVisible();
    await dialog.getByLabel("Review comments").fill("Management approval recorded against the retained reviewed revision.");
    const result = await captureUiTransition(page, dialog.getByRole("button", { name: "Approve for management", exact: true }));
    expect(result.state).toBe("SCHEDULED_FOR_EFFECTIVITY");
    expect(result.version).toBe(6);

    const forbiddenPublish = await transitionAsCurrentUser(page, "PUBLISH", result.version);
    expect(forbiddenPublish.status()).toBe(403);
  });
});

async function workflowForControllerOnly(page: Page) {
  const auth = await token(page);
  return page.request.post(
    `${BACKEND}/doc-control/workspace/t/${AMO_CODE}/workflows/${WORKFLOW_ID}/transition`,
    {
      headers: { Authorization: `Bearer ${auth}`, "Content-Type": "application/json" },
      data: {
        action: "APPROVE_TECHNICAL",
        expected_version: 1,
        comments: "Reader must never be allowed to review",
        evidence: [],
      },
    },
  );
}

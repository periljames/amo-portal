import fs from "node:fs";
import { expect, test, type Page, type Response } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(180_000);

type Fixture = {
  amo_slug: string;
  realtime_user_a_email: string;
  realtime_password: string;
  realtime_user_b_id: string;
  car_loop_id: string;
  car_loop_number: string;
  car_loop_invite_token: string;
};

function fixture(): Fixture {
  return JSON.parse(fs.readFileSync(process.env.E2E_QMS_LIVE_FIXTURE || "/tmp/qms-live-audit-real-e2e.json", "utf-8")) as Fixture;
}

function futureDate(days: number): string {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function watchServerFailures(page: Page, failures: string[]): void {
  page.on("response", (response: Response) => {
    const pathname = new URL(response.url()).pathname;
    if (response.status() >= 500 && (pathname.startsWith("/quality/") || pathname.startsWith("/api/"))) {
      failures.push(`${response.request().method()} ${pathname} -> ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
}

async function login(page: Page, data: Fixture): Promise<void> {
  await page.goto(`/maintenance/${data.amo_slug}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email", { exact: true }).fill(data.realtime_user_a_email);
  await page.getByLabel("Password").fill(data.realtime_password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
    page.getByRole("button", { name: "Sign In" }).click(),
  ]);
}

async function authenticatedPost(page: Page, path: string, payload: unknown): Promise<{ status: number; body: unknown }> {
  return page.evaluate(async ({ requestPath, body }) => {
    const token = window.localStorage.getItem("amo_portal_token");
    const response = await fetch(requestPath, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    let responseBody: unknown = null;
    try { responseBody = await response.json(); } catch { responseBody = await response.text(); }
    return { status: response.status, body: responseBody };
  }, { requestPath: path, body: payload });
}

async function submitResponsibleManagerResponse(page: Page, data: Fixture, suffix: string): Promise<void> {
  await page.goto(`/qms/car-access/${encodeURIComponent(data.car_loop_invite_token)}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".car-invite-kicker").getByText(data.car_loop_number, { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Your name").fill("Responsible Maintenance Manager");
  await page.getByLabel("Your email").fill("responsible.manager@example.com");
  await page.getByRole("button", { name: "Save responder details" }).click();

  await page.getByLabel("Immediate containment action", { exact: true }).fill(`The sampled local CAR index was isolated and reconciled to the governed register ${suffix}.`);
  await page.getByRole("button", { name: "Save containment and continue" }).click();
  await page.getByLabel("Root cause analysis", { exact: true }).fill(`The local workflow lacked an explicit effectiveness checkpoint and evidence-index ownership control ${suffix}.`);
  await page.getByRole("button", { name: "Save root cause and continue" }).click();
  await page.getByLabel("Corrective action plan", { exact: true }).fill(`Add governed RCA/CAPA milestones, assign accountable owners, index evidence and require effectiveness verification before closure ${suffix}.`);
  await page.getByLabel("Preventive action / systemic control", { exact: true }).fill(`Trend CAR effectiveness and overdue milestones in the Quality operating review ${suffix}.`);
  await page.getByLabel("Target closure date").fill(futureDate(28));
  await page.getByLabel("Due date").fill(futureDate(21));
  await page.getByRole("button", { name: "Save corrective action and continue" }).click();
  await page.getByLabel("Evidence reference").fill(`EVID-QMS-CAR-${suffix.replace(/\W+/g, "-").toUpperCase()}`);
  await page.locator(`input[id="evidence-${data.car_loop_invite_token}"]`).setInputFiles({
    name: `car-effectiveness-${suffix}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Governed corrective-action evidence ${suffix}.\n`, "utf-8"),
  });
  await expect(page.getByText(`car-effectiveness-${suffix}.txt`, { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Save evidence and continue" }).click();
  await page.getByLabel("I confirm this response and evidence are accurate for audit closeout.").check();
  await page.getByRole("button", { name: "Preview submission" }).click();
  await expect(page.getByRole("dialog", { name: "Preview CAR submission" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm and submit" }).click();
  await expect(page.getByText("Response submitted. The audit team can now review it.")).toBeVisible({ timeout: 30_000 });
}

test("real responsible-manager and Quality browsers prove CAR rejection/rework, deadline governance, effectiveness and final closure", async ({ browser }) => {
  const data = fixture();
  const publicFailures: string[] = [];
  const internalFailures: string[] = [];
  const publicContext = await browser.newContext();
  const internalContext = await browser.newContext();

  try {
    const publicPage = await publicContext.newPage();
    watchServerFailures(publicPage, publicFailures);
    await submitResponsibleManagerResponse(publicPage, data, "initial");

    const internalPage = await internalContext.newPage();
    watchServerFailures(internalPage, internalFailures);
    await login(internalPage, data);
    const controlPath = `/maintenance/${data.amo_slug}/quality/cars?control=${encodeURIComponent(data.car_loop_id)}`;
    await internalPage.goto(controlPath, { waitUntil: "domcontentloaded" });
    await expect(internalPage.getByRole("heading", { name: new RegExp(data.car_loop_number) })).toBeVisible({ timeout: 30_000 });

    await internalPage.getByLabel("Accountable lead owner").selectOption(data.realtime_user_b_id);
    await internalPage.getByLabel("Controlled final due date").fill(futureDate(28));
    await internalPage.getByRole("button", { name: "Initialize control loop" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Staged CAR control initialized", { timeout: 30_000 });

    const rejected = await authenticatedPost(internalPage, `/quality/cars/${data.car_loop_id}/review`, {
      root_cause_status: "REJECTED",
      root_cause_review_note: "Return for rework: identify the missing management-control checkpoint and accountable evidence owner.",
      capa_status: "REJECTED",
      capa_review_note: "Return for rework: corrective action must include effectiveness verification and recurrence monitoring.",
    });
    expect(rejected.status).toBe(200);

    await submitResponsibleManagerResponse(publicPage, data, "rework");
    await internalPage.reload({ waitUntil: "domcontentloaded" });
    await expect(internalPage.getByText(/Responsible Maintenance Manager/)).toBeVisible({ timeout: 30_000 });
    await expect(internalPage.getByText(/effectiveness checkpoint and evidence-index ownership control rework/)).toBeVisible();

    await internalPage.getByLabel("Requested new date").fill(futureDate(35));
    await internalPage.getByLabel("Reason").fill("Implementation evidence requires an additional controlled observation cycle before effectiveness can be confirmed.");
    await internalPage.getByLabel("Impact statement").fill("Quality will retain weekly oversight; no unsafe condition is being accepted during the controlled extension.");
    await internalPage.getByRole("button", { name: "Request deadline change" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Deadline change submitted", { timeout: 30_000 });
    const deadlineSection = internalPage.getByRole("heading", { name: "Controlled deadline changes" }).locator("xpath=ancestor::section[1]");
    await deadlineSection.getByPlaceholder("Decision note").fill("Approved because the added observation cycle strengthens effectiveness evidence while weekly Quality oversight controls the risk.");
    await deadlineSection.getByRole("button", { name: "Approve" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Deadline change approved", { timeout: 30_000 });

    const dependencySection = internalPage.getByRole("heading", { name: "Dependencies & blockers" }).locator("xpath=ancestor::section[1]");
    await dependencySection.getByLabel("Dependency title").fill("Independent effectiveness observation");
    await dependencySection.getByLabel("Description").fill("A second Quality observer must verify the revised control after implementation.");
    await dependencySection.getByLabel("Risk").selectOption("HIGH");
    await dependencySection.getByLabel("Owner").selectOption(data.realtime_user_b_id);
    await dependencySection.getByLabel("Due date").fill(futureDate(24));
    await dependencySection.getByLabel("Mitigation").fill("Quality Manager tracks the observation as a closure blocker until objective evidence is recorded.");
    await dependencySection.getByLabel("Blocks CAR closure").check();
    await dependencySection.getByRole("button", { name: "Add dependency" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Dependency recorded", { timeout: 30_000 });
    const dependencyRow = dependencySection.getByRole("row", { name: /Independent effectiveness observation/ });
    await dependencyRow.getByRole("combobox").selectOption("RESOLVED");
    await expect(internalPage.getByRole("status")).toContainText("Dependency status updated", { timeout: 30_000 });

    const lifecycle = internalPage.getByRole("heading", { name: "Staged CAR lifecycle" }).locator("xpath=ancestor::section[1]");
    const stages = [
      "Root cause analysis submitted",
      "Corrective action plan approved",
      "Corrective actions implemented",
      "Closure evidence complete",
      "Effectiveness review complete",
    ];
    for (const [index, stage] of stages.entries()) {
      const row = lifecycle.getByRole("row", { name: new RegExp(stage) });
      await row.getByRole("combobox").last().selectOption("ACCEPTED");
      await row.getByPlaceholder("Evidence reference").fill(`car-evidence:stage-${index + 1}`);
      await row.getByPlaceholder("Control note").fill(`${stage} independently reviewed and accepted by Quality.`);
      await row.getByRole("button", { name: "Save" }).click();
      await expect(internalPage.getByRole("status")).toContainText(`${stage} updated`, { timeout: 30_000 });
    }

    const accepted = await authenticatedPost(internalPage, `/quality/cars/${data.car_loop_id}/review`, {
      root_cause_status: "ACCEPTED",
      root_cause_review_note: "RCA accepted after rework identified the management-control and evidence-ownership root cause.",
      capa_status: "ACCEPTED",
      capa_review_note: "CAPA accepted after implementation, evidence and effectiveness milestones were independently verified.",
    });
    expect(accepted.status).toBe(200);

    const governedClose = await authenticatedPost(internalPage, `/api/maintenance/${data.amo_slug}/quality/cars/${data.car_loop_id}/control-loop/close`, {
      evidence_ref: "car-evidence:stage-5",
      closure_reason: "Quality accepts closure after rejected-response rework, approved deadline governance, resolved dependency and completed effectiveness verification.",
    });
    expect(governedClose.status).toBe(200);

    await internalPage.reload({ waitUntil: "domcontentloaded" });
    await expect(internalPage.getByText("Closed", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
    await expect(internalPage.getByRole("heading", { name: "Control event timeline" })).toBeVisible();
    await expect(internalPage.getByText(/Control Loop Closed/i)).toBeVisible();

    await publicPage.reload({ waitUntil: "domcontentloaded" });
    await expect(publicPage.getByText("Closed", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(publicPage.getByText(/This CAR is closed/i)).toBeVisible();

    expect(publicFailures).toEqual([]);
    expect(internalFailures).toEqual([]);
  } finally {
    await Promise.allSettled([publicContext.close(), internalContext.close()]);
  }
});

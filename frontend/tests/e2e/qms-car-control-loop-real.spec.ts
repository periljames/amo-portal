import fs from "node:fs";
import { expect, test, type Page, type Response } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(180_000);

type Fixture = {
  amo_slug: string;
  realtime_user_a_email: string;
  realtime_password: string;
  realtime_user_b_id: string;
  realtime_user_a_id: string;
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
  await page.getByLabel("Password", { exact: true }).fill(data.realtime_password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
    page.getByRole("button", { name: "Sign In" }).click(),
  ]);
}

function structuredEditor(page: Page, label: string) {
  return page.getByLabel(`${label} structured editor`, { exact: true }).locator("textarea");
}

async function authenticatedRequest(
  page: Page, method: "GET" | "POST" | "PATCH" | "PUT", path: string, payload?: unknown,
): Promise<{ status: number; body: unknown }> {
  return page.evaluate(async ({ requestMethod, requestPath, body }) => {
    const token = window.localStorage.getItem("amo_portal_token");
    const response = await fetch(requestPath, {
      method: requestMethod,
      credentials: "include",
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    // A Fetch response body can only be consumed once. Preserve plain-text
    // server errors instead of replacing the original HTTP failure with a
    // second "body stream already read" exception.
    const rawBody = await response.text();
    let responseBody: unknown = rawBody;
    if (rawBody) {
      try { responseBody = JSON.parse(rawBody); } catch { /* Keep the diagnostic text. */ }
    } else {
      responseBody = null;
    }
    return { status: response.status, body: responseBody };
  }, { requestMethod: method, requestPath: path, body: payload });
}
async function authenticatedPost(page: Page, path: string, payload: unknown) {
  return authenticatedRequest(page, "POST", path, payload);
}

async function submitResponsibleManagerResponse(page: Page, data: Fixture, suffix: string): Promise<void> {
  await page.goto(`/qms/car-access/${encodeURIComponent(data.car_loop_invite_token)}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".car-invite-kicker").getByText(data.car_loop_number, { exact: true })).toBeVisible({ timeout: 30_000 });
  const responderName = page.getByLabel("Your name");
  if (await responderName.isVisible().catch(() => false)) {
    await responderName.fill("Responsible Maintenance Manager");
    await page.getByLabel("Your email").fill("responsible.manager@example.com");
    await page.getByRole("button", { name: "Save responder details" }).click();
  }

  const containmentEditor = structuredEditor(page, "Immediate containment action");
  if (await containmentEditor.isVisible().catch(() => false)) {
    await containmentEditor.fill(`The sampled local CAR index was isolated and reconciled to the governed register ${suffix}.`);
    await page.getByRole("button", { name: "Save containment and continue" }).click();
  }
  // The public CAR form is a governed stepper, not a long form: a prior
  // saved draft may leave a different completed step selected on reload.
  const rootCauseStep = page.getByRole("complementary", { name: "Corrective action response progress" })
    .getByRole("button", { name: /Root cause$/i });
  await expect(rootCauseStep).toBeEnabled({ timeout: 30_000 });
  await rootCauseStep.click();
  // Newly issued CARs must use the evidence-linked RCA workbench. Legacy
  // free-text fields exist only for CARs issued before the controlled rollout.
  const investigation = page.getByRole("region", { name: "Root cause investigation" });
  await expect(investigation.getByRole("heading", { name: "Root cause workbench" })).toBeVisible({ timeout: 30_000 });
  await investigation.getByLabel("Problem statement from this CAR").fill(
    `The CAR process failed to verify ownership and independent effectiveness evidence ${suffix}.`,
  );
  await investigation.getByLabel("Evidence classification").selectOption("FACT");
  await investigation.getByLabel("Why did the preceding condition occur?").fill(
    `The sampled CAR register omitted an effectiveness check ${suffix}.`,
  );
  await investigation.getByLabel("Evidence references (one record per line)").fill(`CAR-SAMPLE:${suffix}:register-observation`);
  await investigation.getByRole("button", { name: "Add cause / analysis entry" }).click();
  const causalStatement = `Missing effectiveness checkpoint and evidence-index ownership control ${suffix}`;
  await investigation.getByLabel("Caused by / preceding question").selectOption({
    label: `The sampled CAR register omitted an effectiveness check ${suffix}.`,
  });
  await investigation.getByLabel("Evidence classification").selectOption("CAUSAL_CONCLUSION");
  await investigation.getByLabel("Why did the preceding condition occur?").fill(causalStatement);
  await investigation.getByLabel("Evidence references (one record per line)").fill(`CAR-SAMPLE:${suffix}:governance-control-review`);
  await investigation.getByLabel("Evidence interpretation / why this cause is supported").fill(
    "Compared the controlled procedure, CAR register and the Quality review record.",
  );
  await investigation.getByRole("button", { name: "Add cause / analysis entry" }).click();
  await investigation.getByRole("checkbox", { name: new RegExp(causalStatement) }).check();
  await investigation.getByLabel("Final root cause explanation").fill(
    `The local workflow lacked an explicit effectiveness checkpoint and evidence-index ownership control ${suffix}.`,
  );
  await investigation.getByLabel("Evidence supporting the consolidated conclusion (one per line)").fill(
    `CAR-SAMPLE:${suffix}:governance-control-review`,
  );
  const effectiveness = investigation.getByRole("region", { name: "Proposed effectiveness verification" });
  await effectiveness.getByLabel("Expected result").fill(
    "Every sampled CAR has an accountable owner, independent effectiveness gate and complete evidence index.",
  );
  await effectiveness.getByLabel("Measurable success criterion").fill(
    "The reviewed CAR sample contains zero overdue unverified effectiveness milestones.",
  );
  await effectiveness.getByLabel("Verification method").fill(
    "Independent Quality reviewer checks the corrected register, milestones and documented evidence.",
  );
  await effectiveness.getByLabel("Observation period").fill("Current controlled CAR follow-up observation cycle");
  await effectiveness.getByLabel("Proposed independent review date").fill(futureDate(0));
  await effectiveness.getByLabel("Proposed supporting records (one per line)").fill(
    `CAR-SAMPLE:${suffix}:effectiveness-observation`,
  );
  await page.getByRole("button", { name: "Save root cause and continue" }).click();
  await expect(structuredEditor(page, "Corrective action plan")).toBeVisible({ timeout: 30_000 });
  await structuredEditor(page, "Corrective action plan").fill(`Add governed RCA/CAPA milestones, assign accountable owners, index evidence and require effectiveness verification before closure ${suffix}.`);
  await structuredEditor(page, "Preventive action / systemic control").fill(`Trend CAR effectiveness and overdue milestones in the Quality operating review ${suffix}.`);
  const actionSection = page.getByRole("region", { name: "Individual corrective actions" });
  await expect(actionSection).toBeVisible();
  const revisionButton = actionSection.getByRole("button", { name: "Revise proposed action" }).first();
  if (await revisionButton.isVisible().catch(() => false)) await revisionButton.click();
  const actionName = `Implement a governed effectiveness checkpoint and assign the evidence-index owner ${suffix}`;
  await actionSection.getByLabel("What specifically changes?").fill(actionName);
  await actionSection.getByLabel("Responsible person").fill("Responsible Maintenance Manager");
  await actionSection.getByLabel("Target date").fill(futureDate(14));
  await actionSection.getByLabel("Supporting evidence references (one per line)").fill(
    `CAR-PROCEDURE:${suffix}:implementation-plan`,
  );
  await actionSection.getByRole("checkbox", { name: new RegExp(causalStatement) }).check();
  await actionSection.getByRole("button", {
    name: (await revisionButton.isVisible().catch(() => false)) ? "Save revised action" : "Add corrective action",
  }).click();
  await expect(actionSection.getByRole("status")).toContainText(/Corrective action recorded|Proposed action revision retained/, { timeout: 30_000 });
  // The issued CAR can lock its authoritative deadlines. Public respondents must
  // use the controlled deadline-change request rather than silently rewriting them.
  for (const [label, offset] of [["Target closure date", 28], ["Due date", 21]] as const) {
    const field = page.getByLabel(label, { exact: true });
    if (await field.isEnabled()) await field.fill(futureDate(offset));
    else await expect(field).toBeDisabled();
  }
  await page.getByRole("button", { name: "Save corrective action and continue" }).click();
  await structuredEditor(page, "Evidence reference").fill(`EVID-QMS-CAR-${suffix.replace(/\W+/g, "-").toUpperCase()}`);
  await page.locator(`input[id="evidence-${data.car_loop_invite_token}"]`).setInputFiles({
    name: `car-effectiveness-${suffix}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Governed corrective-action evidence ${suffix}.\n`, "utf-8"),
  });
  await expect(page.getByText(`car-effectiveness-${suffix}.txt`, { exact: true }).first()).toBeVisible({ timeout: 30_000 });
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
  const internalContext = await browser.newContext({ timezoneId: "Africa/Nairobi" });

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
    await expect(internalPage.getByRole("status").filter({ hasText: "Staged CAR control initialized" })).toContainText("Staged CAR control initialized", { timeout: 30_000 });

    const carEndpoint = `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/cars/${data.car_loop_id}`;
    // Both public legacy and tenant-prefixed PATCH aliases must reject an
    // attempted CLOSED transition before independent implementation review.
    for (const legacyPath of [
      `/quality/cars/${data.car_loop_id}`,
      carEndpoint,
    ]) {
      const attemptedClose = await authenticatedRequest(internalPage, "PATCH", legacyPath, {
        status: "CLOSED",
        evidence_ref: "CAR-NEGATIVE:unverified-action",
      });
      expect(attemptedClose.status, `PATCH ${legacyPath}: ${JSON.stringify(attemptedClose.body)}`).toBe(409);
      expect(JSON.stringify(attemptedClose.body)).toMatch(/control-loop\/close|governed CAR/i);
    }
    for (const forbiddenEdit of [
      { due_date: futureDate(80) },
      { target_closure_date: futureDate(80) },
      { closed_at: new Date().toISOString() },
    ]) {
      const response = await authenticatedRequest(internalPage, "PATCH", carEndpoint, forbiddenEdit);
      expect(response.status, JSON.stringify(response.body)).toBe(409);
    }
    const stillActive = await authenticatedRequest(internalPage, "GET", `${carEndpoint}/control-loop`);
    expect(stillActive.status, JSON.stringify(stillActive.body)).toBe(200);
    expect((stillActive.body as { car: { status: string } }).car.status).not.toBe("CLOSED");

    // A non-UTC Quality browser must display the local wall time and preserve
    // the EXACT original expiry instant when Save expiry is clicked unchanged.
    const futureExpiry = new Date(Date.now() + 45 * 86_400_000);
    futureExpiry.setUTCHours(12, 34, 0, 0);
    const expiresAt = futureExpiry.toISOString();
    const initialAccess = await authenticatedRequest(internalPage, "PUT", `${carEndpoint}/invite-access`, {
      expires_at: expiresAt,
      revoke: false,
      reason: "Restrict invited respondent access after the governed follow-up period.",
    });
    expect(initialAccess.status, JSON.stringify(initialAccess.body)).toBe(200);
    await internalPage.reload({ waitUntil: "domcontentloaded" });
    const invitationSecurity = internalPage.getByRole("region", { name: "CAR invitation security" });
    const expiryInput = invitationSecurity.getByLabel("Optional expiry (local date and time)");
    await expect(expiryInput).toBeVisible({ timeout: 30_000 });
    const localExpiry = await internalPage.evaluate(iso => {
      const instant = new Date(iso);
      const pad = (n: number) => String(n).padStart(2, "0");
      return `${instant.getFullYear()}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}T${pad(instant.getHours())}:${pad(instant.getMinutes())}`;
    }, expiresAt);
    await expect(expiryInput).toHaveValue(localExpiry);
    await invitationSecurity.getByLabel("Mandatory controlled change reason").fill(
      "Reviewed the invitation expiry; retain the approved access deadline without altering it.",
    );
    await invitationSecurity.getByRole("button", { name: "Save expiry" }).click();
    await expect(invitationSecurity.getByRole("status")).toContainText("controlled invitation expiry has been updated", { timeout: 30_000 });
    const savedAccess = await authenticatedRequest(internalPage, "GET", `${carEndpoint}/invite-access`);
    expect(savedAccess.status, JSON.stringify(savedAccess.body)).toBe(200);
    expect(new Date((savedAccess.body as { expires_at: string }).expires_at).toISOString()).toBe(expiresAt);

    const rejected = await authenticatedPost(internalPage, `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/cars/${data.car_loop_id}/review`, {
      root_cause_status: "REJECTED",
      root_cause_review_note: "Return for rework: identify the missing management-control checkpoint and accountable evidence owner.",
      capa_status: "REJECTED",
      capa_review_note: "Return for rework: corrective action must include effectiveness verification and recurrence monitoring.",
    });
    expect(rejected.status).toBe(200);

    await submitResponsibleManagerResponse(publicPage, data, "rework");
    // Verify the new submission is actually committed and reviewable, not
    // merely reported as successful in the invited browser.
    const revisedResponses = await authenticatedRequest(
      internalPage, "GET",
      `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/cars/${data.car_loop_id}/responses?mark_open=false`,
    );
    expect(revisedResponses.status, JSON.stringify(revisedResponses.body)).toBe(200);
    const responseRows = revisedResponses.body as Array<{
      root_cause: string; is_latest: boolean; submitted_by_name: string;
    }>;
    expect(responseRows).toHaveLength(1);
    expect(responseRows[0].root_cause).toContain("effectiveness checkpoint and evidence-index ownership control rework");
    expect(responseRows[0].is_latest).toBe(true);
    await internalPage.reload({ waitUntil: "domcontentloaded" });
    const responsePanel = internalPage.getByRole("region", { name: "Corrective action response" });
    // The Quality page may hydrate asynchronously; this check must prove the
    // actual revised response, not match a stale name elsewhere on the page.
    await expect(responsePanel).toBeVisible({ timeout: 30_000 });
    await expect(responsePanel.getByText(/Responsible Maintenance Manager/)).toBeVisible({ timeout: 30_000 });
    await expect(responsePanel.getByText(/effectiveness checkpoint and evidence-index ownership control rework/)).toBeVisible({ timeout: 30_000 });

    const deadlineSection = internalPage.getByRole("heading", { name: "Controlled deadline changes" }).locator("xpath=ancestor::section[1]");
    await deadlineSection.getByLabel("Requested new date", { exact: true }).fill(futureDate(35));
    await deadlineSection.getByLabel("Reason", { exact: true }).fill("Implementation evidence requires an additional controlled observation cycle before effectiveness can be confirmed.");
    await deadlineSection.getByLabel("Impact statement", { exact: true }).fill("Quality will retain weekly oversight; no unsafe condition is being accepted during the controlled extension.");
    await deadlineSection.getByRole("button", { name: "Request deadline change" }).click();
    await expect(internalPage.getByRole("status").filter({ hasText: "Deadline change submitted" })).toContainText("Deadline change submitted", { timeout: 30_000 });
    await deadlineSection.getByPlaceholder("Decision note").fill("Approved because the added observation cycle strengthens effectiveness evidence while weekly Quality oversight controls the risk.");
    await deadlineSection.getByRole("button", { name: "Approve" }).click();
    await expect(internalPage.getByRole("status").filter({ hasText: "Deadline change approved" })).toContainText("Deadline change approved", { timeout: 30_000 });

    const dependencySection = internalPage.getByRole("heading", { name: "Dependencies & blockers" }).locator("xpath=ancestor::section[1]");
    await dependencySection.getByLabel("Dependency title").fill("Independent effectiveness observation");
    await dependencySection.getByLabel("Description").fill("A second Quality observer must verify the revised control after implementation.");
    await dependencySection.getByLabel("Risk").selectOption("HIGH");
    await dependencySection.getByLabel("Owner").selectOption(data.realtime_user_b_id);
    await dependencySection.getByLabel("Due date").fill(futureDate(24));
    await dependencySection.getByLabel("Mitigation").fill("Quality Manager tracks the observation as a closure blocker until objective evidence is recorded.");
    await dependencySection.getByLabel("Blocks CAR closure").check();
    await dependencySection.getByRole("button", { name: "Add dependency" }).click();
    await expect(internalPage.getByRole("status").filter({ hasText: "Dependency recorded" })).toContainText("Dependency recorded", { timeout: 30_000 });
    const dependencyRow = dependencySection.getByRole("row", { name: /Independent effectiveness observation/ });
    await dependencyRow.getByRole("combobox").selectOption("RESOLVED");
    await expect(internalPage.getByRole("status").filter({ hasText: "Dependency status updated" })).toContainText("Dependency status updated", { timeout: 30_000 });

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
      await expect(internalPage.getByRole("status").filter({ hasText: `${stage} updated` })).toContainText(`${stage} updated`, { timeout: 30_000 });
    }

    const accepted = await authenticatedPost(internalPage, `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/cars/${data.car_loop_id}/review`, {
      root_cause_status: "ACCEPTED",
      root_cause_review_note: "RCA accepted after rework identified the management-control and evidence-ownership root cause.",
      capa_status: "ACCEPTED",
      capa_review_note: "CAPA accepted after implementation, evidence and effectiveness milestones were independently verified.",
    });
    expect(accepted.status).toBe(200);

    const apiCarPath = `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/cars/${data.car_loop_id}`;
    const investigationState = await authenticatedRequest(internalPage, "GET", `${apiCarPath}/investigation`);
    expect(investigationState.status, JSON.stringify(investigationState.body)).toBe(200);
    const record = investigationState.body as {
      submitted_revision: number | null;
      actions: Array<{ id: string; kind: string; state: string; description: string }>;
      submitted_snapshot: { investigation: { supported_cause_ids: string[] } } | null;
    };
    expect(record.submitted_revision).toBeGreaterThan(0);
    expect(record.submitted_snapshot?.investigation.supported_cause_ids.length).toBeGreaterThan(0);
    const corrective = record.actions.find(action => action.kind === "CORRECTIVE");
    expect(corrective, "A separate, accountable CAR action must persist with the submitted RCA").toBeDefined();
    expect(corrective!.state).toBe("PROPOSED");
    expect(corrective!.description).toContain("rework");

    // Closing with an unapproved or unverified action must fail even when
    // legacy control-loop milestones have otherwise been accepted.
    const premature = await authenticatedPost(internalPage, `${apiCarPath}/control-loop/close`, {
      evidence_ref: "car-evidence:stage-5",
      closure_reason: "Negative control: reject closure without independent implementation verification.",
    });
    expect(premature.status).toBe(409);
    expect(JSON.stringify(premature.body)).toMatch(/independently verified|Implementation must be independently verified/i);

    const approvedAction = await authenticatedRequest(internalPage, "PATCH",
      `${apiCarPath}/corrective-actions/${corrective!.id}/review`, {
        state: "ACCEPTED",
        reason: "The proposed corrective action addresses the verified RCA and has a responsible owner and deadline.",
      });
    expect(approvedAction.status, JSON.stringify(approvedAction.body)).toBe(200);
    expect((approvedAction.body as { state: string }).state).toBe("ACCEPTED");

    // The actual respondent browser, not a privileged backend shortcut,
    // records implementation evidence after independent Quality approval.
    await publicPage.reload({ waitUntil: "domcontentloaded" });
    const implementation = publicPage.getByRole("region", { name: "Individual corrective actions" });
    await expect(implementation.getByRole("button", { name: "Record progress" })).toBeVisible({ timeout: 30_000 });
    await implementation.getByRole("button", { name: "Record progress" }).click();
    await implementation.getByLabel("Completion declaration").fill(
      "The controlled CAR register now records independent effectiveness checkpoints and an accountable evidence owner.",
    );
    await implementation.getByLabel("Evidence references, one per line").fill(
      "CAR-SAMPLE:rework:effectiveness-observation",
    );
    await implementation.getByRole("button", { name: "Save in progress" }).click();
    await expect(implementation.getByText("IN PROGRESS")).toBeVisible({ timeout: 30_000 });
    await implementation.getByRole("button", { name: "Record progress" }).click();
    await implementation.getByRole("button", { name: "Submit implementation evidence" }).click();
    // Prove the actual action state, not the unrelated success-notification text.
    await expect(implementation.getByRole("cell", { name: /^SUBMITTED\b/ })).toBeVisible({ timeout: 30_000 });
    const submittedActionRead = await authenticatedRequest(internalPage, "GET", `${apiCarPath}/investigation`);
    expect(submittedActionRead.status, JSON.stringify(submittedActionRead.body)).toBe(200);
    const submittedAction = (submittedActionRead.body as { actions: Array<{ id: string; state: string; evidence_references: string[] }> })
      .actions.find(action => action.id === corrective!.id);
    expect(submittedAction?.state).toBe("SUBMITTED");
    expect(submittedAction?.evidence_references).toContain("CAR-SAMPLE:rework:effectiveness-observation");

    const verifiedAction = await authenticatedRequest(internalPage, "PATCH",
      `${apiCarPath}/corrective-actions/${corrective!.id}/review`, {
        state: "VERIFIED",
        reason: "Independent Quality review confirms that the control and indexed implementation evidence were recorded.",
      });
    expect(verifiedAction.status, JSON.stringify(verifiedAction.body)).toBe(200);
    expect((verifiedAction.body as { state: string }).state).toBe("VERIFIED");

    const adopted = await authenticatedPost(internalPage, `${apiCarPath}/effectiveness-plan`, {
      responsible_reviewer_user_id: data.realtime_user_a_id,
      reason: "Independent effectiveness review follows the respondent's measured and evidenced proposal.",
    });
    expect(adopted.status, JSON.stringify(adopted.body)).toBe(201);
    const plan = adopted.body as { case_id: string; plan_id: string };
    expect(plan.case_id).toBeTruthy();
    expect(plan.plan_id).toBeTruthy();

    const conclusion = await authenticatedPost(internalPage,
      `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/assurance-cases/${plan.case_id}/effectiveness-plans/${plan.plan_id}/conclusion`, {
        conclusion: "EFFECTIVE",
        rationale: "Independent check confirms that the sampled CAR register has the effectiveness checkpoint and evidence owner.",
        evidence_references: [{ source_type: "CAR", source_id: data.car_loop_id, reference: "CAR-SAMPLE:rework:effectiveness-observation" }],
      });
    expect(conclusion.status, JSON.stringify(conclusion.body)).toBe(200);
    expect((conclusion.body as { effectiveness_plan: { status: string; conclusion: string } }).effectiveness_plan)
      .toMatchObject({ status: "CONCLUDED", conclusion: "EFFECTIVE" });

    const governedClose = await authenticatedPost(internalPage, `${apiCarPath}/control-loop/close`, {
      evidence_ref: "car-evidence:stage-5",
      closure_reason: "Quality accepts closure after rejected-response rework, controlled extension, independent action verification and concluded effectiveness.",
    });
    expect(governedClose.status, JSON.stringify(governedClose.body)).toBe(200);
    const closedControl = await authenticatedRequest(internalPage, "GET", `${apiCarPath}/control-loop`);
    expect(closedControl.status, JSON.stringify(closedControl.body)).toBe(200);
    expect((closedControl.body as { car: { status: string }; health: { state: string } }).car.status).toBe("CLOSED");
    expect((closedControl.body as { car: { status: string }; health: { state: string } }).health.state).toBe("CLOSED");

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

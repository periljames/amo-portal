import fs from "node:fs";
import { expect, test, type Page, type Response } from "@playwright/test";

// Explicit checkpoint images verify the real UI without continuously recording
// animated pages on the same low-memory host that runs the database VM.
test.use({ trace: "off", screenshot: "only-on-failure", video: "off" });
test.setTimeout(Number(process.env.E2E_CAR_ACCEPTANCE_TIMEOUT_MS || 180_000));

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
  const data=JSON.parse(fs.readFileSync(process.env.E2E_QMS_LIVE_FIXTURE || "/tmp/qms-live-audit-real-e2e.json", "utf-8")) as Fixture;
  const password=process.env.E2E_QMS_AUDITOR_PASSWORD || data.realtime_password;
  if(!password) throw new Error("Provide E2E_QMS_AUDITOR_PASSWORD for the requested auditor; personal credentials are not retained in the fixture.");
  return {...data,realtime_password:password};
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
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 60_000, waitUntil:"domcontentloaded" }),
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
    const token = window.sessionStorage.getItem("amo_portal_token") || window.localStorage.getItem("amo_portal_token");
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

async function reviewThroughUi(page: Page, data: Fixture, decision: "ACCEPTED"|"REJECTED", rootReason: string, actionReason: string) {
  console.log(`CAR acceptance: reviewing RCA/CAPA ${decision} through the auditor dialog`);
  await page.goto(`/maintenance/${data.amo_slug}/quality/cars?carId=${data.car_loop_id}`);
  await page.getByRole("button", {name:"Review response",exact:true}).click({timeout:30000});
  const dialog=page.getByRole("dialog",{name:"Review corrective action response"});
  await dialog.getByLabel("Root cause decision",{exact:true}).selectOption(decision);
  await dialog.getByLabel("Corrective action decision",{exact:true}).selectOption(decision);
  await dialog.getByLabel("Root cause review note",{exact:true}).fill(rootReason);
  await dialog.getByLabel("Corrective action review note",{exact:true}).fill(actionReason);
  await dialog.getByLabel("Message to auditee",{exact:true}).fill(`Quality ${decision.toLowerCase()}: review the retained reasons and next action.`);
  await page.screenshot({path:`test-results/car-feedback-review-${decision.toLowerCase()}.png`,fullPage:true});
  const response=page.waitForResponse(r=>r.url().endsWith(`/cars/${data.car_loop_id}/review`)&&r.request().method()==="POST");
  await dialog.getByRole("button",{name:"Record review decision",exact:true}).click();
  const result=await response;
  expect(result.status(),await result.text()).toBe(200);
  await expect(dialog).toHaveCount(0);
  return {status:result.status(),body:await result.json()};
}

async function reviewIndividualActionUi(page:Page,data:Fixture,description:string,state:"ACCEPTED"|"REJECTED"|"VERIFIED",reason:string) {
  console.log(`CAR acceptance: individual action review ${state} through the auditor view`);
  await page.goto(`/maintenance/${data.amo_slug}/quality/cars?carId=${data.car_loop_id}`);
  const region=page.getByRole("region",{name:"Structured CAR investigation and Quality action review"});
  const row=region.getByRole("row").filter({hasText:description});
  await row.getByLabel("Independent Quality rationale").fill(reason,{timeout:30000});
  const response=page.waitForResponse(r=>r.url().includes("/corrective-actions/")&&r.url().endsWith("/review")&&r.request().method()==="PATCH");
  await row.getByRole("button",{name:state==="ACCEPTED"?"Approve proposed action":state==="VERIFIED"?"Verify implementation":"Return for rework",exact:true}).click();
  const result=await response;
  expect(result.status(),await result.text()).toBe(200);
  return {status:result.status(),body:await result.json()};
}

async function submitResponsibleManagerResponse(page: Page, data: Fixture, suffix: string, whileEditing?:()=>Promise<void>): Promise<void> {
  console.log(`CAR acceptance: ${suffix} public response opened`);
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
  console.log(`CAR acceptance: ${suffix} evidence-linked investigation visible`);
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
  if(whileEditing){
    await whileEditing();
    await expect(investigation.getByLabel("Final root cause explanation")).toHaveValue(`The local workflow lacked an explicit effectiveness checkpoint and evidence-index ownership control ${suffix}.`);
  }
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
  console.log(`CAR acceptance: ${suffix} RCA saved; preparing action plan`);
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
  const actionSave=actionSection.getByRole("button", {
    name: (await revisionButton.isVisible().catch(() => false)) ? "Save revised action" : "Add corrective action",
  });
  const actionRoute="**/quality/cars/invite/*/corrective-actions";
  let dropActionAcknowledgement=suffix==="initial";
  if(dropActionAcknowledgement)await page.route(actionRoute,async route=>{
    if(route.request().method()==="POST"&&dropActionAcknowledgement){dropActionAcknowledgement=false;const committed=await route.fetch();expect(committed.status()).toBe(201);await route.abort("failed");}
    else await route.continue();
  });
  await actionSave.click();
  if(suffix==="initial"){
    await expect(actionSection.getByRole("alert")).toBeVisible({timeout:30000});
    await expect(actionSection.getByLabel("What specifically changes?")).toHaveValue(actionName);
    await actionSave.click();await page.unroute(actionRoute);
  }
  await expect(actionSection.getByRole("status")).toContainText(/Corrective action recorded|Proposed action revision retained/, { timeout: 30_000 });
  // The issued CAR can lock its authoritative deadlines. Public respondents must
  // use the controlled deadline-change request rather than silently rewriting them.
  for (const [label, offset] of [["Target closure date", 28], ["Due date", 21]] as const) {
    const field = page.getByLabel(label, { exact: true });
    if (await field.isEnabled()) await field.fill(futureDate(offset));
    else await expect(field).toBeDisabled();
  }
  await page.getByRole("button", { name: "Save corrective action and continue" }).click();
  console.log(`CAR acceptance: ${suffix} CAP saved; uploading evidence`);
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
  // Live feedback can replace a transient success notice. Assert the durable
  // submitted state, not the timing of a toast relative to background refresh.
  await expect(page.getByText("Response locked — no further submissions or changes are permitted.")).toBeVisible({ timeout: 30_000 });
  console.log(`CAR acceptance: ${suffix} response submitted`);
  await page.screenshot({path:`test-results/car-feedback-${suffix}-submitted.png`});
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

    const initialGuest = await publicPage.request.get(
      `/quality/cars/invite/${encodeURIComponent(data.car_loop_invite_token)}`,
    );
    expect(initialGuest.status()).toBe(200);
    expect(initialGuest.headers()["cache-control"]).toContain("no-store");
    const guestBody = await initialGuest.json() as { related_cars: unknown[] };
    expect(guestBody.related_cars, "A bearer capability must not enumerate sibling CAR invitations").toEqual([]);
    const alteredToken = `${data.car_loop_invite_token}x`;
    const invalidGuest = await publicPage.request.get(
      `/quality/cars/invite/${encodeURIComponent(alteredToken)}`,
    );
    expect(invalidGuest.status()).toBe(404);

    if(process.env.E2E_CAR_RESUME_SUBMITTED === "1") {
      expect((guestBody as {submitted_at?:string}).submitted_at,"Resume requires an already submitted synthetic CAR").toBeTruthy();
      await publicPage.goto(`/qms/car-access/${encodeURIComponent(data.car_loop_invite_token)}`);
      await expect(async()=>{
        const retry=publicPage.getByRole("button",{name:"Retry loading response",exact:true});
        if(await retry.isVisible())await retry.click();
        await expect(publicPage.getByText("Response locked — no further submissions or changes are permitted.")).toBeVisible({timeout:15000});
      }).toPass({timeout:90000,intervals:[3000,6000,10000]});
      console.log("CAR acceptance: resumed the retained initial submission");
    } else await submitResponsibleManagerResponse(publicPage, data, "initial");

    const internalPage = await internalContext.newPage();
    watchServerFailures(internalPage, internalFailures);
    await login(internalPage, data);
    const controlPath = `/maintenance/${data.amo_slug}/quality/cars?control=${encodeURIComponent(data.car_loop_id)}`;
    await internalPage.goto(controlPath, { waitUntil: "domcontentloaded" });
    await expect(async()=>{
      const retry=internalPage.getByRole("button",{name:"Retry",exact:true});
      if(await retry.isVisible())await retry.click();
      await expect(internalPage.getByRole("heading", { name: new RegExp(data.car_loop_number) })).toBeVisible({timeout:15000});
    }).toPass({timeout:120000,intervals:[3000,6000,10000]});

    await internalPage.getByLabel("Accountable lead owner").selectOption(data.realtime_user_b_id);
    await internalPage.getByLabel("Controlled final due date").fill(futureDate(28));
    await internalPage.getByRole("button", { name: "Initialize control loop" }).click();
    await expect(internalPage.getByRole("status").filter({ hasText: "Staged CAR control initialized" })).toContainText("Staged CAR control initialized", { timeout: 30_000 });

    const internalFeedback=internalPage.getByRole("region",{name:"CAR feedback and decision history"});
    console.log("CAR acceptance: exchanging live shared feedback and checking private-note isolation");
    const publicFeedback=publicPage.getByRole("region",{name:"CAR feedback and decision history"});
    await internalFeedback.getByLabel("CAR feedback message",{exact:true}).fill("Please identify the evidence owner and the independent effectiveness check.");
    await internalFeedback.getByRole("button",{name:"Send feedback",exact:true}).click();
    await expect(publicFeedback).toContainText("Please identify the evidence owner",{timeout:20000});
    await internalFeedback.getByLabel("Internal note · hidden from auditee",{exact:true}).check();
    await internalFeedback.getByLabel("CAR feedback message",{exact:true}).fill("PRIVATE QA NOTE: internal reviewer discussion only.");
    await internalFeedback.getByRole("button",{name:"Record internal note",exact:true}).click();
    await expect(internalFeedback).toContainText("PRIVATE QA NOTE");
    await expect(publicFeedback).not.toContainText("PRIVATE QA NOTE");
    await internalFeedback.getByLabel("Internal note · hidden from auditee",{exact:true}).uncheck();
    const publicHistory=await publicPage.request.get(`/quality/cars/invite/${data.car_loop_invite_token}/feedback`);
    expect(publicHistory.status()).toBe(200);
    const safeHistory=await publicHistory.json();
    expect(JSON.stringify(safeHistory)).not.toContain("PRIVATE QA NOTE");
    expect(JSON.stringify(safeHistory)).not.toContain("actor_user_id");
    let dropAcknowledgement=true;
    const feedbackRoute="**/quality/cars/invite/*/feedback";
    await publicPage.route(feedbackRoute,async route=>{
      if(route.request().method()==="POST"&&dropAcknowledgement){dropAcknowledgement=false;const committed=await route.fetch();expect(committed.status()).toBe(201);await route.abort("failed");}
      else await route.continue();
    });
    const reply="Acknowledged: I will clarify ownership and provide the controlled evidence.";
    await publicFeedback.getByLabel("CAR feedback message",{exact:true}).fill(reply);
    await publicFeedback.getByRole("button",{name:"Send feedback",exact:true}).click();
    await expect(publicFeedback.getByLabel("CAR feedback message",{exact:true})).toHaveValue(reply);
    await expect(publicFeedback.getByRole("alert")).toBeVisible();
    await publicFeedback.getByRole("button",{name:"Send feedback",exact:true}).click();
    await expect(publicFeedback.getByLabel("CAR feedback message",{exact:true})).toHaveValue("");
    await publicPage.unroute(feedbackRoute);
    await expect(internalFeedback).toContainText(reply,{timeout:20000});
    const replyHistory=await publicPage.request.get(`/quality/cars/invite/${data.car_loop_invite_token}/feedback`);
    expect((await replyHistory.json()).items.filter((item:{message:string})=>item.message===reply)).toHaveLength(1);
    console.log("CAR acceptance: lost-acknowledgement retry retained exactly one message");

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

    const rejected = await reviewThroughUi(internalPage,data,"REJECTED",
      "Return for rework: identify the missing management-control checkpoint and accountable evidence owner.",
      "Return for rework: corrective action must include effectiveness verification and recurrence monitoring.");
    expect(rejected.status).toBe(200);
    const sharedGuest=publicPage.getByRole("region",{name:"CAR feedback and decision history"});
    await expect(sharedGuest).toContainText("Root cause: REJECTED",{timeout:20000});
    await expect(sharedGuest).toContainText("identify the missing management-control checkpoint");

    await submitResponsibleManagerResponse(publicPage, data, "rework",async()=>{
      const feedback=internalPage.getByRole("region",{name:"CAR feedback and decision history"});
      await feedback.getByLabel("CAR feedback message",{exact:true}).fill("Rework guidance: retain your draft while linking the independent evidence owner.");
      await feedback.getByRole("button",{name:"Send feedback",exact:true}).click();
      await expect(publicFeedback).toContainText("Rework guidance: retain your draft",{timeout:20000});
    });
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
    await internalPage.goto(controlPath, { waitUntil: "domcontentloaded" });
    const responsePanel = internalPage.getByRole("region", { name: "Corrective action response" });
    // The Quality page may hydrate asynchronously; this check must prove the
    // actual revised response, not match a stale name elsewhere on the page.
    await expect(responsePanel).toBeVisible({ timeout: 30_000 });
    await expect(responsePanel.getByText(/Responsible Maintenance Manager/)).toBeVisible({ timeout: 30_000 });
    await expect(responsePanel.getByText(/effectiveness checkpoint and evidence-index ownership control rework/)).toBeVisible({ timeout: 30_000 });
    // Capture the actual authenticated Quality review surface. The synthetic
    // fixture contains no production identities or live invitation tokens.
    await internalPage.screenshot({ path: "test-results/phase3-quality-rework.png", fullPage: true });

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

    const accepted = await reviewThroughUi(internalPage,data,"ACCEPTED",
      "RCA accepted after rework identified the management-control and evidence-ownership root cause.",
      "CAPA accepted as a plan; implementation, evidence and effectiveness still require independent verification.");
    expect(accepted.status).toBe(200);
    await internalPage.goto(controlPath);
    const lifecycle = internalPage.getByRole("heading", { name: "Staged CAR lifecycle" }).locator("xpath=ancestor::section[1]");
    const stages = [
      "Root cause analysis submitted",
      "Corrective action plan approved",
      "Corrective actions implemented",
      "Closure evidence complete",
      "Effectiveness review complete",
    ];
    for (const [index, stage] of stages.slice(0,2).entries()) {
      const row = lifecycle.getByRole("row", { name: new RegExp(stage) });
      await row.getByRole("combobox").last().selectOption("ACCEPTED");
      await row.getByPlaceholder("Evidence reference").fill(`car-evidence:stage-${index + 1}`);
      await row.getByPlaceholder("Control note").fill(`${stage} independently reviewed and accepted by Quality.`);
      await row.getByRole("button", { name: "Save" }).click();
      await expect(internalPage.getByRole("status").filter({ hasText: `${stage} updated` })).toContainText(`${stage} updated`, { timeout: 30_000 });
    }

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
    expect(record.actions,"Retrying a committed action must not create duplicates").toHaveLength(1);

    // Closing with an unapproved or unverified action must fail even when
    // legacy control-loop milestones have otherwise been accepted.
    const premature = await authenticatedPost(internalPage, `${apiCarPath}/control-loop/close`, {
      evidence_ref: "car-evidence:stage-5",
      closure_reason: "Negative control: reject closure without independent implementation verification.",
    });
    expect(premature.status).toBe(409);
    expect(JSON.stringify(premature.body)).toMatch(/implementation|evidence|effectiveness|milestone|independently verified/i);

    await reviewIndividualActionUi(internalPage,data,corrective!.description,"REJECTED","Return this individual action: clarify implementation ownership and the controlled evidence index.");
    await expect(sharedGuest).toContainText("clarify implementation ownership",{timeout:20000});
    const returnedActions=publicPage.getByRole("region",{name:"Individual corrective actions"});
    await returnedActions.getByRole("button",{name:"Revise proposed action",exact:true}).click({timeout:20000});
    const revisedDescription=corrective!.description+" — clarified after independent action review";
    await returnedActions.getByLabel("What specifically changes?").fill(revisedDescription);
    await returnedActions.getByRole("button",{name:"Save revised action",exact:true}).click();
    await expect(returnedActions.getByRole("status")).toContainText("Proposed action revision retained",{timeout:20000});
    const approvedAction = await reviewIndividualActionUi(internalPage,data,revisedDescription,"ACCEPTED",
      "The proposed corrective action addresses the verified RCA and has a responsible owner and deadline.");
    expect(approvedAction.status, JSON.stringify(approvedAction.body)).toBe(200);
    expect((approvedAction.body as { state: string }).state).toBe("ACCEPTED");

    // The actual respondent browser, not a privileged backend shortcut,
    // records implementation evidence after independent Quality approval.
    const implementation = publicPage.getByRole("region", { name: "Individual corrective actions" });
    await expect(implementation.getByRole("button", { name: "Record progress" })).toBeVisible({ timeout: 30_000 });
    await implementation.getByRole("button", { name: "Record progress" }).click();
    await implementation.getByLabel("Completion declaration").fill(
      "The controlled CAR register now records independent effectiveness checkpoints and an accountable evidence owner.",
    );
    await implementation.getByLabel("Evidence references, one per line").fill(
      "CAR-SAMPLE:rework:effectiveness-observation",
    );
    await implementation.getByLabel("Link existing CAR file to implementation evidence").selectOption({label:"car-effectiveness-rework.txt"});
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

    const verifiedAction = await reviewIndividualActionUi(internalPage,data,revisedDescription,"VERIFIED",
      "Independent Quality review confirms that the control and indexed implementation evidence were recorded.");
    expect(verifiedAction.status, JSON.stringify(verifiedAction.body)).toBe(200);
    expect((verifiedAction.body as { state: string }).state).toBe("VERIFIED");
    await internalPage.goto(controlPath);
    for (const [offset,stage] of stages.slice(2,4).entries()) {
      const row=internalPage.getByRole("heading",{name:"Staged CAR lifecycle"}).locator("xpath=ancestor::section[1]").getByRole("row",{name:new RegExp(stage)});
      await row.getByRole("combobox").last().selectOption("ACCEPTED");
      await row.getByPlaceholder("Evidence reference").fill(`car-evidence:stage-${offset+3}`);
      await row.getByPlaceholder("Control note").fill(`${stage} accepted after independent verification of the implemented action.`);
      await row.getByRole("button",{name:"Save",exact:true}).click();
      await expect(internalPage.getByRole("status").filter({hasText:`${stage} updated`})).toContainText(`${stage} updated`,{timeout:30000});
    }

    console.log("CAR acceptance: adopting independent effectiveness plan through Quality controls");
    await internalPage.goto(controlPath);
    await internalPage.getByLabel("Independent effectiveness reviewer",{exact:true}).selectOption(data.realtime_user_a_id,{timeout:30000});
    await internalPage.getByLabel("Quality adoption and independence rationale",{exact:true}).fill("Independent effectiveness review follows the respondent's measured and evidenced proposal.");
    const adopting=internalPage.waitForResponse(r=>r.url().endsWith(`/cars/${data.car_loop_id}/effectiveness-plan`)&&r.request().method()==="POST");
    await internalPage.getByRole("button",{name:"Adopt governed effectiveness plan",exact:true}).click();
    const adoptedResponse=await adopting;
    const adopted={status:adoptedResponse.status(),body:await adoptedResponse.json()};
    expect(adopted.status, JSON.stringify(adopted.body)).toBe(201);
    const plan = adopted.body as { case_id: string; case_ref:string; plan_id: string };
    expect(plan.case_id).toBeTruthy();
    expect(plan.plan_id).toBeTruthy();

    await internalPage.getByRole("button",{name:"Open Assurance Cases",exact:true}).click();
    await internalPage.locator(".qms-assurance-cases__case-list").getByRole("button").filter({hasText:plan.case_ref}).click({timeout:30000});
    await internalPage.getByLabel("Plan ready for review",{exact:true}).selectOption(plan.plan_id);
    await internalPage.getByLabel("Conclusion",{exact:true}).selectOption("EFFECTIVE");
    await internalPage.getByLabel("Evidence-backed rationale",{exact:true}).fill("Independent check confirms that the sampled CAR register has the effectiveness checkpoint and evidence owner.");
    await internalPage.getByLabel("Authoritative evidence reference",{exact:true}).fill(`CAR:${data.car_loop_id}:CAR-SAMPLE:rework:effectiveness-observation`);
    await internalPage.screenshot({path:"test-results/car-feedback-effectiveness-review.png"});
    const concluding=internalPage.waitForResponse(r=>r.url().endsWith(`/effectiveness-plans/${plan.plan_id}/conclusion`)&&r.request().method()==="POST");
    await internalPage.getByRole("button",{name:"Record immutable effectiveness conclusion",exact:true}).click();
    const conclusionResponse=await concluding;
    const conclusion={status:conclusionResponse.status(),body:await conclusionResponse.json()};
    expect(conclusion.status, JSON.stringify(conclusion.body)).toBe(200);
    expect((conclusion.body as { effectiveness_plan: { status: string; conclusion: string } }).effectiveness_plan)
      .toMatchObject({ status: "CONCLUDED", conclusion: "EFFECTIVE" });

    console.log("CAR acceptance: closing through the governed Quality interface");
    await internalPage.goto(controlPath);
    const effectivenessMilestone=internalPage.getByRole("heading",{name:"Staged CAR lifecycle"}).locator("xpath=ancestor::section[1]").getByRole("row",{name:new RegExp(stages[4])});
    await effectivenessMilestone.getByRole("combobox").last().selectOption("ACCEPTED");
    await effectivenessMilestone.getByPlaceholder("Evidence reference").fill("car-evidence:stage-5");
    await effectivenessMilestone.getByPlaceholder("Control note").fill("Effectiveness accepted only after the appointed reviewer recorded the immutable effective conclusion.");
    await effectivenessMilestone.getByRole("button",{name:"Save",exact:true}).click();
    await expect(internalPage.getByRole("status").filter({hasText:`${stages[4]} updated`})).toContainText(`${stages[4]} updated`,{timeout:30000});
    await internalPage.getByLabel("Closure evidence reference",{exact:true}).fill("car-evidence:stage-5",{timeout:30000});
    await internalPage.getByLabel("Closure rationale",{exact:true}).fill("Quality accepts closure after rejected-response rework, controlled extension, independent action verification and concluded effectiveness.");
    const closing=internalPage.waitForResponse(r=>r.url().endsWith(`/cars/${data.car_loop_id}/control-loop/close`)&&r.request().method()==="POST");
    await internalPage.getByRole("button",{name:"Close CAR",exact:true}).click();
    const closeResponse=await closing;
    const governedClose={status:closeResponse.status(),body:await closeResponse.json()};
    expect(governedClose.status, JSON.stringify(governedClose.body)).toBe(200);
    const closedControl = await authenticatedRequest(internalPage, "GET", `${apiCarPath}/control-loop`);
    expect(closedControl.status, JSON.stringify(closedControl.body)).toBe(200);
    expect((closedControl.body as { car: { status: string }; health: { state: string } }).car.status).toBe("CLOSED");
    expect((closedControl.body as { car: { status: string }; health: { state: string } }).health.state).toBe("CLOSED");
    await expect(publicFeedback).toContainText("CAR closed · communication history is read only.",{timeout:20000});
    const retainedHistory=await publicPage.request.get(`/quality/cars/invite/${data.car_loop_invite_token}/feedback`);
    const retained=await retainedHistory.json();
    expect(JSON.stringify(retained)).toContain("Root cause: REJECTED");
    expect(JSON.stringify(retained)).toContain("Root cause: ACCEPTED");
    expect(JSON.stringify(retained)).toContain("Effectiveness: EFFECTIVE");
    expect(JSON.stringify(retained)).not.toContain("PRIVATE QA NOTE");
    console.log("CAR acceptance: governed closure confirmed; rejection, acceptance and effectiveness retained in shared history");

    await internalPage.goto(controlPath, { waitUntil: "domcontentloaded" });
    await expect(internalPage.getByText("Closed", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
    await expect(internalPage.getByRole("heading", { name: "Control event timeline" })).toBeVisible();
    await expect(internalPage.getByText(/Control Loop Closed/i)).toBeVisible();

    await publicPage.reload({ waitUntil: "domcontentloaded" });
    await expect(publicPage.getByText("Closed", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(publicPage.getByText(/This CAR is closed/i)).toBeVisible();
    await internalPage.screenshot({ path: "test-results/phase3-quality-closed.png", fullPage: true });
    await publicPage.setViewportSize({ width: 390, height: 844 });
    const mobileWidth = await publicPage.evaluate(() => document.documentElement.scrollWidth);
    expect(mobileWidth, "Public CAR must not overflow a 390px mobile viewport").toBeLessThanOrEqual(392);
    await publicPage.screenshot({ path: "test-results/phase3-public-closed-mobile.png", fullPage: true });

    // This is an isolated CI-created CAR. Revoke its bearer token after
    // asserting closure to demonstrate that valid former links fail closed.
    const revokedAccess = await authenticatedRequest(internalPage, "PUT", `${apiCarPath}/invite-access`, {
      revoke: true,
      reason: "End the synthetic review access after independently verified closeout.",
    });
    expect(revokedAccess.status, JSON.stringify(revokedAccess.body)).toBe(200);
    const rejectedAfterRevocation = await publicPage.request.get(
      `/quality/cars/invite/${encodeURIComponent(data.car_loop_invite_token)}`,
    );
    expect(rejectedAfterRevocation.status()).toBe(410);
    const rejectedDraft = await publicPage.request.get(
      `/quality/cars/invite/${encodeURIComponent(data.car_loop_invite_token)}/draft`,
    );
    expect(rejectedDraft.status()).toBe(410);
    const stillClosed = await authenticatedRequest(internalPage, "GET", `${apiCarPath}/control-loop`);
    expect(stillClosed.status).toBe(200);
    expect((stillClosed.body as { car: { status: string } }).car.status).toBe("CLOSED");

    expect(publicFailures).toEqual([]);
    expect(internalFailures).toEqual([]);
  } catch(error) {
    const detail=String(error).replaceAll(data.car_loop_invite_token,"[redacted]").replaceAll(data.realtime_password,"[redacted]");
    console.error("CAR acceptance failed:",detail);
    console.error("Observed server/page failures:",JSON.stringify([...publicFailures,...internalFailures]).replaceAll(data.car_loop_invite_token,"[redacted]"));
    await Promise.allSettled([
      publicContext.pages()[0]?.screenshot({path:"test-results/car-feedback-public-failed.png"}),
      internalContext.pages()[0]?.screenshot({path:"test-results/car-feedback-auditor-failed.png"}),
    ]);
    throw error;
  } finally {
    console.log("CAR acceptance: closing auditor and auditee contexts");
    await Promise.allSettled([publicContext.close(), internalContext.close()]);
    console.log("CAR acceptance: browser contexts closed");
  }
});

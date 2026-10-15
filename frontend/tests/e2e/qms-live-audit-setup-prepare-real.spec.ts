import { expect, test, type Page, type Response } from "@playwright/test";
import fs from "node:fs";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(300_000);

type Fixture = {
  amo_slug: string;
  realtime_audit_ref: string;
  realtime_audit_id: string;
  realtime_user_a_email: string;
  realtime_password: string;
  dms_checklist_id: string;
  dms_checklist_code: string;
  dms_checklist_revision_id: string;
};

function fixture(): Fixture {
  return JSON.parse(fs.readFileSync(process.env.E2E_QMS_LIVE_FIXTURE || "/tmp/qms-live-audit-real-e2e.json", "utf-8")) as Fixture;
}

function futureDate(days: number): string {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function futureLocalDateTime(hours: number): string {
  const value = new Date(Date.now() + hours * 60 * 60 * 1000);
  const adjusted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 16);
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

test("real Setup and Prepare browsers persist governed occurrence, meetings, notice, request, auditee upload and internal acceptance", async ({ browser }) => {
  const data = fixture();
  const internalFailures: string[] = [];
  const guestFailures: string[] = [];
  const internalContext = await browser.newContext();
  const guestContext = await browser.newContext();

  try {
    const page = await internalContext.newPage();
    watchServerFailures(page, internalFailures);
    await page.goto(`/maintenance/${data.amo_slug}/login`, { waitUntil: "domcontentloaded" });
    await page.getByLabel("Email", { exact: true }).fill(data.realtime_user_a_email);
    await page.getByLabel("Password", { exact: true }).fill(data.realtime_password);
    await Promise.all([
      page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
      page.getByRole("button", { name: "Sign In" }).click(),
    ]);

    const setupPath = `/maintenance/${data.amo_slug}/quality/audits/${encodeURIComponent(data.realtime_audit_ref)}/setup?tab=war-room`;
    await page.goto(setupPath, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Quality route not found" })).toHaveCount(0);
    const setup = page.getByRole("region", { name: "Audit setup workspace" });
    await expect(setup).toBeVisible({ timeout: 30_000 });

    await setup.getByRole("textbox", { name: "Scope", exact: true }).fill("Real browser setup scope covering controlled maintenance and Quality records.");
    await setup.getByRole("textbox", { name: "Criteria", exact: true }).fill("Approved QMS manual, controlled procedures and applicable aviation regulatory requirements.");
    await setup.getByLabel("Auditee", { exact: true }).fill("Preparation Journey Auditee");
    await setup.getByLabel("Auditee email", { exact: true }).fill("prepare.auditee@example.com");
    // The controlled notice requires an enabled, deliverable auditee contact.
    // Do not bypass the backend recipient gate in acceptance tests.
    await setup.getByLabel("Notify auditee", { exact: true }).check();
    await setup.getByLabel("Planned start date", { exact: true }).fill(futureDate(30));
    await setup.getByLabel("Planned end date", { exact: true }).fill(futureDate(31));
    await setup.getByLabel("Reminder (days)", { exact: true }).fill("5");
    const rescheduleReason = setup.getByRole("textbox", { name: "Reason for rescheduling", exact: true });
    await expect(rescheduleReason).toBeVisible();
    await rescheduleReason.fill("Move this acceptance audit into the governed preparation window.");
    await expect(rescheduleReason).toHaveValue("Move this acceptance audit into the governed preparation window.");
    await expect(setup.getByRole("button", { name: "Save audit definition", exact: true })).toBeEnabled();
    // Setup tiles are exclusive disclosures; ensure the definition is expanded
    // before interacting with its save control after reactive date updates.
    const definitionTile = setup.locator("details.qms-audit-setup-tile").filter({
      // The inner locator must be rooted at the page: it is evaluated relative
      // to each <details>, not relative to the outer Setup region.
      has: page.getByText("Audit definition", { exact: true }),
    });
    await expect(definitionTile).toHaveCount(1);
    if ((await definitionTile.getAttribute("open")) === null) {
      await definitionTile.locator(":scope > summary").click();
    }
    await expect(definitionTile).toHaveAttribute("open", "");
    await definitionTile.getByRole("button", { name: "Save audit definition", exact: true }).click();
    await expect(setup.locator(".qms-occurrence-stage__message").last()).toContainText("Definition saved.", { timeout: 30_000 });

    const meetingsTile = setup.locator("details.qms-audit-setup-tile").filter({
      has: page.getByText("Opening and closing meetings", { exact: true }),
    });
    await expect(meetingsTile).toHaveCount(1);
    if ((await meetingsTile.getAttribute("open")) === null) {
      await meetingsTile.locator(":scope > summary").click();
    }
    await expect(meetingsTile).toHaveAttribute("open", "");

    const openingCard = setup.getByText("Opening", { exact: true }).locator("xpath=ancestor::div[contains(@class, 'qms-audit-setup-stage__meeting')][1]");
    await openingCard.getByRole("button", { name: "On site", exact: true }).click();
    await openingCard.getByLabel("Customize", { exact: true }).check();
    await openingCard.getByLabel("Start", { exact: true }).fill(`${futureDate(30)}T08:00`);
    await openingCard.getByLabel("End", { exact: true }).fill(`${futureDate(30)}T09:00`);
    await openingCard.getByLabel("Location", { exact: true }).fill("Hangar briefing room");
    await openingCard.getByLabel("Agenda / interview plan", { exact: true }).fill("Opening briefing, scope confirmation, safety requirements and evidence access.");
    await openingCard.getByRole("button", { name: "Save meeting" }).click();
    await expect(setup.locator(".qms-occurrence-stage__message").last()).toContainText(/opening meeting saved/i, { timeout: 30_000 });

    const closingCard = setup.getByText("Closing", { exact: true }).locator("xpath=ancestor::div[contains(@class, 'qms-audit-setup-stage__meeting')][1]");
    await closingCard.getByRole("button", { name: "On site", exact: true }).click();
    await closingCard.getByLabel("Customize", { exact: true }).check();
    await closingCard.getByLabel("Start", { exact: true }).fill(`${futureDate(31)}T17:00`);
    await closingCard.getByLabel("End", { exact: true }).fill(`${futureDate(31)}T18:00`);
    await closingCard.getByLabel("Location", { exact: true }).fill("Quality conference room");
    await closingCard.getByLabel("Agenda / interview plan", { exact: true }).fill("Findings, report acknowledgement, corrective-action handoff and closing decisions.");
    await closingCard.getByRole("button", { name: "Save meeting" }).click();
    await expect(setup.locator(".qms-occurrence-stage__message").last()).toContainText(/closing meeting saved/i, { timeout: 30_000 });

    const noticeCard = setup.locator("details.qms-audit-setup-tile").filter({
      has: page.getByText("Audit notice", { exact: true }),
    });
    await expect(noticeCard).toHaveCount(1);
    if ((await noticeCard.getAttribute("open")) === null) {
      await noticeCard.locator(":scope > summary").click();
    }
    await expect(noticeCard).toHaveAttribute("open", "");
    const noticePath = `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/audits/${encodeURIComponent(data.realtime_audit_id)}/notices`;
    const draftResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "POST" && new URL(response.url()).pathname === noticePath,
    );
    await noticeCard.getByRole("button", { name: "Create notice draft" }).click();
    const draftResponse = await draftResponsePromise;
    expect(draftResponse.status()).toBe(201);
    const noticeDraft = await draftResponse.json() as { id: string; status: string; revision_no: number };
    expect(noticeDraft.status).toBe("DRAFT");
    expect(noticeDraft.revision_no).toBe(1);
    await expect(setup.locator(".qms-occurrence-stage__message").last()).toContainText("Notice draft prepared from the saved audit data", { timeout: 30_000 });
    await noticeCard.getByRole("button", { name: "Generate final preview" }).click();
    const noticePreview = page.getByRole("dialog", { name: /Audit notice - revision 1/i });
    await expect(noticePreview).toBeVisible({ timeout: 30_000 });
    await expect(noticePreview).toContainText("Generated and electronically signed notice");
    await noticePreview.getByRole("button", { name: "Close", exact: true }).click();

    // The full notice lifecycle includes governed manual delivery and receipt
    // recording. This is authenticated HTTP against the real FastAPI/PostgreSQL
    // state, not a mocked response or a claim that an SMTP message was sent.
    // The CI persistence contract requires an actual ACKNOWLEDGED notice.
    const bearer = await page.evaluate(() => sessionStorage.getItem("amo_portal_token"));
    expect(bearer).toBeTruthy();
    const transitionPath = `${noticePath}/${encodeURIComponent(noticeDraft.id)}/transitions`;
    // Final signed preview is itself a governed preparation operation. It
    // submits, approves and generates the notice (with attributable events).
    // Replaying SUBMIT on that already-GENERATED revision correctly returns 409.
    // Continue with manual delivery and acknowledgement without bypassing state.
    const afterPreview = await page.request.get(noticePath, {
      headers: { Authorization: `Bearer ${bearer}` },
    });
    expect(afterPreview.ok(), await afterPreview.text()).toBeTruthy();
    const noticeList = await afterPreview.json() as { items: Array<{ id: string; status: string }> };
    expect(noticeList.items.find((item) => item.id === noticeDraft.id)?.status).toBe("GENERATED");
    for (const { action, expectedStatus } of [
      { action: "DELIVER", expectedStatus: "DELIVERED" },
      { action: "ACKNOWLEDGE", expectedStatus: "ACKNOWLEDGED" },
    ]) {
      const response = await page.request.post(transitionPath, {
        headers: { Authorization: `Bearer ${bearer}` },
        data: {
          action,
          reason: "Real browser governed notice lifecycle confirmation.",
          ...(action === "DELIVER" ? {
            delivery_channel: "MANUAL",
            delivery_reference: "Real-browser governed notice delivery",
          } : {}),
        },
      });
      expect(response.status(), `Notice ${action} rejected: ${await response.text()}`).toBe(200);
      const updatedNotice = await response.json() as { id: string; status: string; delivery_reference: string | null };
      expect(updatedNotice.id).toBe(noticeDraft.id);
      expect(updatedNotice.status).toBe(expectedStatus);
      if (action === "DELIVER" || action === "ACKNOWLEDGE") {
        expect(updatedNotice.delivery_reference).toBe("Real-browser governed notice delivery");
      }
    }

    await setup.getByRole("link", { name: "Open Prepare" }).click();
    const prepare = page.getByRole("region", { name: "Pre-audit preparation workspace" });
    await expect(prepare).toBeVisible({ timeout: 30_000 });
    await expect(prepare.getByText("Real browser setup scope covering controlled maintenance and Quality records.")).toBeVisible();

    const controlledChecklist = prepare.getByLabel("Current controlled document", { exact: true });
    await expect(controlledChecklist).toBeVisible({ timeout: 30_000 });
    await controlledChecklist.selectOption(data.dms_checklist_id);
    await prepare.getByLabel("Response vocabulary", { exact: true }).selectOption("YES_NO_NA");
    await prepare.getByLabel("Add to the existing checklist", { exact: true }).check();
    await expect(prepare.getByText("Current effective revision", { exact: true })).toBeVisible();

    const bindResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "POST"
      && response.url().includes(`/checklist-library/${data.dms_checklist_id}/bind-current`),
    );
    await prepare.getByRole("button", { name: "Use current revision", exact: true }).click();
    const bindResponse = await bindResponsePromise;
    expect(bindResponse.status()).toBe(201);
    const persistedBinding = await bindResponse.json() as { id: string; audit_id: string; instantiated_item_ids: string[] };
    expect(persistedBinding.id).toBeTruthy();
    expect(persistedBinding.instantiated_item_ids.length).toBeGreaterThan(0);
    await expect(prepare.getByText("1 bound", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(prepare.getByText(new RegExp(`${data.dms_checklist_code}.*Rev 1`, "i"))).toBeVisible();
    await expect(prepare.getByText("The current effective DMS checklist is bound to fieldwork.", { exact: true })).toBeVisible();
    await expect(prepare.getByText(/has not confirmed the authoritative fieldwork binding/i)).toHaveCount(0);

    await prepare.getByRole("button", { name: "New request" }).click();
    await prepare.getByLabel("Due date", { exact: true }).fill(futureDate(20));
    await prepare.getByLabel("Request title", { exact: true }).fill("Current authorization and competence evidence");
    await prepare.getByLabel("Purpose / records required", { exact: true }).fill("Provide the current authorization and competence evidence for the sampled certifying personnel before fieldwork.");
    await prepare.getByLabel("Linked criterion / requirement", { exact: true }).fill("QMSM 5.4 and approved personnel authorization procedure");
    await prepare.getByLabel("Submission source", { exact: true }).selectOption("UPLOAD");
    const requestPath = `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/audits/${encodeURIComponent(data.realtime_audit_id)}/governed-document-requests`;
    const creationResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "POST" && new URL(response.url()).pathname === requestPath,
    );
    await prepare.getByRole("button", { name: "Create governed request" }).click();
    const requestCreation = await creationResponsePromise;
    expect(requestCreation.status()).toBe(201);
    const governedRequest = await requestCreation.json() as { id: string; status: string };
    expect(governedRequest.status).toBe("REQUESTED");
    await expect(prepare.getByText("Current authorization and competence evidence", { exact: true })).toBeVisible({ timeout: 30_000 });
    // A request may never be marked accepted before actual evidence is received.
    const prematureAcceptance = await page.request.patch(
      `${requestPath}/${encodeURIComponent(governedRequest.id)}`, {
        headers: { Authorization: `Bearer ${bearer}` },
        data: { status: "ACCEPTED", review_note: "Must reject acceptance before auditee submission." },
      },
    );
    expect(prematureAcceptance.status(), await prematureAcceptance.text()).toBe(409);
    const legacyBypass = await page.request.patch(
      `/api/maintenance/${encodeURIComponent(data.amo_slug)}/quality/audits/${encodeURIComponent(data.realtime_audit_id)}/document-requests/${encodeURIComponent(governedRequest.id)}`, {
        headers: { Authorization: `Bearer ${bearer}` },
        data: { status: "ACCEPTED", file_ref: "unverified-manual-reference" },
      },
    );
    expect(legacyBypass.status(), await legacyBypass.text()).toBe(409);
    await expect(prepare.getByText(/QMSM 5\.4/)).toBeVisible();

    await prepare.getByRole("button", { name: "Invite" }).click();
    await prepare.getByLabel("Full name", { exact: true }).fill("Preparation Journey Auditee");
    await prepare.getByLabel("Email", { exact: true }).fill("prepare.auditee@example.com");
    await prepare.getByLabel("Organisation", { exact: true }).fill("Real Browser Auditee Organisation");
    await prepare.getByLabel("Access expires", { exact: true }).fill(futureLocalDateTime(24));
    await prepare.getByLabel("View fieldwork progress", { exact: true }).check();

    const inviteResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/external-participants") && response.status() === 201);
    await prepare.getByRole("button", { name: "Create invitation" }).click();
    const inviteResponse = await inviteResponsePromise;
    const invited = await inviteResponse.json() as { access_url?: string };
    expect(invited.access_url).toBeTruthy();
    await expect(prepare.locator(".qms-occurrence-stage__message").last()).toContainText("Participant access created. Copy the invitation link shown below.", { timeout: 30_000 });

    const guestPage = await guestContext.newPage();
    watchServerFailures(guestPage, guestFailures);
    await guestPage.goto(invited.access_url!, { waitUntil: "domcontentloaded" });
    await expect(guestPage.getByRole("heading", { name: new RegExp(`${data.realtime_audit_ref} · Concurrent realtime browser acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(guestPage.getByText("Current authorization and competence evidence", { exact: true })).toBeVisible();
    await guestPage.getByLabel("Provide document", { exact: true }).setInputFiles({
      name: "authorization-competence-evidence.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Controlled acceptance evidence for the real QMS setup and preparation browser journey.\n", "utf-8"),
    });
    await guestPage.getByLabel("Response / context", { exact: true }).fill("Submitted from the purpose-bound auditee browser session for internal review.");
    await guestPage.getByRole("button", { name: "Submit securely" }).click();
    await expect(guestPage.getByRole("status")).toContainText("authorization-competence-evidence.txt submitted · SHA-256", { timeout: 30_000 });

    await page.reload({ waitUntil: "domcontentloaded" });
    const reloadedPrepare = page.getByRole("region", { name: "Pre-audit preparation workspace" });
    const requestCard = reloadedPrepare.getByText("Current authorization and competence evidence", { exact: true }).locator("xpath=ancestor::article[1]");
    await expect(requestCard.getByText("Uploaded", { exact: true })).toBeVisible({ timeout: 30_000 });
    await requestCard.getByPlaceholder("Review note / return instructions").fill("Evidence reviewed against the linked criterion and accepted for fieldwork preparation.");
    await requestCard.getByRole("button", { name: "Accept" }).click();
    await expect(requestCard.getByText("Accepted", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(requestCard.getByText(/Evidence reviewed against the linked criterion/)).toBeVisible();

    expect(internalFailures).toEqual([]);
    expect(guestFailures).toEqual([]);
  } finally {
    await Promise.allSettled([internalContext.close(), guestContext.close()]);
  }
});
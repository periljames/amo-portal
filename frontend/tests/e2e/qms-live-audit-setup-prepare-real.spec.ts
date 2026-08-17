import { expect, test, type Page, type Response } from "@playwright/test";
import fs from "node:fs";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(150_000);

type Fixture = {
  amo_slug: string;
  realtime_audit_ref: string;
  realtime_user_a_email: string;
  realtime_password: string;
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
    await page.getByLabel("Email or staff code").fill(data.realtime_user_a_email);
    await page.getByLabel("Password").fill(data.realtime_password);
    await Promise.all([
      page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
      page.getByRole("button", { name: "Sign In" }).click(),
    ]);

    const setupPath = `/maintenance/${data.amo_slug}/quality/audits/${encodeURIComponent(data.realtime_audit_ref)}/setup?tab=war-room`;
    await page.goto(setupPath, { waitUntil: "domcontentloaded" });
    const setup = page.getByRole("region", { name: "Audit setup workspace" });
    await expect(setup).toBeVisible({ timeout: 30_000 });

    await setup.getByLabel("Scope").fill("Real browser setup scope covering controlled maintenance and Quality records.");
    await setup.getByLabel("Criteria").fill("Approved QMS manual, controlled procedures and applicable aviation regulatory requirements.");
    await setup.getByLabel("Auditee").fill("Preparation Journey Auditee");
    await setup.getByLabel("Auditee email").fill("prepare.auditee@example.com");
    await setup.getByLabel("Planned start").fill(futureDate(30));
    await setup.getByLabel("Planned end").fill(futureDate(31));
    await setup.getByLabel("Reminder interval (days)").fill("5");
    await setup.getByRole("button", { name: "Save audit definition" }).click();
    await expect(setup.getByRole("status")).toContainText("Audit definition and notification settings saved", { timeout: 30_000 });

    const openingCard = setup.getByText("Opening meeting", { exact: true }).locator("xpath=ancestor::article[1]");
    await openingCard.getByLabel("Start").fill(futureLocalDateTime(1));
    await openingCard.getByLabel("End").fill(futureLocalDateTime(2));
    await openingCard.getByLabel("Location").fill("Hangar briefing room");
    await openingCard.getByLabel("Agenda").fill("Opening briefing, scope confirmation, safety requirements and evidence access.");
    await openingCard.getByRole("button", { name: "Save meeting" }).click();
    await expect(setup.getByRole("status")).toContainText("opening meeting saved", { timeout: 30_000 });

    const closingCard = setup.getByText("Closing meeting", { exact: true }).locator("xpath=ancestor::article[1]");
    await closingCard.getByLabel("Start").fill(futureLocalDateTime(7));
    await closingCard.getByLabel("End").fill(futureLocalDateTime(8));
    await closingCard.getByLabel("Location").fill("Quality conference room");
    await closingCard.getByLabel("Agenda").fill("Findings, report acknowledgement, corrective-action handoff and closing decisions.");
    await closingCard.getByRole("button", { name: "Save meeting" }).click();
    await expect(setup.getByRole("status")).toContainText("closing meeting saved", { timeout: 30_000 });

    const noticeCard = setup.getByText("Audit notice", { exact: true }).locator("xpath=ancestor::article[1]");
    await noticeCard.getByRole("button", { name: "Create notice" }).click();
    await expect(setup.getByRole("status")).toContainText("Governed audit notice draft created", { timeout: 30_000 });
    for (const action of ["SUBMIT", "APPROVE", "GENERATE"] as const) {
      await noticeCard.getByRole("button", { name: action, exact: true }).click();
      await expect(setup.getByRole("status")).toContainText(action === "SUBMIT" ? "under review" : action === "APPROVE" ? "approved" : "generated", { timeout: 30_000 });
    }
    await noticeCard.getByLabel("Delivery reference").fill("Real-browser governed notice delivery");
    await noticeCard.getByRole("button", { name: "DELIVER", exact: true }).click();
    await expect(setup.getByRole("status")).toContainText("delivered", { timeout: 30_000 });
    await noticeCard.getByRole("button", { name: "ACKNOWLEDGE", exact: true }).click();
    await expect(setup.getByRole("status")).toContainText("acknowledged", { timeout: 30_000 });

    await setup.getByRole("link", { name: "Open Pre-Audit Room" }).click();
    const prepare = page.getByRole("region", { name: "Pre-audit preparation workspace" });
    await expect(prepare).toBeVisible({ timeout: 30_000 });
    await expect(prepare.getByText("Real browser setup scope covering controlled maintenance and Quality records.")).toBeVisible();

    await prepare.getByRole("button", { name: "New request" }).click();
    await prepare.getByLabel("Due date").fill(futureDate(20));
    await prepare.getByLabel("Request title").fill("Current authorization and competence evidence");
    await prepare.getByLabel("Purpose / records required").fill("Provide the current authorization and competence evidence for the sampled certifying personnel before fieldwork.");
    await prepare.getByLabel("Linked criterion / requirement").fill("QMSM 5.4 and approved personnel authorization procedure");
    await prepare.getByLabel("Submission source").selectOption("UPLOAD");
    await prepare.getByRole("button", { name: "Create governed request" }).click();
    await expect(prepare.getByText("Current authorization and competence evidence", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(prepare.getByText(/QMSM 5\.4/)).toBeVisible();

    await prepare.getByRole("button", { name: "Invite" }).click();
    await prepare.getByLabel("Full name").fill("Preparation Journey Auditee");
    await prepare.getByLabel("Email").fill("prepare.auditee@example.com");
    await prepare.getByLabel("Organisation").fill("Real Browser Auditee Organisation");
    await prepare.getByLabel("Access expires").fill(futureLocalDateTime(24));
    await prepare.getByLabel("View fieldwork progress").check();

    const inviteResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/external-participants") && response.status() === 201);
    await prepare.getByRole("button", { name: "Create invitation" }).click();
    const inviteResponse = await inviteResponsePromise;
    const invited = await inviteResponse.json() as { access_url?: string };
    expect(invited.access_url).toBeTruthy();
    await expect(prepare.getByRole("status")).toContainText("One-time invitation link created", { timeout: 30_000 });

    const guestPage = await guestContext.newPage();
    watchServerFailures(guestPage, guestFailures);
    await guestPage.goto(invited.access_url!, { waitUntil: "domcontentloaded" });
    await expect(guestPage.getByRole("heading", { name: new RegExp(`${data.realtime_audit_ref} · Concurrent realtime browser acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(guestPage.getByText("Current authorization and competence evidence", { exact: true })).toBeVisible();
    await guestPage.getByLabel("Provide document").setInputFiles({
      name: "authorization-competence-evidence.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Controlled acceptance evidence for the real QMS setup and preparation browser journey.\n", "utf-8"),
    });
    await guestPage.getByLabel("Response / context").fill("Submitted from the purpose-bound auditee browser session for internal review.");
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

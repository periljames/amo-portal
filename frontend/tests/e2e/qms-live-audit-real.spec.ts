import fs from "node:fs";
import { expect, test, type BrowserContext, type CDPSession, type Page, type Response } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(180_000);

type LiveAuditFixture = {
  amo_id: string;
  amo_slug: string;
  audit_id: string;
  audit_ref: string;
  checklist_item_id: string;
  finding_id: string;
  external_auditor_token: string;
  auditee_token: string;
  realtime_audit_id: string;
  realtime_audit_ref: string;
  realtime_checklist_item_id: string;
  realtime_user_a_id: string;
  realtime_user_a_email: string;
  realtime_user_b_id: string;
  realtime_user_b_email: string;
  realtime_password: string;
  ceremony_audit_id: string;
  ceremony_audit_ref: string;
  ceremony_checklist_item_id: string;
  ceremony_finding_id: string;
  ceremony_car_id: string;
  ceremony_car_number: string;
  ceremony_auditee_token: string;
};

function fixture(): LiveAuditFixture {
  const path = process.env.E2E_QMS_LIVE_FIXTURE || "/tmp/qms-live-audit-real-e2e.json";
  return JSON.parse(fs.readFileSync(path, "utf-8")) as LiveAuditFixture;
}

function watchServerFailures(page: Page, failures: string[]): void {
  page.on("response", (response: Response) => {
    const url = new URL(response.url());
    if (response.status() >= 500 && (url.pathname.startsWith("/quality/") || url.pathname.startsWith("/api/"))) {
      failures.push(`${response.request().method()} ${url.pathname} -> ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
}

async function loginInternalUser(context: BrowserContext, options: { amoSlug: string; email: string; password: string }): Promise<Page> {
  const page = await context.newPage();
  await page.goto(`/maintenance/${options.amoSlug}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email", { exact: true }).fill(options.email);
  await page.getByLabel("Password", { exact: true }).fill(options.password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
    page.getByRole("button", { name: "Sign In" }).click(),
  ]);
  return page;
}

async function installVirtualPasskey(context: BrowserContext, page: Page): Promise<{ client: CDPSession; authenticatorId: string }> {
  const client = await context.newCDPSession(page);
  await client.send("WebAuthn.enable");
  const { authenticatorId } = await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return { client, authenticatorId };
}

async function removeVirtualPasskey(client: CDPSession, authenticatorId: string): Promise<void> {
  await client.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId });
  await client.send("WebAuthn.disable");
  await client.detach();
}

const mutationRoute = "**/quality/audit-access/fieldwork/checklist-items/**/mutations";

test("real browsers prove two-party persistence, offline replay, exactly-once recovery and stale-version conflict through FastAPI/PostgreSQL", async ({ browser }) => {
  const data = fixture();
  const externalFailures: string[] = [];
  const auditeeFailures: string[] = [];
  const staleFailures: string[] = [];
  const externalContext = await browser.newContext();
  const auditeeContext = await browser.newContext();
  const staleContext = await browser.newContext();

  try {
    const externalPage = await externalContext.newPage();
    watchServerFailures(externalPage, externalFailures);
    await externalPage.goto(`/qms/audit-access/${encodeURIComponent(data.external_auditor_token)}`, { waitUntil: "domcontentloaded" });
    await expect(externalPage.getByRole("heading", { name: new RegExp(`${data.audit_ref} · Real browser live audit acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(externalPage).toHaveURL(/\/qms\/audit-access$/);
    await expect(externalPage.getByText("Assigned audit checklist")).toBeVisible();
    await expect(externalPage.getByText("0%", { exact: true })).toBeVisible();

    const auditeePage = await auditeeContext.newPage();
    watchServerFailures(auditeePage, auditeeFailures);
    await auditeePage.goto(`/qms/audit-access/${encodeURIComponent(data.auditee_token)}`, { waitUntil: "domcontentloaded" });
    await expect(auditeePage.getByRole("heading", { name: new RegExp(`${data.audit_ref} · Real browser live audit acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(auditeePage).toHaveURL(/\/qms\/audit-access$/);
    await expect(auditeePage.getByText("0%", { exact: true })).toBeVisible();
    await expect(auditeePage.getByText("A superseded controlled procedure was available at a sampled point of use.")).toBeVisible();

    const fieldwork = externalPage.getByLabel("External auditor fieldwork");
    const firstNote = "Verified in the real browser against the controlled DMS revision.";
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(firstNote);
    await fieldwork.getByRole("button", { name: "Compliant" }).click();
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v2" })).toBeVisible({ timeout: 30_000 });

    await auditeePage.getByRole("button", { name: "Refresh" }).click();
    await expect(auditeePage.getByText("100%", { exact: true })).toBeVisible({ timeout: 30_000 });

    await auditeePage.getByRole("button", { name: "Acknowledge finding" }).click();
    await expect(auditeePage.getByText(/Finding receipt recorded/)).toBeVisible();
    await expect(auditeePage.getByText(/Receipt acknowledged/)).toBeVisible();

    const offlineNote = "Queued while offline and replayed after session revalidation.";
    await externalContext.setOffline(true);
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(offlineNote);
    await fieldwork.getByRole("button", { name: "N/A" }).click();
    await expect(fieldwork.getByText(/Offline: fieldwork change encrypted locally/i)).toBeVisible();
    await expect(fieldwork.getByText("1 encrypted change pending sync", { exact: true })).toBeVisible();
    await externalContext.setOffline(false);
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 NOT APPLICABLE · v3" })).toBeVisible({ timeout: 30_000 });
    await expect(fieldwork.getByText("No pending fieldwork changes", { exact: true })).toBeVisible();

    let committedBeforeResponseLoss = false;
    await externalPage.route(mutationRoute, async (route) => {
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      committedBeforeResponseLoss = true;
      await route.abort("connectionfailed");
    }, { times: 1 });
    const lostResponseNote = "Server committed this mutation before its response was deliberately lost.";
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(lostResponseNote);
    await fieldwork.getByRole("button", { name: "Compliant" }).click();
    await expect.poll(() => committedBeforeResponseLoss).toBe(true);
    await expect(fieldwork.getByText(/exact idempotent mutation was encrypted locally for replay/i)).toBeVisible();
    await expect(fieldwork.getByText("1 encrypted change pending sync", { exact: true })).toBeVisible();
    await externalPage.unroute(mutationRoute);
    await fieldwork.getByRole("button", { name: "Sync now" }).click();
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v4" })).toBeVisible({ timeout: 30_000 });
    await expect(fieldwork.getByText("No pending fieldwork changes", { exact: true })).toBeVisible();

    const stalePage = await staleContext.newPage();
    watchServerFailures(stalePage, staleFailures);
    await stalePage.goto(`/qms/audit-access/${encodeURIComponent(data.external_auditor_token)}`, { waitUntil: "domcontentloaded" });
    const staleFieldwork = stalePage.getByLabel("External auditor fieldwork");
    await expect(staleFieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v4" })).toBeVisible({ timeout: 30_000 });

    const authoritativeNote = "Authoritative v5 update from the first external-auditor browser.";
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(authoritativeNote);
    await fieldwork.getByRole("button", { name: "N/A" }).click();
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 NOT APPLICABLE · v5" })).toBeVisible({ timeout: 30_000 });

    await staleFieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill("This stale v4 edit must not overwrite v5.");
    await staleFieldwork.getByRole("button", { name: "Compliant" }).click();
    await expect(staleFieldwork.getByRole("alert")).toContainText(/changed on the server|newer authoritative version/i);
    await expect(staleFieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v4" })).toBeVisible();

    await externalPage.reload({ waitUntil: "domcontentloaded" });
    const reloadedFieldwork = externalPage.getByLabel("External auditor fieldwork");
    await expect(reloadedFieldwork.getByRole("button", { name: "CHK-LIVE-001 NOT APPLICABLE · v5" })).toBeVisible({ timeout: 30_000 });
    await expect(reloadedFieldwork.getByRole("textbox", { name: "My attributable fieldwork note" })).toHaveValue(authoritativeNote);

    await auditeePage.reload({ waitUntil: "domcontentloaded" });
    await expect(auditeePage.getByText("100%", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(auditeePage.getByText(/Receipt acknowledged/)).toBeVisible();

    expect(externalFailures).toEqual([]);
    expect(auditeeFailures).toEqual([]);
    expect(staleFailures).toEqual([]);
  } finally {
    await Promise.allSettled([externalContext.close(), auditeeContext.close(), staleContext.close()]);
  }
});

test("two authenticated Quality browsers receive the same committed live-audit checklist update through SSE without refresh", async ({ browser }) => {
  const data = fixture();
  const failuresA: string[] = [];
  const failuresB: string[] = [];
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();

  try {
    const pageA = await loginInternalUser(contextA, {
      amoSlug: data.amo_slug,
      email: data.realtime_user_a_email,
      password: data.realtime_password,
    });
    const pageB = await loginInternalUser(contextB, {
      amoSlug: data.amo_slug,
      email: data.realtime_user_b_email,
      password: data.realtime_password,
    });
    watchServerFailures(pageA, failuresA);
    watchServerFailures(pageB, failuresB);

    const livePath = `/maintenance/${data.amo_slug}/quality/audits/${encodeURIComponent(data.realtime_audit_ref)}/live`;
    await Promise.all([
      pageA.goto(livePath, { waitUntil: "domcontentloaded" }),
      pageB.goto(livePath, { waitUntil: "domcontentloaded" }),
    ]);

    await expect(pageA.getByText("Concurrent realtime browser acceptance")).toBeVisible({ timeout: 30_000 });
    await expect(pageB.getByText("Concurrent realtime browser acceptance")).toBeVisible({ timeout: 30_000 });
    await expect(pageA.getByText("Verify concurrent authenticated browsers receive committed fieldwork updates without manual refresh.")).toBeVisible();
    await expect(pageB.getByText("Verify concurrent authenticated browsers receive committed fieldwork updates without manual refresh.")).toBeVisible();

    await expect(pageA.locator("html")).toHaveAttribute("data-qms-realtime-state", "connected", { timeout: 30_000 });
    await expect(pageB.locator("html")).toHaveAttribute("data-qms-realtime-state", "connected", { timeout: 30_000 });

    const note = "Committed by Quality Alpha and delivered to Quality Bravo by the authenticated SSE stream.";
    await pageA.getByLabel("Auditor note").fill(note);
    await pageA.getByRole("button", { name: "Compliant", exact: true }).click();
    await expect(pageA.getByText("Saved to the authoritative audit record.")).toBeVisible({ timeout: 30_000 });

    // Browser B receives no click, focus, reload or explicit refresh. The only
    // admissible cause of this change is the authenticated audit-scoped SSE event
    // invalidating its occurrence-scoped React Query cache after A's DB commit.
    await expect(pageB.getByRole("button", { name: "Compliant", exact: true })).toHaveClass(/is-active/, { timeout: 30_000 });
    await expect(pageB.getByLabel("Auditor note")).toHaveValue(note, { timeout: 30_000 });

    expect(failuresA).toEqual([]);
    expect(failuresB).toEqual([]);
  } finally {
    await Promise.allSettled([contextA.close(), contextB.close()]);
  }
});

test("same-day closing performs exact-SHA auditee acknowledgement, real WebAuthn approval, issue, verification, execution close and governed archive", async ({ browser }) => {
  const data = fixture();
  const internalFailures: string[] = [];
  const auditeeFailures: string[] = [];
  const verificationFailures: string[] = [];
  const internalContext = await browser.newContext();
  const auditeeContext = await browser.newContext();
  const verificationContext = await browser.newContext();
  let virtualPasskey: { client: CDPSession; authenticatorId: string } | null = null;

  try {
    const internalPage = await loginInternalUser(internalContext, {
      amoSlug: data.amo_slug,
      email: data.realtime_user_a_email,
      password: data.realtime_password,
    });
    watchServerFailures(internalPage, internalFailures);
    virtualPasskey = await installVirtualPasskey(internalContext, internalPage);

    const closingPath = `/maintenance/${data.amo_slug}/quality/audits/${encodeURIComponent(data.ceremony_audit_ref)}/closing?tab=report`;
    await internalPage.goto(closingPath, { waitUntil: "domcontentloaded" });
    await expect(internalPage.getByRole("heading", { name: new RegExp(`${data.ceremony_audit_ref} · Same-day closing and archive browser acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(internalPage.getByText("0", { exact: true }).last()).toBeVisible();

    const generate = internalPage.getByRole("button", { name: "Generate closing report draft" });
    await expect(generate).toBeEnabled();
    await generate.click();
    await expect(internalPage.getByRole("status")).toContainText("Closing report snapshot generated", { timeout: 30_000 });
    await expect(internalPage.getByText("Artifact SHA-256")).toBeVisible();

    const downloadPromise = internalPage.waitForEvent("download");
    await internalPage.getByRole("button", { name: "Preview / download" }).click();
    const generatedDownload = await downloadPromise;
    expect(await generatedDownload.path()).toBeTruthy();

    await internalPage.getByRole("button", { name: "Adopt governed draft" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Generated report adopted as a governed draft revision", { timeout: 30_000 });
    await expect(internalPage.getByText(/R1 · DRAFT/i)).toBeVisible();
    const draftSha = await internalPage.locator("dt", { hasText: "SHA-256" }).locator("..").locator("code").first().innerText();
    expect(draftSha).toMatch(/^[0-9a-f]{64}$/i);

    const auditeePage = await auditeeContext.newPage();
    watchServerFailures(auditeePage, auditeeFailures);
    await auditeePage.goto(`/qms/audit-access/${encodeURIComponent(data.ceremony_auditee_token)}`, { waitUntil: "domcontentloaded" });
    await expect(auditeePage.getByRole("heading", { name: new RegExp(`${data.ceremony_audit_ref} · Same-day closing and archive browser acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(auditeePage.getByLabel("Closing meeting acknowledgement")).toBeVisible({ timeout: 30_000 });
    await expect(auditeePage.getByText(data.ceremony_car_number)).toBeVisible();
    await auditeePage.getByLabel("Comments").fill("Closing draft reviewed during the same-day closing meeting; receipt acknowledged without waiving CAR response rights.");
    await auditeePage.getByRole("button", { name: "Record closing response" }).click();
    await expect(auditeePage.getByRole("status")).toContainText("Closing-meeting response recorded against the exact draft revision and SHA-256", { timeout: 30_000 });

    await internalPage.getByRole("button", { name: "Refresh" }).click();
    await expect(internalPage.getByText(/ACKNOWLEDGED/i)).toBeVisible({ timeout: 30_000 });
    await internalPage.getByRole("button", { name: "Submit acknowledged draft for review" }).click();
    await expect(internalPage.getByRole("status")).toContainText("SUBMIT recorded", { timeout: 30_000 });
    await internalPage.getByRole("button", { name: "Approve exact report revision" }).click();
    await expect(internalPage.getByRole("status")).toContainText("APPROVE recorded", { timeout: 30_000 });
    await expect(internalPage.getByText(/R1 is approved and locked to SHA-256/i)).toBeVisible();

    await expect(internalPage.getByRole("button", { name: "Issue passkey-approved report" })).toBeDisabled();
    await internalPage.getByRole("button", { name: "Register passkey" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Passkey registered for governed Quality approvals", { timeout: 30_000 });
    await internalPage.getByRole("button", { name: "Approve exact report with passkey" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Passkey approval recorded against the exact approved report SHA-256", { timeout: 30_000 });
    await expect(internalPage.getByText("WEBAUTHN", { exact: true })).toBeVisible();

    const issue = internalPage.getByRole("button", { name: "Issue passkey-approved report" });
    await expect(issue).toBeEnabled();
    await issue.click();
    await expect(internalPage.getByRole("status")).toContainText("ISSUE recorded", { timeout: 30_000 });
    await expect(internalPage.getByText(/Issued R1/i)).toBeVisible();

    await internalPage.getByRole("button", { name: "Create public verification link" }).click();
    await expect(internalPage.getByRole("status")).toContainText("purpose-bound verification link was created", { timeout: 30_000 });
    const verificationHref = await internalPage.getByText("Verification URL").locator("..").getByRole("link").getAttribute("href");
    expect(verificationHref).toBeTruthy();

    const verificationPage = await verificationContext.newPage();
    watchServerFailures(verificationPage, verificationFailures);
    await verificationPage.goto(verificationHref!, { waitUntil: "domcontentloaded" });
    await expect(verificationPage.getByRole("heading", { name: new RegExp(`${data.ceremony_audit_ref} · Same-day closing and archive browser acceptance`, "i") })).toBeVisible({ timeout: 30_000 });
    await expect(verificationPage.getByText("Valid governed record")).toBeVisible();
    await expect(verificationPage.getByText("WEBAUTHN", { exact: true })).toBeVisible();
    const governedSha = (await verificationPage.locator("dt", { hasText: "Governed SHA-256" }).locator("..").locator("code").innerText()).trim();
    expect(governedSha).toBe(draftSha);
    await verificationPage.getByLabel("SHA-256").fill(governedSha);
    await verificationPage.getByRole("button", { name: "Compare hash" }).click();
    await expect(verificationPage.getByRole("status")).toContainText("Hash matches the governed artifact", { timeout: 30_000 });

    await auditeePage.getByRole("button", { name: "Refresh" }).click();
    await expect(auditeePage.getByLabel("Issued audit report")).toBeVisible({ timeout: 30_000 });
    const issuedDownloadPromise = auditeePage.waitForEvent("download");
    await auditeePage.getByRole("button", { name: "Download issued report" }).click();
    const issuedDownload = await issuedDownloadPromise;
    expect(await issuedDownload.path()).toBeTruthy();
    await auditeePage.getByRole("button", { name: "Acknowledge issued report" }).click();
    await expect(auditeePage.getByRole("status")).toContainText("Issued-report receipt recorded against the exact issued revision and checksum", { timeout: 30_000 });

    const closeExecution = internalPage.getByRole("button", { name: "Close audit execution" });
    await expect(closeExecution).toBeEnabled();
    await closeExecution.click();
    await expect(internalPage.getByRole("status")).toContainText("Execution closed. CAR/CAPA follow-up remains open", { timeout: 30_000 });
    await expect(internalPage.getByText(/CAR status is OPEN/i)).toBeVisible();

    const archivePath = `/maintenance/${data.amo_slug}/quality/audits/${encodeURIComponent(data.ceremony_audit_ref)}/archive?tab=evidence`;
    await internalPage.goto(archivePath, { waitUntil: "domcontentloaded" });
    await expect(internalPage.getByRole("region", { name: "Audit archive and retention workspace" })).toBeVisible({ timeout: 30_000 });
    await expect(internalPage.getByText("QMS-AUDIT-7Y", { exact: true })).toBeVisible();
    await internalPage.getByRole("button", { name: "Generate governed archive" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Immutable archive manifest and package generated", { timeout: 30_000 });
    await expect(internalPage.getByText("CAR · 1", { exact: true })).toBeVisible();
    await expect(internalPage.getByText("SIGNATURE EVIDENCE · 1", { exact: true })).toBeVisible();
    await expect(internalPage.getByText("REPORT REVISION · 1", { exact: true })).toBeVisible();

    const archiveDownloadPromise = internalPage.waitForEvent("download");
    await internalPage.getByRole("button", { name: "Download verified package" }).click();
    const archiveDownload = await archiveDownloadPromise;
    expect(await archiveDownload.path()).toBeTruthy();

    await internalPage.getByLabel("Legal hold reference").fill("CASE-QMS-LIVE-992");
    await internalPage.getByLabel("Legal hold reason").fill("Preserve the completed acceptance audit while legal-hold controls are exercised.");
    await internalPage.getByLabel("Legal hold governing basis").fill("Governed Quality archive acceptance and retention control validation.");
    await internalPage.getByRole("button", { name: "Place legal hold" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Legal hold placed", { timeout: 30_000 });
    await expect(internalPage.getByText("CASE-QMS-LIVE-992", { exact: true })).toBeVisible();
    await internalPage.getByRole("button", { name: "Release" }).click();
    await expect(internalPage.getByRole("status")).toContainText("Legal hold released with an append-only release event", { timeout: 30_000 });
    await expect(internalPage.getByText("No active legal holds.")).toBeVisible();

    expect(internalFailures).toEqual([]);
    expect(auditeeFailures).toEqual([]);
    expect(verificationFailures).toEqual([]);
  } finally {
    if (virtualPasskey) await removeVirtualPasskey(virtualPasskey.client, virtualPasskey.authenticatorId).catch(() => undefined);
    await Promise.allSettled([internalContext.close(), auditeeContext.close(), verificationContext.close()]);
  }
});

import fs from "node:fs";
import { expect, test, type BrowserContext, type Page, type Response } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(120_000);

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

async function loginInternalUser(context: BrowserContext, *, amoSlug: string, email: string, password: string): Promise<Page> {
  const page = await context.newPage();
  await page.goto(`/maintenance/${amoSlug}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email or staff code").fill(email);
  await page.getByLabel("Password").fill(password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
    page.getByRole("button", { name: "Sign In" }).click(),
  ]);
  return page;
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

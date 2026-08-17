import fs from "node:fs";
import { expect, test, type Page, type Response } from "@playwright/test";

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

    // The auditee is a separate browser context with a separate HTTP-only guest
    // session. Its server-filtered projection must observe the row committed by
    // the external auditor through FastAPI/PostgreSQL.
    await auditeePage.getByRole("button", { name: "Refresh" }).click();
    await expect(auditeePage.getByText("100%", { exact: true })).toBeVisible({ timeout: 30_000 });

    await auditeePage.getByRole("button", { name: "Acknowledge finding" }).click();
    await expect(auditeePage.getByText(/Finding receipt recorded/)).toBeVisible();
    await expect(auditeePage.getByText(/Receipt acknowledged/)).toBeVisible();

    // Queue a real structured fieldwork mutation while the browser is offline.
    // Reconnection must revalidate the HTTP-only session and replay the original
    // mutation identity into PostgreSQL.
    const offlineNote = "Queued while offline and replayed after session revalidation.";
    await externalContext.setOffline(true);
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(offlineNote);
    await fieldwork.getByRole("button", { name: "N/A" }).click();
    await expect(fieldwork.getByText(/Offline: fieldwork change encrypted locally/i)).toBeVisible();
    await expect(fieldwork.getByText("1 encrypted change pending sync", { exact: true })).toBeVisible();
    await externalContext.setOffline(false);
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 NOT APPLICABLE · v3" })).toBeVisible({ timeout: 30_000 });
    await expect(fieldwork.getByText("No pending fieldwork changes", { exact: true })).toBeVisible();

    // Simulate the hardest exactly-once case without mocking the backend: let the
    // real request reach FastAPI/PostgreSQL and commit, then drop only its response.
    // The UI must queue the same client_mutation_id; replay must return the stored
    // receipt rather than apply a second database mutation.
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

    // Open a second external-auditor browser on v4, then advance the authoritative
    // row in the first browser. The stale browser must receive a real 409 and must
    // not overwrite the newer version.
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

    // Reload independent sessions. Browser memory cannot satisfy these assertions;
    // the final v5 fieldwork and auditee receipt must be reconstructed from DB.
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

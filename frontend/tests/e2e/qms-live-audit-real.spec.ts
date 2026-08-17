import fs from "node:fs";
import { expect, test, type Page, type Response } from "@playwright/test";

test.use({ trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });
test.setTimeout(90_000);

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

test("real concurrent external-auditor and auditee browsers persist fieldwork and released-finding receipt through FastAPI/PostgreSQL", async ({ browser }) => {
  const data = fixture();
  const externalFailures: string[] = [];
  const auditeeFailures: string[] = [];
  const externalContext = await browser.newContext();
  const auditeeContext = await browser.newContext();

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
    const note = "Verified in the real browser against the controlled DMS revision.";
    await fieldwork.getByRole("textbox", { name: "My attributable fieldwork note" }).fill(note);
    await fieldwork.getByRole("button", { name: "Compliant" }).click();
    await expect(fieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v2" })).toBeVisible({ timeout: 30_000 });

    // The auditee is a separate browser context with a separate HTTP-only guest
    // session. Refreshing its server-filtered projection must observe the row
    // committed by the external auditor through FastAPI/PostgreSQL.
    await auditeePage.getByRole("button", { name: "Refresh" }).click();
    await expect(auditeePage.getByText("100%", { exact: true })).toBeVisible({ timeout: 30_000 });

    await auditeePage.getByRole("button", { name: "Acknowledge finding" }).click();
    await expect(auditeePage.getByText(/Finding receipt recorded/)).toBeVisible();
    await expect(auditeePage.getByText(/Receipt acknowledged/)).toBeVisible();

    // Reload both independently. The committed checklist version, external
    // attribution and auditee receipt must be reconstructed from PostgreSQL;
    // browser memory alone cannot satisfy these assertions.
    await externalPage.reload({ waitUntil: "domcontentloaded" });
    const reloadedFieldwork = externalPage.getByLabel("External auditor fieldwork");
    await expect(reloadedFieldwork.getByRole("button", { name: "CHK-LIVE-001 COMPLIANT · v2" })).toBeVisible({ timeout: 30_000 });
    await expect(reloadedFieldwork.getByRole("textbox", { name: "My attributable fieldwork note" })).toHaveValue(note);

    await auditeePage.reload({ waitUntil: "domcontentloaded" });
    await expect(auditeePage.getByText("100%", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(auditeePage.getByText(/Receipt acknowledged/)).toBeVisible();

    expect(externalFailures).toEqual([]);
    expect(auditeeFailures).toEqual([]);
  } finally {
    await Promise.allSettled([externalContext.close(), auditeeContext.close()]);
  }
});

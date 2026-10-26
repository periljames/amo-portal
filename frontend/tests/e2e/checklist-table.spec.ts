import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

test.beforeEach(async ({ page }) => {
  await page.route("**/__checklist_table__", (route) => route.fulfill({ contentType: "text/html", body: '<html><body style="margin:0"><div id="root"></div></body></html>' }));
  await page.goto("/__checklist_table__");
  await page.evaluate(async () => {
    const { default: RefreshRuntime } = await import(/* @vite-ignore */ "/@react-refresh");
    RefreshRuntime.injectIntoGlobalHook(window);
    Object.assign(window, { $RefreshReg$: () => {}, $RefreshSig$: () => (type: unknown) => type, __vite_plugin_react_preamble_installed__: true });
    const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/checklistTableHarness.tsx");
    fixture.mount();
  });
});

test("source columns, original order, inline remarks and pending answers work in the table", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const table = page.getByRole("table", { name: "Checklist assessment table" });
  await expect(table.getByRole("columnheader")).toHaveText(["No.", "Checklist question", "S", "U", "N/C", "N/A", "Remarks / evidence", "Context"]);
  await expect(table.getByRole("radio", { name: "S — question 1", exact: true })).toBeChecked();
  await expect(table.getByRole("radio", { name: "N/C — question 3", exact: true })).not.toBeChecked();
  const question2 = table.getByRole("radio", { name: "S — question 2", exact: true });
  await question2.check();
  await expect(question2).toBeChecked();
  await expect(page.getByRole("progressbar", { name: "Checklist progress" })).toHaveAttribute("value", "1");
  await expect(table.getByText("Saved on device · awaiting sync")).toBeVisible();
  await table.getByRole("textbox", { name: "Remarks for question 2" }).fill("Reviewed training records.");
  await table.getByRole("button", { name: "Save remarks" }).click();
  await expect(table.getByRole("textbox", { name: "Remarks for question 2" })).toHaveValue("Reviewed training records.");
  await expect(table.getByRole("button", { name: "Save remarks" })).toHaveCount(0);
  await table.getByRole("button", { name: "Evidence and details for question 2" }).click();
  await expect(table.getByRole("button", { name: "Evidence and details for question 2" })).toHaveAttribute("aria-expanded", "true");
  await expect(table.locator("tbody tr").nth(1)).toContainText("Is there a description and organogram?");
  const notChecked = table.getByRole("radio", { name: "N/C — question 3", exact: true });
  await notChecked.focus();
  await page.keyboard.press("Space");
  await expect(notChecked).toBeChecked();
  await page.screenshot({ path: info.outputPath("checklist-desktop.png"), fullPage: true });
});

test("small screens keep each question, source choices and remarks together", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("table")).toBeVisible();
  const dimensions = await page.locator(".audit-checklist-table-scroll").evaluate((element) => ({
    scroll: element.scrollWidth, width: element.clientWidth,
    page: document.documentElement.scrollWidth, viewport: innerWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
  await expect(page.getByRole("radio", { name: "S — question 1", exact: true })).toBeVisible();
  await expect(page.getByRole("radio", { name: "N/A — question 1", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Remarks for question 1" }).fill("Mobile note");
  await expect(page.getByRole("textbox", { name: "Remarks for question 1" })).toHaveValue("Mobile note");
  await page.screenshot({ path: info.outputPath("checklist-mobile.png"), fullPage: true });
});

test("search shortcuts, clear, filter and section navigation work in the full workspace", async ({ page }) => {
  await page.keyboard.press("/");
  const search = page.getByRole("textbox", { name: "Search checklist" });
  await expect(search).toBeFocused();
  await search.fill("risk assessments");
  await expect(page.getByRole("table").getByRole("radio")).toHaveCount(4);
  await expect(page.getByText("1 of 3 questions", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear checklist search" }).click();
  await expect(search).toHaveValue("");
  await page.getByRole("combobox", { name: "Filter checklist" }).selectOption("UNANSWERED");
  await expect(page.getByRole("table").getByRole("radio")).toHaveCount(8);
  await page.getByRole("combobox", { name: "Jump to section" }).selectOption("third");
  await expect(page.locator("#audit-section-third")).toBeVisible();
  await search.fill("no matching question");
  await expect(page.getByText("No questions match this filter.")).toBeVisible();
  await search.press("Escape");
  await expect(search).toHaveValue("");
});

test("actual uploaded checklist remains readable with all 172 rows", async ({ page }, info) => {
  const root = resolve(process.cwd(), "..");
  const source = resolve(root, "backend/uploads/manuals/safarilink/SL_QMS_20/ID-8YK4VWD6/SL-QMS-20_Contractors_Audit_Checklist.docx");
  const python = resolve(root, ".venv/Scripts/python.exe");
  test.skip(!existsSync(source) || !existsSync(python), "Local controlled source and Python environment are required");
  const script = "import importlib.util,json,sys,pathlib;spec=importlib.util.spec_from_file_location('parser',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);p=pathlib.Path(sys.argv[2]);print(json.dumps(m.draft_from_upload(p.read_bytes(),p.name)['items']))";
  const rows = JSON.parse(execFileSync(python, ["-c", script, resolve(root, "backend/amodb/apps/quality/audit_checklist_upload_parser.py"), source], { encoding: "utf8" }));
  await page.evaluate(async (items) => { const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/checklistTableHarness.tsx"); fixture.mount(items); }, rows);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(page.getByText("172 questions", { exact: true })).toBeVisible();
  await expect(page.getByRole("table").getByRole("radio")).toHaveCount(688);
  await expect(page.getByRole("table")).not.toContainText("Date of Audit:");
  await page.screenshot({ path: info.outputPath("uploaded-checklist-desktop.png"), fullPage: true });
  const jump = page.getByRole("combobox", { name: "Jump to section" });
  const last = await jump.locator("option").last().getAttribute("value");
  await jump.selectOption(last!);
  await expect(page.locator(`#audit-section-${last}`)).toBeInViewport();
});

test("offline and read-only states stay visible and prevent editing", async ({ page }, info) => {
  await page.evaluate(async () => { const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/checklistTableHarness.tsx"); fixture.mount(undefined, { readOnly: true, connectivity: "OFFLINE", pendingStatus: "conflict" }); });
  await expect(page.getByText("Read-only", { exact: true })).toBeVisible();
  await expect(page.getByText("1 awaiting sync", { exact: true })).toBeVisible();
  await expect(page.getByRole("radio", { name: "S — question 1", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "Remarks for question 1" })).toHaveAttribute("readonly", "");
  await expect(page.getByText("Sync needs review", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("checklist-offline-readonly.png"), fullPage: true });
});


test("details open immediately beneath their question and answer labels stay visible", async ({ page }) => {
  await page.getByRole("button", { name: "Evidence and details for question 2" }).click();
  const detail = page.getByRole("region", { name: "Question context" });
  await expect(detail).toBeVisible();
  expect(await detail.evaluate((element) => element.closest("tr")?.previousElementSibling?.querySelector(".audit-checklist-table__question")?.textContent)).toContain("approved key post holders");
  await expect(page.locator(".audit-checklist-table__mobile-choice").first()).toBeVisible();
  const header = await page.locator(".audit-fieldwork-header").boundingBox();
  expect(header!.height).toBeLessThan(110);
});

test("paperclip offers upload and camera and retains encrypted evidence offline", async ({ page, context }) => {
  await page.evaluate(() => localStorage.setItem("amo_current_user", JSON.stringify({ id: "fixture-auditor", amo_id: "test-amo" })));
  const attachment = page.locator(".audit-question-attachments").first();
  await attachment.locator("summary").click();
  await expect(attachment.getByRole("button", { name: "Upload files" })).toBeVisible();
  await expect(attachment.getByRole("button", { name: "Take photo" })).toBeVisible();
  await expect(attachment.locator('input[capture="environment"]')).toHaveAttribute("accept", "image/*");
  await context.setOffline(true);
  await attachment.locator('input[multiple]').setInputFiles({ name: "inspection.txt", mimeType: "text/plain", buffer: Buffer.from("Inspection evidence") });
  await expect(attachment.getByRole("alert")).toHaveCount(0);
  await expect.poll(async () => page.evaluate(async () => {
    const module = await import(/* @vite-ignore */ "/src/services/qmsOfflineAuditEvidence.ts");
    return (await module.listOfflineAuditEvidence("test-amo", "audit")).length;
  })).toBe(1);
  await context.setOffline(false);
  await page.reload();
  expect(await page.evaluate(async () => {
    const module = await import(/* @vite-ignore */ "/src/services/qmsOfflineAuditEvidence.ts");
    return (await module.listOfflineAuditEvidence("test-amo", "audit"))[0].filename;
  })).toBe("inspection.txt");
});

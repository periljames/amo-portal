import { expect, test, type Page } from "@playwright/test";
import { QMS_ROUTE_REGISTRY } from "../../src/pages/qms/routes/qmsRouteRegistry";
import { mockQualityShell } from "./helpers/mockQualityShell";

async function prepare(page: Page, admin = false) {
  await mockQualityShell(page);
  const configuration = { numbering_rules: { audit_prefix: "QAR", sequence_digits: 4 }, workflow_rules: { require_review: true }, notification_rules: {}, retention_rules: {} };
  let active = false;
  const periods: string[] = [];
  const writes: unknown[] = [];
  await page.route("**/*", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (["document", "stylesheet", "script", "image", "font", "media", "manifest"].includes(request.resourceType())) return route.fallback();
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (path.includes("/admin-profile/")) {
      if (path.endsWith("/activate")) { periods.push(request.postDataJSON().period); active = true; }
      if (path.endsWith("/deactivate")) active = false;
      return json({ eligible: admin, active, session_id: active ? "fixture-session" : null, expires_at: active ? new Date(Date.now() + 4 * 3600000).toISOString() : null, grant_type: "PERMANENT" });
    }
    if (path.endsWith("/quality/settings")) {
      if (request.method() === "PATCH") { writes.push(request.postDataJSON()); Object.assign(configuration, request.postDataJSON()); }
      return json({ settings: configuration, compliance_policy: { version: "MOPM-4-00", source: "MOPM Issue 4", retention: [{ code: "MAINTENANCE_RECORDS", label: "Maintenance work packages and releases", event: "release_signed_at", years: 3, days: 0, reference: "MOPM 2.14.1.2; AMO Regulation 34(3)", regulatory_minimum_years: 2 }], contracting: { maximum_supplier_review_days: 365, reference: "MOPM 2.23; 3.13" } } });
    }
    if (path.endsWith("/quality/mail-identity")) return json({ tenant_name: "Tenant A", shared_domain: "example.test", shared_sender: "quality@example.test", custom_domains: [], from_name: "Quality", from_email: "quality@example.test", reply_to: "", effective_reply_to: "quality@example.test", reply_mode: "QUALITY_ROLES", sender_mode: "SHARED", enabled: true, can_manage: true, provider_status: "READY", sending_mode: "SANDBOX", ready: true });
    if (path.startsWith("/api/maintenance/") && path.includes("/quality/")) return json({ items: [{ id: "record-1", title: "Scheduled Quality review", status: "OPEN", due_date: "2026-11-01" }], columns: ["title", "status", "due_date"], limit: 30, offset: 0, total: 1, has_more: false });
    return route.fallback();
  });
  await page.addInitScript(({ admin }) => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "quality-user-a", amo_id: "amo-a", amo_slug: "tenant-a", amo_code: "AMO-A", department_code: "quality", role: "QUALITY_MANAGER", first_name: "Quality", last_name: "Manager", full_name: "Quality Manager", email: "quality@example.test", is_active: true, is_amo_admin: admin, is_superuser: false }));
  }, { admin });
  return { periods, writes };
}

test("settings is a configuration workspace and saves only changed policy groups", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  await expect(page.locator(".qms-settings-page h1")).toHaveText("Settings");
  await expect(page.getByRole("grid")).toHaveCount(0);
  await page.getByRole("button", { name: "Controls & settings", exact: true }).click();
  await page.locator(".qms-page-menu__panel summary").filter({ hasText: /^Settings$/ }).click();
  await page.getByRole("navigation", { name: "QMS controls and settings" }).getByRole("link", { name: "Numbering", exact: true }).click();
  await page.getByLabel("Audit Prefix").fill("QA");
  await expect(page.getByText("Unsaved changes", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved and recorded in Quality activity history.")).toBeVisible();
  expect(state.writes).toEqual([{ numbering_rules: { audit_prefix: "QA", sequence_digits: 4 } }]);
  await page.locator(".tenant-shell__main").evaluate(node => node.scrollTo(0, 0));
  await page.screenshot({ path: "../.artifacts/qms-settings-desktop.png", fullPage: true });
});

test("an available portal update leaves unsaved settings intact and remains reachable from the profile", async ({ page }) => {
  await prepare(page);
  await page.route("**/portal-precache.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ urls: ["/", "/assets/index-next-release.js"] }) }));
  await page.goto("/maintenance/tenant-a/quality/settings/numbering");
  await page.getByLabel("Audit Prefix").fill("DRAFT");
  const notice = page.getByRole("status", { name: "Portal update available" });
  await expect(notice).toBeVisible();
  await expect(page.getByLabel("Audit Prefix")).toHaveValue("DRAFT");
  await notice.getByRole("button", { name: "Later", exact: true }).click();
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Account and appearance" }).click();
  await expect(page.getByRole("menuitem", { name: "Reload portal update", exact: true })).toBeVisible();
  await expect(page.getByLabel("Audit Prefix")).toHaveValue("DRAFT");
});

test("switching registers never shows the previous page's rows under the new title", async ({ page }) => {
  await prepare(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/quality/system/processes?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ id: "process-one", title: "Only the process register owns this row" }], columns: ["title"] }) }));
  await page.route("**/quality/risk/register?**", async route => { await pending; await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], columns: ["title"], total: 0, has_more: false }) }); });
  await page.goto("/maintenance/tenant-a/quality/system/processes");
  await expect(page.getByText("Only the process register owns this row", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Assurance", exact: true }).click();
  const panel = page.locator(".qms-page-menu__panel");
  await panel.locator("summary").filter({ hasText: /^Risk & Opportunities$/ }).click();
  await panel.getByRole("link", { name: "Register", exact: true }).click();
  try {
    await expect(page.getByRole("heading", { name: "Risk and Opportunities", exact: true })).toBeVisible();
    await expect(page.getByText("Only the process register owns this row", { exact: true })).toHaveCount(0);
    await expect(page.locator(".qms-register-loading")).toBeVisible();
  } finally { release(); }
  await expect(page.getByText("No records in this view", { exact: true })).toBeVisible();
  expect((await page.locator(".qms-register-empty").boundingBox())!.height).toBeLessThanOrEqual(130);
  await expect(page.locator(".qms-register-workspace .ag-root-wrapper")).toHaveCount(0);
});

test("retention settings preserve the MOPM floor and allow a longer tenant period", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/settings/retention");
  await expect(page.getByRole("heading", { name: "MOPM retention minimums" })).toBeVisible();
  const years = page.getByRole("spinbutton", { name: /^Tenant years/ });
  await expect(years).toHaveValue("3");
  await years.fill("2"); await years.blur();
  await expect(page.getByText("Enter a whole number of at least 3.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
  await years.fill("5");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved and recorded in Quality activity history.")).toBeVisible();
  expect(state.writes).toEqual([{ retention_rules: { extensions_years: { MAINTENANCE_RECORDS: 5 } } }]);
});

test("reply addresses use plus and remove controls with inline feedback before submission", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/mail-identity/overview");
  const displayName = page.getByRole("textbox", { name: /^Display name/ });
  await displayName.fill("A"); await displayName.blur();
  await expect(page.getByText("Use at least 2 characters.", { exact: true })).toBeVisible();
  await displayName.fill("Quality"); await displayName.blur();
  await page.getByRole("radio", { name: /Choose reply addresses/ }).check();
  const first = page.getByRole("textbox", { name: "Reply-To destinations 1", exact: true });
  await first.fill("broken-address"); await first.blur();
  await expect(page.getByText("Enter one complete email address, such as name@organization.com.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save mailing identity" })).toBeDisabled();
  await first.fill("quality@example.test"); await first.blur();
  await expect(first).not.toHaveAttribute("aria-invalid", "true");
  await page.getByRole("button", { name: "Add email", exact: true }).click();
  const second = page.getByRole("textbox", { name: "Reply-To destinations 2", exact: true });
  await second.fill("QUALITY@example.test"); await second.blur();
  await expect(page.getByText("This email address has already been added.", { exact: true })).toBeVisible();
  await second.fill("review@example.test"); await second.blur();
  await expect(page.getByRole("button", { name: "Save mailing identity" })).toBeEnabled();
  await page.getByRole("button", { name: "Remove email 2" }).click();
  await expect(second).toHaveCount(0);
  await page.screenshot({ path: "../.artifacts/qms-email-entry.png", fullPage: true });
});

test("QMS stays focused for an administrator and the profile offers all timed views", async ({ page }) => {
  const state = await prepare(page, true);
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "QMS navigation" });
  await expect(drawer.getByText("QMS App", { exact: true }).first()).toBeVisible();
  await expect(drawer.getByText("User Management", { exact: true })).toHaveCount(0);
  await expect(drawer.getByText("Procurement & Stores", { exact: true })).toHaveCount(0);
  await drawer.getByRole("button", { name: "Close navigation", exact: true }).click();
  await page.getByRole("button", { name: "Account and appearance" }).click();
  const period = page.getByLabel("Admin View duration", { exact: true });
  await expect(period).toHaveValue("FOUR_HOURS");
  await expect(period.locator("option")).toHaveCount(4);
  await period.selectOption("ONE_WEEK");
  await page.screenshot({ path: "../.artifacts/qms-admin-view.png", fullPage: true });
  await expect(page.getByRole("menuitem", { name: "Activate Admin View" })).toBeEnabled();
  await page.getByRole("menuitem", { name: "Activate Admin View" }).click();
  await expect(page).toHaveURL(/\/admin\/overview$/);
  expect(state.periods).toEqual(["ONE_WEEK"]);
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  await page.locator(".tenant-shell__main").evaluate(node => node.scrollTo(0, 200));
  const header = await page.locator(".tenant-shell__topbar").boundingBox();
  const controlButton = await page.getByText("Controls & settings", { exact: true }).boundingBox();
  expect(controlButton!.y).toBeGreaterThanOrEqual(header!.y + header!.height - 1);
  await page.getByRole("button", { name: "Account and appearance" }).click();
  await page.getByRole("menuitem", { name: "Turn off Admin View" }).click();
  await expect(page).toHaveURL(/\/quality$/);
});

test("controls remain reachable at narrow widths without covering the page", async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  await page.getByText("Controls & settings", { exact: true }).click();
  const controls = page.getByRole("navigation", { name: "QMS controls and settings" });
  await expect(controls.locator("summary").filter({ hasText: /^External Providers$/ })).toBeVisible();
  await expect(controls.locator("summary").filter({ hasText: /^Settings$/ })).toHaveCount(1);
  await expect(controls.getByText("Settings pages", { exact: true })).toHaveCount(0);
  await controls.locator("summary").filter({ hasText: /^Settings$/ }).click();
  await controls.getByRole("link", { name: "General", exact: true }).click();
  await expect(controls).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator(".tenant-shell__main").evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: "../.artifacts/qms-settings-mobile.png", fullPage: true });
});

test("one compact menu owns page navigation and the drawer has readable width", async ({ page }) => {
  await prepare(page, true);
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  const bar = page.getByRole("navigation", { name: "QMS page menus" });
  await expect(bar).toBeVisible();
  expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(48);
  await expect(page.locator(".quality-context-bar__tabs,.quality-context-bar__subtabs,.qa-workspace-rail,.qms-register-views")).toHaveCount(0);
  await bar.getByRole("button", { name: "Assurance", exact: true }).click();
  const assurance = page.getByRole("navigation", { name: "Assurance pages", exact: true });
  await assurance.locator("summary").filter({ hasText: /^Audits$/ }).click();
  await expect(assurance.getByRole("link", { name: "Checklists", exact: true })).toHaveAttribute("href", "/maintenance/tenant-a/quality/audits/checklists");
  await page.keyboard.press("Escape");
  await expect(assurance).toHaveCount(0);
  await expect(bar.getByRole("button", { name: "Assurance", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "QMS navigation" });
  expect((await drawer.boundingBox())!.width).toBeGreaterThanOrEqual(340);
});

test("settings keeps its configuration cards readable in dark appearance", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/settings/general");
  await page.getByRole("button", { name: "Account and appearance" }).click();
  await page.getByRole("menuitem", { name: "Appearance" }).click();
  await page.getByRole("combobox", { name: "Theme", exact: true }).selectOption("dark");
  await page.locator(".qms-settings__header h1").click();
  await expect(page.locator(".qms-settings__cards")).toBeVisible();
  await page.screenshot({ path: "../.artifacts/qms-settings-dark.png", fullPage: true });
});

test("qualification uses named templates and structured questions while retaining literal manual references", async ({ page }) => {
  await prepare(page);
  const saved: Array<Record<string, unknown>> = [];
  await page.route("**/api/maintenance/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/suppliers/providers/17")) return json({ id: 17, supplier_code: "PROV-17", legal_name: "Provider fixture", provider_kind: "SUPPLIER", risk_level: "MEDIUM", status: "APPROVED", active_scope_count: 1, active_contract_count: 1, verified_evidence_count: 0, allowed_transitions: [], approval_scopes: [], contracts: [], evidence: [] });
    if (path.endsWith("/supplier-governance/templates")) return json([{ id: "template-1", code: "EVAL-1", name: "Provider evaluation", revision_no: 2, status: "ACTIVE" }]);
    if (path.includes("/external-qualification/policies/") && route.request().method() === "PUT") { saved.push(route.request().postDataJSON()); return json({}); }
    if (path.endsWith("/external-qualification/policies")) return json({ items: [{ category: "SUBCONTRACTOR", revision: 1, evaluation_template_id: "template-1", questionnaire_json: [{ key: "BASIS", label: "Approval basis", kind: "TEXT", required: true }], manual_references_json: ["MPM 2.1"], surveillance_days: 90 }] });
    if (path.endsWith("/external-qualification/providers/17/overview")) return json({ cases: [], restrictions: [], audits: [], history: [], approved_scopes: [] });
    if (path.endsWith("/external-qualification/alerts")) return json({ overdue_qualification_reviews: [], overdue_cars: [] });
    return route.fallback();
  });
  await page.goto("/maintenance/tenant-a/quality/suppliers/17/qualification");
  await page.getByRole("button", { name: "policy", exact: true }).click();
  await expect(page.getByRole("combobox", { name: /Evaluation template/ })).toHaveValue("template-1");
  await expect(page.getByRole("option", { name: "EVAL-1 · Provider evaluation · Revision 2" })).toHaveCount(1);
  await expect(page.getByRole("textbox", { name: "Question 1 Question text", exact: true })).toHaveValue("Approval basis");
  await page.getByRole("textbox", { name: "Manual references 1", exact: true }).fill("MPM 2.1; Appendix A");
  await page.getByRole("textbox", { name: "Attributable rationale" }).fill("Review provider policy with current manual references.");
  await page.getByRole("button", { name: "Save Quality-approved policy" }).click();
  await expect.poll(() => saved.length).toBe(1);
  expect(saved[0].manual_references).toEqual(["MPM 2.1; Appendix A"]);
  expect(saved[0].evaluation_template_id).toBe("template-1");
  await page.screenshot({ path: "../.artifacts/qms-qualification-controls.png", fullPage: true });
});

test("reviews every shared QMS register view for rendering and navigation errors", async ({ page }) => {
  test.setTimeout(180000);
  await prepare(page);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const modules = QMS_ROUTE_REGISTRY.filter(module => module.componentType === "canonical" && !["calendar", "findings", "change-control"].includes(module.id));
  await page.goto("/maintenance/tenant-a/quality/settings/general", { waitUntil: "domcontentloaded" });
  const menuLabels = { command: "Work", assurance: "Assurance", control: "Controls & settings", administration: "Controls & settings", reporting: "Reports" };
  let reviewed = 0;
  for (const module of modules) for (const view of module.validViews.filter(view => view !== "new" && view !== "car-performance")) {
    const target = `/maintenance/tenant-a/quality/${module.segment}/${view}`;
    await page.getByRole("navigation", { name: "QMS page menus" }).getByRole("button", { name: menuLabels[module.section], exact: true }).click();
    const panel = page.locator(".qms-page-menu__panel");
    if (module.validViews.length > 1) await panel.locator("summary").filter({ hasText: new RegExp(`^${module.navigationLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }).click();
    await panel.locator(`a[href="${target}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`${target}$`));
    await expect(page.locator(".qms-register-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Quality route not found" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "QMS page menus" })).toBeVisible();
    await expect(page.locator(".qms-register-views")).toHaveCount(0);
    expect(errors, `${module.id}/${view}`).toEqual([]);
    reviewed += 1;
  }
  console.log(`Reviewed ${reviewed} QMS register views using isolated API fixtures.`);
});

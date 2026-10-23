import { expect, test, type Page, type Route } from "@playwright/test";
import { mockPortalBackgroundRequests } from "./helpers/portalBackgroundMocks";
import type { QmsMission } from "../../src/services/qmsMissions";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

const gateCodes = [
  "APPROVAL_RATING",
  "FACILITIES",
  "TECHNICAL_DATA",
  "TOOLING",
  "MATERIALS",
  "PERSONNEL",
  "TRAINING",
  "PROCEDURES",
  "CONTRACTED_FUNCTIONS",
  "MANPOWER",
  "SAFETY_CHANGE_ASSESSMENT",
] as const;

type GateCode = (typeof gateCodes)[number];

const gateTitles: Record<GateCode, string> = {
  APPROVAL_RATING: "Approval / rating",
  FACILITIES: "Facilities and housing",
  TECHNICAL_DATA: "Current technical data",
  TOOLING: "Tooling and test equipment",
  MATERIALS: "Materials and parts support",
  PERSONNEL: "Qualified personnel",
  TRAINING: "Training and competence evidence",
  PROCEDURES: "Approved procedures",
  CONTRACTED_FUNCTIONS: "Contracted functions and specialist support",
  MANPOWER: "Manpower and competent coverage",
  SAFETY_CHANGE_ASSESSMENT: "Safety / change assessment",
};

function mission(id = "mission-1") {
  return {
    id,
    mission_ref: "MSN-26-A1B2C3D4",
    mission_type: "CAPABILITY_ADDITION",
    title: "DHC-8-400 capability inclusion",
    description: "Add DHC-8-400 line and base maintenance capability.",
    scope: { capability: "DHC-8-400 · Airframe · Line + Base" } as Record<string, unknown>,
    next_action: undefined as QmsMission["next_action"],
    regulatory_basis: ["Capability self-evaluation"],
    risk_level: "HIGH",
    status: "PLANNING",
    owner_user_id: "quality-user-a",
    requested_by_user_id: "quality-user-a",
    sponsor_user_id: null,
    requested_at: "2026-08-08T12:00:00Z",
    target_date: "2026-08-22",
    started_at: "2026-08-08T12:00:00Z",
    approved_at: null,
    completed_at: null,
    created_at: "2026-08-08T12:00:00Z",
    updated_at: "2026-08-08T12:00:00Z",
    gates: gateCodes.map((gateCode, index) => ({
      id: `gate-${index + 1}`,
      gate_code: gateCode,
      title: gateTitles[gateCode],
      category: index < 2 ? "Approval" : "Readiness",
      description: null,
      gate_type: "HARD",
      status: "PENDING",
      requirement_ref: `Capability self-evaluation: ${gateCode.toLowerCase().replaceAll("_", " ")}`,
      source_owner_module: gateCode === "TRAINING" ? "training" : gateCode === "TOOLING" ? "tooling" : "quality",
      source_type: gateCode === "TRAINING" ? "TRAINING" : gateCode === "TOOLING" ? "EQUIPMENT" : "APPROVAL",
      source_id: null,
      source_route: null,
      source_snapshot: null,
      evidence_status: "UNLINKED",
      owner_user_id: null,
      due_date: null,
      blocking_reason: null,
      sort_order: (index + 1) * 10,
      passed_at: null,
      passed_by_user_id: null,
      updated_at: "2026-08-08T12:00:00Z",
    })),
    readiness: {
      hard_gates: { passed: 0, total: gateCodes.length },
      soft_gates: { passed: 0, total: 0 },
      ready_for_quality_self_evaluation: false,
      blocking_gates: gateCodes.map((gateCode, index) => ({
        id: `gate-${index + 1}`, gate_code: gateCode, title: gateTitles[gateCode],
        status: "PENDING", evidence_status: "UNLINKED",
      })),
    },
    decisions: [],
  };
}

async function prepare(page: Page, overrides: Partial<ReturnType<typeof mission>> = {}): Promise<void> {
  const token = futureToken();
  let currentMission = { ...mission(), ...overrides };

  await page.addInitScript(({ storedToken }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_session_last_user_activity", String(Date.now()));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a",
      amo_id: "amo-a",
      department_id: "department-quality",
      staff_code: "QMS-001",
      email: "quality@tenant-a.test",
      first_name: "Quality",
      last_name: "Manager",
      full_name: "Quality Manager",
      role: "QUALITY_MANAGER",
      position_title: "Quality Manager",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    // Avoid a synthetic login being evicted by background session checks.
    if (path === "/auth/me" || path === "/auth/me/") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        id: "quality-user-a", amo_id: "amo-a", role: "QUALITY_MANAGER",
        department_id: "department-quality", email: "quality@tenant-a.test",
        first_name: "Quality", last_name: "Manager", is_active: true,
      }) });
      return;
    }
    if (path === "/auth/portal-preferences/") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "quality-user-a",
          amo_id: "amo-a",
          text_scale: "standard",
          density: "comfortable",
          motion: "system",
          color_scheme: "light",
          accent: "tenant",
          version: 1,
          updated_at: "2026-08-08T12:00:00Z",
        }),
      });
      return;
    }

    if (path.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }

    if (path === "/api/maintenance/tenant-a/quality/missions" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [currentMission], total: 1, limit: 25, offset: 0, has_more: false }),
      });
      return;
    }

    if (path === "/api/maintenance/tenant-a/quality/missions" && request.method() === "POST") {
      const payload = request.postDataJSON() as { title: string; description?: string; scope?: Record<string, unknown>; risk_level?: string; target_date?: string };
      currentMission = {
        ...mission("mission-created"),
        title: payload.title,
        description: payload.description || null,
        scope: payload.scope || {},
        risk_level: payload.risk_level || "MEDIUM",
        target_date: payload.target_date || null,
      } as ReturnType<typeof mission>;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(currentMission) });
      return;
    }

    if (path === "/api/maintenance/tenant-a/quality/missions/mission-1" || path === "/api/maintenance/tenant-a/quality/missions/mission-created") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentMission) });
      return;
    }

    // Audit personnel options is a bare array. A generic paginated-object
    // fallback causes QmsMissionActions to crash when rendering assignment selects.
    if (path === "/api/maintenance/tenant-a/quality/audits/personnel/options") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([
        { id: "quality-user-a", full_name: "Quality Manager", email: "quality@tenant-a.test" },
      ]) });
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], columns: [], limit: 25, offset: 0, has_more: false }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in Mission browser test" }) });
  };

  await page.route("**/auth/me", fulfil);
  await page.route("**/auth/me/", fulfil);
  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
  await mockPortalBackgroundRequests(page);
}

test("Mission portfolio uses hard readiness gates rather than a compliance percentage", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=missions", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Change & capability projects", exact: true })).toBeVisible();
  await expect(page.getByText("DHC-8-400 capability inclusion", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Mission portfolio summary")).toBeVisible();

  // The grid opens detail on its explicit action; a cell click alone only selects the row.
  await page.getByRole("button", { name: "Manage project" }).click();
  await expect(page).toHaveURL(/missionId=mission-1/);
  await expect(page.locator(".qms-mission-detail")).toBeVisible();
  await expect(page.getByText("0/11", { exact: true })).toBeVisible();
  await expect(page.getByText("Hard gates remain open", { exact: true })).toBeVisible();
  await expect(page.getByText("Accountable Executive", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__summary article").filter({ hasText: "Accountable Executive" }).getByText("Not assigned", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__gate")).toHaveCount(11);
  await expect(page.locator(".qms-mission-detail__gates").getByText("Tooling and test equipment", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__gates").getByText("Training and competence evidence", { exact: true })).toBeVisible();
});

test("Quality Manager can create a capability Mission and receives seeded hard gates", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=missions", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "New controlled change" }).click();
  const form = page.locator("form.qms-missions__create");
  await form.getByLabel("Change title").fill("C208 EX capability expansion");
  await form.getByLabel("Affected capability, location or procedure").fill("C208 EX · Base maintenance");
  await form.getByLabel("Target date").fill("2026-09-30");
  await form.getByLabel("Initial risk").selectOption("HIGH");
  await form.getByLabel("Proposed change and reason").fill("Add the controlled C208 EX base-maintenance capability.");
  await form.getByRole("button", { name: "Create controlled change" }).click();

  await expect(page).toHaveURL(/workspace=missions.*missionId=mission-created|missionId=mission-created.*workspace=missions/);
  await expect(page.getByRole("heading", { name: "C208 EX capability expansion" })).toBeVisible();
  await expect(page.getByText("0/11", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__gate")).toHaveCount(11);
  await expect(page.getByText("Hard gates remain open", { exact: true })).toBeVisible();
});

test("Change Control opens a real governed procedure-change form with early field validation", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/change-control/new", { waitUntil: "domcontentloaded" });
  const form = page.locator("form.qms-missions__create");
  await expect(page.getByRole("heading", { name: "Change Control", exact: true })).toBeVisible();
  await expect(form.getByLabel("Change type")).toHaveValue("PROCEDURE_CHANGE");
  await expect(form.getByRole("button", { name: "Create controlled change" })).toBeDisabled();
  await form.getByLabel("Change title").fill("x"); await form.getByLabel("Change title").blur();
  await expect(form.getByLabel("Change title")).toHaveAttribute("aria-invalid", "true");
  await expect(form.getByLabel("Change title", { exact: true })).toHaveAccessibleName("Change title");
  await form.getByLabel("Change title").fill("Revise incoming inspection procedure");
  await form.getByLabel("Affected capability, location or procedure").fill("MOPM 2.2 incoming inspection");
  await form.getByLabel("Proposed change and reason").fill("Update the inspection responsibilities and controlled evidence requirements.");
  const request = page.waitForRequest(r => r.url().includes("/quality/missions") && r.method() === "POST");
  await form.getByRole("button", { name: "Create controlled change" }).click();
  expect((await request).postDataJSON()).toMatchObject({ mission_type: "PROCEDURE_CHANGE", scope: { affected_scope: "MOPM 2.2 incoming inspection" }, regulatory_basis: ["MOPM 1.9; 1.10"] });
  await expect(page.locator(".qms-mission-detail")).toBeVisible();
  await expect(page.getByRole("button", { name: "Record decision", exact: true })).toHaveCount(0);
});

test("Authority decisions select retained correspondence and remain disabled without evidence", async ({ page }) => {
  await prepare(page, { status: "APPROVED" });
  await page.route("**/missions/mission-1/authority-evidence?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ asset_id: "authority-letter", filename: "Authority approval letter.pdf", sha256: "a".repeat(64), size_bytes: 100 }] }) }));
  await page.goto("/maintenance/tenant-a/quality/change-control/register?missionId=mission-1", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Rationale", { exact: true }).fill("Submit the approved change package to the Authority.");
  await expect(page.getByRole("button", { name: "Record decision", exact: true })).toBeDisabled();
  await page.getByLabel("Retained Authority evidence").selectOption({ label: "Authority approval letter.pdf" });
  await expect(page.getByRole("button", { name: "Record decision", exact: true })).toBeEnabled();
  await page.screenshot({ path: "../.artifacts/qms-authority-evidence-fixture.png", fullPage: true });
});

test("Every Change Control queue reads governed projects with its own server filter", async ({ page }) => {
  await prepare(page);
  const legacyCalls: string[] = [];
  page.on("request", request => { if (/\/api\/maintenance\/.*\/quality\/change-control\//.test(request.url())) legacyCalls.push(request.url()); });
  for (const [view, title] of [["pending-approval","Pending Approval"],["implemented","Implemented"],["rejected","Rejected"]]) {
    const request = page.waitForRequest(request => request.url().includes(`/quality/missions?view=${view}`));
    await page.goto(`/maintenance/tenant-a/quality/change-control/${view}`, { waitUntil: "domcontentloaded" });
    await request;
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Manage project" })).toBeVisible();
  }
  expect(legacyCalls).toEqual([]);
});

test("Empty approval queues do not reserve a blank grid or pagination", async ({ page }) => {
  await prepare(page);
  await page.route("**/quality/missions?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({items:[],total:0,limit:25,offset:0,has_more:false}) }));
  await page.goto("/maintenance/tenant-a/quality/change-control/pending-approval", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("status").filter({hasText:"No controlled changes in this view."})).toBeVisible();
  await expect(page.locator(".qms-workspace-grid")).toHaveCount(0);
  await expect(page.getByRole("navigation",{name:"Projects pagination"})).toHaveCount(0);
  expect((await page.locator(".qms-missions__portfolio").boundingBox())!.height).toBeLessThan(250);
});

test("Controlled readiness selects retained evidence and requires review findings", async ({ page }) => {
  await prepare(page, { scope: { change_workflow_version: 2, affected_scope: "DHC-8 capability" } });
  let peopleUrl = "";
  page.on("request", request => { if (request.url().includes("/audits/personnel/options")) peopleUrl = request.url(); });
  await page.route("**/missions/mission-1/readiness-evidence?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ asset_id: "readiness-proof", filename: "Safety assessment.pdf", sha256: "a".repeat(64), size_bytes: 100 }] }) }));
  await page.goto("/maintenance/tenant-a/quality/change-control/register?missionId=mission-1", { waitUntil: "domcontentloaded" });
  await page.getByRole("combobox", { name: "Readiness gate", exact: true }).selectOption("gate-1");
  expect(new URL(peopleUrl).searchParams.get("auditors_only")).toBe("false");
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("PASS");
  await page.getByRole("combobox", { name: "Evidence", exact: true }).selectOption("VERIFIED");
  await expect(page.getByRole("button", { name: "Save gate" })).toBeDisabled();
  await page.getByLabel("Retained readiness evidence").selectOption("readiness-proof");
  await page.getByLabel("Readiness review findings").fill("Reviewed the signed assessment and its applicable mitigations.");
  await expect(page.getByRole("button", { name: "Save gate" })).toBeEnabled();
  await expect(page.getByLabel("Source record", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open Document Control to retain evidence" })).not.toHaveAttribute("target", "_blank");
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("Readiness review findings")).toHaveValue("Reviewed the signed assessment and its applicable mitigations.");
  await expect(page.getByRole("combobox", { name: "Readiness gate", exact: true })).toHaveValue("gate-1");
  await page.getByRole("region", { name: "Mission actions" }).screenshot({ path: "../.artifacts/change-readiness-desktop.png" });
});

test("Historical changes remain accessible separately from governed approvals", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/change-control/register", { waitUntil: "domcontentloaded" });
  await page.getByRole("link", { name: "Historical records", exact: true }).click();
  await expect(page).toHaveURL(/legacy=1/);
  await expect(page.getByText("Historical change records", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Manage controlled changes and approvals" }).click();
  await expect(page.getByRole("heading", { name: "Change Control", exact: true })).toBeVisible();
  await expect(page.getByText("Historical change records", { exact: true })).toHaveCount(0);
});

test("Authority acceptance leads to implementation and a separate effectiveness review", async ({ page }) => {
  test.setTimeout(60_000);
  let current = { ...mission(), status: "SUBMITTED_TO_AUTHORITY", next_action: "IMPLEMENTATION" as QmsMission["next_action"], scope: { change_workflow_version: 2, affected_scope: "Approved maintenance procedure" } };
  await prepare(page, current);
  await page.route("**/missions/mission-1", route => route.fulfill({ contentType: "application/json", body: JSON.stringify(current) }));
  await page.route("**/missions/mission-1/readiness-evidence?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ asset_id: "implementation-proof", filename: "Implementation report.pdf", sha256: "a".repeat(64), size_bytes: 100 }] }) }));
  await page.route("**/missions/mission-1/implementation", route => {
    current = { ...current, next_action: "EFFECTIVENESS_REVIEW", updated_at: "2026-10-23T12:00:00Z" };
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(current) });
  });
  await page.route("**/missions/mission-1/effectiveness-review", route => {
    current = { ...current, status: "COMPLETE", next_action: null, updated_at: "2026-10-23T13:00:00Z" };
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(current) });
  });
  await page.goto("/maintenance/tenant-a/quality/change-control/register?missionId=mission-1", { waitUntil: "domcontentloaded" });
  const implementation = page.getByRole("form", { name: "Record implementation", exact: true });
  await expect(implementation).toBeVisible();
  await expect(page.getByRole("button", { name: "Record decision", exact: true })).toHaveCount(0);
  await implementation.getByLabel("Actual implementation date").fill("2026-10-23");
  await implementation.getByLabel("Implementation and conditions met").fill("Implemented the approved revision within its operating conditions.");
  await implementation.getByLabel("Implementation / review evidence").selectOption("implementation-proof");
  await expect(implementation.getByRole("button", { name: "Record implementation", exact: true })).toBeDisabled();
  await implementation.getByRole("checkbox").check();
  const implementationVersion = current.updated_at;
  const request = page.waitForRequest(request => request.url().endsWith("/implementation") && request.method() === "POST");
  await implementation.getByRole("button", { name: "Record implementation", exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({ conditions_satisfied: true, effective_date: "2026-10-23", evidence_asset_id: "implementation-proof", expected_updated_at: implementationVersion });
  const review = page.getByRole("form", { name: "Effectiveness review", exact: true });
  await expect(review).toBeVisible();
  await review.getByLabel("Effectiveness findings and closure basis").fill("Verified that the procedure is effective and all assigned actions are resolved.");
  await review.getByLabel("Implementation / review evidence").selectOption("implementation-proof");
  await review.getByRole("checkbox").check();
  await review.screenshot({ path: "../.artifacts/change-effectiveness-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await review.screenshot({ path: "../.artifacts/change-effectiveness-mobile.png" });
  await page.locator(".qms-mission-detail__gate").first().screenshot({ path: "../.artifacts/change-readiness-mobile-card.png" });
  expect(await page.locator(".qms-mission-detail__gate").first().evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await review.getByRole("button", { name: "Close change", exact: true }).click();
  await expect(page.getByText("Decision chain closed.", { exact: true })).toBeVisible();
});

import { expect, test, type Page, type Route } from "@playwright/test";

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

function mission(id = "mission-1") {
  return {
    id,
    mission_ref: "MSN-26-A1B2C3D4",
    mission_type: "CAPABILITY_ADDITION",
    title: "DHC-8-400 capability inclusion",
    description: "Add DHC-8-400 line and base maintenance capability.",
    scope: { capability: "DHC-8-400 · Airframe · Line + Base" },
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
    readiness: {
      hard_gates: { passed: 0, total: 11 },
      soft_gates: { passed: 0, total: 0 },
      ready_for_quality_self_evaluation: false,
      blocking_gates: gateCodes.map((gateCode, index) => ({
        id: `gate-${index + 1}`,
        gate_code: gateCode,
        title: gateCode.replaceAll("_", " "),
        status: "PENDING",
        evidence_status: "UNLINKED",
        blocking_reason: null,
      })),
    },
    gates: gateCodes.map((gateCode, index) => ({
      id: `gate-${index + 1}`,
      gate_code: gateCode,
      title: gateCode.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()),
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
    decisions: [],
  };
}

async function prepare(page: Page): Promise<void> {
  const token = futureToken();
  let currentMission = mission();

  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
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

    if (path.includes("/api/maintenance/tenant-a/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], columns: [], limit: 25, offset: 0, has_more: false }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in Mission browser test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("Mission portfolio uses hard readiness gates rather than a compliance percentage", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=missions", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Missions", exact: true })).toBeVisible();
  await expect(page.getByText("DHC-8-400 capability inclusion", { exact: true })).toBeVisible();
  await expect(page.getByText("0/11", { exact: true })).toBeVisible();
  await expect(page.getByText("11 hard gates open", { exact: true })).toBeVisible();
  await expect(page.getByText(/compliance percentage/i)).toBeVisible();

  await page.getByText("DHC-8-400 capability inclusion", { exact: true }).click();
  await expect(page.getByText("Hard gates remain open", { exact: true })).toBeVisible();
  await expect(page.getByText("Accountable Executive", { exact: true })).toBeVisible();
  await expect(page.getByText("Not assigned", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__gate")).toHaveCount(11);
  await expect(page.getByText("Tooling And Test Equipment", { exact: true })).toBeVisible();
  await expect(page.getByText("Training And Competence Evidence", { exact: true })).toBeVisible();
});

test("Quality Manager can create a capability Mission and receives seeded hard gates", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality?workspace=missions", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "New capability mission" }).click();
  const form = page.locator("form.qms-missions__create");
  await form.getByLabel("Mission title").fill("C208 EX capability expansion");
  await form.getByLabel("Capability / scope").fill("C208 EX · Base maintenance");
  await form.getByLabel("Target date").fill("2026-09-30");
  await form.getByLabel("Initial risk").selectOption("HIGH");
  await form.getByLabel("Description").fill("Add the controlled C208 EX base-maintenance capability.");
  await form.getByRole("button", { name: "Create Mission" }).click();

  await expect(page).toHaveURL(/workspace=missions.*missionId=mission-created|missionId=mission-created.*workspace=missions/);
  await expect(page.getByRole("heading", { name: "C208 EX capability expansion" })).toBeVisible();
  await expect(page.getByText("0/11", { exact: true })).toBeVisible();
  await expect(page.locator(".qms-mission-detail__gate")).toHaveCount(11);
  await expect(page.getByText("Hard gates remain open", { exact: true })).toBeVisible();
});

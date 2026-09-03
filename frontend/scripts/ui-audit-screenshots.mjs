import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const outDir = "d:/XLK-Assets-AMO-Portal-and-DB/amo-portal/.runtime-logs/ui-audit";
fs.mkdirSync(outDir, { recursive: true });

function futureToken() {
  const encode = (v) => Buffer.from(JSON.stringify(v)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4102444800 })}.signature`;
}

const token = futureToken();
const currentUser = {
  id: "quality-user-a",
  email: "quality.a@example.com",
  full_name: "Quality User A",
  amo_id: "amo-a",
  amo_code: "AMO-A",
  amo_name: "Tenant A",
  login_slug: "tenant-a",
  department_id: "department-quality",
  department_code: "quality",
  department_name: "Quality",
  roles: ["QUALITY_MANAGER"],
  permissions: ["qms.audit.view", "qms.audit.manage", "qms.evidence.view", "qms.car.view"],
  is_amo_admin: true,
  must_change_password: false,
};

const routes = [
  ["01-assurance-overview", "/maintenance/tenant-a/quality/audits/dashboard"],
  ["02-programme", "/maintenance/tenant-a/quality/audits/program"],
  ["03-register", "/maintenance/tenant-a/quality/audits/register?tab=findings"],
  ["04-planner", "/maintenance/tenant-a/quality/calendar/week"],
  ["05-evidence", "/maintenance/tenant-a/quality/evidence-vault"],
  ["06-checklists", "/maintenance/tenant-a/quality/audits/checklists"],
  ["07-evidence-viewer", "/maintenance/tenant-a/quality/evidence-vault/ev-demo?name=sample.pdf&auditRef=QAR-2026-001"],
];

const browser = await chromium.launch({ headless: true, channel: "chrome" });
const notes = [];

for (const width of [1440, 1100, 860]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  await page.addInitScript(
    ({ storedToken, storedUser }) => {
      sessionStorage.setItem("amo_portal_token", storedToken);
      localStorage.setItem("amo_portal_token", storedToken);
      localStorage.setItem("amo_code", "AMO-A");
      localStorage.setItem("amo_slug", "tenant-a");
      localStorage.setItem("amo_department", "quality");
      localStorage.setItem("amo_color_scheme", "light");
      localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
      sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
      localStorage.setItem("amo_current_user", JSON.stringify(storedUser));
      localStorage.setItem("amo_session_last_user_activity", String(Date.now()));
    },
    { storedToken: token, storedUser: currentUser },
  );

  await page.route("**/auth/me**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentUser) });
  });
  await page.route("**/auth/refresh", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: token,
        token_type: "bearer",
        expires_in: 3600,
        user: currentUser,
        amo: { id: "amo-a", amo_code: "AMO-A", name: "Tenant A", login_slug: "tenant-a", data_mode: "REAL" },
        department: { id: "department-quality", code: "quality", name: "Quality" },
      }),
    });
  });
  await page.route("**/platform/product-events**", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/chat/threads**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

  for (const [name, url] of routes) {
    try {
      await page.goto(`http://127.0.0.1:5173${url}`, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(2800);
      const file = path.join(outDir, `${name}-w${width}.png`);
      await page.screenshot({ path: file, fullPage: true });
      const h1 = await page
        .locator("h1,h2")
        .first()
        .textContent()
        .catch(() => "");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
      const bodySnippet = await page.evaluate(() => (document.body?.innerText || "").slice(0, 400));
      notes.push({ name, width, h1: (h1 || "").trim().slice(0, 80), overflow, file, url: page.url(), bodySnippet });
      console.log(`OK ${name} w${width} overflow=${overflow}`);
    } catch (e) {
      notes.push({ name, width, error: String(e) });
      console.log(`FAIL ${name} w${width}: ${e}`);
    }
  }
  await context.close();
}

fs.writeFileSync(path.join(outDir, "audit-notes.json"), JSON.stringify(notes, null, 2));
await browser.close();
console.log("DONE", notes.length);

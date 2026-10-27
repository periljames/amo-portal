import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

const carId = "11111111-1111-4111-8111-111111111111";
const car = { id: carId, car_number: "CAR/TEST/26/001", title: "Controlled investigation",
  summary: "Review a documented maintenance process", program: "QUALITY", priority: "HIGH", status: "OPEN" };
const investigation = { version: 1, problem_statement: car.summary, investigations: [], conclusion: "",
  supported_cause_ids: [], conclusion_evidence_references: [], evidence_notes: "", effectiveness_proposal: null };
const projection = { car_id: carId, revision: 0, draft: { form: {}, investigation }, submitted_revision: null,
  submitted_snapshot: null, submitted_at: null, actions: [], history: [], retained_responses: [], action_events: [] };

async function prepare(page: Page, reader = false, invalid = false) {
  await mockQualityShell(page);
  await page.addInitScript(({ reader }) => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({exp: Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a"); localStorage.setItem("amo_department", "quality");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({is_complete:true,missing:[]}));
    localStorage.setItem("amo_current_user", JSON.stringify({id:"quality",amo_id:"amo-a",amo_slug:"tenant-a",amo_code:"AMO-A",
      department_code:"quality",role:reader?"VIEW_ONLY":"QUALITY_MANAGER",full_name:"Quality User",is_active:true,
      capability_codes:reader?["qms.car.view","qms.dashboard.view"]:undefined}));
  }, { reader });
  let malformed = invalid;
  let paretoRequests = 0;
  await page.route("**/api/maintenance/tenant-a/quality/**", async route => {
    if (route.request().resourceType() === "document") return route.fallback();
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith("/cars/register/paged")) body = { items:[car],total:1,limit:25,offset:0,has_more:false,summary:{total:1,open:1,overdue:0,in_review:0} };
    if (path.endsWith("/investigation")) body = malformed ? { module:"cars",record_id:carId } : projection;
    if (path.endsWith("/pareto-snapshots")) paretoRequests++;
    return route.fulfill({ contentType:"application/json",body:JSON.stringify(body) });
  });
  return { recover: () => { malformed = false; }, paretoRequests: () => paretoRequests };
}

test("CAR readers can inspect the investigation without requesting restricted report sources", async ({page}) => {
  const state = await prepare(page, true);
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  const section = page.getByRole("region", {name:"Structured CAR investigation and Quality action review"});
  await expect(section.getByText("No structured investigation recorded.",{exact:false})).toBeVisible({timeout:15000});
  await expect(section.getByText("Source frequency analysis",{exact:true})).toHaveCount(0);
  expect(state.paretoRequests()).toBe(0);
  await expect(section.getByRole("alert")).toHaveCount(0);
});

test("a misleading HTTP 200 fails visibly and can recover through retry", async ({page}) => {
  const state = await prepare(page, false, true);
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  const section = page.getByRole("region", {name:"Structured CAR investigation and Quality action review"});
  await expect(section.getByRole("alert")).toContainText("invalid CAR investigation response",{timeout:15000});
  await expect(section.getByText("Add a Quality-managed action",{exact:true})).toHaveCount(0);
  state.recover(); await section.getByRole("button",{name:"Retry",exact:true}).click();
  await expect(section.getByRole("alert")).toHaveCount(0);
  await expect(section.getByText("Add a Quality-managed action",{exact:true})).toBeVisible();
});

test("Quality action controls stay compact, readable and require owner and deadline", async ({page}) => {
  await prepare(page);
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  const section = page.getByRole("region", {name:"Structured CAR investigation and Quality action review"});
  const action = section.getByText("Add a Quality-managed action",{exact:true});
  await expect(action).toBeVisible({timeout:15000});
  await expect(section.getByLabel("Responsible person's name")).toBeHidden();
  await action.click();
  const create = section.getByRole("button",{name:"Create governed action"});
  await expect(create).toBeDisabled();
  await section.getByLabel("Action description",{exact:true}).fill("Reconcile the source register and revise the controlled process.");
  await section.getByLabel("Responsible person's name").fill("Responsible manager");
  await expect(create).toBeDisabled();
  await section.getByLabel("Target date",{exact:true}).fill("2026-12-31");
  await expect(create).toBeEnabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

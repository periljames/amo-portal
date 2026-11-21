import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

const carId = "11111111-1111-4111-8111-111111111111";
const car = { id: carId, car_number: "CAR/TEST/26/001", title: "Controlled investigation", audit_ref:"AUD/26/004", finding_ref:"F-012", due_date:"2026-12-10", responsible_personnel:"Jane Smith",
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
    if (path.endsWith("/feedback")) body = {car_id:carId,status:"OPEN",root_cause_status:"PENDING",capa_status:"PENDING",items:[],next_cursor:null};
    if (path.endsWith("/cars/register/paged")) body = { items:[car],total:1,limit:25,offset:0,has_more:false,summary:{total:1,open:1,overdue:0,in_review:0} };
    if (path.endsWith("/investigation")) body = malformed ? { module:"cars",record_id:carId } : projection;
    if (path.endsWith("/pareto-snapshots")) paretoRequests++;
    return route.fulfill({ contentType:"application/json",body:JSON.stringify(body) });
  });
  return { recover: () => { malformed = false; }, paretoRequests: () => paretoRequests };
}

test("register hierarchy, queues and actions remain usable", async ({page}) => {
 await prepare(page);
 await page.goto('/maintenance/tenant-a/quality/cars?dueWindow=week');
 await expect(page.getByRole('button',{name:car.car_number,exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole('heading',{name:'Corrective action register',exact:true})).toHaveCount(1);
 await expect(page.getByRole('table',{name:'Corrective action register'}).getByRole('columnheader')).toHaveCount(6);
 await expect(page.getByRole('combobox',{name:'Status',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Filters',exact:true}).click();
 const status=page.getByRole('combobox',{name:'Status',exact:true});
 await status.selectOption('OPEN');
 await expect(page.getByRole('button',{name:'Clear status filter'})).toBeVisible();
 await page.getByRole('button',{name:'Clear status filter'}).click();
 await page.getByRole('button',{name:'Overdue',exact:true}).click();
 await expect(page.getByRole('button',{name:'Overdue',exact:true})).toHaveAttribute('aria-current','page');
 await page.getByRole('combobox',{name:'CAR scope',exact:true}).selectOption('mine');
 await expect(page).toHaveURL(/overdue\?dueWindow=week&view=mine/);
 await page.getByRole('button',{name:'New CAR',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Create corrective action',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:'Actions for '+car.car_number}).click();
 await expect(page.getByRole('button',{name:'Edit assignment & dates'})).toBeVisible();
});
test("register fits desktop and mobile", async ({page}) => {
 await prepare(page);await page.setViewportSize({width:1440,height:1000});
 await page.goto('/maintenance/tenant-a/quality/cars');
 await expect(page.getByRole('button',{name:car.car_number,exact:true})).toBeVisible({timeout:20000});
 await page.screenshot({path:'test-results/car-register-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await expect(page.getByText(car.title,{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:'test-results/car-register-mobile.png',fullPage:true});
 await page.evaluate(() => { localStorage.setItem('amo_color_scheme','dark'); window.dispatchEvent(new CustomEvent('amo:color-scheme-changed',{detail:'dark'})); });
 await page.screenshot({path:'test-results/car-register-dark.png',fullPage:true});
});

test("read only register exposes records without management controls",async({page})=>{
 await prepare(page,true);await page.goto('/maintenance/tenant-a/quality/cars');
 await expect(page.getByRole('button',{name:car.car_number,exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole('button',{name:'New CAR',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Actions for '+car.car_number}).click();
 await expect(page.getByRole('button',{name:'Download evidence pack'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Edit assignment & dates'})).toHaveCount(0);
});

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
  await page.route("**/quality/cars/*/attachments", route => route.fulfill({contentType:"application/json",body:"[]"}));
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

test("auditor action evidence opens by filename and the review fits a phone viewport", async ({page}) => {
  await prepare(page,true);
  const fileId="22222222-2222-4222-8222-222222222222";
  await page.route("**/quality/cars/*/investigation",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({...projection,actions:[{
    id:"action-1",car_id:carId,sequence_no:1,action_number:"CA-01",kind:"CORRECTIVE",
    description:"Restore the controlled evidence index and independently verify ownership.",cause_node_ids:[],
    evidence_references:[`CAR-ATTACHMENT:${fileId}`],owner_user_id:null,external_owner_name:"Maintenance manager",
    target_date:"2026-12-31",priority:"MEDIUM",state:"SUBMITTED",completion_note:"Evidence is ready for independent review.",
    completed_at:null,quality_review_note:null,reviewed_by_user_id:null,reviewed_at:null,
  }]})}));
  await page.route("**/quality/cars/*/attachments",route=>route.fulfill({contentType:"application/json",body:JSON.stringify([{
    id:fileId,car_id:carId,filename:"implementation-evidence.txt",uploaded_at:"2026-10-28T12:00:00Z",
    content_type:"text/plain",size_bytes:30,
  }])}));
  await page.route("**/quality/cars/*/attachments/*/download",route=>route.fulfill({contentType:"text/plain",body:"Synthetic implementation evidence."}));
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  const section=page.getByRole("region",{name:"Structured CAR investigation and Quality action review"});
  const row=section.getByRole("row").filter({hasText:"CA-01"});
  await expect(row.getByText("SUBMITTED",{exact:true})).toBeVisible({timeout:15000});
  const evidence=row.getByRole("button",{name:"implementation-evidence.txt",exact:true});
  await expect(evidence).toBeVisible();
  const downloads:string[]=[];page.on("download",event=>downloads.push(event.suggestedFilename()));
  await evidence.click();
  const preview=page.getByRole("region",{name:"Evidence preview",exact:true});
  await expect(preview).toContainText("Synthetic implementation evidence.");
  expect(downloads).toEqual([]);
  const downloading=page.waitForEvent("download");await preview.getByRole("button",{name:"Download a copy",exact:true}).click();
  expect((await downloading).suggestedFilename()).toBe("implementation-evidence.txt");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await section.screenshot({path:"../.artifacts/qms-ux-20261028/action-review-mobile.png"});
  await page.setViewportSize({width:1440,height:1000});
  await section.screenshot({path:"../.artifacts/qms-ux-20261028/action-review-desktop.png"});
});

test("background history refresh preserves an unconfirmed reply and its error", async ({page}) => {
  await prepare(page);
  let reads=0;
  await page.route("**/quality/cars/*/feedback",async route=>{
    if(route.request().method()==="POST")return route.abort("failed");
    reads++;
    await route.fulfill({contentType:"application/json",body:JSON.stringify({car_id:carId,status:"OPEN",root_cause_status:"PENDING",capa_status:"PENDING",items:[],next_cursor:null})});
  });
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  const feedback=page.getByRole("region",{name:"CAR feedback and decision history"});
  await feedback.getByLabel("CAR feedback message",{exact:true}).fill("Please confirm the independent review evidence.");
  await expect(feedback.getByRole("button",{name:"Send feedback",exact:true})).toBeEnabled();
  await feedback.getByRole("button",{name:"Send feedback",exact:true}).click();
  await expect(feedback.getByRole("alert")).toBeVisible();
  const beforeRefresh=reads;
  await expect.poll(()=>reads,{timeout:12000}).toBeGreaterThan(beforeRefresh);
  await expect(feedback.getByRole("alert")).toBeVisible();
  await expect(feedback.getByLabel("CAR feedback message",{exact:true})).toHaveValue("Please confirm the independent review evidence.");
  await expect(feedback.getByRole("button",{name:"Send feedback",exact:true})).toBeEnabled();
});

test("a closed CAR remains read only even for an account with management permissions", async ({page}) => {
  await prepare(page);
  await page.route("**/quality/cars/register/paged*",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({
    items:[{...car,status:"CLOSED",can_current_user_modify:true,can_current_user_review:true}],
    total:1,limit:25,offset:0,has_more:false,summary:{total:1,open:0,overdue:0,in_review:0},
  })}));
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  await expect(page.getByRole("heading",{name:car.car_number,exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole("button",{name:"Edit assignment & dates",exact:true})).toHaveCount(0);
  await expect(page.getByText("Add a Quality-managed action",{exact:true})).toHaveCount(0);
  await expect(page.getByRole("region",{name:"CAR feedback and decision history"}).getByLabel("CAR feedback message")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Evidence pack",exact:true})).toBeVisible();
});


test("a new review does not reuse old rejection reasons and validates return notes before saving",async({page})=>{
  await prepare(page);
  await page.route("**/api/maintenance/tenant-a/quality/cars/register/paged?**",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({items:[{...car,status:"PENDING_VERIFICATION",root_cause_status:"SUBMITTED",capa_status:"SUBMITTED",root_cause_review_note:"Previous root cause rejection.",capa_review_note:"Previous action rejection."}],total:1,limit:1,offset:0,has_more:false,summary:{total:1,open:1,overdue:0,in_review:1}})}));
  await page.route(`**/quality/cars/${carId}/attachments`,route=>route.fulfill({contentType:"application/json",body:"[]"}));
  await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
  await page.getByRole("button",{name:"Review response",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Review corrective action response"});
  await expect(dialog.getByLabel("Root cause review note",{exact:true})).toHaveValue("");
  await expect(dialog.getByLabel("Corrective action review note",{exact:true})).toHaveValue("");
  await dialog.getByText("Previous review reasons",{exact:true}).click();
  await expect(dialog).toContainText("Previous root cause rejection.");
  await dialog.getByRole("combobox",{name:"Root cause decision",exact:true}).selectOption("REJECTED");
  await dialog.getByRole("combobox",{name:"Corrective action decision",exact:true}).selectOption("ACCEPTED");
  const save=dialog.getByRole("button",{name:"Record review decision",exact:true});
  await expect(save).toBeDisabled();
  await dialog.getByLabel("Root cause review note",{exact:true}).fill("New evidence requires a revised cause.");
  await expect(save).toBeEnabled();
  await dialog.getByRole("combobox",{name:"Corrective action decision",exact:true}).selectOption("NEEDS_EVIDENCE");
  await expect(save).toBeDisabled();
  await dialog.getByLabel("Corrective action review note",{exact:true}).fill("Link the controlled implementation record.");
  await expect(save).toBeEnabled();
});

 test("feedback follows response evidence in the sidebar without duplicate histories",async({page})=>{
 await prepare(page);
 await page.route('**/quality/cars/*/feedback',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({car_id:carId,status:'OPEN',items:[{id:'feedback-1',actor_name:'Quality Manager',actor_kind:'STAFF',visibility:'SHARED',created_at:'2026-11-21T10:00:00Z',message:'Implementation evidence verified. Confirm effectiveness at the next review.'},{id:'feedback-2',actor_name:'Maintenance Manager',actor_kind:'AUDITEE',visibility:'SHARED',created_at:'2026-11-21T10:30:00Z',message:'Updated records attached for independent review.'}],next_cursor:null})}));
 await page.route('**/quality/cars/*/investigation',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...projection,history:[{id:'revision-1',event_type:'DRAFT_SAVED',revision:1}],action_events:[{id:'event-1',previous_state:'SUBMITTED',next_state:'VERIFIED',reason:'Evidence verified'}]})}));
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
 const feedback=page.getByRole('region',{name:'CAR feedback and decision history'});
 await expect(feedback).toBeVisible({timeout:15000});
 await expect(page.getByText('No structured investigation recorded.',{exact:false})).toBeVisible();
 await expect(page.getByText(/Attributable action implementation|Attributed investigation revisions/)).toHaveCount(0);
 expect(await feedback.evaluate(element=>element.parentElement?.tagName)).toBe('ASIDE');
 const response=page.locator('.case-response');
 await expect(response.getByRole('heading',{name:'Root cause',exact:true})).toBeVisible();
 await expect(response.getByRole('heading',{name:'Corrective Action (CAP)',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Preventive action',exact:true})).toHaveCount(0);
 await expect(page.getByText('Revision 0',{exact:false})).toHaveCount(0);
 await page.getByText('Attach evidence',{exact:true}).click();
 await expect(page.locator('.case-evidence-upload input[type="file"]')).toBeVisible();
 const evidence=page.getByRole('heading',{name:'Response evidence',exact:true});
 expect(await evidence.evaluate((element)=>Boolean(element.closest('aside')?.querySelector('.car-feedback')))).toBe(true);
 await feedback.screenshot({path:'test-results/car-feedback-timeline.png'});
 await page.screenshot({path:'test-results/car-record-sidebar.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 });

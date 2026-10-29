import {test,expect,type Page} from "@playwright/test";
import {mockQualityShell} from "./helpers/mockQualityShell";

const carId="11111111-1111-4111-8111-111111111111";
async function prepare(page:Page,closed=false,holdFirst=false){
  await mockQualityShell(page);
  let revision=0;
  const writes:Array<{expected_revision:number;form:Record<string,string>;investigation:Record<string,unknown>}>=[];
  let release=()=>{};
  const firstGate=new Promise<void>(resolve=>{release=resolve;});
  const investigation={version:1,problem_statement:"Synthetic finding",investigations:[],conclusion:"",supported_cause_ids:[],conclusion_evidence_references:[],evidence_notes:"",effectiveness_proposal:null};
  let draft={form:{submitted_by_name:"Respondent",submitted_by_email:"qa@example.invalid",containment_action:"Immediate exposure contained.",root_cause:"",corrective_action:"",preventive_action:"",evidence_ref:"",due_date:"2026-12-01",target_closure_date:"2026-12-01"},investigation};
  await page.route("**/quality/cars/invite/**",async route=>{
    if(route.request().resourceType()==="document")return route.fallback();
    const path=new URL(route.request().url()).pathname;
    const json=(value:unknown)=>route.fulfill({contentType:"application/json",body:JSON.stringify(value)});
    if(path.endsWith("/feedback/events"))return route.fulfill({status:204,body:""});
    if(path.endsWith("/feedback"))return json({car_id:carId,status:closed?"CLOSED":"OPEN",root_cause_status:"PENDING",capa_status:"PENDING",items:[],next_cursor:null});
    if(path.endsWith("/draft")){
      if(route.request().method()==="PUT"){
        const payload=route.request().postDataJSON();writes.push(payload);
        if(holdFirst&&writes.length===1)await firstGate;
        expect(payload.expected_revision).toBe(revision);
        revision++;draft={form:payload.form,investigation:payload.investigation};
      }
      return json({car_id:carId,revision,draft,submitted_revision:null,submitted_snapshot:null,submitted_at:null,actions:[],action_events:[],retained_responses:[],history:[]});
    }
    if(path.endsWith("/attachments")||path.endsWith("/actions"))return json([]);
    return json({car_id:carId,car_number:"QA-CAR-001",title:"Synthetic draft coordination",summary:"Synthetic finding",priority:"HIGH",status:closed?"CLOSED":"OPEN",can_edit:!closed,can_submit:!closed,related_cars:[],evidence_required:false,structured_rca_required:true,...draft.form,submitted_at:null,submission_count:0,remaining_submissions:2});
  });
  return {writes,release};
}

test("initial invite load survives synchronous draft-ref updates",async({page})=>{
  await prepare(page,true);
  await page.goto("/qms/car-access/synthetic-token");
  await expect(page.locator(".car-invite-kicker").getByText("QA-CAR-001",{exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByText("0 CARs",{exact:true})).toHaveCount(0);
  await expect(page.getByRole("region",{name:"CAR feedback and decision history"})).toContainText("communication history is read only");
});

test("continue flushes edits made during an earlier autosave without losing the draft",async({page})=>{
  const state=await prepare(page,false,true);
  await page.goto("/qms/car-access/synthetic-token");
  const editor=page.getByRole("region",{name:"Root cause investigation"});
  await expect(editor.getByLabel("Problem statement from this CAR")).toBeVisible({timeout:15000});
  await editor.getByLabel("Problem statement from this CAR").fill("First autosave while newer work is still being entered.");
  await expect.poll(()=>state.writes.length).toBe(1);
  await editor.getByLabel("Final root cause explanation").fill("A newer conclusion entered while the first save is in flight.");
  await page.getByRole("button",{name:"Save root cause and continue",exact:true}).click();
  await expect(page.getByLabel("Corrective action plan structured editor").locator("textarea")).toBeHidden();
  state.release();
  await expect(page.getByLabel("Corrective action plan structured editor").locator("textarea")).toBeVisible({timeout:15000});
  expect(state.writes.length).toBeGreaterThanOrEqual(2);
  expect(state.writes.at(-1)?.form.root_cause).toBe("A newer conclusion entered while the first save is in flight.");
  expect(state.writes.at(-1)?.investigation.conclusion).toBe(state.writes.at(-1)?.form.root_cause);
});

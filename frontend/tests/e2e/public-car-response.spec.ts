import {test,expect,type Page} from "@playwright/test";
import {mockQualityShell} from "./helpers/mockQualityShell";

const carId="11111111-1111-4111-8111-111111111111";
async function prepare(page:Page,closed=false,holdFirst=false,withAction=false,legacyConclusion=""){
  await mockQualityShell(page);
  let revision=0;
  const writes:Array<{expected_revision:number;form:Record<string,string>;investigation:Record<string,unknown>}>=[];
  let release=()=>{};
  const firstGate=new Promise<void>(resolve=>{release=resolve;});
  const investigation={version:1,problem_statement:"Synthetic finding",investigations:[],conclusion:"",supported_cause_ids:[],conclusion_evidence_references:[],evidence_notes:"",effectiveness_proposal:null};
  let draft={form:{submitted_by_name:"Respondent",submitted_by_email:"qa@example.invalid",containment_action:"Immediate exposure contained.",root_cause:legacyConclusion,corrective_action:"",preventive_action:"",evidence_ref:"",due_date:"2026-12-01",target_closure_date:"2026-12-01"},investigation};
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
      return json({car_id:carId,revision,draft,submitted_revision:null,submitted_snapshot:null,submitted_at:null,actions:withAction?[{id:"action-mobile",car_id:carId,sequence_no:1,action_number:"CA-001",kind:"CORRECTIVE",description:"Maintain an independently verified effectiveness checkpoint and accountable evidence owner.",external_owner_name:"SIMULATED responsible manager",target_date:"2026-11-01",state:"VERIFIED",cause_node_ids:[],evidence_references:[],priority:"MEDIUM",completion_note:"Controlled register and evidence index updated.",quality_review_note:"Independently verified against the retained evidence."}]:[],action_events:[],retained_responses:[],history:[]});
    }
    if(path.endsWith("/attachments")||path.endsWith("/actions"))return json([]);
    return json({car_id:carId,car_number:"QA-CAR-001",title:"Synthetic draft coordination",summary:"Synthetic finding",priority:"HIGH",status:closed?"CLOSED":"OPEN",can_edit:!closed&&!withAction,can_submit:!closed&&!withAction,root_cause_status:withAction?"ACCEPTED":"PENDING",capa_status:withAction?"ACCEPTED":"PENDING",related_cars:[],evidence_required:false,structured_rca_required:false,...draft.form,submitted_at:null,submission_count:0,remaining_submissions:2});
  });
  return {writes,release};
}

test("public RCA uses one conclusion field and a keyboard accessible tool drawer",async({page})=>{
 await prepare(page);await page.goto('/qms/car-access/synthetic-token');
 const workbench=page.getByRole('region',{name:'Root cause investigation'});
 await expect(workbench.getByLabel('Final root cause explanation')).toBeVisible({timeout:20000});
 await expect(page.getByText('Root cause analysis (legacy narrative response)',{exact:true})).toHaveCount(0);
 await workbench.getByRole('button',{name:'Choose analysis tool',exact:true}).click();
 const drawer=page.getByRole('dialog',{name:'Choose analysis tool',exact:true});
 await expect(drawer).toBeVisible();await drawer.getByRole('button',{name:/^Fishbone/}).click();
 await expect(drawer).not.toBeVisible();
 await expect(workbench.getByText('Editable cause-and-effect diagram',{exact:true})).toBeVisible();
 await workbench.getByRole('button',{name:'Choose analysis tool',exact:true}).click();await page.keyboard.press('Escape');await expect(drawer).not.toBeVisible();
 const conclusion=workbench.getByLabel('Final root cause explanation', {exact:true});await conclusion.fill('Supported control gap');await conclusion.press('Control+a');
 await conclusion.press('Control+b');await expect(conclusion).toHaveValue('**Supported control gap**');
 const field=conclusion.locator('..');await field.getByRole('button',{name:'Preview',exact:true}).click();
 await expect(field.getByRole('region',{name:'Formatted text preview'}).locator('strong')).toHaveText('Supported control gap');
 await field.getByRole('button',{name:'Edit text',exact:true}).click();await expect(conclusion).toHaveValue('**Supported control gap**');
 await page.setViewportSize({width:390,height:844});
 await workbench.getByRole('button',{name:'Choose analysis tool',exact:true}).click();await drawer.screenshot({path:'test-results/public-car-tool-drawer-mobile.png'});
 expect(await drawer.evaluate(element=>element.scrollWidth<=element.clientWidth+1)).toBe(true);
});

test("phone capture opens evidence directly and permits multiple attachments and retry",async({page})=>{
 await prepare(page);await page.setViewportSize({width:390,height:844});
 let uploads=0;let fail=true;
 await page.route('**/quality/cars/invite/current/attachments',async route=>{
 if(route.request().method()!=='POST')return route.fulfill({contentType:'application/json',body:'[]'});
 uploads++;if(fail){fail=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Temporary upload failure'})});}
 return route.fulfill({contentType:'application/json',body:JSON.stringify({id:'file-'+uploads,filename:'evidence.pdf',content_type:'application/pdf',uploaded_at:'2026-11-21T10:00:00Z',download_url:'/files/evidence.pdf'})});
 });
 await page.goto('/qms/car-access/synthetic-token?capture=1');
 await expect(page.getByLabel('Evidence reference',{exact:true})).toBeVisible({timeout:20000});
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Upload files',exact:true}).click();
 await (await chooser).setFiles({name:'evidence.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF synthetic attachment')});
 await expect(page.locator('.car-invite-error').filter({hasText:'Temporary upload failure'})).toBeVisible();
 await page.getByRole('button',{name:/Retry .*failed file/}).click();
 await expect.poll(()=>uploads).toBe(2);await expect(page.locator('.car-invite-evidence-actions')).toContainText('1 attached');
 await page.locator('input[type="file"][multiple]').setInputFiles([{name:'photo.jpg',mimeType:'image/jpeg',buffer:Buffer.from('synthetic image')},{name:'record.txt',mimeType:'text/plain',buffer:Buffer.from('record')}]);
 await expect.poll(()=>uploads).toBe(4);await expect(page.locator('.car-invite-evidence-actions')).toContainText('3 attached');
 await page.getByText('Use phone camera',{exact:false}).click();
 await expect(page.getByRole('link',{name:'Open phone capture page'})).toHaveAttribute('href',/\/qms\/car-access#token=synthetic-token&capture=1$/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test("camera captures a real video frame and uploads the JPEG",async({page})=>{
 await prepare(page);
 await page.addInitScript(()=>{
 const tracks:MediaStreamTrack[]=[];
 Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
 const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;
 const draw=()=>{const context=canvas.getContext('2d')!;context.fillStyle='#126fa8';context.fillRect(0,0,320,240);};draw();
 const timer=setInterval(draw,40);const stream=canvas.captureStream(15);tracks.push(...stream.getTracks());stream.getTracks().forEach(track=>track.addEventListener('ended',()=>clearInterval(timer)));return stream;
 }});
 (window as unknown as {cameraTracks:MediaStreamTrack[]}).cameraTracks=tracks;
 });
 let imageBytes=0;
 await page.route('**/quality/cars/invite/current/attachments',async route=>{
 if(route.request().method()!=='POST')return route.fulfill({contentType:'application/json',body:'[]'});
 imageBytes=route.request().postDataBuffer()?.length||0;
 await route.fulfill({contentType:'application/json',body:JSON.stringify({id:'photo-1',filename:'captured.jpg',content_type:'image/jpeg',download_url:'/files/captured.jpg'})});
 });
 await page.goto('/qms/car-access/synthetic-token?capture=1');await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const camera=page.getByRole('dialog',{name:'Camera capture'});await expect(camera).toBeVisible();
 await expect(camera.getByRole('button',{name:'Capture and upload',exact:true})).toBeEnabled();
 await camera.getByRole('button',{name:'Capture and upload',exact:true}).click();
 await expect.poll(()=>imageBytes).toBeGreaterThan(500);await expect(camera).toHaveCount(0);
 await expect(page.locator('.car-invite-evidence-actions')).toContainText('1 attached');
 expect(await page.evaluate(()=>(window as unknown as {cameraTracks:MediaStreamTrack[]}).cameraTracks.every(track=>track.readyState==='ended'))).toBe(true);
});

test("mobile photo control opens the native camera input and permission errors offer upload",async({page})=>{
 await prepare(page);await page.addInitScript(()=>Object.defineProperty(navigator,'userAgent',{configurable:true,get:()=> 'Mozilla/5.0 Android Mobile'}));
 await page.goto('/qms/car-access/synthetic-token?capture=1');
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const picker=await chooser;expect(await picker.element().getAttribute('capture')).toBe('environment');expect(await picker.element().getAttribute('accept')).toBe('image/*');
 await page.evaluate(()=>Object.defineProperty(navigator,'userAgent',{get:()=> 'Desktop browser'}));
 await page.evaluate(()=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{throw new DOMException('Camera permission denied','NotAllowedError');}}));
 await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Camera capture'});await expect(modal).toContainText('Camera permission denied');
 const files=page.waitForEvent('filechooser');await modal.getByRole('button',{name:'Upload files instead',exact:true}).click();
 expect((await files).isMultiple()).toBe(true);await expect(modal).toHaveCount(0);
});

test("attachments can be uploaded and cited without leaving the root cause tools",async({page})=>{
 const state=await prepare(page);
 await page.route('**/quality/cars/invite/current/attachments',route=>route.fulfill({contentType:'application/json',body:route.request().method()==='POST'?JSON.stringify({id:'analysis-file',filename:'inspection.pdf',content_type:'application/pdf',download_url:'/files/inspection.pdf'}):'[]'}));
 await page.goto('/qms/car-access/synthetic-token');
 const workbench=page.getByRole('region',{name:'Root cause investigation'});
 await expect(workbench.getByLabel('Final root cause explanation',{exact:true})).toBeVisible({timeout:20000});
 await page.locator('input[type="file"][multiple]').setInputFiles({name:'inspection.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF inspection')});
 const reference=workbench.getByRole('combobox',{name:'Link uploaded CAR evidence to the conclusion',exact:true});
 await reference.selectOption('CAR-ATTACHMENT:analysis-file');
 await expect.poll(()=>state.writes.at(-1)?.investigation.conclusion_evidence_references).toEqual(['CAR-ATTACHMENT:analysis-file']);
});

test("existing legacy response is retained in the single conclusion editor and can be saved",async({page})=>{
 const state=await prepare(page,false,false,false,'Retained root cause explanation from the original response.');
 await page.goto('/qms/car-access/synthetic-token');
 const progress=page.getByRole('complementary',{name:'Corrective action response progress'});
 await progress.getByRole('button',{name:'Root cause',exact:true}).click();
 const conclusion=page.getByLabel('Final root cause explanation',{exact:true});
 await expect(conclusion).toHaveValue('Retained root cause explanation from the original response.');
 await conclusion.fill('Updated root cause explanation with retained original context.');
 await page.getByRole('button',{name:'Save investigation',exact:true}).click();
 await expect.poll(()=>state.writes.at(-1)?.investigation.conclusion).toBe('Updated root cause explanation with retained original context.');
 await expect(page.getByText('Root cause analysis (legacy narrative response)',{exact:true})).toHaveCount(0);
});

test("public evidence keeps its response-section label through upload and reassignment",async({page})=>{
 await prepare(page);let uploaded=false;let patched=false;
 const file={id:'section-file',car_id:carId,filename:'containment.txt',description:'Isolation record',response_section:'CONTAINMENT',content_type:'text/plain',download_url:'/files/containment.txt'};
 await page.route('**/quality/cars/invite/current/attachments*',async route=>{
  if(route.request().method()==='POST'){
   const data=route.request().postDataBuffer()?.toString()||'';expect(data).toContain('name="response_section"');expect(data).toContain('CONTAINMENT');uploaded=true;
   return route.fulfill({contentType:'application/json',body:JSON.stringify(file)});
  }
  return route.fulfill({contentType:'application/json',body:'[]'});
 });
 await page.route('**/quality/cars/invite/current/attachments/section-file',route=>{const data=route.request().postDataJSON();expect(data).toEqual({response_section:'ROOT_CAUSE'});patched=true;return route.fulfill({contentType:'application/json',body:JSON.stringify({...file,response_section:data.response_section})});});
 await page.goto('/qms/car-access/synthetic-token?capture=1');
 await page.getByRole('combobox',{name:'Evidence response section',exact:true}).selectOption('CONTAINMENT');
 await page.locator('input[type="file"][multiple]').setInputFiles({name:'containment.txt',mimeType:'text/plain',buffer:Buffer.from('Isolation record')});
 await expect.poll(()=>uploaded).toBe(true);
 const section=page.getByRole('combobox',{name:'Response section for containment.txt',exact:true});await expect(section).toHaveValue('CONTAINMENT');
 await section.selectOption('ROOT_CAUSE');await expect.poll(()=>patched).toBe(true);await expect(section).toHaveValue('ROOT_CAUSE');
});

test("fragment invitation opens without employee login and keeps the bearer out of API paths", async ({ page }) => {
  await prepare(page);
  const publicRequests: Array<{ pathname: string; authorization: string | undefined }> = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.pathname.includes("/quality/cars/invite/current")) {
      publicRequests.push({ pathname: url.pathname, authorization: request.headers()["authorization"] });
    }
  });
  await page.goto("/qms/car-access#token=synthetic-token");
  await expect(page.locator(".car-invite-kicker").getByText("QA-CAR-001", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page).toHaveURL(/\/qms\/car-access#token=synthetic-token$/);
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await expect.poll(() => publicRequests.some(request => request.authorization === "Bearer synthetic-token")).toBe(true);
  expect(publicRequests.length).toBeGreaterThan(0);
  expect(publicRequests.every(request => !request.pathname.includes("synthetic-token"))).toBe(true);
});

test("legacy query invites migrate to a token fragment without employee login", async ({ page }) => {
  await prepare(page);
  await page.goto("/car-invite?token=synthetic-token&capture=1");
  await expect(page.locator(".car-invite-kicker").getByText("QA-CAR-001", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page).toHaveURL(/\/qms\/car-access#token=synthetic-token&capture=1$/);
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
});

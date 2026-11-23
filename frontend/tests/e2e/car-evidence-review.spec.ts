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
    if (path.endsWith("/feedback")) body = {car_id:carId,status:"OPEN",root_cause_status:"PENDING",capa_status:"PENDING",items:[],next_cursor:null};
    if (path.endsWith("/cars/register/paged")) body = { items:[car],total:1,limit:25,offset:0,has_more:false,summary:{total:1,open:1,overdue:0,in_review:0} };
    if (path.endsWith("/investigation")) body = malformed ? { module:"cars",record_id:carId } : projection;
    if (path.endsWith("/pareto-snapshots")) paretoRequests++;
    return route.fulfill({ contentType:"application/json",body:JSON.stringify(body) });
  });
  return { recover: () => { malformed = false; }, paretoRequests: () => paretoRequests };
}

test("reviewer views linked evidence beside responses and sees independent RC and CAP decisions",async({page})=>{
 await prepare(page);
 const image={id:'photo-1',car_id:carId,filename:'containment.png',response_section:'CONTAINMENT',content_type:'image/png',size_bytes:68,uploaded_at:'2026-11-21T12:00:00Z'};
 const text={id:'root-1',car_id:carId,filename:'investigation.txt',response_section:'ROOT_CAUSE',content_type:'text/plain',size_bytes:90,uploaded_at:'2026-11-21T12:00:00Z'};
 await page.route('**/quality/cars/register/paged*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({items:[{...car,containment_action:'Affected equipment isolated.',root_cause:'The independent review control was missing.',corrective_action:'Introduce independent release review.',root_cause_status:'REJECTED',capa_status:'ACCEPTED',root_cause_review_note:'Explain why the missing control was not detected.',capa_review_note:'Plan has an accountable owner and deadline.'}],total:1,limit:1,offset:0,has_more:false,summary:{total:1,open:1,overdue:0,in_review:0}})}));
 await page.route('**/quality/cars/*/attachments',route=>route.fulfill({contentType:'application/json',body:JSON.stringify([image,text])}));
 let fileReads=0;await page.route('**/quality/cars/*/attachments/*/download',route=>{fileReads++;return route.request().url().includes('photo-1')?route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jk0cAAAAASUVORK5CYII=','base64')}):route.fulfill({contentType:'text/plain',body:'Documented investigation evidence for independent assessment.'});});
 await page.setViewportSize({width:1440,height:1000});await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
 const immediate=page.getByRole('region',{name:'Immediate action',exact:true});
 await expect(immediate.getByRole('button',{name:'View containment.png for Immediate action',exact:true})).toBeVisible({timeout:15000});
 const root=page.getByRole('region',{name:'Root cause',exact:true});const cap=page.getByRole('region',{name:'Corrective Action (CAP)',exact:true});
 await expect(root.locator('.case-response-prose')).toContainText('The independent review control was missing.');
 await expect(root.locator('.case-quality-decision')).toContainText('Explain why the missing control was not detected.');
 await expect(root.locator('.case-response-evidence__body > header')).toContainText('Rejected');
 await expect(cap.locator('.case-response-evidence__body > header')).toContainText('Accepted');
 await expect(page.locator('.case-decision')).toHaveCount(2);
 await expect(page.getByText(/System audit trail|Source frequency analysis|Original CAR statement/)).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'Non-conformance',exact:true})).toBeVisible();
 await expect(cap.locator('.case-evidence-thumbnail')).toHaveCount(0);
 const downloads:string[]=[];page.on('download',event=>downloads.push(event.suggestedFilename()));
 await root.getByRole('button',{name:'View investigation.txt for Root cause',exact:true}).click();
 const preview=page.getByRole('region',{name:'Evidence preview',exact:true});await expect(preview).toContainText('Documented investigation evidence');
 expect(downloads).toEqual([]);
 const left=await root.boundingBox(),right=await preview.boundingBox();expect(right!.x).toBeGreaterThan(left!.x+left!.width-1);
 await page.screenshot({path:'test-results/car-evidence-side-by-side.png',fullPage:true});
 await preview.getByRole('button',{name:'Close evidence preview'}).click();
 await immediate.getByRole('button',{name:'View containment.png for Immediate action',exact:true}).click();
 await expect(page.getByRole('region',{name:'Evidence preview',exact:true}).getByRole('img',{name:'containment.png',exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 const readsBeforeReopen=fileReads;
 await page.getByRole('region',{name:'Evidence preview',exact:true}).getByRole('button',{name:'Close evidence preview'}).click();
 await immediate.getByRole('button',{name:'View containment.png for Immediate action',exact:true}).click();
 await expect(page.getByRole('region',{name:'Evidence preview',exact:true}).getByRole('img',{name:'containment.png',exact:true})).toBeVisible();
 expect(fileReads).toBe(readsBeforeReopen);
 expect(downloads).toEqual([]);
});
test("unassigned evidence stays in the general list and preview failures can be retried",async({page})=>{
 await prepare(page);await page.route('**/quality/cars/*/attachments',route=>route.fulfill({contentType:'application/json',body:JSON.stringify([{id:'general',car_id:carId,filename:'general.txt',content_type:'text/plain'}])}));
 let fail=true;await page.route('**/quality/cars/*/attachments/general/download',route=>fail?route.fulfill({status:503,body:'Unavailable'}):route.fulfill({contentType:'text/plain',body:'Recovered evidence.'}));
 await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
 await expect(page.getByRole('button',{name:'general.txt',exact:true})).toBeVisible({timeout:15000});
 await expect(page.locator('.case-evidence-thumbnail')).toHaveCount(0);
 await page.getByRole('button',{name:'general.txt',exact:true}).click();
 const preview=page.getByRole('region',{name:'Evidence preview',exact:true});await expect(preview.getByRole('alert')).toContainText('Evidence could not be opened.');
 fail=false;await preview.getByRole('button',{name:'Retry preview'}).click();await expect(preview).toContainText('Recovered evidence.');
});

function twoPagePdf(){
 const stream=(number:number)=>`BT /F1 14 Tf 30 250 Td (Evidence page ${number}) Tj ET`;
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',`<< /Length ${stream(1).length} >>\nstream\n${stream(1)}\nendstream`,'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',`<< /Length ${stream(2).length} >>\nstream\n${stream(2)}\nendstream`,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
 let body='%PDF-1.4\n';const offsets=[0];objects.forEach((object,index)=>{offsets.push(Buffer.byteLength(body));body+=`${index+1} 0 obj\n${object}\nendobj\n`;});const start=Buffer.byteLength(body);body+=`xref\n0 8\n0000000000 65535 f \n${offsets.slice(1).map(offset=>`${offset.toString().padStart(10,'0')} 00000 n \n`).join('')}trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF`;return Buffer.from(body);
}
test("PDF evidence has a first-page thumbnail and can be paged without downloading",async({page})=>{
 await prepare(page);await page.route('**/quality/cars/*/attachments',route=>route.fulfill({contentType:'application/json',body:JSON.stringify([{id:'pdf-1',car_id:carId,filename:'inspection.pdf',response_section:'ROOT_CAUSE',content_type:'application/pdf',size_bytes:1000}])}));
 await page.route('**/quality/cars/*/attachments/pdf-1/download',route=>route.fulfill({contentType:'application/pdf',body:twoPagePdf()}));
 await page.goto(`/maintenance/tenant-a/quality/cars?carId=${carId}`);
 const thumbnail=page.getByRole('button',{name:'View inspection.pdf for Root cause',exact:true});await expect(thumbnail.locator('canvas')).toBeVisible({timeout:20000});
 await thumbnail.click();const preview=page.getByRole('region',{name:'Evidence preview',exact:true});await expect(preview.getByRole('navigation',{name:'Evidence document pages'})).toContainText('Page 1 of 2');
 await preview.getByRole('button',{name:'Next',exact:true}).click();await expect(preview).toContainText('Page 2 of 2');await expect(preview.locator('canvas')).toBeVisible();
});

import { expect, test } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";
const id="11111111-1111-4111-8111-111111111111";
const second="22222222-2222-4222-8222-222222222222";
const row={id,work_number:"CW-001",work_title:"Component overhaul and inspection",site_code:"NBO",status:"IN_PROGRESS",work_type:"WORKSHOP",updated_at:"2026-11-20",version:1,supplier_id:1};
const detail={work:{...row,function:"Component overhaul",scope_text:"Inspect and overhaul the assigned component against the approved maintenance data.",defect:"Scheduled overhaul",data_reference:"CMM-001",data_revision:"4",inspections_json:[],required_release:"Approved release certificate",internal_work_reference:"WP-001",registration:null,part_number:"PN-123",serial_number:"SN-456",requirements_json:{},contract_id:"AGR-001",purchase_order_id:null},inspection_checks:[],history:[],additional_work:[],custody:[{id:"custody",item_type:"COMPONENT",description:"Component assembly with a long identification reference",quantity:1,uom:"EA",state:"DISPATCHED",serial_batch:"SN-456"}],evidence:[],closure_blockers:["Release evidence awaiting review"],allowed_actions:[],can_review_inspections:false};
const capabilities=["profile.read","document.read","document.submit","task.read","task.respond","procurement.read","procurement.respond"];
async function partner(page:import("@playwright/test").Page){
  await page.route("**/api/external-provider/**",route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown={items:[],limit:25,offset:0,has_more:false};
    if(path.endsWith("/partner/tenant-a/session"))body={tenant:"tenant-a",organization:{legal_name:"Example Aviation"},role:"TECHNICAL_REPRESENTATIVE",capabilities,restricted:false};
    else if(path.endsWith("/session"))body={csrf:"test"};
    else if(path.endsWith("/maintenance-work"))body={items:[row]};
    else if(path.endsWith("/maintenance-work/"+id))body=detail;
    else if(path.endsWith("/documents/requirements"))body={items:[{id:"req",code:"WORK_ORDER",title:"Work records",description:"Submit original work evidence",mandatory:true}]};
    else if(path.endsWith("/commerce/rfqs"))body={items:[{id:1,rfq_number:"RFQ-001",title:"Overhaul service quotation",status:"ISSUED",response_due_at:"2026-12-01"}]};
    else if(path.endsWith("/commerce/rfqs/1"))body={id:1,rfq_number:"RFQ-001",title:"Overhaul service quotation",status:"ISSUED",response_due_at:"2026-12-01",terms:"Standard payment terms",quality_clauses:"Approved supplier requirements",lines:[{id:1,line_number:1,part_number:"PN-123",description:"Component overhaul",quantity:1,uom:"EA"}],my_quotes:[],history:[]};
    return route.fulfill({contentType:"application/json",body:JSON.stringify(body)});
  });
}
test("subcontractor work and evidence retain context on desktop and phone",async({page})=>{
  test.setTimeout(90000);await partner(page);
  await page.goto("/partner/tenant-a/work?work="+id);
  await expect(page.getByRole("heading",{name:"Technical work control"})).toBeVisible();
  await expect(page.getByLabel("Contracted work progress")).toBeVisible();
  await page.screenshot({path:"../.artifacts/subcontract-work-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.locator("body").evaluate(el=>el.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"../.artifacts/subcontract-work-mobile.png",fullPage:true});
  await page.getByRole("link",{name:"Open governed work-document uploads"}).click();
  await expect(page.getByRole("combobox",{name:"Linked scope",exact:true})).toHaveValue("CONTRACTED_WORK");
  await expect(page.getByRole("combobox",{name:"Authorized contracted work",exact:true})).toHaveValue(id);
  await page.screenshot({path:"../.artifacts/subcontract-evidence-mobile.png",fullPage:true});
});
test("supplier RFQ forms and line tables fit phone width",async({page})=>{
  await partner(page);await page.setViewportSize({width:390,height:844});
  await page.goto("/partner/tenant-a/procurement");
  await page.getByRole("button",{name:"Open",exact:true}).click();
  await expect(page.getByRole("heading",{name:"RFQ response & revisions"})).toBeVisible();
  await expect(page.getByRole("region",{name:"Commercial line items"})).toBeVisible();
  expect(await page.locator("body").evaluate(el=>el.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"../.artifacts/supplier-rfq-mobile.png",fullPage:true});
});
test("internal contracted work has a responsive creation form and clears obsolete detail",async({page})=>{
  test.setTimeout(90000);await mockQualityShell(page);

  await page.addInitScript(()=>{
    sessionStorage.setItem("amo_portal_token",`e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code","AMO-A");localStorage.setItem("amo_slug","tenant-a");localStorage.setItem("amo_department","maintenance");
    localStorage.setItem("amo_onboarding_status",JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user",JSON.stringify({id:"admin-a",amo_id:"amo-a",amo_code:"AMO-A",amo_slug:"tenant-a",role:"AMO_ADMIN",is_active:true,is_amo_admin:true,full_name:"Administrator"}));
  });
  await page.route("**/api/maintenance/tenant-a/contracted-work**",async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown={items:[]};
    if(path.endsWith("/contracted-work"))body={items:[row,{...row,id:second,work_number:"CW-002",work_title:"Second technical order"}],can_create:true};
    else if(path.endsWith("/options"))body={providers:[],scopes:[],contracts:[],coordinators:[]};
    else if(path.endsWith("/"+id))body=detail;
    else if(path.endsWith("/"+second)){await new Promise(resolve=>setTimeout(resolve,600));body={...detail,work:{...detail.work,id:second,work_number:"CW-002",work_title:"Second technical order"}};}
    return route.fulfill({contentType:"application/json",body:JSON.stringify(body)});
  });
  await page.goto("/maintenance/tenant-a/contracted-work");
  await expect(page.getByRole("heading",{name:"CW-001",exact:false})).toBeVisible();
  await page.getByRole("button",{name:/CW-002/}).click();
  await expect(page.getByText("Loading selected work order...")).toBeVisible();
  await expect(page.getByRole("heading",{name:/CW-001/})).toHaveCount(0);
  await expect(page.getByRole("heading",{name:/CW-002/})).toBeVisible();
  await page.getByRole("button",{name:"New controlled work order"}).click();
  await expect(page.getByRole("group",{name:"1. Provider and agreement"})).toBeVisible();
  await page.screenshot({path:"../.artifacts/internal-subcontract-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.locator(".contracted-workspace").evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  await page.screenshot({path:"../.artifacts/internal-subcontract-mobile.png",fullPage:true});
});

import {expect,test} from "@playwright/test";
import {mockQualityShell} from "./helpers/mockQualityShell";
test.beforeEach(async({page})=>{
  await mockQualityShell(page);
  await page.addInitScript(()=>{
    sessionStorage.setItem("amo_portal_token",`e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code","AMO-A");localStorage.setItem("amo_slug","tenant-a");localStorage.setItem("amo_department","quality");
    localStorage.setItem("amo_onboarding_status",JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user",JSON.stringify({id:"admin-a",amo_id:"amo-a",amo_slug:"tenant-a",amo_code:"AMO-A",role:"AMO_ADMIN",is_active:true,is_amo_admin:true,is_superuser:false,full_name:"Administrator"}));
  });
  await page.route("**/api/maintenance/**/quality/suppliers/**",route=>{
    const path=new URL(route.request().url()).pathname;
    const body=path.endsWith("/governance")?{total:0,approved:0,suspended:0,review_due:0,required_contract_missing:0,evidence_expiring:0}:{items:[],total:0,columns:[],limit:30,offset:0,has_more:false};
    return route.fulfill({contentType:"application/json",body:JSON.stringify(body)});
  });
});
test("approved and expired provider menus request the intended status from the governed register",async({page})=>{
  for(const [view,status,title] of [["approved-list","APPROVED","Approved external providers"],["expired-approvals","EXPIRED","Expired provider approvals"]]){
    const response=page.waitForRequest(r=>r.url().includes("/suppliers/providers?")&&new URL(r.url()).searchParams.get("status")===status);
    await page.goto(`/maintenance/tenant-a/quality/suppliers/${view}`);await response;
    await expect(page.getByRole("heading",{name:title,exact:true})).toBeVisible();
    await expect(page.getByRole("combobox",{name:"Provider status",exact:true})).toHaveValue(status);
    await expect(page.getByRole("combobox",{name:"Provider status",exact:true})).toBeDisabled();
    await expect(page.getByRole("button",{name:"Switch app",exact:true})).toBeVisible();
  }
});
test("provider evaluation, audit and finding menus use their distinct bounded registers",async({page})=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  for(const [view,title] of [["evaluations","Provider evaluations"],["supplier-audits","Provider audits"],["supplier-findings","Provider findings"]]){
    const response=page.waitForRequest(r=>new URL(r.url()).pathname.endsWith(`/suppliers/${view}`)&&r.resourceType()==="fetch");
    await page.goto(`/maintenance/tenant-a/quality/suppliers/${view}`);await response;
    await expect(page.getByRole("heading",{name:title,exact:true})).toBeVisible();
    await expect(page.getByRole("navigation",{name:"QMS page menus"})).toHaveCount(1);
    await expect(page.locator(".qms-provider-summary")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

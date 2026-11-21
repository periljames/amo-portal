import { expect, test } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

test("sandbox invitation identifies both addresses and stays readable on mobile", async ({ page }) => {
  test.setTimeout(90000);
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A"); localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user", JSON.stringify({id:"admin-a",amo_id:"amo-a",amo_code:"AMO-A",amo_slug:"tenant-a",role:"AMO_ADMIN",is_active:true,is_amo_admin:true,full_name:"Administrator"}));
  });
  await page.route("**/quality/external-accounts**", route => {
    if (route.request().resourceType() === "document") return route.continue();
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/invitations") ? {id:"grant-a",delivery:{email_status:"SENT",email_delivery_status:"ACCEPTED",provider_accepted:true,sending_mode:"SANDBOX",recipient:"vendor@example.test",effective_recipient:"test-mailbox@example.test"}} : path.endsWith("/suppliers") ? {items:[{id:1,legal_name:"Example Aviation",supplier_code:"V001",status:"APPROVED"}],has_more:false} : {items:[]};
    return route.fulfill({contentType:"application/json",body:JSON.stringify(body)});
  });
  await page.goto("/maintenance/tenant-a/quality/external-accounts?view=invite");
  await page.getByRole("combobox", {name:"Provider organization",exact:true}).selectOption("1");
  await page.getByLabel("Full name", {exact:true}).fill("Vendor Representative");
  await page.getByLabel("Email", {exact:true}).fill("vendor@example.test");
  await page.getByRole("button", {name:"Issue one-time email invitation",exact:true}).click();
  const notice = page.getByRole("alert").filter({hasText:"Test email accepted"});
  await expect(notice).toContainText("vendor@example.test");
  await expect(notice).toContainText("test-mailbox@example.test");
  await page.screenshot({path:"../.artifacts/vendor-review-quality-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(notice).toBeVisible();
  await page.screenshot({path:"../.artifacts/vendor-review-quality-mobile.png",fullPage:true});
  expect(await page.locator(".vendor-quality-workspace").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("vendor entry keeps tenant context through invitation and recovery", async ({ page }) => {
  await page.route("**/api/external-provider/session", route => route.fulfill({status:401,contentType:"application/json",body:'{"detail":"Sign in required"}'}));
  await page.goto("/vendor/login?amo=tenant-a");
  await page.getByRole("link",{name:"Invitation",exact:true}).click();
  await expect(page).toHaveURL(/vendor\/invite\?amo=tenant-a/);
  await expect(page.getByRole("heading",{name:"Accept invitation",exact:true})).toBeVisible();
  await page.screenshot({path:"../.artifacts/vendor-review-invitation-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:"../.artifacts/vendor-review-invitation-mobile.png",fullPage:true});
  expect(await page.locator("body").evaluate(el => el.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("link",{name:"Forgot password",exact:true}).click();
  await expect(page.getByLabel("AMO tenant code")).toHaveValue("tenant-a");
});
test("partner organization has a bounded mobile workspace and account navigation", async ({ page }) => {
  await page.route("**/api/external-provider/**", route => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/partner/tenant-a/session") ? {tenant:"tenant-a",organization:{legal_name:"Example Aviation",trading_name:"Example Aviation"},role:"READ_ONLY",capabilities:["profile.read"],restricted:false} : path.endsWith("/session") ? {csrf:"fixture"} : path.endsWith("/organization") ? {supplier:{legal_name:"Example Aviation",email:"vendor@example.test",supplier_code:"V001"},roles:[{role_code:"SUPPLIER"}],profile:null} : {items:[],limit:15,offset:0,has_more:false};
    return route.fulfill({contentType:"application/json",body:JSON.stringify(body)});
  });
  await page.goto("/partner/tenant-a/organization");
  await expect(page.getByRole("heading",{name:"Registered organization"})).toBeVisible();
  await expect(page.getByRole("link",{name:"Account security"})).toHaveAttribute("href","/vendor/account?amo=tenant-a");
  await page.screenshot({path:"../.artifacts/vendor-review-partner-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:"../.artifacts/vendor-review-partner-mobile.png",fullPage:true});
  expect(await page.locator("body").evaluate(el=>el.scrollWidth<=window.innerWidth)).toBe(true);
});
test("six-digit invitation sends the AMO and email with a clear expiry hint", async ({ page }) => {
  await page.route("**/api/external-provider/session", route=>route.fulfill({status:401,contentType:"application/json",body:'{"detail":"Sign in required"}'}));
  let submitted:Record<string,unknown>|null=null;
  let requested:Record<string,unknown>|null=null;
  await page.route("**/api/external-provider/invitations/request-code",route=>{
    requested=route.request().postDataJSON();
    return route.fulfill({status:202,contentType:"application/json",body:'{"message":"If a pending invitation matches, a new code will be emailed."}'});
  });
  await page.route("**/api/external-provider/invitations/accept",route=>{
    submitted=route.request().postDataJSON();
    return route.fulfill({contentType:"application/json",body:'{"status":"VERIFIED"}'});
  });
  await page.goto("/vendor/invite?amo=tenant-a");
  await page.getByRole("textbox",{name:"Email address",exact:true}).fill("person@example.com");
  const code=page.getByRole("textbox",{name:"One-time email code",exact:true});
  await expect(code).toHaveAttribute("autocomplete","one-time-code");
  await page.getByRole("button",{name:"Send a new code",exact:true}).click();
  await expect(page.getByRole("status")).toContainText("If a pending invitation matches");
  expect(requested).toMatchObject({amo_slug:"tenant-a",email:"person@example.com"});
  await code.fill("123 456");
  await page.getByLabel("Password (required for a new account)").fill("ExamplePassword!123");
  await expect(page.getByText(/expires after 10 minutes/)).toBeVisible();
  await page.screenshot({path:"../.artifacts/vendor-six-digit-code.png",fullPage:true});
  await page.getByRole("button",{name:"Accept invitation",exact:true}).click();
  await expect(page).toHaveURL(/vendor\/login\?amo=tenant-a/);
  expect(submitted).toMatchObject({code:"123456",amo_slug:"tenant-a",email:"person@example.com"});
});

test("Quality officers reach account review without an unrelated audit-management gate",async({page})=>{
  test.setTimeout(90000);await mockQualityShell(page);
  await page.addInitScript(()=>{
    sessionStorage.setItem("amo_portal_token",`e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code","AMO-A");localStorage.setItem("amo_slug","tenant-a");localStorage.setItem("amo_department","quality");
    localStorage.setItem("amo_onboarding_status",JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user",JSON.stringify({id:"officer",amo_id:"amo-a",amo_code:"AMO-A",amo_slug:"tenant-a",role:"QUALITY_OFFICER",is_active:true,is_superuser:false,is_amo_admin:false,module_access:{quality:"view"},full_name:"Quality Officer"}));
  });
  await page.route("**/quality/external-accounts**",route=>route.request().resourceType()==="document"?route.continue():route.fulfill({contentType:"application/json",body:'{"items":[]}'}));
  await page.goto("/maintenance/tenant-a/quality/external-accounts/register");
  await expect(page.getByRole("heading",{name:"Vendor accounts & access",exact:true})).toBeVisible({timeout:20000});
  await expect(page.getByText("You do not have permission to access this QMS page.", {exact:true})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Invite representative",exact:true})).toHaveCount(0);
});

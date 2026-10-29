import { expect,test,type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";
async function prepare(page:Page,admin=false){
  await mockQualityShell(page);
  await page.route("**/quality/settings",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({settings:{numbering_rules:{audit_prefix:"QAR",sequence_digits:4},workflow_rules:{},notification_rules:{},retention_rules:{}}})}));
  await page.route("**/quality/settings/numbering",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({rules:{audit_prefix:"QAR",car_prefix:"CAR",reliability_car_prefix:"RCAR",finding_prefix:"F",sequence_digits:3,date_format:"YY"},series:[],server_date:"2026-10-26",server_period:"2026",counter_year:26,audit_scopes:[{code:"MO",name:"Maintenance organisation"}],car_unit_code:"MO"})}));
  await page.addInitScript(({admin})=>{
    sessionStorage.setItem("amo_portal_token",`e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code","AMO-A");localStorage.setItem("amo_slug","tenant-a");localStorage.setItem("amo_department","quality");
    localStorage.setItem("amo_onboarding_status",JSON.stringify({is_complete:true}));localStorage.setItem("amo_color_scheme","light");
    localStorage.setItem("amo_current_user",JSON.stringify({id:"quality-user-a",amo_id:"amo-a",amo_slug:"tenant-a",amo_code:"AMO-A",role:"QUALITY_MANAGER",department_code:"quality",full_name:"Quality User",first_name:"Quality",is_active:true,is_amo_admin:admin,is_superuser:false,module_access:{quality:"manage",documents:"view",training:"view"}}));
  },{admin});
  await page.goto("/maintenance/tenant-a/quality/settings/general",{waitUntil:"domcontentloaded"});
  await expect(page.locator(".qms-settings-page h1")).toBeVisible({timeout:20000});
}
const selector=(page:Page)=>page.getByRole("dialog",{name:"Choose your next destination."});
test("normal users can browse assigned apps without losing page edits",async({page})=>{
  await prepare(page);
  await page.getByRole("link",{name:/^Numbering Reference/}).click();
  const field=page.getByRole("textbox").first();await field.fill("EDITEDDRAFT");
  const before=page.url();await page.getByRole("button",{name:"Switch app",exact:true}).click();
  const modal=selector(page);await expect(modal).toBeVisible();
  await expect(modal.getByRole("button",{name:"QMS",exact:true})).toHaveAttribute("aria-pressed","true");
  await expect(modal.getByRole("button",{name:"Document Control",exact:true})).toBeVisible();
  await expect(modal.getByRole("button",{name:"Administration",exact:true})).toHaveCount(0);
  await expect(modal.getByRole("button",{name:"Maintenance",exact:true})).toHaveCount(0);
  await page.keyboard.press("ArrowRight");await expect(page).toHaveURL(before);
  await page.keyboard.press("Escape");await expect(modal).toHaveCount(0);await expect(field).toHaveValue("EDITEDDRAFT");
  await expect(page.getByRole("button",{name:"Switch app",exact:true})).toBeFocused();
});
test("administrator can open another app and return through its navigation",async({page})=>{
  await prepare(page,true);await page.getByRole("button",{name:"Switch app",exact:true}).click();
  const modal=selector(page);
  const training=modal.getByRole("button",{name:"Training & Competence",exact:true});
  await training.focus();await expect(training).toHaveAttribute("aria-pressed","true");
  await modal.getByRole("button",{name:"Open app",exact:true}).click();
  await expect(page).toHaveURL(/\/training\/competence\/control-room$/);
  await expect(modal).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Switch app",exact:true})).toBeVisible({timeout:15000});
});
test("Administration appears after the existing timed Admin View is activated",async({page})=>{
  await prepare(page,true);let active=false;
  await page.route("**/accounts/admin/overview-summary",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({system:{status:"healthy",last_checked_at:new Date().toISOString(),refresh_paused:false,errors:[]},badges:{},issues:[],recent_activity:[],recent_activity_available:true})}));
  await page.route("**/admin-profile/**",route=>{
    if(new URL(route.request().url()).pathname.endsWith("/activate"))active=true;
    return route.fulfill({contentType:"application/json",body:JSON.stringify({eligible:true,active,session_id:active?"fixture-session":null,expires_at:active?new Date(Date.now()+4*3600000).toISOString():null,grant_type:"PERMANENT"})});
  });
  await page.reload();await page.getByRole("button",{name:"Account and appearance"}).click();
  await page.getByRole("menuitem",{name:"Activate Admin View",exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/overview$/);
  await expect(page.getByRole("heading",{name:"Overview",exact:true})).toBeVisible();
  await expect(page.locator(".tenant-shell__admin-chip")).toBeVisible();
  await page.getByRole("button",{name:"Switch app",exact:true}).click();
  await expect(selector(page).getByRole("button",{name:"Administration",exact:true})).toBeVisible();
});
test("drawer entry and keyboard focus stay within the selector",async({page})=>{
  await prepare(page);await page.getByRole("button",{name:"Open navigation",exact:true}).click();
  await page.getByRole("dialog",{name:"QMS navigation"}).getByRole("button",{name:"Apps",exact:true}).click();
  const modal=selector(page);await expect(modal).toBeVisible();
  expect(await modal.locator("h1").evaluate(e=>getComputedStyle(e).color)).toBe("rgb(240, 247, 255)");
  const close=modal.getByRole("button",{name:"Close app selector"});await close.focus();await page.keyboard.press("Shift+Tab");
  await expect(modal.getByRole("button",{name:"Pause aviation background"})).toBeFocused();
  await page.keyboard.press("Tab");await expect(close).toBeFocused();
  await close.click();await expect(modal).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Switch app",exact:true})).toBeEnabled();
});
test("aviation background animates, can be paused and obeys reduced motion",async({page})=>{
  await prepare(page,true);await page.getByRole("button",{name:"Switch app",exact:true}).click();
  const modal=selector(page);await expect(modal).toBeVisible();
  expect(await page.locator(".portal-apps__aircraft").evaluate(e=>getComputedStyle(e).animationName)).toBe("portal-flight");
  await modal.getByRole("button",{name:"Pause aviation background"}).click();
  expect(await page.locator(".portal-apps__aircraft").evaluate(e=>getComputedStyle(e).animationPlayState)).toBe("paused");
  await page.emulateMedia({reducedMotion:"reduce"});
  expect(await page.locator(".portal-apps__aircraft").evaluate(e=>getComputedStyle(e).animationName)).toBe("none");
  await page.screenshot({path:"../.artifacts/app-selector-desktop-fixture.png"});
});
test("mobile selector keeps app navigation reachable without page overflow",async({page})=>{
  await page.setViewportSize({width:390,height:844});await prepare(page,true);
  await page.getByRole("button",{name:"Switch app",exact:true}).click();const modal=selector(page);await expect(modal).toBeVisible();
  expect(await modal.evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
  await modal.getByRole("button",{name:"QMS",exact:true}).focus();await page.keyboard.press("End");
  await expect(modal.locator('.portal-apps__tile').last()).toBeFocused();
  await page.screenshot({path:"../.artifacts/app-selector-mobile-fixture.png"});
});
test("an unavailable selector chunk can be closed without losing a draft",async({page})=>{
  await prepare(page);await page.getByRole("link",{name:/^Numbering Reference/}).click();
  const field=page.getByRole("textbox").first();await field.fill("RETAINEDDRAFT");
  await page.route("**/PortalAppSelector-*.js",route=>route.abort());
  await page.getByRole("button",{name:"Switch app",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Apps could not be opened"})).toBeVisible();
  await page.getByRole("button",{name:"Back to work",exact:true}).click();
  await expect(field).toHaveValue("RETAINEDDRAFT");
});

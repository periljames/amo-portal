import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

const reference = "QAR/MO/26/006-F-004";
const path = "/maintenance/tenant-a/quality/findings/finding-one/overview";
async function openFinding(page: Page) {
  await page.goto(path,{waitUntil:"domcontentloaded"});
  await expect(page.locator(".case-finding")).toBeVisible({timeout:15_000});
}
async function prepare(page: Page, linkedCar = false) {
  await mockQualityShell(page);
  await page.addInitScript(() => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code","AMO-A"); localStorage.setItem("amo_slug","tenant-a"); localStorage.setItem("amo_department","quality");
    localStorage.setItem("amo_color_scheme","light");
    localStorage.setItem("amo_onboarding_status",JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user",JSON.stringify({id:"quality-user-a",amo_id:"amo-a",amo_slug:"tenant-a",role:"QUALITY_MANAGER",full_name:"Quality Manager",first_name:"Quality",last_name:"Manager",is_active:true,is_amo_admin:true,is_superuser:false}));
  });
  await page.route("**/audits/register/paged?**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({rows:[{
    audit:{id:"audit-one",audit_ref:"QAR/MO/26/006",title:"Maintenance audit"},
    finding:{id:"finding-one",audit_id:"audit-one",finding_ref:reference,requirement_ref:"2.6",level:linkedCar?"LEVEL_2":"LEVEL_4",finding_type:linkedCar?"NON_CONFORMITY":"OBSERVATION",severity:"MINOR",description:"Review the controlled maintenance procedure and document the observed gap without losing the full finding statement.",objective_evidence:"Inspected the signed checklist and retained documentary evidence for procedure 2.6.",created_at:"2026-10-18T10:00:00Z",closed_at:null},
    linked_cars:linkedCar?[{id:"car-one",car_number:"CAR-006",status:"OPEN",responsible_personnel:"Quality owner",root_cause_text:"A reviewed root cause remains visible.",capa_text:"The corrective action remains visible."}]:[],
  }],total:1,limit:1,offset:0,has_more:false,car_linked_findings:linkedCar?1:0,open_car_count:linkedCar?1:0})}));
  await page.route("**/audits/audit-one/evidence?**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({items:[]})}));
}

test("Finding detail has one identity and uses both desktop columns", async ({page}) => {
  await prepare(page);
  await openFinding(page);
  await expect(page.getByRole("heading",{name:reference,exact:true})).toHaveCount(1);
  await expect(page.getByRole("heading",{level:1})).toHaveText(reference);
  await expect(page.getByRole("link",{name:"Source checklist",exact:true})).toHaveCount(1);
  await expect(page.getByRole("heading",{name:"Observation follow-up"})).toHaveCount(0);
  const record=page.getByRole("heading",{name:"Record & acknowledgement",exact:true});
  await expect(record).toBeInViewport();
  const left=(await page.locator(".case-finding__content").boundingBox())!;
  const right=(await page.locator(".case-finding__record").boundingBox())!;
  expect(right.x).toBeGreaterThan(left.x+left.width);
  expect(right.y).toBeLessThan(400);
  await page.locator(".case-files").waitFor({state:"attached"});
  await page.screenshot({path:"../.artifacts/finding-density-desktop-fixture.png"});
});

test("Finding detail retains CAR context and remains readable on mobile", async ({page}) => {
  await prepare(page,true);
  await page.setViewportSize({width:390,height:844});
  await openFinding(page);
  await expect(page.getByText("A reviewed root cause remains visible.",{exact:true})).toBeVisible();
  await expect(page.getByText("The corrective action remains visible.",{exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"Open CAR-006"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"../.artifacts/finding-density-mobile-fixture.png"});
});

test("Page menus open the current module, keep one section expanded and support keyboard selection",async({page})=>{
  await prepare(page); await openFinding(page);
  await expect(page.getByRole("heading",{name:reference,exact:true})).toBeVisible();
  const assurance=page.getByRole("button",{name:"Assurance",exact:true});
  await assurance.focus(); await page.keyboard.press("ArrowDown");
  const panel=page.getByRole("navigation",{name:"Assurance pages",exact:true});
  await expect(panel.locator("details[open] summary")).toHaveText("Findings");
  await expect(panel.locator("summary").first()).toBeFocused();
  await panel.locator("summary").filter({hasText:/^Audits$/}).click();
  await expect(panel.locator("details[open]")).toHaveCount(1);
  await expect(panel.locator("details[open] summary")).toHaveText("Audits");
  await page.keyboard.press("End");
  await expect(panel.locator("summary").filter({hasText:/^Change Control$/})).toBeFocused();
  await page.keyboard.press("Escape"); await expect(panel).toHaveCount(0); await expect(assurance).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("button",{name:"Controls & settings",exact:true})).toBeFocused();
});

test("Drawer parent rows expand without navigating and close sibling sections",async({page})=>{
  await prepare(page); await openFinding(page);
  await expect(page.getByRole("heading",{name:reference,exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Open navigation",exact:true}).click();
  const drawer=page.getByRole("dialog",{name:"QMS navigation",exact:true});
  const alignment=await drawer.getByRole("button",{name:"Expand Work",exact:true}).evaluate(el=>{
    const label=el.querySelector("span:nth-child(2)")!.getBoundingClientRect();
    const chevron=el.querySelector(".tenant-nav__branch-chevron")!.getBoundingClientRect();
    return {offset:Math.abs(label.y+label.height/2-chevron.y-chevron.height/2),width:el.getBoundingClientRect().width,rowWidth:el.parentElement!.getBoundingClientRect().width};
  });
  expect(alignment.offset).toBeLessThan(2);
  expect(alignment.rowWidth-alignment.width).toBeLessThan(3);
  await drawer.getByRole("button",{name:"Expand Work",exact:true}).click();
  await expect(page).toHaveURL(new RegExp(path+"$"));
  await expect(drawer.getByRole("button",{name:"Collapse Work",exact:true})).toBeVisible();
  await drawer.getByRole("button",{name:"Expand Assurance",exact:true}).click();
  await expect(drawer.getByRole("button",{name:"Expand Work",exact:true})).toBeVisible();
  await expect(page).toHaveURL(new RegExp(path+"$"));
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button",{name:"Open navigation",exact:true})).toBeFocused();
});

test("Reduced motion disables menu animation",async({page})=>{
  await page.emulateMedia({reducedMotion:"reduce"});
  await prepare(page); await openFinding(page);
  await page.getByRole("button",{name:"Assurance",exact:true}).click();
  expect(await page.locator(".qms-page-menu__panel").evaluate(el=>getComputedStyle(el).animationName)).toBe("none");
});

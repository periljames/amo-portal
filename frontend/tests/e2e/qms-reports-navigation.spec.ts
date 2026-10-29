import { expect, test, type Page } from "@playwright/test";
import { mockQualityShell } from "./helpers/mockQualityShell";

async function prepare(page: Page, readOnly = false) {
  await mockQualityShell(page);
  const rows = [["QAR/MO/26/001", "Audit one"], ["QAR/MO/26/002", "Audit two " + "Complete report narrative must remain readable. ".repeat(10)]];
  await page.addInitScript(({readOnly}) => {
    sessionStorage.setItem("amo_portal_token", `e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
    localStorage.setItem("amo_code", "AMO-A");localStorage.setItem("amo_slug", "tenant-a");localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({is_complete:true}));
    localStorage.setItem("amo_current_user", JSON.stringify({id:"quality",amo_id:"amo-a",amo_slug:"tenant-a",amo_code:"AMO-A",department_code:"quality",role:readOnly?"VIEW_ONLY":"QUALITY_MANAGER",full_name:"Quality User",is_active:true,is_amo_admin:!readOnly,capability_codes:readOnly?["qms.reports.view","qms.dashboard.view"]:undefined}));
  },{readOnly});
  await page.route("**/quality/reports/**", async route => {
    if (route.request().resourceType() === "document") return route.fallback();
    const url = new URL(route.request().url());
    expect(url.pathname).toContain("/api/maintenance/tenant-a/quality/reports/");
    if (url.pathname.endsWith("/output")) return route.fulfill({contentType:"text/csv",headers:{"Content-Disposition":"attachment; filename=QMS-audit-performance.csv"},body:"Tenant A\r\nAudit reference,Title\r\n" + rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(",")).join("\r\n")});
    return route.fulfill({contentType:"application/json",body:JSON.stringify({kind:url.searchParams.get("kind"),title:"Audit performance",tenant:"Tenant A",generated_at:"2026-10-26T10:00:00Z",start:url.searchParams.get("start")||"2026-01-01",end:url.searchParams.get("end")||"2026-10-26",population:"Non-deleted audits created in the period.",columns:["Audit reference","Title"],rows,total:2})});
  });
}

test("reports preview real columns, apply dates and download a complete output", async ({page}) => {
  await prepare(page);await page.goto("/maintenance/tenant-a/quality/reports/audit-performance");
  await expect(page.getByRole("heading",{name:"Audit performance",exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole("cell",{name:"QAR/MO/26/001",exact:true})).toBeVisible();
  const narrative=page.getByRole("cell",{name:/^Audit two /});
  expect(await narrative.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBeTruthy();
  const csv=page.getByRole("button",{name:"Download CSV",exact:true});await expect(csv).toBeEnabled();
  await page.getByLabel("Report period start").fill("2026-09-01");await expect(csv).toBeDisabled();
  await page.getByRole("button",{name:"Apply / refresh",exact:true}).click();await expect(csv).toBeEnabled();
  const [download]=await Promise.all([page.waitForEvent("download"),csv.click()]);expect(download.suggestedFilename()).toBe("QMS-audit-performance.csv");expect(await download.failure()).toBeNull();
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.getByRole("navigation",{name:"Reports & Analytics views"}).getByRole("link",{name:"Exports",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Report downloads",exact:true})).toBeVisible();await expect(page.locator(".qms-reports__catalogue>a")).toHaveCount(5);
});

test("report viewing does not grant export permission",async({page})=>{
  await prepare(page,true);await page.goto("/maintenance/tenant-a/quality/reports/audit-performance");
  await expect(page.getByRole("cell",{name:"Audit one",exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"Download CSV",exact:true})).toBeDisabled();
});

test("QMS dropdowns have direct second-level destinations and no document controls",async({page})=>{
  await prepare(page);await page.goto("/maintenance/tenant-a/quality/reports/exports");
  await page.getByRole("button",{name:"Controls & settings",exact:true}).click();
  const panel=page.getByRole("navigation",{name:"QMS controls and settings"});
  await expect(panel.locator("summary,details")).toHaveCount(0);await expect(panel.getByRole("link",{name:"Controlled Documents",exact:true})).toHaveCount(0);
  await expect(panel.getByRole("link",{name:"Settings",exact:true})).toHaveAttribute("href","/maintenance/tenant-a/quality/settings/general");
  await panel.getByRole("link",{name:"Settings",exact:true}).focus();await page.keyboard.press("Escape");await expect(panel).toHaveCount(0);
  await page.getByRole("button",{name:"Reports",exact:true}).click();await page.getByRole("navigation",{name:"Reports pages",exact:true}).getByRole("link",{name:"Reports & Analytics",exact:true}).click();
  await expect(page).toHaveURL(/reports\/executive-dashboard$/);
});

test("legacy document-control links hand off to native DMS destinations",async({page})=>{
  await prepare(page);
  for (const [oldView,target] of [["library","library"],["approvals","changes"],["distribution","distribution"]]) {
    await page.goto(`/maintenance/tenant-a/quality/documents/${oldView}`);
    await expect(page).toHaveURL(new RegExp(`/maintenance/tenant-a/document-control/${target}$`));
  }
});

test("the current report tab is visible on a narrow direct entry",async({page})=>{
  await prepare(page);await page.setViewportSize({width:390,height:844});
  await page.goto("/maintenance/tenant-a/quality/reports/training-compliance");
  const active=page.getByRole("navigation",{name:"Reports & Analytics views",exact:true}).getByRole("link",{name:"Training validity",exact:true});
  await expect(active).toHaveAttribute("aria-current","page");await expect(active).toBeInViewport({ratio:1});
});

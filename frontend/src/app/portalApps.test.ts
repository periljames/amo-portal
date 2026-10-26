import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import type { PortalUser } from "../services/auth";
import { currentPortalApp,getPortalApps } from "./portalApps";
beforeEach(()=>vi.stubGlobal("localStorage",{getItem:()=>null}));
afterEach(()=>vi.unstubAllGlobals());
const employee=(changes:Partial<PortalUser>={})=>({id:"u-1",amo_id:"amo-1",amo_slug:"tenant-a",amo_code:"AMO-A",is_active:true,is_superuser:false,is_amo_admin:false,role:"QUALITY_OFFICER",department_code:"quality",...changes} as PortalUser);
const apps=(user:PortalUser,active=false)=>getPortalApps({amoCode:"tenant-a",user,activeDepartment:"quality",contextDepartment:"quality",adminModeActive:active});
describe("portal app destinations",()=>{
  it("offers cross-app destinations inside QMS using explicit module grants",()=>{
    const rows=apps(employee({module_access:{quality:"view",documents:"view",training:"view"}}));
    expect(rows.map(a=>a.id)).toEqual(expect.arrayContaining(["quality","document-control"]));
    expect(rows.some(a=>a.id==="procurement"||a.id==="administration"||a.id==="maintenance")).toBe(false);
  });
  it("does not restore a removed QMS module from department metadata",()=>{
    expect(apps(employee({module_access:{documents:"view"}})).some(a=>a.id==="quality")).toBe(false);
  });
  it("does not recreate simple department apps after explicit removal",()=>{
    expect(apps(employee({department_code:"stores",role:"STOREKEEPER",module_access:{documents:"view"}})).some(a=>a.id==="stores")).toBe(false);
  });
  it("retains operational app access for standing tenant administrators",()=>{
    const rows=apps(employee({is_amo_admin:true,module_access:{}}));
    expect(rows.map(a=>a.id)).toEqual(expect.arrayContaining(["quality","planning","maintenance","procurement","training-competence"]));
    expect(rows.some(a=>a.id==="administration")).toBe(false);
    expect(apps(employee({is_amo_admin:true}),true).some(a=>a.id==="administration")).toBe(true);
  });
  it.each([{is_active:false},{amo_slug:"different",amo_code:"OTHER"},{is_superuser:true},{amo_id:null}])("does not list apps for invalid tenant identity %j",changes=>{
    expect(apps(employee(changes as Partial<PortalUser>))).toEqual([]);
  });
  it("matches the most specific app, without prefix collisions",()=>{
    const rows=apps(employee({is_amo_admin:true}),true);
    expect(currentPortalApp(rows,"/maintenance/tenant-a/production/records/logbooks")?.id).toBe("technical-records");
    expect(currentPortalApp(rows,"/maintenance/tenant-a/quality/findings/register")?.id).toBe("quality");
    expect(currentPortalApp(rows,"/maintenance/tenant-a/quality-other")).toBeUndefined();
    expect(currentPortalApp(rows,"/maintenance/tenant-a/training/competence/people")?.id).toBe("training-competence");
    expect(currentPortalApp(rows,"/maintenance/tenant-a/admin/users")?.id).toBe("administration");
  });
});

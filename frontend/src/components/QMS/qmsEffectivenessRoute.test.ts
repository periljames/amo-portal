import { expect,it } from "vitest";
import { isEffectivenessResponseRoute } from "./qmsEffectivenessRoute";
it.each(["cars/register","cars/overdue","cars/awaiting-quality-review","cars/new","findings/register"])("keeps floating effectiveness tools off %s",path=>{
  expect(isEffectivenessResponseRoute(`/maintenance/amo/quality/${path}`,"")).toBe(false);
});
it("keeps case pages focused and retains the dedicated assurance workspace",()=>{
  expect(isEffectivenessResponseRoute("/maintenance/amo/quality/findings/abc-123/overview","")).toBe(false);
  expect(isEffectivenessResponseRoute("/maintenance/amo/quality/assurance/cases/abc-123","")).toBe(true);
  expect(isEffectivenessResponseRoute("/maintenance/amo/quality/assurance","?workspace=assurance")).toBe(true);
});

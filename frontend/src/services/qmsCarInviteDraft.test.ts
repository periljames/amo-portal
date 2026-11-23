import { afterEach, expect, it, vi } from "vitest";
import { readCarInviteDraft } from "./qmsCarInviteDraft";
import type { CARInviteOut } from "./qms";

afterEach(() => vi.unstubAllGlobals());

it("recovers both narratives from an old browser draft into CAP", () => {
  const invite = {car_id:"car-1",submitted_at:null,root_cause_status:"PENDING",capa_status:"PENDING",containment_action:"",root_cause:"",corrective_action:"Saved CAP\n\nSaved systemic control",evidence_ref:"",due_date:null,target_closure_date:null} as CARInviteOut;
  const old = {revision:JSON.stringify([null,"PENDING","PENDING","","","Saved CAP","Saved systemic control","",null,null]),form:{submitted_by_name:"Respondent",submitted_by_email:"",containment_action:"",root_cause:"",corrective_action:"Unfinished CAP",preventive_action:"Unfinished systemic control",evidence_ref:"",due_date:"",target_closure_date:""}};
  vi.stubGlobal("sessionStorage", {getItem:()=>JSON.stringify(old),removeItem:vi.fn()});
  const recovered = readCarInviteDraft(invite);
  expect(recovered?.corrective_action).toBe("Unfinished CAP\n\nUnfinished systemic control");
  expect(recovered).not.toHaveProperty("preventive_action");
});

it("retains an unfinished old draft when both saved server fields were empty", () => {
  const invite = {car_id:"car-1",submitted_at:null,root_cause_status:"PENDING",capa_status:"PENDING",containment_action:"",root_cause:"",corrective_action:"",evidence_ref:"",due_date:null,target_closure_date:null} as CARInviteOut;
  const old = {revision:JSON.stringify([null,"PENDING","PENDING","","","","","",null,null]),form:{submitted_by_name:"Respondent",submitted_by_email:"",containment_action:"",root_cause:"",corrective_action:"Unfinished CAP",preventive_action:"",evidence_ref:"",due_date:"",target_closure_date:""}};
  vi.stubGlobal("sessionStorage", {getItem:()=>JSON.stringify(old),removeItem:vi.fn()});
  expect(readCarInviteDraft(invite)?.corrective_action).toBe("Unfinished CAP");
});

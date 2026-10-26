import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getCachedUser } from "../../../services/auth";
import { listMissionReadinessEvidence, recordMissionDelivery, updateQmsMission, type QmsMission } from "../../../services/qmsMissions";
import { clearMissionDraft, useMissionDraft } from "./useMissionDraft";

type AuthorityPolicy = { approval_required: boolean; notification_required: boolean; physical_address_change: boolean; justification: string };

export default function QmsChangeDelivery({ amoCode, mission }: { amoCode: string; mission: QmsMission }) {
  const client = useQueryClient();
  const mutable = ["PLANNING", "IN_PROGRESS", "GATE_REVIEW"].includes(mission.status);
  const [policy, setPolicy] = useMissionDraft<AuthorityPolicy>(amoCode, mission, "policy", (mission.scope.authority_policy as AuthorityPolicy) || { approval_required: true, notification_required: true, physical_address_change: false, justification: "Authority approval and written notification required." });
  const [search, setSearch] = useMissionDraft(amoCode, mission, "delivery-search", "");
  const [asset, setAsset] = useMissionDraft(amoCode, mission, "delivery-asset", "");
  const [rationale, setRationale] = useMissionDraft(amoCode, mission, "delivery-rationale", "");
  const [effectiveDate, setEffectiveDate] = useMissionDraft(amoCode, mission, "delivery-date", "");
  const [conditions, setConditions] = useMissionDraft(amoCode, mission, "delivery-conditions", false);
  const [title, setTitle] = useMissionDraft(amoCode, mission, "title", mission.title);
  const [description, setDescription] = useMissionDraft(amoCode, mission, "description", mission.description || "");
  const [affectedScope, setAffectedScope] = useMissionDraft(amoCode, mission, "affected-scope", String(mission.scope.affected_scope || mission.scope.capability || ""));
  const delivery = mission.next_action === "IMPLEMENTATION" || mission.next_action === "EFFECTIVENESS_REVIEW" ? mission.next_action : null;
  const evidence = useQuery({ queryKey: ["change-delivery-evidence", amoCode, mission.id, search], queryFn: () => listMissionReadinessEvidence(amoCode, mission.id, search), enabled: Boolean(delivery) });
  const mutation = useMutation({
    mutationFn: (action: "policy" | "delivery") => action === "policy"
      ? updateQmsMission(amoCode, mission.id, { title: title.trim(), description: description.trim(), scope: { ...mission.scope, affected_scope: affectedScope.trim(), authority_policy: policy }, expected_updated_at: mission.updated_at })
      : recordMissionDelivery(amoCode, mission.id, delivery!, { rationale: rationale.trim(), evidence_asset_id: asset, effective_date: effectiveDate || undefined, conditions_satisfied: conditions, expected_updated_at: mission.updated_at }),
    onSuccess: async updated => { clearMissionDraft(amoCode, mission); client.setQueryData(["qms-mission", amoCode, mission.id], updated); await client.invalidateQueries({ queryKey: ["qms-missions", amoCode.trim().toLowerCase()] }); },
  });
  const owner = getCachedUser()?.id === mission.owner_user_id;
  return <>
    {mutable ? <details><summary>Change details & Authority requirements</summary><form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); mutation.mutate("policy"); }}>
      <label>Change title<input required minLength={3} maxLength={255} value={title} onChange={event => setTitle(event.target.value)}/></label>
      <label>Affected capability, location or procedure<input required minLength={3} maxLength={500} value={affectedScope} onChange={event => setAffectedScope(event.target.value)}/></label>
      <label>Proposed change and reason<textarea required minLength={10} maxLength={4000} value={description} onChange={event => setDescription(event.target.value)}/></label>
      <label><input type="checkbox" checked={policy.approval_required} onChange={event => setPolicy({ ...policy, approval_required: event.target.checked, notification_required: event.target.checked || policy.notification_required })}/> Prior Authority approval / acceptance required</label>
      <label><input type="checkbox" checked={policy.notification_required} disabled={policy.approval_required || policy.physical_address_change} onChange={event => setPolicy({ ...policy, notification_required: event.target.checked })}/> Written Authority notification required</label>
      <label><input type="checkbox" checked={policy.physical_address_change} onChange={event => setPolicy({ ...policy, physical_address_change: event.target.checked, notification_required: event.target.checked || policy.notification_required })}/> Physical address change — 14 days' advance notice</label>
      <label>Authority applicability and conditions<textarea required minLength={10} maxLength={2000} value={policy.justification} onChange={event => setPolicy({ ...policy, justification: event.target.value })}/></label>
      <button disabled={mutation.isPending || title.trim().length < 3 || description.trim().length < 10 || affectedScope.trim().length < 3 || policy.justification.trim().length < 10}>Save change details</button>
      <small>Changing requirements reopens the readiness gates.</small>
    </form></details> : null}
    {delivery ? <form className="qms-workspace-form" aria-label={delivery === "IMPLEMENTATION" ? "Record implementation" : "Effectiveness review"} onSubmit={event => { event.preventDefault(); mutation.mutate("delivery"); }}>
      <h3>{delivery === "IMPLEMENTATION" ? "Record implementation" : "Effectiveness review and closure"}</h3>
      {delivery === "IMPLEMENTATION" ? <label>Actual implementation date<input required type="date" max={new Date().toISOString().slice(0, 10)} value={effectiveDate} onChange={event => setEffectiveDate(event.target.value)}/></label> : null}
      <label>{delivery === "IMPLEMENTATION" ? "Implementation and conditions met" : "Effectiveness findings and closure basis"}<textarea required minLength={10} maxLength={4000} value={rationale} onChange={event => setRationale(event.target.value)}/></label>
      <label>Find retained evidence<input type="search" value={search} onChange={event => { setSearch(event.target.value); setAsset(""); }}/></label>
      <label>Implementation / review evidence<select required value={asset} onChange={event => setAsset(event.target.value)}><option value="">Select evidence</option>{evidence.data?.items.map(item => <option key={item.asset_id} value={item.asset_id}>{item.filename}</option>)}</select></label>
      {evidence.error ? <p role="alert">{evidence.error.message}</p> : null}
      <label><input required type="checkbox" checked={conditions} onChange={event => setConditions(event.target.checked)}/> {delivery === "IMPLEMENTATION" ? "Applicable approval conditions and limitations have been satisfied." : "The change is effective and outstanding actions and conditions are resolved."}</label>
      <button disabled={mutation.isPending || !owner || !conditions || !asset || rationale.trim().length < 10 || (delivery === "IMPLEMENTATION" && !effectiveDate)}>{delivery === "IMPLEMENTATION" ? "Record implementation" : "Close change"}</button>
      {!owner ? <p>The assigned Quality owner must record this action.</p> : null}
    </form> : null}
    {mutation.error ? <p role="alert">{mutation.error.message}</p> : null}
    <Link to={`/maintenance/${amoCode}/document-control`}>Open Document Control to retain evidence</Link>
  </>;
}

import { eventLabel, retentionDate, type AmoCompliancePolicy, type RetentionFacts } from "../../services/amoCompliancePolicy";

export default function RetentionFields({ policy, primary, onPrimary, value, onChange, disabled = false }: { policy: AmoCompliancePolicy | null; primary: string; onPrimary: (code: string) => void; value: RetentionFacts; onChange: (value: RetentionFacts) => void; disabled?: boolean }) {
  if (!policy) return <p role="status">Loading retention schedule…</p>;
  const selected = policy.retention.filter(rule => rule.code === primary || value.classes?.includes(rule.code));
  const events = [...new Set(selected.map(rule => rule.event))];
  const pending = selected.some(rule => !value.events?.[rule.event] || (!rule.years && !rule.days && (!value.quality_schedule_until || (value.quality_schedule_reference || "").trim().length < 8))) || (selected.some(rule => rule.code === "STATUS_SUMMARIES") && !value.underlying_records_separately_retained);
  const dates = selected.map(rule => retentionDate(rule, value.events?.[rule.event], policy.extensions)).filter(Boolean);
  const until = [...dates, value.contractual_until || "", value.linked_record_until || "", value.sms_until || "", value.quality_schedule_until || ""].sort().at(-1);
  return <fieldset className="qms-retention-fields" disabled={disabled}>
    <legend>Retention schedule</legend>
    <label><span>Record class</span><select required value={primary} onChange={event => onPrimary(event.target.value)}><option value="">Select record class</option>{policy.retention.map(rule => <option value={rule.code} key={rule.code}>{rule.label}</option>)}</select></label>
    <details><summary>Additional obligations</summary><div className="qms-retention-fields__checks">{policy.retention.filter(rule => rule.code !== primary).map(rule => <label key={rule.code}><input type="checkbox" checked={value.classes?.includes(rule.code)} onChange={event => onChange({ ...value, classes: event.target.checked ? [...(value.classes || []), rule.code] : (value.classes || []).filter(code => code !== rule.code) })} />{rule.label}</label>)}</div>
      {([['contractual_until', 'Contract requires retention until'], ['linked_record_until', 'Linked record requires retention until'], ['sms_until', 'SMS requires retention until']] as const).map(([key, label]) => <label key={key}><span>{label}</span><input type="date" value={value[key] || ""} onChange={event => onChange({ ...value, [key]: event.target.value })} /></label>)}
      <label><input type="checkbox" checked={Boolean(value.preservation_hold)} onChange={event => onChange({ ...value, preservation_hold: event.target.checked })} /> Preservation hold</label>
      <label><input type="checkbox" checked={Boolean(value.investigation_open)} onChange={event => onChange({ ...value, investigation_open: event.target.checked })} /> Investigation remains open</label>
    </details>
    {events.map(event => <label key={event}><span>{eventLabel(event)}</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={value.events?.[event] || ""} onChange={change => onChange({ ...value, events: { ...value.events, [event]: change.target.value } })} /><small>Leave blank while this event has not occurred; the record remains retained.</small></label>)}
    {selected.some(rule => !rule.years && !rule.days) && <><label><span>Governing Quality records schedule reference</span><input minLength={8} value={value.quality_schedule_reference || ""} onChange={event=>onChange({...value,quality_schedule_reference:event.target.value})} /></label><label><span>Quality schedule requires retention through</span><input type="date" value={value.quality_schedule_until || ""} onChange={event=>onChange({...value,quality_schedule_until:event.target.value})} /></label></>}
    {selected.some(rule => rule.code === "STATUS_SUMMARIES") && <label><input type="checkbox" checked={Boolean(value.underlying_records_separately_retained)} onChange={event => onChange({ ...value, underlying_records_separately_retained: event.target.checked })} /> Underlying maintenance, logbook and life-limited history remain separately retained</label>}
    {selected.length > 0 && <p role="status">{pending || value.preservation_hold || value.investigation_open ? "Retain pending confirmed events, governing schedule and release of holds." : `Retain through ${until}. Longer linked obligations also apply.`}</p>}
    {selected.map(rule => <small key={rule.code}>{rule.reference}</small>)}
  </fieldset>;
}

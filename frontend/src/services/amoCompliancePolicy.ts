export type RetentionRule = { code: string; label: string; event: string; years: number; days: number; reference: string; regulatory_minimum_years: number | null };
export type RetentionExtensions = { extensions_years?: Record<string, number>; extensions_days?: Record<string, number> };
export type AmoCompliancePolicy = { version: string; source: string; retention: RetentionRule[]; extensions?: RetentionExtensions; contracting: { maximum_supplier_review_days: number; reference: string } };
export type RetentionFacts = { classes: string[]; events: Record<string, string>; underlying_records_separately_retained?: boolean; contractual_until?: string; linked_record_until?: string; sms_until?: string; quality_schedule_until?: string; quality_schedule_reference?: string; preservation_hold?: boolean; investigation_open?: boolean; requirements_unconfirmed?: boolean };
export const emptyRetentionFacts = (): RetentionFacts => ({ classes: [], events: {} });
export const eventLabel = (event: string) => ({ release_signed_at: "Release signed", last_entry_at: "Last log entry", permanent_withdrawal_at: "Permanent withdrawal / destruction", contract_ended_at: "Contract ended", tool_scrapped_at: "Tool scrapped", scrapped_at: "Scrapped", employment_ended_at: "Employment ended", authorization_withdrawn_at: "Authorization withdrawn", qms_retention_event_at: "QMSM retention event confirmed", quality_retention_determined_at: "Quality schedule confirmed" }[event] || event.replaceAll("_", " "));

export function retentionDispositionReady(policy: AmoCompliancePolicy | null, primary: string, metadata: Record<string, unknown>, storedUntil?: string | null): boolean {
  const facts = metadata.compliance_retention as RetentionFacts | undefined;
  if (!policy || !facts || facts.preservation_hold || facts.investigation_open || facts.requirements_unconfirmed) return false;
  const dates: string[] = [];
  for (const code of new Set([primary, ...(facts.classes || [])])) {
    const rule = policy.retention.find(item => item.code === code);
    if (!rule || !facts.events?.[rule.event]) return false;
    if (code === "STATUS_SUMMARIES" && !facts.underlying_records_separately_retained) return false;
    if (!rule.years && !rule.days) {
      if (!facts.quality_schedule_until || (facts.quality_schedule_reference || "").trim().length < 8) return false;
      dates.push(facts.quality_schedule_until);
    } else dates.push(retentionDate(rule, facts.events[rule.event].slice(0, 10), policy.extensions));
  }
  dates.push(storedUntil?.slice(0, 10) || "", facts.contractual_until || "", facts.linked_record_until || "", facts.sms_until || "");
  return Boolean(dates.length && dates.every(date => !date || date < new Date().toISOString().slice(0, 10)));
}

export function retentionDate(rule: RetentionRule, event: string, extensions?: RetentionExtensions): string {
  if (!event || (!rule.years && !rule.days)) return "";
  const [year, month, day] = event.split("-").map(Number);
  if (!year || !month || !day) return "";
  const targetYear = year + (extensions?.extensions_years?.[rule.code] ?? rule.years);
  const targetDay = Math.min(day, new Date(Date.UTC(targetYear, month, 0)).getUTCDate());
  const date = new Date(Date.UTC(targetYear, month - 1, targetDay));
  date.setUTCDate(date.getUTCDate() + (extensions?.extensions_days?.[rule.code] ?? rule.days));
  return date.toISOString().slice(0, 10);
}

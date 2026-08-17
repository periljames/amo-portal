import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  CheckCircle2,
  FileCheck2,
  Plane,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Undo2,
} from "lucide-react";

import {
  listRosterAssignments,
  listRosterPeriods,
} from "../../../services/rostering";
import {
  createRegulatoryExemption,
  getRosterWorkflowGates,
  listDutyExtensions,
  listExemptionEvidence,
  listRegulatoryExemptions,
  proposeDutyExtension,
  revokeRegulatoryExemption,
  verifyRegulatoryExemption,
} from "../../../services/rosteringCompliance";
import type { RosterAssignmentRead, RosterPeriodRead, RosterVersionRead } from "../../../types/rostering";
import type {
  RosterDutyExtensionRead,
  RosterRegulatoryExemptionRead,
  RosterWorkflowGateRead,
} from "../../../types/rosteringCompliance";
import { errorMessage, formatDateTime } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { EmptyState, StatusPill } from "./RosterShell";
import { SupervisorRosterConsentPanel } from "./RosterConsentWorkflows";

const GOVERNED_PERIODS_KEY = ["rostering", "governed-compliance", "periods"] as const;
const EXEMPTIONS_KEY = ["rostering", "regulatory-exemptions"] as const;
const EVIDENCE_KEY = ["rostering", "regulatory-exemptions", "supporting-documents"] as const;

function latestPeriods(rows: RosterPeriodRead[]): RosterPeriodRead[] {
  return [...rows].sort((left, right) => right.starts_on.localeCompare(left.starts_on));
}

function latestVersions(rows: RosterVersionRead[]): RosterVersionRead[] {
  return [...rows].sort((left, right) => right.version_no - left.version_no);
}

function asString(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value ? value : null;
}

function asNumber(details: Record<string, unknown>, key: string): number | null {
  const value = details[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

type DutyInterval = { starts_at: string; ends_at: string; assignment_ids?: string[]; source?: string };

function dutyIntervals(details: Record<string, unknown>): DutyInterval[] {
  const source = details.duty_intervals;
  if (!Array.isArray(source)) return [];
  return source.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    if (typeof record.starts_at !== "string" || typeof record.ends_at !== "string") return [];
    return [{
      starts_at: record.starts_at,
      ends_at: record.ends_at,
      assignment_ids: Array.isArray(record.assignment_ids) ? record.assignment_ids.map(String) : [],
      source: typeof record.source === "string" ? record.source : undefined,
    }];
  });
}

function minutesLabel(minutes: number | null): string {
  if (minutes === null) return "—";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function gateTone(severity: RosterWorkflowGateRead["severity"]): "blocker" | "warning" {
  return severity === "HARD_BLOCK" ? "blocker" : "warning";
}

function Timeline({ gate }: { gate: RosterWorkflowGateRead }) {
  const startIso = asString(gate.details, "window_start");
  const endIso = asString(gate.details, "window_end");
  const intervals = dutyIntervals(gate.details);
  if (!startIso || !endIso) return null;
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  const span = end - start;
  if (!Number.isFinite(start) || !Number.isFinite(end) || span <= 0) return null;

  return (
    <div className="wr-recommendation">
      <div className="wr-section-heading">
        <div><span className="wr-eyebrow">Exact rolling interval</span><strong>{formatDateTime(startIso)} → {formatDateTime(endIso)}</strong></div>
        <StatusPill value="7-DAY TIMELINE" tone="warning" />
      </div>
      <div
        aria-label="Seven-day protected-rest timeline"
        style={{ position: "relative", minHeight: 58, border: "1px solid var(--wr-border, #d9dee7)", borderRadius: 10, overflow: "hidden" }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", minHeight: 58 }}>
          {Array.from({ length: 7 }, (_, index) => (
            <div key={index} style={{ borderRight: index === 6 ? undefined : "1px solid var(--wr-border, #d9dee7)", padding: "4px 5px", fontSize: 11 }}>
              Day {index + 1}
            </div>
          ))}
        </div>
        {intervals.map((interval, index) => {
          const intervalStart = Math.max(start, Date.parse(interval.starts_at));
          const intervalEnd = Math.min(end, Date.parse(interval.ends_at));
          const left = Math.max(0, Math.min(100, ((intervalStart - start) / span) * 100));
          const width = Math.max(0.7, Math.min(100 - left, ((intervalEnd - intervalStart) / span) * 100));
          return (
            <span
              key={`${interval.starts_at}:${interval.ends_at}:${index}`}
              title={`Duty ${formatDateTime(interval.starts_at)} → ${formatDateTime(interval.ends_at)}${interval.source ? ` · ${interval.source}` : ""}`}
              style={{
                position: "absolute",
                left: `${left}%`,
                width: `${width}%`,
                bottom: 8 + (index % 2) * 13,
                height: 10,
                borderRadius: 999,
                background: "currentColor",
                opacity: 0.72,
              }}
            />
          );
        })}
      </div>
      <div className="wr-form-grid wr-form-grid--inspector">
        <div><span className="wr-eyebrow">Longest uninterrupted rest</span><strong>{minutesLabel(asNumber(gate.details, "longest_rest_minutes"))}</strong></div>
        <div><span className="wr-eyebrow">Required</span><strong>{minutesLabel(asNumber(gate.details, "required_rest_minutes"))}</strong></div>
        {asString(gate.details, "longest_rest_start") ? <div className="wr-span-2"><span className="wr-eyebrow">Best available rest gap</span><strong>{formatDateTime(asString(gate.details, "longest_rest_start")!)} → {formatDateTime(asString(gate.details, "longest_rest_end")!)}</strong></div> : null}
      </div>
      <div className="wr-schedule-list">
        {intervals.map((interval, index) => (
          <div key={`${interval.starts_at}:detail:${index}`} className="wr-schedule-row">
            <CalendarClock size={16} />
            <div><strong>Duty interval</strong><small>{formatDateTime(interval.starts_at)} → {formatDateTime(interval.ends_at)}</small></div>
            <small>{interval.source || "Roster duty"}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function GateCard({ gate, onOpenPlanner }: { gate: RosterWorkflowGateRead; onOpenPlanner: (gate: RosterWorkflowGateRead, action?: string) => void }) {
  const protectedRest = gate.code === "ROSTER_PROTECTED_REST_VIOLATION";
  return (
    <article className="wr-recommendation">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">{gate.severity.replace(/_/g, " ")}</span>
          <strong>{protectedRest ? "Protected Rest Required — Publication Blocked" : gate.code.replace(/_/g, " ")}</strong>
          <p>{gate.message}</p>
        </div>
        <StatusPill value={gate.severity.replace(/_/g, " ")} tone={gateTone(gate.severity)} />
      </div>
      {protectedRest ? (
        <div className="wr-inline-error">
          <ShieldAlert size={16} /> This is a statutory hard block. Personnel acknowledgement, supervisor approval, ordinary override, or force-publish cannot satisfy it.
        </div>
      ) : null}
      {gate.personnel_id ? <small>Personnel: {gate.personnel_id}</small> : null}
      {gate.assignment_id ? <small> · Assignment: {gate.assignment_id}</small> : null}
      {protectedRest ? <Timeline gate={gate} /> : null}
      {gate.remediation_actions.length ? (
        <div className="wr-actions">
          {gate.remediation_actions.map((action) => (
            <button key={action} type="button" className="wr-button wr-button--secondary" onClick={() => onOpenPlanner(gate, action)}>
              {action === "ASSIGN_PROTECTED_REST" ? "Assign protected rest" : action === "REASSIGN_DUTY" ? "Reassign duty" : action === "CHANGE_SHIFT" ? "Change shift" : action === "VIEW_7_DAY_TIMELINE" ? "View timeline" : action.replace(/_/g, " ").toLowerCase()}
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function VersionSelector({
  periods,
  periodId,
  versionId,
  onPeriod,
  onVersion,
}: {
  periods: RosterPeriodRead[];
  periodId: string;
  versionId: string;
  onPeriod: (value: string) => void;
  onVersion: (value: string) => void;
}) {
  const period = periods.find((row) => row.id === periodId);
  const versions = latestVersions(period?.versions || []);
  return (
    <div className="wr-form-grid wr-form-grid--inline">
      <label><span>Roster period</span><select value={periodId} onChange={(event) => onPeriod(event.target.value)}>{periods.map((row) => <option key={row.id} value={row.id}>{row.period_code} · {row.name}</option>)}</select></label>
      <label><span>Version</span><select value={versionId} onChange={(event) => onVersion(event.target.value)}>{versions.map((row) => <option key={row.id} value={row.id}>v{row.version_no} · {row.status}</option>)}</select></label>
    </div>
  );
}

function RegulatoryExemptionPanel({ enabled }: { enabled: boolean }) {
  const queryClient = useQueryClient();
  const evidenceQuery = useQuery({ queryKey: EVIDENCE_KEY, queryFn: listExemptionEvidence, enabled, staleTime: 60_000 });
  const exemptionsQuery = useQuery({ queryKey: EXEMPTIONS_KEY, queryFn: listRegulatoryExemptions, enabled, staleTime: 30_000 });
  const evidence = evidenceQuery.data || [];
  const [authority, setAuthority] = useState("");
  const [reference, setReference] = useState("");
  const [provision, setProvision] = useState("");
  const [scope, setScope] = useState("");
  const [personnelId, setPersonnelId] = useState("");
  const [role, setRole] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [conditions, setConditions] = useState("");
  const [conditionsVerified, setConditionsVerified] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId && evidence[0]?.id) setDocumentId(evidence[0].id);
  }, [documentId, evidence]);

  const create = async () => {
    if (!authority.trim() || !reference.trim() || !provision.trim() || !scope.trim() || !effectiveDate || !expiryDate || !documentId) {
      setError("Authority, reference, regulatory provision, scope, dates and controlled supporting evidence are required.");
      return;
    }
    setBusy("create"); setError(null);
    try {
      await createRegulatoryExemption({
        authority: authority.trim(),
        exemption_reference: reference.trim(),
        regulation_provision: provision.trim().toUpperCase(),
        scope: scope.trim(),
        personnel_id: personnelId.trim() || null,
        role_applicability: role.trim() || null,
        effective_date: effectiveDate,
        expiry_date: expiryDate,
        supporting_document_id: documentId,
        conditions: {
          rule_codes: [provision.trim().toUpperCase()],
          manual_conditions: conditions.trim() || null,
          conditions_verified: conditions.trim() ? conditionsVerified : true,
        },
      });
      setAuthority(""); setReference(""); setProvision(""); setScope(""); setPersonnelId(""); setRole(""); setEffectiveDate(""); setExpiryDate(""); setConditions(""); setConditionsVerified(false);
      await queryClient.invalidateQueries({ queryKey: EXEMPTIONS_KEY });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally { setBusy(null); }
  };

  const verify = async (row: RosterRegulatoryExemptionRead) => {
    setBusy(`verify:${row.id}`); setError(null);
    try { await verifyRegulatoryExemption(row.id); await queryClient.invalidateQueries({ queryKey: EXEMPTIONS_KEY }); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); }
  };

  const revoke = async (row: RosterRegulatoryExemptionRead) => {
    const reason = window.prompt("Revocation reason");
    if (!reason?.trim()) return;
    setBusy(`revoke:${row.id}`); setError(null);
    try { await revokeRegulatoryExemption(row.id, reason.trim()); await queryClient.invalidateQueries({ queryKey: EXEMPTIONS_KEY }); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); }
  };

  if (!enabled) return null;
  const today = new Date().toISOString().slice(0, 10);
  return (
    <details className="wr-native-guidance">
      <summary>Authority regulatory exemptions</summary>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Exceptional regulatory authority</span><h2>Verified Authority exemptions</h2><p>This is separate from employee acknowledgement, supervisor approval and ordinary roster rules.</p></div><FileCheck2 size={20} /></div>
        <div className="wr-inline-warning"><ShieldCheck size={16} /> An exemption only applies when tenant-owned controlled evidence is current, verified, in date and expressly covers the affected rule, scope and conditions.</div>
        <div className="wr-form-grid">
          <label><span>Authority</span><input value={authority} onChange={(event) => setAuthority(event.target.value)} placeholder="Regulatory authority" /></label>
          <label><span>Exemption reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} /></label>
          <label><span>Rule / provision</span><input value={provision} onChange={(event) => setProvision(event.target.value)} placeholder="Exact rule code or provision" /></label>
          <label><span>Controlled evidence</span><select value={documentId} onChange={(event) => setDocumentId(event.target.value)}><option value="">Select controlled document</option>{evidence.map((row) => <option key={row.id} value={row.id}>{row.document_number} · {row.title} · v{row.version}</option>)}</select></label>
          <label><span>Effective date</span><input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></label>
          <label><span>Expiry date</span><input type="date" value={expiryDate} onChange={(event) => setExpiryDate(event.target.value)} /></label>
          <label><span>Personnel ID (optional)</span><input value={personnelId} onChange={(event) => setPersonnelId(event.target.value)} /></label>
          <label><span>Role applicability (optional)</span><input value={role} onChange={(event) => setRole(event.target.value)} /></label>
          <label className="wr-span-2"><span>Scope</span><textarea rows={3} value={scope} onChange={(event) => setScope(event.target.value)} /></label>
          <label className="wr-span-2"><span>Authority conditions</span><textarea rows={3} value={conditions} onChange={(event) => setConditions(event.target.value)} placeholder="Any limits or conditions stated by the Authority" /></label>
          {conditions.trim() ? <label className="wr-span-2"><input type="checkbox" checked={conditionsVerified} onChange={(event) => setConditionsVerified(event.target.checked)} /> Conditions have been independently verified against the controlled evidence</label> : null}
        </div>
        {evidenceQuery.error ? <div className="wr-inline-error">Controlled evidence unavailable: {errorMessage(evidenceQuery.error)}</div> : null}
        {error ? <div className="wr-inline-error">{error}</div> : null}
        <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || evidenceQuery.isPending} onClick={() => void create()}><FileCheck2 size={15} /> Attach exemption</button></div>
        <div className="wr-recommendation-list">
          {(exemptionsQuery.data || []).map((row) => {
            const expired = row.expiry_date < today;
            const active = Boolean(row.verified_at) && !row.is_revoked && !expired && row.effective_date <= today;
            return <article key={row.id} className="wr-recommendation">
              <div className="wr-section-heading"><div><strong>{row.authority} · {row.exemption_reference}</strong><p>{row.regulation_provision} · {row.scope}</p></div><StatusPill value={row.is_revoked ? "REVOKED" : expired ? "EXPIRED" : active ? "VERIFIED ACTIVE" : row.verified_at ? "VERIFIED NOT YET ACTIVE" : "AWAITING VERIFICATION"} tone={active ? "good" : row.is_revoked || expired ? "blocker" : "warning"} /></div>
              <small>{row.effective_date} → {row.expiry_date} · evidence {row.supporting_document_id}</small>
              {active ? <div className="wr-success-note"><BadgeCheck size={15} /> May only produce “compliant under verified regulatory exemption” when the validator independently confirms exact applicability.</div> : null}
              <div className="wr-actions">{!row.verified_at && !row.is_revoked ? <button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => void verify(row)}><BadgeCheck size={14} /> Verify evidence</button> : null}{!row.is_revoked ? <button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => void revoke(row)}><Undo2 size={14} /> Revoke</button> : null}</div>
            </article>;
          })}
        </div>
      </section>
    </details>
  );
}

function DutyExtensionPanel({ versionId, assignments, canEdit }: { versionId: string; assignments: RosterAssignmentRead[]; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const queryKey = ["rostering", "duty-extensions", versionId] as const;
  const extensionQuery = useQuery({ queryKey, queryFn: () => listDutyExtensions(versionId), enabled: Boolean(versionId), staleTime: 20_000 });
  const dutyAssignments = useMemo(() => assignments.filter((row) => !["OFF", "LEAVE", "UNAVAILABLE"].includes(row.status)), [assignments]);
  const [assignmentId, setAssignmentId] = useState("");
  const [extendedEnd, setExtendedEnd] = useState("");
  const [aircraft, setAircraft] = useState("");
  const [operationalRef, setOperationalRef] = useState("");
  const [workOrderRef, setWorkOrderRef] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (assignmentId && dutyAssignments.some((row) => row.id === assignmentId)) return;
    setAssignmentId(dutyAssignments[0]?.id || "");
  }, [assignmentId, dutyAssignments]);

  const submit = async () => {
    if (!assignmentId || !extendedEnd || !aircraft.trim() || !operationalRef.trim() || reason.trim().length < 5) {
      setError("Assignment, proposed end, aircraft registration, operational/AOG reference and reason are required.");
      return;
    }
    setBusy(true); setError(null);
    try {
      await proposeDutyExtension({
        assignment_id: assignmentId,
        proposed_extended_end: new Date(extendedEnd).toISOString(),
        aircraft_registration: aircraft.trim().toUpperCase(),
        operational_reference: operationalRef.trim(),
        work_order_reference: workOrderRef.trim() || null,
        reason: reason.trim(),
      });
      setExtendedEnd(""); setAircraft(""); setOperationalRef(""); setWorkOrderRef(""); setReason("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "workflow-gates"] }),
      ]);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };

  return (
    <details className="wr-native-guidance">
      <summary>Controlled AOG / unscheduled unserviceability duty extension</summary>
      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Exceptional operational workflow</span><h2>Unscheduled aircraft unserviceability</h2><p>This is not a generic overtime or statutory override path.</p></div><Plane size={20} /></div>
        <div className="wr-inline-warning"><AlertTriangle size={16} /> The active duty rule must expressly permit this extension. Employee acknowledgement, supervisor approval, fatigue review and mandatory recovery rest remain required; all other hard limits still apply.</div>
        {canEdit ? <>
          <div className="wr-form-grid">
            <label className="wr-span-2"><span>Affected assignment</span><select value={assignmentId} onChange={(event) => setAssignmentId(event.target.value)}><option value="">Select duty</option>{dutyAssignments.map((row) => <option key={row.id} value={row.id}>{row.user_full_name || row.user_staff_code || row.user_id} · {row.shift_code || row.status} · {formatDateTime(row.starts_at)} → {formatDateTime(row.ends_at)}</option>)}</select></label>
            <label><span>Aircraft registration</span><input value={aircraft} onChange={(event) => setAircraft(event.target.value)} placeholder="5Y-..." /></label>
            <label><span>Operational / AOG / defect reference</span><input value={operationalRef} onChange={(event) => setOperationalRef(event.target.value)} /></label>
            <label><span>Work order reference</span><input value={workOrderRef} onChange={(event) => setWorkOrderRef(event.target.value)} /></label>
            <label><span>Proposed extended end</span><input type="datetime-local" value={extendedEnd} onChange={(event) => setExtendedEnd(event.target.value)} /></label>
            <label className="wr-span-2"><span>Operational reason</span><textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          </div>
          {error ? <div className="wr-inline-error">{error}</div> : null}
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--primary" disabled={busy || !dutyAssignments.length} onClick={() => void submit()}><Plane size={15} /> Start controlled extension</button></div>
        </> : <div className="wr-inline-note">You can review controlled extensions, but your current scope does not permit roster edits.</div>}
        {extensionQuery.error ? <div className="wr-inline-error">{errorMessage(extensionQuery.error)}</div> : null}
        <div className="wr-recommendation-list">{(extensionQuery.data || []).map((row: RosterDutyExtensionRead) => <article key={row.id} className="wr-recommendation">
          <div className="wr-section-heading"><div><strong>{row.aircraft_registration} · {row.operational_reference}</strong><p>{row.reason}</p></div><StatusPill value={row.status.replace(/_/g, " ")} tone={row.status === "READY" ? "good" : row.status === "COMPLIANCE_BLOCKED" ? "blocker" : "warning"} /></div>
          <div className="wr-form-grid wr-form-grid--inspector"><div><span className="wr-eyebrow">Original end</span><strong>{formatDateTime(row.original_planned_end)}</strong></div><div><span className="wr-eyebrow">Proposed end</span><strong>{formatDateTime(row.proposed_extended_end)}</strong></div><div><span className="wr-eyebrow">Continuous duty</span><strong>{minutesLabel(row.continuous_duty_minutes)}</strong></div><div><span className="wr-eyebrow">Mandatory recovery rest</span><strong>{minutesLabel(row.required_recovery_rest_minutes)}</strong></div></div>
          {row.recovery_rest_basis ? <small>{row.recovery_rest_basis}</small> : null}
        </article>)}</div>
      </section>
    </details>
  );
}

export function RosterComplianceControlCenter() {
  const permissionsQuery = useWorkforcePermissions();
  const permissions = permissionsQuery.data?.permissions || [];
  const canManageRules = permissions.includes("roster.manage_rules");
  const canEdit = permissions.includes("roster.edit");
  const periodsQuery = useQuery({ queryKey: GOVERNED_PERIODS_KEY, queryFn: () => listRosterPeriods(), staleTime: 60_000 });
  const periods = useMemo(() => latestPeriods(periodsQuery.data || []), [periodsQuery.data]);
  const [periodId, setPeriodId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [remediationNotice, setRemediationNotice] = useState<string | null>(null);

  useEffect(() => {
    if (periods.some((row) => row.id === periodId)) return;
    setPeriodId(periods[0]?.id || "");
  }, [periodId, periods]);
  const period = periods.find((row) => row.id === periodId);
  const versions = useMemo(() => latestVersions(period?.versions || []), [period?.versions]);
  useEffect(() => {
    if (versions.some((row) => row.id === versionId)) return;
    setVersionId(versions[0]?.id || "");
  }, [versionId, versions]);

  const gatesQuery = useQuery({
    queryKey: ["rostering", "workflow-gates", versionId],
    queryFn: () => getRosterWorkflowGates(versionId),
    enabled: Boolean(versionId),
    staleTime: 10_000,
  });
  const assignmentsQuery = useQuery({
    queryKey: ["rostering", "governed-compliance", "assignments", versionId],
    queryFn: () => listRosterAssignments(versionId),
    enabled: Boolean(versionId),
    staleTime: 20_000,
  });
  const gates = gatesQuery.data?.gates || [];
  const hard = gates.filter((row) => row.severity === "HARD_BLOCK");
  const conditional = gates.filter((row) => row.severity === "CONDITIONAL_BLOCK");
  const warnings = gates.filter((row) => row.severity === "WARNING");

  const openPlanner = (gate: RosterWorkflowGateRead, action?: string) => {
    if (action === "VIEW_7_DAY_TIMELINE") {
      setRemediationNotice("The exact failing rolling interval is shown above, including every duty interval and the longest available rest gap.");
      return;
    }
    const actionText = action === "ASSIGN_PROTECTED_REST"
      ? "Remove, move or reassign enough duty to create at least 24 uninterrupted hours free from all duty. Adding an RD/O marker without clearing duty does not satisfy the rule."
      : action === "REASSIGN_DUTY"
        ? "Use the planner below to reassign an affected duty to another eligible person."
        : action === "CHANGE_SHIFT"
          ? "Open the affected assignment in the planner below and change its configured shift or exact timestamps."
          : "Complete the required workflow action in the planner below.";
    setRemediationNotice(`${actionText}${gate.assignment_id ? ` Affected assignment: ${gate.assignment_id}.` : ""}`);
    document.querySelector(".wr-roster-grid")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="wr-settings">
      <SupervisorRosterConsentPanel />
      <section className="wr-panel" aria-labelledby="roster-compliance-control-title">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Governed lifecycle state</span><h2 id="roster-compliance-control-title">Compliance, consent and publication gates</h2><p>Hard law/aviation limits are separate from consent/supervisor workflow and from operational warnings.</p></div>
          {gatesQuery.isFetching ? <RefreshCw size={18} className="is-spinning" /> : <ShieldCheck size={20} />}
        </div>
        {periods.length ? <VersionSelector periods={periods} periodId={periodId} versionId={versionId} onPeriod={(value) => { setPeriodId(value); setVersionId(""); }} onVersion={setVersionId} /> : null}
        {periodsQuery.error ? <div className="wr-inline-error">{errorMessage(periodsQuery.error)}</div> : null}
        {gatesQuery.error ? <div className="wr-inline-error">{errorMessage(gatesQuery.error)}</div> : null}
        {remediationNotice ? <div className="wr-inline-note"><CheckCircle2 size={15} /> {remediationNotice}</div> : null}
        {gatesQuery.data ? <div className="wr-inline-counts"><StatusPill value={`${gatesQuery.data.hard_block_count} HARD BLOCK`} tone={gatesQuery.data.hard_block_count ? "blocker" : "good"} /><StatusPill value={`${gatesQuery.data.conditional_block_count} CONDITIONAL`} tone={gatesQuery.data.conditional_block_count ? "warning" : "good"} /><StatusPill value={`${gatesQuery.data.warning_count} WARNING`} tone={gatesQuery.data.warning_count ? "warning" : "good"} /><StatusPill value={gatesQuery.data.workflow_state.replace(/_/g, " ")} tone={gatesQuery.data.workflow_state === "READY" ? "good" : gatesQuery.data.hard_block_count ? "blocker" : "warning"} /></div> : null}
        {hard.length ? <div className="wr-recommendation-list">{hard.map((gate, index) => <GateCard key={`${gate.code}:${gate.assignment_id || index}`} gate={gate} onOpenPlanner={openPlanner} />)}</div> : null}
        {conditional.length ? <details className="wr-native-guidance" open><summary>{conditional.length} conditional workflow block{conditional.length === 1 ? "" : "s"}</summary><div className="wr-recommendation-list">{conditional.map((gate, index) => <GateCard key={`${gate.code}:${gate.consent_id || gate.extension_id || index}`} gate={gate} onOpenPlanner={openPlanner} />)}</div></details> : null}
        {warnings.length ? <details className="wr-native-guidance"><summary>{warnings.length} warning{warnings.length === 1 ? "" : "s"}</summary><div className="wr-recommendation-list">{warnings.map((gate, index) => <GateCard key={`${gate.code}:warning:${index}`} gate={gate} onOpenPlanner={openPlanner} />)}</div></details> : null}
        {gatesQuery.data && gates.length === 0 ? <div className="wr-success-note"><CheckCircle2 size={17} /> No statutory, conditional or warning gate is currently open for this version.</div> : null}
        {!periodsQuery.isPending && !periods.length ? <EmptyState title="No roster period" description="Create a roster period before running governed compliance workflow." /> : null}
      </section>
      <DutyExtensionPanel versionId={versionId} assignments={assignmentsQuery.data || []} canEdit={canEdit} />
      <RegulatoryExemptionPanel enabled={canManageRules} />
    </div>
  );
}

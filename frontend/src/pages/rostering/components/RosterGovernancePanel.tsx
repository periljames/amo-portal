import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  UserRoundCog,
} from "lucide-react";

import {
  approveRosterVersion,
  createRosterApprovalAuthority,
  getRosterApprovalMatrix,
  listRosterApprovalAuthorities,
  listRosterRules,
  listRosterRuleSets,
  requestRosterChanges,
} from "../../../services/rostering";
import type { RosterPersonRead } from "../../../services/rosterPeople";
import type {
  RosterApprovalAuthorityLevel,
  RosterPeriodRead,
  RosterRuleRead,
} from "../../../types/rostering";
import { errorMessage, newIdempotencyKey } from "../rosterUi";
import { EmptyState, StatusPill } from "./RosterShell";

function ruleValue(rule: RosterRuleRead): string {
  const params = rule.parameters_json || {};
  if (typeof params.minimum_minutes === "number") return `${params.minimum_minutes / 60}h minimum`;
  if (typeof params.maximum_minutes === "number") {
    const window = typeof params.window_days === "number" ? ` / ${params.window_days} days` : "";
    return `${params.maximum_minutes / 60}h maximum${window}`;
  }
  if (typeof params.maximum_days === "number") return `${params.maximum_days} consecutive days`;
  if (typeof params.maximum_nights === "number") return params.maximum_nights > 0 ? `${params.maximum_nights} consecutive nights` : "Set from approved MoPM";
  if (typeof params.minimum_continuous_minutes === "number") return `${params.minimum_continuous_minutes / 60}h continuous rest`;
  return "Policy validation";
}

export function RosterGovernancePanel({
  people,
  periods,
  bases,
  canManageRules,
  canManageAuthorities,
}: {
  people: RosterPersonRead[];
  periods: RosterPeriodRead[];
  bases: Array<{ id: string; code: string }>;
  canManageRules: boolean;
  canManageAuthorities: boolean;
}) {
  const queryClient = useQueryClient();
  const versions = useMemo(
    () => periods.flatMap((period) => period.versions.map((version) => ({ ...version, periodName: period.name })))
      .filter((version) => ["SUBMITTED", "APPROVED"].includes(version.status))
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at)),
    [periods],
  );
  const [versionId, setVersionId] = useState(versions[0]?.id || "");
  const effectiveVersionId = versionId || versions[0]?.id || "";
  const [userId, setUserId] = useState("");
  const [baseId, setBaseId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [level, setLevel] = useState<RosterApprovalAuthorityLevel>("DELEGATE");
  const [canPublish, setCanPublish] = useState(false);
  const [comment, setComment] = useState("");

  const departments = useMemo(() => {
    const map = new Map<string, { id: string; label: string }>();
    people.forEach((person) => {
      if (person.department_id) map.set(person.department_id, {
        id: person.department_id,
        label: `${person.department_code || "DEPT"} · ${person.department_name || "Department"}`,
      });
    });
    return [...map.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [people]);

  const rulesQuery = useQuery({ queryKey: ["rostering", "governance", "rules"], queryFn: () => listRosterRules(true) });
  const setsQuery = useQuery({ queryKey: ["rostering", "governance", "rule-sets"], queryFn: () => listRosterRuleSets(true) });
  const authoritiesQuery = useQuery({ queryKey: ["rostering", "governance", "authorities"], queryFn: () => listRosterApprovalAuthorities(true) });
  const matrixQuery = useQuery({
    queryKey: ["rostering", "governance", "matrix", effectiveVersionId],
    queryFn: () => getRosterApprovalMatrix(effectiveVersionId),
    enabled: Boolean(effectiveVersionId),
  });

  const authorityMutation = useMutation({
    mutationFn: createRosterApprovalAuthority,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rostering", "governance"] });
    },
  });
  const decisionMutation = useMutation({
    mutationFn: async ({ action }: { action: "approve" | "changes" }) => {
      const version = versions.find((row) => row.id === effectiveVersionId);
      if (!version) throw new Error("Select a submitted roster version");
      const payload = {
        expected_state_revision: version.state_revision,
        idempotency_key: newIdempotencyKey(action),
        comment: comment || (action === "approve" ? "Departmental roster approved" : "Roster changes requested"),
      };
      if (action === "approve") return approveRosterVersion(version.id, payload);
      return requestRosterChanges(version.id, payload);
    },
    onSuccess: async () => {
      setComment("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["rostering"] }),
        matrixQuery.refetch(),
      ]);
    },
  });

  const loading = rulesQuery.isPending || setsQuery.isPending || authoritiesQuery.isPending;
  const failure = rulesQuery.error || setsQuery.error || authoritiesQuery.error || matrixQuery.error || authorityMutation.error || decisionMutation.error;

  return (
    <div className="wr-governance-stack">
      {failure ? <div className="wr-inline-error" role="alert">{errorMessage(failure)}</div> : null}

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Controlled compliance baseline</span><h2>Hours, shifts and rest rules</h2></div>
          <ShieldCheck size={20} />
        </div>
        <p className="wr-panel-intro">
          Numerical limits are tenant-controlled against the approved MoPM. Regulatory and manual references remain attached to the active rule set for audit evidence.
        </p>
        <div className="wr-rule-set-banner">
          {(setsQuery.data || []).map((set) => (
            <article key={set.id}>
              <div><strong>{set.name}</strong><StatusPill value={set.is_active ? "ACTIVE" : "INACTIVE"} /></div>
              <span>{set.version_label || set.code}</span>
              <p>{set.manual_reference || set.regulatory_basis}</p>
            </article>
          ))}
        </div>
        <div className="wr-compliance-rule-grid">
          {(rulesQuery.data || []).map((rule) => (
            <article key={rule.id} className={!rule.is_active ? "is-inactive" : ""}>
              <div><Clock3 size={16} /><strong>{rule.name}</strong></div>
              <span>{ruleValue(rule)}</span>
              <small>{rule.scope.replace(/_/g, " ")} · {rule.severity} · {rule.allow_override ? "controlled override" : "mandatory"}</small>
            </article>
          ))}
        </div>
        {!loading && !rulesQuery.data?.length ? <EmptyState title="No roster rules" description="The operational baseline will seed automatically when the rules API is opened." /> : null}
        {!canManageRules ? <small className="wr-help-text">Rule editing is restricted to users with roster rule-management permission.</small> : null}
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Base and department delegation</span><h2>Approval authority assignments</h2></div>
          <UserRoundCog size={20} />
        </div>
        <p className="wr-panel-intro">Base Manager is the default publishing authority. Department Heads and explicitly delegated line managers or supervisors can approve only the scopes assigned to them.</p>
        {canManageAuthorities ? (
          <div className="wr-inline-create wr-inline-create--governance">
            <label><span>Person</span><select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">Select active user</option>{people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
            <label><span>Base</span><select value={baseId} onChange={(event) => setBaseId(event.target.value)}><option value="">All bases</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code}</option>)}</select></label>
            <label><span>Department</span><select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}><option value="">Base-wide</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.label}</option>)}</select></label>
            <label><span>Authority</span><select value={level} onChange={(event) => setLevel(event.target.value as RosterApprovalAuthorityLevel)}><option value="BASE_MANAGER">Base Manager</option><option value="DEPARTMENT_HEAD">Department Head</option><option value="DELEGATE">Delegated line manager / supervisor</option></select></label>
            <label className="wr-checkbox-field"><input type="checkbox" checked={canPublish} onChange={(event) => setCanPublish(event.target.checked)} /><span>May publish</span></label>
            <button type="button" className="wr-button wr-button--primary" disabled={!userId || authorityMutation.isPending} onClick={() => authorityMutation.mutate({ user_id: userId, base_station_id: baseId || null, department_id: departmentId || null, authority_level: level, can_approve: true, can_publish: canPublish, effective_from: null, effective_to: null, reason: "Assigned in rostering governance", is_active: true })}><Plus size={16} /> Assign permission</button>
          </div>
        ) : null}
        <div className="wr-data-list">
          {(authoritiesQuery.data || []).map((authority) => {
            const person = people.find((row) => row.user_id === authority.user_id);
            const department = departments.find((row) => row.id === authority.department_id);
            const base = bases.find((row) => row.id === authority.base_station_id);
            return <article key={authority.id} className="wr-data-row"><div><strong>{person?.full_name || authority.user_id}</strong><small>{authority.authority_level.replace(/_/g, " ")} · {base?.code || "All bases"} · {department?.label || "Base-wide"}</small></div><StatusPill value={authority.is_active ? "ACTIVE" : "INACTIVE"} /><span>{authority.can_publish ? "Approve + publish" : "Approve"}</span></article>;
          })}
        </div>
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><span className="wr-eyebrow">Draft → departmental approval → publish</span><h2>Roster approval matrix</h2></div>
          <BadgeCheck size={20} />
        </div>
        <div className="wr-filter-bar">
          <label><span>Submitted version</span><select value={effectiveVersionId} onChange={(event) => setVersionId(event.target.value)}><option value="">No submitted roster</option>{versions.map((version) => <option key={version.id} value={version.id}>{version.periodName} · v{version.version_no} · {version.status}</option>)}</select></label>
          <button type="button" className="wr-icon-button" onClick={() => void matrixQuery.refetch()} disabled={!effectiveVersionId}><RefreshCw size={16} className={matrixQuery.isFetching ? "is-spinning" : ""} /></button>
        </div>
        {matrixQuery.data ? <div className="wr-metric-grid"><article><strong>{matrixQuery.data.required_count}</strong><span>Required scopes</span></article><article><strong>{matrixQuery.data.approved_count}</strong><span>Approved</span></article><article><strong>{matrixQuery.data.pending_count}</strong><span>Pending</span></article><article><strong>{matrixQuery.data.changes_requested_count}</strong><span>Changes requested</span></article></div> : null}
        <div className="wr-data-list">
          {(matrixQuery.data?.items || []).map((approval) => {
            const department = departments.find((row) => row.id === approval.department_id);
            const base = bases.find((row) => row.id === approval.base_station_id);
            const approver = people.find((row) => row.user_id === approval.assigned_approver_user_id);
            return <article key={approval.id} className="wr-data-row"><div><strong>{department?.label || "Base-wide roster"}</strong><small>{base?.code || "Unassigned base"} · assigned to {approver?.full_name || "Base Manager / authority required"}</small></div><StatusPill value={approval.status} /><span>{approval.decision_comment || "Awaiting decision"}</span></article>;
          })}
        </div>
        {effectiveVersionId ? <div className="wr-governance-decision"><label><span>Decision comment</span><input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Approval evidence or required changes" /></label><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ action: "changes" })}><RotateCcw size={15} /> Request changes</button><button type="button" className="wr-button wr-button--success" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ action: "approve" })}><CheckCircle2 size={15} /> Approve my scopes</button></div></div> : <EmptyState title="No roster awaiting approval" description="Validate and submit a departmental roster from the planner to generate its approval matrix." />}
      </section>

      <section className="wr-panel wr-calendar-policy-note"><CalendarDays size={20} /><div><strong>Automatic personal calendar</strong><p>Published duty, Quality audits, training and aircraft work allocations are exposed through each user's secure subscription feed. Users subscribe once; their device refreshes the calendar automatically.</p></div></section>
    </div>
  );
}

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  CheckCircle2,
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
  updateRosterApprovalAuthority,
} from "../../../services/rostering";
import type { RosterPersonRead } from "../../../services/rosterPeople";
import type {
  RosterApprovalAuthorityLevel,
  RosterPeriodRead,
} from "../../../types/rostering";
import { errorMessage, newIdempotencyKey } from "../rosterUi";
import { EmptyState, StatusPill } from "./RosterShell";

export function RosterGovernancePanel({
  people,
  periods,
  bases,
  canManageRules,
  canManageAuthorities,
  showApprovalWorkflow = true,
}: {
  people: RosterPersonRead[];
  periods: RosterPeriodRead[];
  bases: Array<{ id: string; code: string }>;
  canManageRules: boolean;
  canManageAuthorities: boolean;
  showApprovalWorkflow?: boolean;
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
    enabled: Boolean(effectiveVersionId) && showApprovalWorkflow,
  });

  const activeRules = (rulesQuery.data || []).filter((rule) => rule.is_active);
  const activeSet = (setsQuery.data || []).find((set) => set.is_active) || setsQuery.data?.[0];
  const blockingChecks = activeRules.filter((rule) => rule.severity === "BLOCKER").length;
  const warningChecks = activeRules.filter((rule) => rule.severity === "WARNING").length;

  const authorityMutation = useMutation({
    mutationFn: createRosterApprovalAuthority,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rostering", "governance"] });
    },
  });
  const authorityUpdateMutation = useMutation({
    mutationFn: ({ authorityId, canPublish: nextCanPublish, active }: { authorityId: string; canPublish?: boolean; active?: boolean }) => updateRosterApprovalAuthority(authorityId, {
      ...(typeof nextCanPublish === "boolean" ? { can_publish: nextCanPublish } : {}),
      ...(typeof active === "boolean" ? { is_active: active } : {}),
      reason: typeof active === "boolean"
        ? (active ? "Approval authority restored in Rostering setup" : "Approval authority retired in Rostering setup")
        : "Publishing scope changed in Rostering setup",
    }),
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
  const failure = rulesQuery.error || setsQuery.error || authoritiesQuery.error || matrixQuery.error || authorityMutation.error || authorityUpdateMutation.error || decisionMutation.error;

  return (
    <div className="wr-governance-stack">
      {failure ? <div className="wr-inline-error" role="alert">{errorMessage(failure)}</div> : null}

      <section className="wr-panel wr-policy-compact" aria-label="Roster policy summary">
        <div className="wr-policy-compact__identity">
          <span className="wr-policy-compact__icon"><ShieldCheck size={18} /></span>
          <div>
            <h2>Roster policy</h2>
            <p>{activeSet?.name || (loading ? "Loading active policy…" : "No active rule set")}</p>
          </div>
          {activeSet ? <StatusPill value={activeSet.is_active ? "ACTIVE" : "INACTIVE"} /> : null}
        </div>
        <div className="wr-policy-compact__metric"><strong>{activeRules.length}</strong><span>active checks</span></div>
        <div className="wr-policy-compact__metric"><strong>{blockingChecks}</strong><span>hard stops</span></div>
        <div className="wr-policy-compact__metric"><strong>{warningChecks}</strong><span>warnings</span></div>
        <details className="wr-policy-compact__reference">
          <summary>{canManageRules ? "Manage values in Rules" : "Policy reference"}</summary>
          <p>{activeSet?.manual_reference || activeSet?.regulatory_basis || "Policy references are maintained with the active rule set."}</p>
        </details>
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading">
          <div><h2>Approval authority</h2></div>
          <UserRoundCog size={19} />
        </div>
        {canManageAuthorities ? (
          <div className="wr-inline-create wr-inline-create--governance">
            <label><span>Person</span><select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">Select active user</option>{people.map((person) => <option key={person.user_id} value={person.user_id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
            <label><span>Base</span><select value={baseId} onChange={(event) => setBaseId(event.target.value)}><option value="">All bases</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code}</option>)}</select></label>
            <label><span>Department</span><select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}><option value="">Base-wide</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.label}</option>)}</select></label>
            <label><span>Authority</span><select value={level} onChange={(event) => setLevel(event.target.value as RosterApprovalAuthorityLevel)}><option value="BASE_MANAGER">Base Manager</option><option value="DEPARTMENT_HEAD">Department Head</option><option value="DELEGATE">Line manager / supervisor</option></select></label>
            <label className="wr-checkbox-field"><input type="checkbox" checked={canPublish} onChange={(event) => setCanPublish(event.target.checked)} /><span>May publish</span></label>
            <button type="button" className="wr-button wr-button--primary" disabled={!userId || authorityMutation.isPending} onClick={() => authorityMutation.mutate({ user_id: userId, base_station_id: baseId || null, department_id: departmentId || null, authority_level: level, can_approve: true, can_publish: canPublish, effective_from: null, effective_to: null, reason: "Assigned in rostering governance", is_active: true })}><Plus size={16} /> Assign</button>
          </div>
        ) : null}
        <div className="wr-data-list">
          {(authoritiesQuery.data || []).map((authority) => {
            const person = people.find((row) => row.user_id === authority.user_id);
            const department = departments.find((row) => row.id === authority.department_id);
            const base = bases.find((row) => row.id === authority.base_station_id);
            return <article key={authority.id} className="wr-data-row"><div><strong>{person?.full_name || authority.user_id}</strong><small>{authority.authority_level.replace(/_/g, " ")} · {base?.code || "All bases"} · {department?.label || "Base-wide"}</small></div><StatusPill value={authority.is_active ? "ACTIVE" : "INACTIVE"} /><span>{authority.can_publish ? "Approve + publish" : "Approve only"}</span>{canManageAuthorities ? <div className="wr-actions"><button type="button" className="wr-button wr-button--small" disabled={authorityUpdateMutation.isPending || !authority.is_active} onClick={() => authorityUpdateMutation.mutate({ authorityId: authority.id, canPublish: !authority.can_publish })}>{authority.can_publish ? "Remove publish" : "Grant publish"}</button><button type="button" className={`wr-button wr-button--small${authority.is_active ? " is-danger" : ""}`} disabled={authorityUpdateMutation.isPending} onClick={() => authorityUpdateMutation.mutate({ authorityId: authority.id, active: !authority.is_active })}>{authority.is_active ? "Retire" : "Restore"}</button></div> : null}</article>;
          })}
        </div>
      </section>

      {showApprovalWorkflow ? (
        <section className="wr-panel">
          <div className="wr-section-heading">
            <div><h2>Roster approval</h2></div>
            <BadgeCheck size={19} />
          </div>
          <div className="wr-filter-bar">
            <label><span>Submitted version</span><select value={effectiveVersionId} onChange={(event) => setVersionId(event.target.value)}><option value="">No submitted roster</option>{versions.map((version) => <option key={version.id} value={version.id}>{version.periodName} · v{version.version_no} · {version.status}</option>)}</select></label>
            <button type="button" className="wr-icon-button" aria-label="Refresh approval matrix" onClick={() => void matrixQuery.refetch()} disabled={!effectiveVersionId}><RefreshCw size={16} className={matrixQuery.isFetching ? "is-spinning" : ""} /></button>
          </div>
          {matrixQuery.data ? <div className="wr-metric-grid"><article><strong>{matrixQuery.data.required_count}</strong><span>Required</span></article><article><strong>{matrixQuery.data.approved_count}</strong><span>Approved</span></article><article><strong>{matrixQuery.data.pending_count}</strong><span>Pending</span></article><article><strong>{matrixQuery.data.changes_requested_count}</strong><span>Changes</span></article></div> : null}
          <div className="wr-data-list">
            {(matrixQuery.data?.items || []).map((approval) => {
              const department = departments.find((row) => row.id === approval.department_id);
              const base = bases.find((row) => row.id === approval.base_station_id);
              const approver = people.find((row) => row.user_id === approval.assigned_approver_user_id);
              return <article key={approval.id} className="wr-data-row"><div><strong>{department?.label || "Base-wide roster"}</strong><small>{base?.code || "Unassigned base"} · {approver?.full_name || "Authority required"}</small></div><StatusPill value={approval.status} /><span>{approval.decision_comment || "Awaiting decision"}</span></article>;
            })}
          </div>
          {effectiveVersionId ? <div className="wr-governance-decision"><label><span>Comment</span><input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Approval evidence or required change" /></label><div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ action: "changes" })}><RotateCcw size={15} /> Request changes</button><button type="button" className="wr-button wr-button--success" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ action: "approve" })}><CheckCircle2 size={15} /> Approve my scopes</button></div></div> : <EmptyState title="No roster awaiting approval" description="Submit a roster from the planner to create its approval matrix." />}
        </section>
      ) : null}
    </div>
  );
}

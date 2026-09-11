import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock3, RefreshCw, ShieldCheck, ShieldX, UserRoundCog } from "lucide-react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";
import {
  activateAdminProfile,
  approveAdminAccessGrant,
  fetchAdminProfileState,
  listAdminAccessGrants,
  listAdminGrantCandidates,
  requestAdminAccessGrant,
  revokeAdminAccessGrant,
  removeTenantAdministrator,
  type AdminAccessGrant,
  type AdminGrantRequestPayload,
} from "../services/adminProfileMode";
import { getAssignedDepartment } from "../utils/departmentAccess";
import "../styles/admin-access-governance.css";

type Params = { amoCode?: string };
type StatusFilter = "ALL" | AdminAccessGrant["status"];

function displayDate(value?: string | null): string {
  if (!value) return "No expiry";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function subjectName(grant: AdminAccessGrant): string {
  return grant.user_name?.trim() || grant.user_email?.trim() || grant.user_id;
}

export default function AdminAccessGovernancePage() {
  const { amoCode: routeAmoCode } = useParams<Params>();
  const queryClient = useQueryClient();
  const context = getContext();
  const currentUser = useMemo(() => getCachedUser(), []);
  const amoCode = routeAmoCode || context.amoCode || context.amoSlug || "UNKNOWN";
  const activeDepartment = getAssignedDepartment(currentUser, context.department) || "admin";
  const canApprove = currentUser?.role === "ACCOUNTABLE_EXECUTIVE";
  const isStandingAdmin = Boolean(
    currentUser
    && !currentUser.is_superuser
    && (currentUser.is_amo_admin || currentUser.role === "AMO_ADMIN"),
  );
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("PENDING");
  const [feedback, setFeedback] = useState("");
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});
  const [request, setRequest] = useState<AdminGrantRequestPayload>({
    user_id: "",
    grant_type: "TEMPORARY",
    valid_until: "",
    reason: "",
  });

  const profileQuery = useQuery({
    queryKey: ["admin-profile-state", amoCode, currentUser?.id],
    queryFn: () => fetchAdminProfileState(amoCode),
    enabled: Boolean(currentUser && amoCode !== "UNKNOWN"),
    staleTime: 5_000,
  });
  const canUseGovernance = Boolean(currentUser?.amo_id && !currentUser.is_superuser);
  const canAssign = Boolean(profileQuery.data?.active || canApprove);
  const canRequest = canUseGovernance;
  const canListGrants = canUseGovernance;

  const grantsQuery = useQuery({
    queryKey: ["admin-access-grants", amoCode, currentUser?.id],
    queryFn: () => listAdminAccessGrants(amoCode),
    enabled: canListGrants,
    staleTime: 5_000,
  });
  const candidatesQuery = useQuery({
    queryKey: ["admin-grant-candidates", amoCode, currentUser?.id],
    queryFn: () => listAdminGrantCandidates(amoCode),
    enabled: canRequest,
    staleTime: 10_000,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-access-grants", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["admin-grant-candidates", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["admin-profile-state", amoCode] }),
    ]);
  };

  const activateMutation = useMutation({
    mutationFn: () => activateAdminProfile(amoCode),
    onSuccess: async () => {
      setFeedback("Administrator profile activated for this signed-in session.");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const requestMutation = useMutation({
    mutationFn: () => requestAdminAccessGrant(amoCode, {
      ...request,
      valid_until: request.grant_type === "TEMPORARY" && request.valid_until
        ? new Date(request.valid_until).toISOString()
        : null,
      reason: request.reason.trim(),
    }),
    onSuccess: async (result) => {
      setRequest({ user_id: "", grant_type: "TEMPORARY", valid_until: "", reason: "" });
      setFeedback(result.status === "ACTIVE" ? "Administrator access assigned for the selected duration." : "Request submitted to the Accountable Executive.");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const approveMutation = useMutation({
    mutationFn: (grant: AdminAccessGrant) => approveAdminAccessGrant(
      amoCode,
      grant.id,
      decisionNotes[grant.id],
    ),
    onSuccess: async (result) => {
      setFeedback(result.status === "ACTIVE"
        ? "The administrator grant is approved and active."
        : "Your decision is recorded.");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const revokeMutation = useMutation({
    mutationFn: (grant: AdminAccessGrant) => revokeAdminAccessGrant(
      amoCode,
      grant.id,
      decisionNotes[grant.id],
    ),
    onSuccess: async (result) => {
      setFeedback(result.status === "REVOKED" ? "Administrator grant revoked." : "Grant updated.");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  const removeMutation = useMutation({
    mutationFn: ({ id, deactivate }: { id: string; deactivate: boolean }) => removeTenantAdministrator(amoCode, id, deactivate),
    onSuccess: async () => { setFeedback("Administrator access removed."); await refresh(); },
    onError: (error: Error) => setFeedback(error.message),
  });

  const grants = grantsQuery.data?.items ?? [];
  const visibleGrants = statusFilter === "ALL"
    ? grants
    : grants.filter((grant) => grant.status === statusFilter);

  if (!currentUser) return null;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={activeDepartment}>
      <main className="aag-shell">
        <header className="aag-header">
          <div>
            <span className="aag-eyebrow"><ShieldCheck size={15} /> Segregated administration</span>
            <h1>Administrator governance</h1>
            <p>Tenant Administrator is a controlled access overlay. It does not change a person’s approved AMO position, job title, certification or departmental reporting line.</p>
          </div>
          <button type="button" className="aag-button aag-button--quiet" onClick={() => void refresh()} disabled={grantsQuery.isFetching}>
            <RefreshCw size={16} className={grantsQuery.isFetching ? "is-spinning" : ""} /> Refresh
          </button>
        </header>

        {feedback ? <div className="aag-feedback" role="status">{feedback}</div> : null}

        {!canUseGovernance && !profileQuery.isLoading ? (
          <section className="aag-empty" role="alert">
            <ShieldX size={28} />
            <h2>Governance access is not assigned</h2>
            <p>Sign in under your AMO tenant to use administrator governance.</p>
          </section>
        ) : (
          <>
            <section className="aag-control-strip" aria-label="Administrator grant control">
              <div><strong>Request approver</strong><span>Accountable Executive</span></div>
              <div><strong>Current persona</strong><span>{currentUser.access_profile_name || currentUser.role.replaceAll("_", " ")}</span></div>
              <div><strong>Administrative authority</strong><span>{isStandingAdmin ? "Standing · platform assigned" : profileQuery.data?.active ? "Delegated · active for this session" : profileQuery.data?.eligible ? "Delegated · eligible, not active" : "Not assigned"}</span></div>
              {!isStandingAdmin && !profileQuery.data?.active && profileQuery.data?.eligible ? (
                <button type="button" className="aag-button" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
                  <UserRoundCog size={16} /> {activateMutation.isPending ? "Activating…" : "Activate Admin Profile"}
                </button>
              ) : null}
            </section>

            {canRequest ? (
              <section className="aag-panel">
                <div className="aag-section-heading">
                  <div><h2>Request administrator access</h2><p>{canAssign ? "Assign permanent or temporary administrator access to a tenant user." : "Request permanent or temporary administrator access from your Accountable Executive."}</p></div>
                </div>
                <div className="aag-request-grid">
                  <label><span>User</span><select value={request.user_id} onChange={(event) => setRequest((current) => ({ ...current, user_id: event.target.value }))}>
                    <option value="">Select eligible user</option>
                    {(candidatesQuery.data ?? []).map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>{candidate.full_name || candidate.email} — {candidate.access_profile_name || candidate.position_title || "User"}</option>
                    ))}
                  </select></label>
                  <label><span>Access duration</span><select value={request.grant_type} onChange={(event) => setRequest((current) => ({ ...current, grant_type: event.target.value as AdminGrantRequestPayload["grant_type"], valid_until: event.target.value === "PERMANENT" ? "" : current.valid_until }))}>
                    <option value="TEMPORARY">Temporary</option><option value="PERMANENT">Permanent</option>
                  </select></label>
                  {request.grant_type === "TEMPORARY" ? <label><span>Expires</span><input type="datetime-local" value={request.valid_until || ""} onChange={(event) => setRequest((current) => ({ ...current, valid_until: event.target.value }))} /></label> : null}
                  <label className="aag-request-reason"><span>Operational reason</span><textarea value={request.reason} minLength={8} maxLength={1000} onChange={(event) => setRequest((current) => ({ ...current, reason: event.target.value }))} placeholder="State the task, access scope and reason this administrator overlay is required." /></label>
                  <button type="button" className="aag-button" onClick={() => requestMutation.mutate()} disabled={!request.user_id || request.reason.trim().length < 8 || (request.grant_type === "TEMPORARY" && !request.valid_until) || requestMutation.isPending}>
                    {requestMutation.isPending ? "Submitting…" : canAssign ? "Assign administrator access" : "Submit request"}
                  </button>
                </div>
              </section>
            ) : null}

            {grantsQuery.data?.standing_administrators?.length ? <section className="aag-panel">
              <div className="aag-section-heading"><div><h2>Standing administrators</h2><p>Platform appointments are permanent. Only the superuser or Accountable Executive may remove them.</p></div></div>
              <div className="aag-grants">{grantsQuery.data.standing_administrators.map((admin) => <article className="aag-grant" key={admin.id}>
                <div><h3>{admin.full_name}</h3><p>{admin.email}</p></div>
                {canApprove ? <div className="aag-actions">
                  <button className="aag-button aag-button--danger" disabled={removeMutation.isPending} onClick={() => removeMutation.mutate({ id: admin.id, deactivate: false })}>Remove administrator access</button>
                  <button className="aag-button aag-button--danger" disabled={removeMutation.isPending || admin.id === currentUser.id} onClick={() => removeMutation.mutate({ id: admin.id, deactivate: true })}>Deactivate account</button>
                </div> : null}
              </article>)}</div>
            </section> : null}

            <section className="aag-panel">
              <div className="aag-section-heading">
                <div><h2>Grant register</h2><p>Every request, decision, activation and revocation remains tenant-scoped and auditable.</p></div>
                <label className="aag-filter"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
                  <option value="PENDING">Pending</option><option value="ACTIVE">Active</option><option value="REVOKED">Revoked</option><option value="EXPIRED">Expired</option><option value="ALL">All</option>
                </select></label>
              </div>

              {!canListGrants ? <div className="aag-empty"><UserRoundCog size={24} /><p>Activate Admin Profile to request and inspect administrator grants.</p></div> : null}
              {grantsQuery.isLoading ? <div className="aag-empty"><Clock3 size={24} /><p>Loading governed requests…</p></div> : null}
              {grantsQuery.isError ? <div className="aag-empty" role="alert"><ShieldX size={24} /><p>{grantsQuery.error instanceof Error ? grantsQuery.error.message : "Administrator requests could not be loaded."}</p></div> : null}
              {canListGrants && !grantsQuery.isLoading && !visibleGrants.length ? <div className="aag-empty"><ShieldCheck size={24} /><p>No {statusFilter === "ALL" ? "" : statusFilter.toLowerCase()} administrator grants.</p></div> : null}

              <div className="aag-grants">
                {visibleGrants.map((grant) => {
                  const selfExcluded = grant.user_id === currentUser.id;
                  const canCancelOwn = canRequest && grant.status === "PENDING" && grant.requested_by_user_id === currentUser.id;
                  const canRevoke = canApprove && ["PENDING", "ACTIVE"].includes(grant.status);
                  return (
                    <article className="aag-grant" key={grant.id}>
                      <div className="aag-grant-main">
                        <div className="aag-grant-title"><h3>{subjectName(grant)}</h3><span className={`aag-status is-${grant.status.toLowerCase()}`}>{grant.status}</span></div>
                        <p>{grant.reason}</p>
                        <dl>
                          <div><dt>Appointed / requested by</dt><dd>{grant.requested_by_name || grant.requested_by_user_id}</dd></div>
                          <div><dt>Type</dt><dd>{grant.grant_type === "TEMPORARY" ? `Temporary · ${displayDate(grant.valid_until)}` : "Permanent"}</dd></div>
                          <div><dt>Requested</dt><dd>{displayDate(grant.created_at)}</dd></div>
                        </dl>
                      </div>
                      <div className="aag-decision">
                        <div className="aag-approval-pair" aria-label="Request approval">
                          <span className={grant.status === "ACTIVE" || grant.accountable_executive_approved ? "is-complete" : ""}>
                            {grant.status === "ACTIVE" || grant.accountable_executive_approved ? <CheckCircle2 size={15} /> : <Clock3 size={15} />}
                            {grant.accountable_executive_approved ? "Approved by Accountable Executive" : grant.status === "PENDING" ? "Awaiting Accountable Executive" : grant.status === "ACTIVE" ? "Direct appointment" : "Appointment ended"}
                          </span>
                        </div>
                        {(canApprove || canCancelOwn) && ["PENDING", "ACTIVE"].includes(grant.status) ? <textarea value={decisionNotes[grant.id] || ""} onChange={(event) => setDecisionNotes((current) => ({ ...current, [grant.id]: event.target.value }))} placeholder="Decision note (optional)" maxLength={1000} /> : null}
                        <div className="aag-actions">
                          {canApprove && grant.status === "PENDING" ? <button type="button" className="aag-button" onClick={() => approveMutation.mutate(grant)} disabled={grant.current_user_decided || selfExcluded || approveMutation.isPending}>{grant.current_user_decided ? "Decision recorded" : selfExcluded ? "Segregation applies" : "Approve in my capacity"}</button> : null}
                          {(canRevoke || canCancelOwn) ? <button type="button" className="aag-button aag-button--danger" onClick={() => revokeMutation.mutate(grant)} disabled={revokeMutation.isPending}>{grant.status === "PENDING" ? "Cancel request" : "Revoke access"}</button> : null}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          </>
        )}
      </main>
    </DepartmentLayout>
  );
}

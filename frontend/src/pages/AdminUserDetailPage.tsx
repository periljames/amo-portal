import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import {
  deactivateAdminUser,
  disableAdminUser,
  enableAdminUser,
  forceAdminUserPasswordReset,
  getAdminUser,
  notifyAdminUser,
  revokeAdminUserAccess,
  scheduleAdminUserReview,
  updateAdminUser,
} from "../services/adminUsers";
import type { AccountRole, AdminUserUpdatePayload } from "../services/adminUsers";
import { addTrainingEventParticipant, listTrainingEvents } from "../services/training";
import type { TrainingEventRead } from "../types/training";

const ROLE_OPTIONS: AccountRole[] = [
  "SUPERUSER",
  "AMO_ADMIN",
  "QUALITY_MANAGER",
  "SAFETY_MANAGER",
  "PLANNING_ENGINEER",
  "PRODUCTION_ENGINEER",
  "CERTIFYING_ENGINEER",
  "CERTIFYING_TECHNICIAN",
  "TECHNICIAN",
  "AUDITOR",
  "STORES",
  "VIEW_ONLY",
];

const AdminUserDetailPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; userId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const userId = params.userId ?? "";

  const [selectedRole, setSelectedRole] = useState<AccountRole | "">("");
  const [selectedEventId, setSelectedEventId] = useState<string>("");
  const [notifySubject, setNotifySubject] = useState("QMS user notification");
  const [notifyMessage, setNotifyMessage] = useState("");
  const [reviewTitle, setReviewTitle] = useState("Authorization review");
  const [reviewDueAt, setReviewDueAt] = useState("");

  const { data: user, isLoading } = useQuery({
    queryKey: ["user-profile", userId],
    queryFn: () => getAdminUser(userId),
    enabled: !!userId,
  });

  const { data: events = [] } = useQuery({
    queryKey: ["training-events"],
    queryFn: () => listTrainingEvents(),
  });

  const invalidateUserViews = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    queryClient.invalidateQueries({ queryKey: ["user-profile", userId] });
    queryClient.invalidateQueries({ queryKey: ["qms-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const updateUserMutation = useMutation({
    mutationFn: (payload: AdminUserUpdatePayload) => updateAdminUser(userId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(["user-profile", userId], updated);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  const commandMutation = useMutation({
    mutationFn: async (command: "disable" | "enable" | "revoke" | "reset") => {
      if (!user) return;
      if (command === "disable") return disableAdminUser(user.id);
      if (command === "enable") return enableAdminUser(user.id);
      if (command === "revoke") return revokeAdminUserAccess(user.id);
      return forceAdminUserPasswordReset(user.id);
    },
    onSuccess: () => invalidateUserViews(),
  });

  const notifyMutation = useMutation({
    mutationFn: async () => {
      if (!user) return;
      return notifyAdminUser(user.id, {
        subject: notifySubject.trim(),
        message: notifyMessage.trim(),
      });
    },
    onSuccess: () => {
      setNotifyMessage("");
      invalidateUserViews();
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: async () => {
      if (!user) return;
      return scheduleAdminUserReview(user.id, {
        title: reviewTitle.trim(),
        due_at: reviewDueAt || undefined,
        priority: 2,
      });
    },
    onSuccess: () => invalidateUserViews(),
  });

  const deactivateMutation = useMutation({
    mutationFn: async () => {
      if (!user) return;
      if (user.is_active) {
        await deactivateAdminUser(user.id);
        return getAdminUser(user.id);
      }
      return updateAdminUser(user.id, { is_active: true });
    },
    onSuccess: (updated) => {
      if (updated) {
        queryClient.setQueryData(["user-profile", userId], updated);
      }
      invalidateUserViews();
    },
  });

  const assignTrainingMutation = useMutation({
    mutationFn: async () => {
      if (!selectedEventId || !userId) return;
      await addTrainingEventParticipant({ event_id: selectedEventId, user_id: userId, status: "INVITED" });
    },
  });

  const resolvedUser = useMemo(() => user ?? null, [user]);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-users">
      <div className="page-header">
        <h1 className="page-header__title">User management</h1>
        <p className="page-header__subtitle">Command center for account lifecycle, authorization, and notifications.</p>
      </div>

      {isLoading && <div className="card">Loading user profile…</div>}

      {resolvedUser && (
        <div className="page-section" style={{ display: "grid", gap: 16 }}>
          <div className="card">
            <div className="card-header">
              <div>
                <h3 style={{ margin: 0 }}>{resolvedUser.full_name}</h3>
                <p className="text-muted" style={{ margin: 0 }}>
                  {resolvedUser.email} · {resolvedUser.role}
                </p>
                <p className="text-muted" style={{ margin: "4px 0 0" }}>
                  {resolvedUser.is_active ? "Active" : "Disabled"} · Must change password: {resolvedUser.must_change_password ? "Yes" : "No"}
                </p>
              </div>
              <div className="page-section__actions">
                <button type="button" className="btn btn-secondary" onClick={() => (window.location.href = `mailto:${resolvedUser.email}?subject=AMO%20Portal%20Notification`)}>
                  Email user
                </button>
                <button type="button" className="btn btn-primary" onClick={() => deactivateMutation.mutate()}>
                  {resolvedUser.is_active ? "Revoke access" : "Restore access"}
                </button>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Command Center</h3>
            <div className="page-section__actions" style={{ marginBottom: 12, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (window.confirm("Disable this user account?")) commandMutation.mutate("disable");
                }}
              >
                Disable
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => commandMutation.mutate("enable")}>Enable</button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (window.confirm("Revoke all active sessions for this user?")) commandMutation.mutate("revoke");
                }}
              >
                Revoke Access
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (window.confirm("Force password reset and revoke sessions?")) commandMutation.mutate("reset");
                }}
              >
                Force Password Reset
              </button>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              <input className="input" value={notifySubject} onChange={(e) => setNotifySubject(e.target.value)} placeholder="Notification subject" />
              <textarea className="input" value={notifyMessage} onChange={(e) => setNotifyMessage(e.target.value)} placeholder="Notification message" rows={3} />
              <button type="button" className="btn btn-primary" onClick={() => notifyMutation.mutate()} disabled={!notifySubject.trim() || !notifyMessage.trim()}>
                Notify
              </button>
            </div>
            <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
              <input className="input" value={reviewTitle} onChange={(e) => setReviewTitle(e.target.value)} placeholder="Review task title" />
              <input className="input" type="datetime-local" value={reviewDueAt} onChange={(e) => setReviewDueAt(e.target.value)} />
              <button type="button" className="btn btn-primary" onClick={() => scheduleMutation.mutate()} disabled={!reviewTitle.trim()}>
                Schedule Review
              </button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Authorization & role</h3>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <select className="input" value={selectedRole || resolvedUser.role} onChange={(event) => setSelectedRole(event.target.value as AccountRole)}>
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn-primary" onClick={() => updateUserMutation.mutate({ role: (selectedRole || resolvedUser.role) as AccountRole })}>
                Update role
              </button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Schedule training</h3>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <select className="input" value={selectedEventId} onChange={(event) => setSelectedEventId(event.target.value)}>
                <option value="">Select training event</option>
                {events.map((event: TrainingEventRead) => (
                  <option key={event.id} value={event.id}>
                    {event.title} · {event.starts_on}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn-primary" onClick={() => assignTrainingMutation.mutate()}>
                Assign to event
              </button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Quick links</h3>
            <div className="page-section__actions">
              <button type="button" className="btn btn-secondary" onClick={() => navigate(`/maintenance/${amoCode}/quality/qms/training/${resolvedUser.id}`)}>
                Training profile
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => navigate(`/maintenance/${amoCode}/admin/users`)}>
                Back to users
              </button>
            </div>
          </div>
        </div>
      )}
    </DepartmentLayout>
  );
};

export default AdminUserDetailPage;

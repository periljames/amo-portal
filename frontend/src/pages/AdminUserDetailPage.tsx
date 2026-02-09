import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import {
  AccountRole,
  AdminUserRead,
  AdminUserUpdatePayload,
  deactivateAdminUser,
  getAdminUser,
  updateAdminUser,
} from "../services/adminUsers";
import {
  addTrainingEventParticipant,
  listTrainingEvents,
  type TrainingEventRead,
} from "../services/training";

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

  const { data: user, isLoading } = useQuery({
    queryKey: ["user-profile", userId],
    queryFn: () => getAdminUser(userId),
    enabled: !!userId,
  });

  const { data: events = [] } = useQuery({
    queryKey: ["training-events"],
    queryFn: () => listTrainingEvents(),
  });

  const updateUserMutation = useMutation({
    mutationFn: (payload: AdminUserUpdatePayload) => updateAdminUser(userId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(["user-profile", userId], updated);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
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
    },
  });

  const assignTrainingMutation = useMutation({
    mutationFn: async () => {
      if (!selectedEventId || !userId) return;
      await addTrainingEventParticipant({
        event_id: selectedEventId,
        user_id: userId,
        status: "INVITED",
      });
    },
  });

  const resolvedUser = useMemo(() => user ?? null, [user]);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-users">
      <div className="page-header">
        <h1 className="page-header__title">User management</h1>
        <p className="page-header__subtitle">Manage roles, authorization, and training actions.</p>
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
              </div>
              <div className="page-section__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    (window.location.href = `mailto:${resolvedUser.email}?subject=AMO%20Portal%20Notification`)
                  }
                >
                  Notify
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => deactivateMutation.mutate()}
                >
                  {resolvedUser.is_active ? "Revoke access" : "Restore access"}
                </button>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Authorization & role</h3>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <select
                className="input"
                value={selectedRole || resolvedUser.role}
                onChange={(event) => setSelectedRole(event.target.value as AccountRole)}
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() =>
                  updateUserMutation.mutate({ role: (selectedRole || resolvedUser.role) as AccountRole })
                }
              >
                Update role
              </button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Schedule training</h3>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <select
                className="input"
                value={selectedEventId}
                onChange={(event) => setSelectedEventId(event.target.value)}
              >
                <option value="">Select training event</option>
                {events.map((event: TrainingEventRead) => (
                  <option key={event.id} value={event.id}>
                    {event.title} · {event.starts_on}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => assignTrainingMutation.mutate()}
              >
                Assign to event
              </button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Quick links</h3>
            <div className="page-section__actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() =>
                  navigate(`/maintenance/${amoCode}/quality/qms/training/${resolvedUser.id}`)
                }
              >
                Training profile
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/users`)}
              >
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

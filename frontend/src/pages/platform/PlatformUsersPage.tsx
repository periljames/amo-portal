import React, { useState } from "react";
import { platformApi, type PlatformUser } from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

export default function PlatformUsersPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("Platform user security action");
  const users = usePlatformData(() => platformApi.users({ q, status, limit: 100 }), [q, status]);
  const act = (id: string, action: "enable" | "disable" | "revoke-sessions" | "force-password-reset") =>
    platformApi.userAction(id, action, reason).then(users.reload);

  return (
    <PlatformShell
      title="Global User Hub"
      subtitle="Platform-wide user visibility, account state, MFA coverage indicators and session revocation."
    >
      {users.error ? <ErrorState error={users.error} retry={users.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Users loaded" value={users.data?.total ?? 0} />
        <MetricCard label="Filter" value={status || "All"} />
        <MetricCard label="Session control" value="Server revoke" caption="Revocation uses token_revoked_at." />
      </section>
      <section className="platform-card">
        <div className="platform-form" style={{ gridTemplateColumns: "1fr 180px 1fr", marginBottom: 12 }}>
          <input placeholder="Search name/email" value={q} onChange={(event) => setQ(event.target.value)} />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </select>
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
        {users.data?.items?.length ? (
          <DataTable>
            <thead>
              <tr>
                <th>User</th>
                <th>Tenant</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((user: PlatformUser) => (
                <tr key={user.id}>
                  <td>
                    {user.full_name}
                    <br />
                    <small>{user.email}</small>
                  </td>
                  <td>{user.tenant_name || user.amo_id || "Platform"}</td>
                  <td>{user.role}</td>
                  <td><StatusBadge value={user.is_active ? "ACTIVE" : "DISABLED"} /></td>
                  <td>{user.last_login_at || "-"}</td>
                  <td>
                    <button className="platform-btn" onClick={() => act(user.id, "revoke-sessions")}>Revoke sessions</button>{" "}
                    {user.is_active ? (
                      <button className="platform-btn danger" onClick={() => act(user.id, "disable")}>Disable</button>
                    ) : (
                      <button className="platform-btn" onClick={() => act(user.id, "enable")}>Enable</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : (
          <EmptyState label="No users found." />
        )}
      </section>
    </PlatformShell>
  );
}

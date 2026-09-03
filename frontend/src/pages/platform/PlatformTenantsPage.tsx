import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  platformApi,
  type PlatformUser,
  type TenantModuleSubscription,
} from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const PAGE_SIZE = 25;
const USER_PAGE_SIZE = 25;

type ModuleDraft = {
  module_code: string;
  status: string;
  plan_code: string;
};

type TenantDetailView = {
  tenant?: { name?: unknown; amo_code?: unknown; login_slug?: unknown } | null;
  subscription?: { status?: unknown; sku_code?: unknown } | null;
  users?: { total?: unknown } | null;
  assets?: { total?: unknown } | null;
  asset_count?: unknown;
  [key: string]: unknown;
};

export default function PlatformTenantsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const [status, setStatus] = useState("");
  const [dataMode, setDataMode] = useState("REAL");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [reason, setReason] = useState("Platform support or subscription action");
  const [moduleOverrides, setModuleOverrides] = useState<Record<string, ModuleDraft>>({});
  const [newModule, setNewModule] = useState("quality");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    amo_code: "",
    login_slug: "",
    owner_email: "",
    reason: "Initial tenant provisioning",
  });

  const tenants = usePlatformData(
    () => platformApi.tenants({ q, status, data_mode: dataMode, limit: PAGE_SIZE, offset }),
    [q, status, dataMode, offset],
    { pollMs: 15_000 },
  );
  const detail = usePlatformData(
    () => selected ? platformApi.tenantDetail(selected) : Promise.resolve(null),
    [selected],
    { pollMs: 15_000 },
  );
  const modules = usePlatformData(
    () => selected ? platformApi.tenantModules(selected) : Promise.resolve({ items: [] as TenantModuleSubscription[] }),
    [selected],
    { pollMs: 15_000 },
  );
  const [userQuery, setUserQuery] = useState("");
  const [userOffset, setUserOffset] = useState(0);
  // On-demand and bounded (read pool + limit, no polling) so deep drill-down
  // never saturates the connection pool.
  const tenantUsers = usePlatformData(
    () => selected
      ? platformApi.users({ tenant_id: selected, q: userQuery, limit: USER_PAGE_SIZE, offset: userOffset })
      : Promise.resolve({ items: [] as PlatformUser[], total: 0 }),
    [selected, userQuery, userOffset],
    { pollMs: 0, live: false },
  );
  const userTotal = tenantUsers.data?.total ?? 0;

  const moduleDrafts = useMemo(() => {
    const rows = new Map<string, ModuleDraft>();
    (modules.data?.items ?? []).forEach((module) => rows.set(module.module_code, {
      module_code: module.module_code,
      status: module.status,
      plan_code: module.plan_code ?? "STANDARD",
    }));
    Object.values(moduleOverrides).forEach((module) => rows.set(module.module_code, module));
    return Array.from(rows.values()).sort((left, right) => left.module_code.localeCompare(right.module_code));
  }, [moduleOverrides, modules.data?.items]);

  const selectedDetail = detail.data as TenantDetailView | null;
  const tenantRecord = selectedDetail?.tenant ?? null;
  const tenantTotal = tenants.data?.total ?? 0;
  const enabledCount = useMemo(
    () => moduleDrafts.filter((module) => module.status === "ENABLED" || module.status === "TRIAL").length,
    [moduleDrafts],
  );
  const integrationSetupPath = selected && tenantRecord?.amo_code
    ? `/maintenance/${encodeURIComponent(String(tenantRecord.amo_code))}/admin/email-settings?tenant_id=${encodeURIComponent(selected)}`
    : null;

  const updateTenantQuery = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set("q", value);
    else next.delete("q");
    setOffset(0);
    setSearchParams(next, { replace: true });
  };

  const execute = async (action: () => Promise<unknown>, success: string) => {
    setActionError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      tenants.reload();
      detail.reload();
      modules.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const selectTenant = (tenantId: string) => {
    setSelected(tenantId);
    setModuleOverrides({});
    setUserQuery("");
    setUserOffset(0);
    setNotice(null);
    setActionError(null);
  };

  const runUserAction = async (
    userId: string,
    action: "enable" | "disable" | "revoke-sessions" | "force-password-reset",
  ) => {
    setActionError(null);
    setNotice(null);
    try {
      await platformApi.userAction(userId, action, reason);
      setNotice(`User ${action.replaceAll("-", " ")} completed.`);
      tenantUsers.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const tenantAction = (id: string, action: "suspend" | "reactivate" | "lock" | "unlock") => execute(
    () => platformApi.tenantAction(id, action, { reason }),
    `Tenant ${action} action completed.`,
  );

  const saveModules = () => {
    if (!selected) return;
    return execute(
      () => platformApi.updateTenantModules(selected, moduleDrafts, reason),
      "Tenant module subscriptions updated.",
    ).then(() => setModuleOverrides({}));
  };

  const updateModuleDraft = (module: ModuleDraft) => {
    setModuleOverrides((current) => ({ ...current, [module.module_code]: module }));
  };

  const addModuleDraft = () => {
    const moduleCode = newModule.trim().toLowerCase().replaceAll("-", "_");
    if (!moduleCode || moduleDrafts.some((module) => module.module_code === moduleCode)) return;
    updateModuleDraft({ module_code: moduleCode, status: "DISABLED", plan_code: "STANDARD" });
    setNewModule("");
  };

  return (
    <PlatformShell
      title="Tenants & Institutions"
      subtitle="Provision, drill into and control tenants"
      actions={<button className="platform-btn" onClick={() => { tenants.reload(); detail.reload(); modules.reload(); }}>Refresh</button>}
    >
      {tenants.error ? <ErrorState error={tenants.error} retry={tenants.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <p><StatusBadge value="SUCCEEDED" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="Tenants" value={tenantTotal} caption={`${dataMode} data mode`} tone="blue" mark="TI" />
        <MetricCard label="Current page" value={`${tenantTotal ? offset + 1 : 0}-${Math.min(offset + PAGE_SIZE, tenantTotal)}`} tone="purple" mark="PG" />
        <MetricCard label="Selected tenant" value={selected ? "Open" : "None"} tone={selected ? "green" : "amber"} mark="SE" />
        <MetricCard label="Enabled modules" value={selected ? enabledCount : "-"} tone="green" mark="MO" />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Tenant register</h2><p>Search and select a tenant to open its operational controls.</p></div><StatusBadge value={`${tenantTotal} TOTAL`} /></div>
          <div className="platform-toolbar">
            <input placeholder="Search tenants" value={q} onChange={(event) => updateTenantQuery(event.target.value)} />
            <select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">All states</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
            <select value={dataMode} onChange={(event) => { setDataMode(event.target.value); setOffset(0); }}><option value="REAL">Real tenants</option><option value="DEMO">Demo tenants</option><option value="ALL">All data</option></select>
          </div>
          {tenants.data?.items?.length ? (
            <DataTable><thead><tr><th>Tenant</th><th>Plan</th><th>Status</th><th>Users</th><th>Actions</th></tr></thead><tbody>{tenants.data.items.map((tenant) => (
              <tr key={tenant.id}>
                <td><button className="platform-btn" onClick={() => selectTenant(tenant.id)}>{tenant.name}</button><br /><small>{tenant.amo_code} · {tenant.login_slug}</small></td>
                <td>{tenant.plan_code || "-"}</td><td><StatusBadge value={tenant.is_read_only ? "LOCKED" : tenant.status} /></td><td>{tenant.user_count ?? 0}</td>
                <td><div className="platform-actions"><button className="platform-btn" onClick={() => tenantAction(tenant.id, "reactivate")}>Reactivate</button><button className="platform-btn" onClick={() => tenantAction(tenant.id, "unlock")}>Unlock</button><button className="platform-btn danger" onClick={() => tenantAction(tenant.id, "suspend")}>Suspend</button></div></td>
              </tr>
            ))}</tbody></DataTable>
          ) : <EmptyState label="No tenants match the current filters." />}
          <div className="platform-actions" style={{ marginTop: 10 }}><button className="platform-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span>{tenantTotal ? offset + 1 : 0}-{Math.min(offset + PAGE_SIZE, tenantTotal)} of {tenantTotal}</span><button className="platform-btn" disabled={offset + PAGE_SIZE >= tenantTotal} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></div>
        </div>

        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Provision tenant</h2><p>Create the AMO and its initial owner through an audited platform action.</p></div></div>
          <div className="platform-form"><input placeholder="Tenant name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /><input placeholder="AMO code" value={form.amo_code} onChange={(event) => setForm({ ...form, amo_code: event.target.value })} /><input placeholder="Login slug" value={form.login_slug} onChange={(event) => setForm({ ...form, login_slug: event.target.value })} /><input placeholder="Owner email" value={form.owner_email} onChange={(event) => setForm({ ...form, owner_email: event.target.value })} /><textarea placeholder="Reason" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /><button className="platform-btn primary" onClick={() => execute(() => platformApi.createTenant(form), "Tenant provisioned.")}>Provision new tenant</button></div>
        </div>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Tenant control</h2><p>Time-boxed support access and high-impact tenant state controls.</p></div></div>
          {tenantRecord ? <><p><strong>{String(tenantRecord.name ?? "Tenant")}</strong><br /><small>{String(tenantRecord.amo_code ?? "")} · {String(tenantRecord.login_slug ?? "")}</small></p><p><StatusBadge value={selectedDetail?.subscription?.status || "NO_SUBSCRIPTION"} /> {String(selectedDetail?.subscription?.sku_code || "")}</p><p>Users: {String(selectedDetail?.users?.total ?? 0)} · Assets: {String(selectedDetail?.assets?.total ?? selectedDetail?.asset_count ?? 0)}</p><textarea value={reason} onChange={(event) => setReason(event.target.value)} /><div className="platform-actions" style={{ marginTop: 8 }}>{integrationSetupPath ? <Link className="platform-btn primary" to={integrationSetupPath}>Open integrations & pipeline</Link> : null}<button className="platform-btn" onClick={() => selected && execute(() => platformApi.startSupportSession({ tenant_id: selected, reason, mode: "READ_ONLY", minutes: 30 }), "Read-only support session started.")}>Start support session</button><button className="platform-btn" onClick={() => selected && tenantAction(selected, "unlock")}>Unlock</button><button className="platform-btn danger" onClick={() => selected && tenantAction(selected, "lock")}>Set read-only</button></div><details><summary>Advanced tenant record</summary><pre className="platform-json">{JSON.stringify(selectedDetail, null, 2)}</pre></details></> : <EmptyState label="Select a tenant to inspect details." />}
        </div>

        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Module subscription control</h2><p>Tenant-scoped module state synchronized with billing and entitlement enforcement.</p></div></div>
          {!selected ? <EmptyState label="Select a tenant before editing modules." /> : null}
          {selected && modules.error ? <ErrorState error={modules.error} retry={modules.reload} /> : null}
          {selected ? <><div className="platform-toolbar"><input placeholder="Add module code" value={newModule} onChange={(event) => setNewModule(event.target.value)} /><button className="platform-btn" onClick={addModuleDraft}>Add module</button></div>{moduleDrafts.length ? <DataTable><thead><tr><th>Module</th><th>Plan</th><th>Status</th></tr></thead><tbody>{moduleDrafts.map((module) => <tr key={module.module_code}><td>{module.module_code}</td><td><input value={module.plan_code} onChange={(event) => updateModuleDraft({ ...module, plan_code: event.target.value.toUpperCase() })} /></td><td><select value={module.status} onChange={(event) => updateModuleDraft({ ...module, status: event.target.value })}><option value="ENABLED">Enabled</option><option value="TRIAL">Trial</option><option value="SUSPENDED">Suspended</option><option value="DISABLED">Disabled</option></select></td></tr>)}</tbody></DataTable> : <EmptyState label="No modules yet — add one above." />}<button className="platform-btn primary" style={{ marginTop: 10 }} onClick={saveModules}>Save modules</button></> : null}
        </div>
      </section>

      {selected ? (
        <section className="platform-card">
          <div className="platform-section-title">
            <div><h2>Users in this tenant</h2></div>
            <StatusBadge value={`${userTotal} USERS`} />
          </div>
          <div className="platform-toolbar">
            <input placeholder="Search users" value={userQuery} onChange={(event) => { setUserOffset(0); setUserQuery(event.target.value); }} />
          </div>
          {tenantUsers.error ? <ErrorState error={tenantUsers.error} retry={tenantUsers.reload} /> : null}
          {tenantUsers.data?.items?.length ? (
            <DataTable>
              <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead>
              <tbody>
                {tenantUsers.data.items.map((tenantUser) => (
                  <tr key={tenantUser.id}>
                    <td>{tenantUser.full_name || tenantUser.email}<br /><small>{tenantUser.email}</small></td>
                    <td>{tenantUser.role}</td>
                    <td><StatusBadge value={tenantUser.is_active ? "ACTIVE" : "DISABLED"} /></td>
                    <td>{tenantUser.last_login_at ? new Date(tenantUser.last_login_at).toLocaleString() : "—"}</td>
                    <td>
                      <div className="platform-actions">
                        {tenantUser.is_active
                          ? <button className="platform-btn" onClick={() => runUserAction(tenantUser.id, "disable")}>Disable</button>
                          : <button className="platform-btn" onClick={() => runUserAction(tenantUser.id, "enable")}>Enable</button>}
                        <button className="platform-btn" onClick={() => runUserAction(tenantUser.id, "revoke-sessions")}>Revoke sessions</button>
                        <button className="platform-btn" onClick={() => runUserAction(tenantUser.id, "force-password-reset")}>Reset password</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          ) : <EmptyState label="No users match." />}
          <div className="platform-actions" style={{ marginTop: 10 }}>
            <button className="platform-btn" disabled={userOffset === 0} onClick={() => setUserOffset(Math.max(0, userOffset - USER_PAGE_SIZE))}>Previous</button>
            <span>{userTotal ? userOffset + 1 : 0}-{Math.min(userOffset + USER_PAGE_SIZE, userTotal)} of {userTotal}</span>
            <button className="platform-btn" disabled={userOffset + USER_PAGE_SIZE >= userTotal} onClick={() => setUserOffset(userOffset + USER_PAGE_SIZE)}>Next</button>
          </div>
        </section>
      ) : null}
    </PlatformShell>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  ChevronRight,
  CopyPlus,
  Network,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  UserRoundCog,
} from "lucide-react";

import {
  assignUserAccessProfile,
  createTenantAccessProfile,
  getTenantAccessFramework,
  initializeTenantAccessFramework,
  updateTenantAccessProfile,
  type ModuleAccessLevel,
  type TenantAccessProfile,
} from "../../services/accessProfiles";
import { listAdminUsers, type AdminUserRead } from "../../services/adminUsers";
import type { AccountRole } from "../../services/auth";
import "./access-roles-panel.css";
import "./access-roles-assignment.css";

type View = "hierarchy" | "matrix";
type Draft = {
  id: string;
  code: string;
  display_name: string;
  base_role_key: AccountRole;
  category: string;
  reports_to_role_code: string;
  description: string;
  is_active: boolean;
  is_regulated: boolean;
  is_system: boolean;
  is_editable: boolean;
  version: number;
  module_permissions: Record<string, ModuleAccessLevel>;
};

function toDraft(profile: TenantAccessProfile): Draft {
  return {
    id: profile.id,
    code: profile.code,
    display_name: profile.display_name,
    base_role_key: profile.base_role_key,
    category: profile.category,
    reports_to_role_code: profile.reports_to_role_code || "",
    description: profile.description || "",
    is_active: profile.is_active,
    is_regulated: profile.is_regulated,
    is_system: profile.is_system,
    is_editable: profile.is_editable,
    version: profile.version,
    module_permissions: { ...profile.module_permissions },
  };
}

function permissionLabel(value?: ModuleAccessLevel): string {
  return value === "manage" ? "Manage" : value === "view" ? "View" : "None";
}

function nextPermission(value?: ModuleAccessLevel): ModuleAccessLevel | undefined {
  if (!value) return "view";
  if (value === "view") return "manage";
  return undefined;
}

function userLabel(user: AdminUserRead): string {
  const identity = user.staff_code ? ` · ${user.staff_code}` : "";
  return `${user.full_name || user.email}${identity}`;
}

function RoleNode({
  role,
  childrenByParent,
  seen,
  onSelect,
}: {
  role: TenantAccessProfile;
  childrenByParent: Map<string, TenantAccessProfile[]>;
  seen: Set<string>;
  onSelect: (profile: TenantAccessProfile) => void;
}) {
  if (seen.has(role.code)) return null;
  const branchSeen = new Set(seen).add(role.code);
  const children = childrenByParent.get(role.code) || [];
  return <li>
    <button type="button" className="access-role-node" onClick={() => onSelect(role)}>
      <span className={`access-role-node__status${role.is_active ? "" : " is-inactive"}`} />
      <span><strong>{role.display_name}</strong><small>{role.code} · {role.base_role_key.replaceAll("_", " ")}</small></span>
      {role.is_regulated ? <ShieldCheck size={15} aria-label="Protected prescribed role" /> : <ChevronRight size={15} />}
    </button>
    {children.length ? <ul>{children.map((child) => <RoleNode key={child.id} role={child} childrenByParent={childrenByParent} seen={branchSeen} onSelect={onSelect} />)}</ul> : null}
  </li>;
}

export default function AccessRolesPanel({ amoId }: { amoId?: string | null }) {
  const client = useQueryClient();
  const [view, setView] = useState<View>("hierarchy");
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [feedback, setFeedback] = useState("");
  const [search, setSearch] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");

  const framework = useQuery({
    queryKey: ["accounts", "access-framework", amoId],
    queryFn: () => getTenantAccessFramework(amoId),
    staleTime: 30_000,
  });
  const profiles = framework.data?.profiles || [];
  const modules = framework.data?.modules || [];
  const selected = profiles.find((profile) => profile.id === selectedId) || null;

  const users = useQuery({
    queryKey: ["accounts", "access-role-users", amoId, userSearch],
    queryFn: () => listAdminUsers({
      amo_id: amoId || undefined,
      limit: 100,
      search: userSearch.trim() || undefined,
    }),
    enabled: Boolean(selected?.id),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (selected) setDraft(toDraft(selected));
  }, [selected]);

  useEffect(() => {
    setSelectedUserId("");
    setUserSearch("");
  }, [selectedId]);

  const initialize = useMutation({
    mutationFn: () => initializeTenantAccessFramework(amoId),
    onSuccess: async (result) => {
      setFeedback(`Framework ready: ${result.created} roles created, ${result.assigned} users aligned.`);
      await client.invalidateQueries({ queryKey: ["accounts", "access-framework"] });
      await client.invalidateQueries({ queryKey: ["admin-user-directory"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error("Select a role first.");
      if (!draft.is_editable) throw new Error("This prescribed access profile is protected and cannot be changed here.");
      if (draft.id) {
        return updateTenantAccessProfile(draft.id, {
          expected_version: draft.version,
          display_name: draft.display_name,
          base_role_key: draft.base_role_key,
          category: draft.category,
          reports_to_role_code: draft.reports_to_role_code || null,
          description: draft.description || null,
          module_permissions: draft.module_permissions,
          is_active: draft.is_active,
        }, amoId);
      }
      return createTenantAccessProfile({
        code: draft.code,
        display_name: draft.display_name,
        base_role_key: draft.base_role_key,
        category: draft.category,
        reports_to_role_code: draft.reports_to_role_code || null,
        description: draft.description || null,
        module_permissions: draft.module_permissions,
      }, amoId);
    },
    onSuccess: async (profile) => {
      setFeedback(`Saved ${profile.display_name}.`);
      setSelectedId(profile.id);
      await client.invalidateQueries({ queryKey: ["accounts", "access-framework"] });
      await client.invalidateQueries({ queryKey: ["admin-user-directory"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  const assign = useMutation({
    mutationFn: async () => {
      if (!selected?.id) throw new Error("Select an access profile first.");
      if (!selectedUserId) throw new Error("Select a user first.");
      if (!selected.is_active) throw new Error("Activate this profile before assigning it.");
      return assignUserAccessProfile(selectedUserId, selected.id, amoId);
    },
    onSuccess: async () => {
      const chosen = users.data?.find((user) => user.id === selectedUserId);
      setFeedback(`${chosen?.full_name || "User"} now uses ${selected?.display_name || "the selected access profile"}.`);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["accounts", "access-framework"] }),
        client.invalidateQueries({ queryKey: ["accounts", "access-role-users"] }),
        client.invalidateQueries({ queryKey: ["admin-user-directory"] }),
      ]);
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  const childrenByParent = useMemo(() => {
    const result = new Map<string, TenantAccessProfile[]>();
    for (const profile of profiles.filter((item) => item.reports_to_role_code)) {
      const key = profile.reports_to_role_code!;
      result.set(key, [...(result.get(key) || []), profile]);
    }
    for (const children of result.values()) children.sort((a, b) => a.display_name.localeCompare(b.display_name));
    return result;
  }, [profiles]);
  const knownCodes = useMemo(() => new Set(profiles.map((profile) => profile.code)), [profiles]);
  const roots = useMemo(
    () => profiles.filter((profile) => !profile.reports_to_role_code || !knownCodes.has(profile.reports_to_role_code)),
    [knownCodes, profiles],
  );
  const filteredProfiles = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return profiles;
    return profiles.filter((profile) => `${profile.display_name} ${profile.code} ${profile.category} ${profile.base_role_key}`.toLowerCase().includes(term));
  }, [profiles, search]);
  const baseRoleOptions = useMemo(
    () => Array.from(new Set(
      profiles
        .filter((profile) => !profile.is_regulated && !["SUPERUSER", "AMO_ADMIN"].includes(profile.base_role_key))
        .map((profile) => profile.base_role_key),
    )).sort(),
    [profiles],
  );

  const beginClone = (profile: TenantAccessProfile) => {
    setSelectedId("");
    setDraft({
      ...toDraft(profile),
      id: "",
      code: `CUSTOM_${profile.code}`,
      display_name: `${profile.display_name} — Custom`,
      is_regulated: false,
      is_system: false,
      is_editable: true,
      version: 1,
    });
  };

  if (framework.isPending) return <section className="access-roles-panel"><p>Loading access roles…</p></section>;
  if (framework.isError) return <section className="access-roles-panel"><div className="access-roles-panel__feedback is-error">{(framework.error as Error).message}</div></section>;

  if (!framework.data?.initialized) {
    return <section className="access-roles-panel access-roles-panel--empty">
      <Network size={34} />
      <h2>Apply the tenant access framework</h2>
      <p>This creates prescribed management profiles and editable AMO/MRO support profiles, then maps existing users without changing approved Workforce appointments, licences or personal authorizations.</p>
      <button type="button" className="aum2-button aum2-button--primary" disabled={initialize.isPending} onClick={() => initialize.mutate()}>
        {initialize.isPending ? "Applying…" : "Apply AMO/MRO framework"}
      </button>
      {feedback ? <div className="access-roles-panel__feedback">{feedback}</div> : null}
    </section>;
  }

  return <section className="access-roles-panel">
    <header className="access-roles-panel__header">
      <div><span>AMO administrator workspace</span><h2>Access Roles</h2><p>Create and edit tenant access profiles, set module boundaries, and assign profiles to users from the portal. Workforce appointments, regulated approvals and certifying authorizations remain separately governed.</p></div>
      <div className="access-roles-panel__header-actions">
        <button type="button" onClick={() => initialize.mutate()} disabled={initialize.isPending}><BadgeCheck size={16} /> Reconcile framework</button>
        <button
          type="button"
          onClick={() => selected && beginClone(selected)}
          disabled={!selected || selected.is_regulated}
          title={selected?.is_regulated ? "Prescribed management profiles cannot be cloned" : "Create a tenant-specific access profile from this profile"}
        ><CopyPlus size={16} /> Clone profile</button>
      </div>
    </header>

    <div className="access-roles-panel__principles">
      <div><ShieldCheck size={18} /><span><strong>Prescribed management profiles</strong> remain protected. Their legal identity and reserved approval authority cannot be rewritten as ordinary portal permissions.</span></div>
      <div><Network size={18} /><span><strong>Supporting access roles</strong> are editable by AMO administrators here in the frontend.</span></div>
      <div><SlidersHorizontal size={18} /><span><strong>Module access</strong> controls portal reach. Workflow gates and personal authorizations still apply after access is granted.</span></div>
    </div>

    <nav className="access-roles-panel__views" aria-label="Access profile views">
      <button type="button" className={view === "hierarchy" ? "is-active" : ""} onClick={() => setView("hierarchy")}><Network size={16} /> Role hierarchy</button>
      <button type="button" className={view === "matrix" ? "is-active" : ""} onClick={() => setView("matrix")}><SlidersHorizontal size={16} /> Module matrix</button>
    </nav>

    <div className="access-roles-panel__workspace">
      <div className="access-roles-panel__canvas">
        {view === "hierarchy" ? <>
          <div className="access-roles-panel__search"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter role, code or function" /></div>
          {search ? <div className="access-roles-panel__results">{filteredProfiles.map((profile) => <button type="button" key={profile.id} onClick={() => setSelectedId(profile.id)}><strong>{profile.display_name}</strong><span>{profile.category} · reports to {profile.reports_to_role_code || "root / tenant-defined"}</span></button>)}</div>
            : <ul className="access-role-tree">{roots.map((profile) => <RoleNode key={profile.id} role={profile} childrenByParent={childrenByParent} seen={new Set()} onSelect={(item) => setSelectedId(item.id)} />)}</ul>}
        </> : <div className="access-role-matrix">
          <div className="access-role-matrix__head"><span>Role</span>{modules.map((module) => <span key={module.code} title={module.description}>{module.label}</span>)}</div>
          {filteredProfiles.map((profile) => <div className="access-role-matrix__row" key={profile.id}>
            <button type="button" onClick={() => setSelectedId(profile.id)}><strong>{profile.display_name}</strong><small>{profile.base_role_key.replaceAll("_", " ")}</small></button>
            {modules.map((module) => <span key={module.code} className={`is-${profile.module_permissions[module.code] || "none"}`}>{permissionLabel(profile.module_permissions[module.code])}</span>)}
          </div>)}
        </div>}
      </div>

      {draft ? <aside className="access-role-editor">
        <header><div><span>{draft.is_regulated ? "Prescribed profile" : draft.is_system ? "Framework profile" : "Custom profile"}</span><h3>{draft.id ? "Edit access role" : "Create cloned access role"}</h3></div>{draft.id && selected ? <small>{selected.assigned_user_count} users</small> : null}</header>
        {!draft.is_editable ? <div className="access-role-editor__lock"><ShieldCheck size={16} /> This prescribed profile is protected. Use Workforce for the appointment; its portal authority is fixed here.</div> : null}
        <label><span>Access profile code</span><input value={draft.code} disabled={Boolean(draft.id)} onChange={(event) => setDraft({ ...draft, code: event.target.value.toUpperCase().replace(/[^A-Z0-9]+/g, "_") })} /></label>
        <label><span>Display terminology</span><input value={draft.display_name} disabled={!draft.is_editable} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></label>
        <label><span>Stable access persona</span><select value={draft.base_role_key} disabled={Boolean(draft.id)} onChange={(event) => setDraft({ ...draft, base_role_key: event.target.value as AccountRole })}>{baseRoleOptions.map((role) => <option key={role} value={role}>{role.replaceAll("_", " ")}</option>)}</select><small>Choose on creation only. Terminology never changes this security identity.</small></label>
        <label><span>Function / category</span><input value={draft.category} disabled={!draft.is_editable} onChange={(event) => setDraft({ ...draft, category: event.target.value })} /></label>
        <label><span>Reports to</span><select value={draft.reports_to_role_code} disabled={!draft.is_editable} onChange={(event) => setDraft({ ...draft, reports_to_role_code: event.target.value })}><option value="">Root / tenant-defined</option>{profiles.filter((profile) => profile.is_active && profile.code !== draft.code).map((profile) => <option key={profile.code} value={profile.code}>{profile.display_name}</option>)}</select></label>
        <label><span>Responsibilities</span><textarea rows={4} value={draft.description} disabled={!draft.is_editable} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
        <div className="access-role-editor__modules"><span>Module access</span>{modules.map((module) => {
          const value = draft.module_permissions[module.code];
          return <button type="button" key={module.code} disabled={!draft.is_editable} className={`is-${value || "none"}`} title={!draft.is_editable ? "Prescribed module boundaries are protected" : module.description} onClick={() => {
            const next = nextPermission(value);
            const updated = { ...draft.module_permissions };
            if (next) updated[module.code] = next;
            else delete updated[module.code];
            setDraft({ ...draft, module_permissions: updated });
          }}><span>{module.label}</span><strong>{permissionLabel(value)}</strong></button>;
        })}</div>
        {draft.is_editable ? <label className="access-role-editor__active"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /><span>Active and assignable</span></label> : null}
        <button type="button" className="aum2-button aum2-button--primary access-role-editor__save" disabled={!draft.is_editable || save.isPending || !draft.code.trim() || !draft.display_name.trim()} onClick={() => save.mutate()}><Save size={16} /> {!draft.is_editable ? "Protected profile" : save.isPending ? "Saving…" : "Save access role"}</button>

        {draft.id && selected ? <section className="access-role-assignment" aria-label="Assign this access profile to a user">
          <div className="access-role-assignment__heading"><UserRoundCog size={17} /><div><strong>Assign users</strong><small>Apply this access role without leaving the frontend.</small></div></div>
          {selected.is_regulated ? <p className="access-role-assignment__notice">Regulated profiles can only be assigned when the user already holds the matching governed Workforce position. The server will reject any bypass attempt.</p> : null}
          <label><span>Find user</span><input value={userSearch} onChange={(event) => setUserSearch(event.target.value)} placeholder="Name, email or staff code" /></label>
          <label><span>User</span><select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)} disabled={users.isPending || users.isError}>
            <option value="">{users.isPending ? "Loading users…" : users.isError ? "Could not load users" : "Select user"}</option>
            {(users.data || []).map((user) => <option key={user.id} value={user.id}>{userLabel(user)} — {user.access_profile_name || user.role.replaceAll("_", " ")}</option>)}
          </select></label>
          <button type="button" className="aum2-button access-role-assignment__button" disabled={!selectedUserId || !selected.is_active || assign.isPending} onClick={() => assign.mutate()}>
            <UserRoundCog size={16} /> {assign.isPending ? "Assigning…" : `Assign ${selected.display_name}`}
          </button>
          {!selected.is_active ? <small className="access-role-assignment__warning">This profile is inactive. Activate and save it before assigning users.</small> : null}
        </section> : null}
      </aside> : <aside className="access-role-editor access-role-editor--blank"><Network size={28} /><p>Select an access role to inspect, edit or assign it.</p></aside>}
    </div>
    {feedback ? <div className="access-roles-panel__feedback" role="status">{feedback}</div> : null}
  </section>;
}
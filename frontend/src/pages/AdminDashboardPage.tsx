// src/pages/AdminDashboardPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import {
  Button,
  EmptyState,
  InlineAlert,
  PageHeader,
  Panel,
  Table,
} from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import {
  createAdminAmo,
  getAdminContext,
  listAdminAmos,
  listAdminDepartments,
  listAdminUsers,
  deactivateAdminUser,
  updateAdminUser,
  setAdminContext,
} from "../services/adminUsers";
import type {
  AdminAmoRead,
  AdminDepartmentRead,
  AdminUserRead,
  DataMode,
} from "../services/adminUsers";
import { LS_ACTIVE_AMO_ID } from "../services/adminUsers";

type UrlParams = {
  amoCode?: string;
};

const RESERVED_LOGIN_SLUGS = new Set(["system", "root"]);

const AdminDashboardPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();

  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccessAdmin = isSuperuser || isAmoAdmin;

  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [departments, setDepartments] = useState<AdminDepartmentRead[]>([]);
  const [departmentsLoading, setDepartmentsLoading] = useState(false);
  const [departmentsError, setDepartmentsError] = useState<string | null>(null);
  const [departmentSelections, setDepartmentSelections] = useState<Record<string, string>>({});
  const lastUsersRequestKey = useRef<string | null>(null);
  const lastUsersFetchAt = useRef<number>(0);
  const usersRequestRef = useRef<{
    key: string;
    controller: AbortController;
  } | null>(null);

  // SUPERUSER AMO picker
  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);
  const [amoCreateError, setAmoCreateError] = useState<string | null>(null);
  const [amoCreateSuccess, setAmoCreateSuccess] = useState<string | null>(null);
  const [lastCreatedAmoId, setLastCreatedAmoId] = useState<string | null>(null);
  const [contextMode, setContextMode] = useState<DataMode>("REAL");
  const [contextLoading, setContextLoading] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [lastRealAmoId, setLastRealAmoId] = useState<string | null>(null);
  const contextInitRef = useRef(false);

  type AmoFormState = {
    amoCode: string;
    name: string;
    loginSlug: string;
    icaoCode: string;
    country: string;
    contactEmail: string;
    contactPhone: string;
    timeZone: string;
  };

  const [amoForm, setAmoForm] = useState<AmoFormState>({
    amoCode: "",
    name: "",
    loginSlug: "",
    icaoCode: "",
    country: "",
    contactEmail: "",
    contactPhone: "",
    timeZone: "",
  });

  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const v = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return v && v.trim() ? v.trim() : null;
  });

  // Search + paging
  const [search, setSearch] = useState<string>("");
  const [skip, setSkip] = useState<number>(0);
  const [limit] = useState<number>(200);

  const effectiveAmoId = useMemo(() => {
    if (!currentUser?.amo_id) return null;
    if (isSuperuser) return activeAmoId || currentUser.amo_id;
    return currentUser.amo_id;
  }, [currentUser?.amo_id, isSuperuser, activeAmoId]);

  const departmentMap = useMemo(() => {
    return new Map(departments.map((dept) => [dept.id, dept]));
  }, [departments]);

  useEffect(() => {
    if (!effectiveAmoId) return;
    let active = true;
    const loadDepartments = async () => {
      setDepartmentsLoading(true);
      setDepartmentsError(null);
      try {
        const data = await listAdminDepartments(effectiveAmoId);
        if (!active) return;
        setDepartments(data);
      } catch (err: any) {
        if (!active) return;
        setDepartmentsError(err?.message || "Failed to load departments.");
      } finally {
        if (active) setDepartmentsLoading(false);
      }
    };
    loadDepartments();
    return () => {
      active = false;
    };
  }, [effectiveAmoId]);

  // If user is not admin, redirect to THEIR department, not planning
  useEffect(() => {
    if (!currentUser) return;
    if (canAccessAdmin) return;

    const dept = ctx.department;
    if (amoCode && dept) {
      navigate(`/maintenance/${amoCode}/${dept}`, { replace: true });
      return;
    }

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/login`, { replace: true });
      return;
    }

    navigate("/login", { replace: true });
  }, [currentUser, canAccessAdmin, amoCode, ctx.department, navigate]);

  // Load AMOs for SUPERUSER only
  useEffect(() => {
    if (!isSuperuser) return;

    const loadAmos = async () => {
      setAmoError(null);
      setAmoLoading(true);
      try {
        const data = await listAdminAmos();
        setAmos(data);

        const stored = localStorage.getItem(LS_ACTIVE_AMO_ID);
        const storedTrimmed = stored && stored.trim() ? stored.trim() : null;
        const storedValid =
          !!storedTrimmed && data.some((a) => a.id === storedTrimmed);

        if (!storedValid) {
          const preferred =
            currentUser?.amo_id && data.some((a) => a.id === currentUser.amo_id)
              ? currentUser.amo_id
              : null;

          const fallback = preferred || data[0]?.id || null;

          if (fallback) {
            localStorage.setItem(LS_ACTIVE_AMO_ID, fallback);
            setActiveAmoId(fallback);
          }
        }
      } catch (e: any) {
        console.error("Failed to load AMOs", e);
        setAmoError(e?.message || "Could not load AMOs.");
      } finally {
        setAmoLoading(false);
      }
    };

    loadAmos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperuser]);

  useEffect(() => {
    if (!isSuperuser || contextInitRef.current) return;
    contextInitRef.current = true;
    const loadContext = async () => {
      setContextLoading(true);
      setContextError(null);
      try {
        const ctx = await getAdminContext();
        setContextMode(ctx.data_mode);
        setLastRealAmoId(ctx.last_real_amo_id);
        if (ctx.active_amo_id) {
          setActiveAmoId(ctx.active_amo_id);
          localStorage.setItem(LS_ACTIVE_AMO_ID, ctx.active_amo_id);
        }
      } catch (err: any) {
        setContextError(err?.message || "Failed to load admin context.");
      } finally {
        setContextLoading(false);
      }
    };
    loadContext();
  }, [isSuperuser]);

  useEffect(() => {
    if (!isSuperuser || !amos.length) return;
    if (activeAmoId && amos.some((a) => a.id === activeAmoId)) return;

    const fallback =
      (lastCreatedAmoId && amos.find((a) => a.id === lastCreatedAmoId)?.id) ||
      (currentUser?.amo_id && amos.find((a) => a.id === currentUser.amo_id)?.id) ||
      amos[0]?.id ||
      null;

    if (!fallback) return;

    const fallbackAmo = amos.find((a) => a.id === fallback);
    const fallbackMode: DataMode = fallbackAmo?.is_demo ? "DEMO" : "REAL";

    setContextLoading(true);
    setContextError(null);
    setAdminContext({ active_amo_id: fallback, data_mode: fallbackMode })
      .then((ctx) => {
        setActiveAmoId(ctx.active_amo_id);
        setContextMode(ctx.data_mode);
        setLastRealAmoId(ctx.last_real_amo_id);
        if (ctx.active_amo_id) {
          localStorage.setItem(LS_ACTIVE_AMO_ID, ctx.active_amo_id);
        }
      })
      .catch((err: any) => {
        setContextError(err?.message || "Failed to update admin context.");
      })
      .finally(() => setContextLoading(false));
  }, [isSuperuser, amos, activeAmoId, lastCreatedAmoId, currentUser?.amo_id]);

  const trimmedSearch = search.trim();
  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);
  const usersRequestKey = useMemo(
    () =>
      JSON.stringify({
        amo_id: effectiveAmoId,
        skip,
        limit,
        search: trimmedSearch,
      }),
    [effectiveAmoId, skip, limit, trimmedSearch]
  );

  // Load users
  useEffect(() => {
    const loadUsers = async () => {
      setError(null);

      if (!currentUser) {
        setError("No user session found. Please sign in again.");
        return;
      }

      if (!canAccessAdmin) {
        setError("You do not have access to the admin area.");
        return;
      }

      if (!effectiveAmoId) {
        setError("Could not determine AMO context. Please sign in again.");
        return;
      }

      if (lastUsersRequestKey.current === usersRequestKey) {
        const now = Date.now();
        if (now - lastUsersFetchAt.current < 1000) {
          return;
        }
      }

      if (usersRequestRef.current?.key === usersRequestKey) {
        return;
      }

      if (usersRequestRef.current) {
        usersRequestRef.current.controller.abort();
        usersRequestRef.current = null;
      }

      try {
        const controller = new AbortController();
        usersRequestRef.current = { key: usersRequestKey, controller };
        lastUsersRequestKey.current = usersRequestKey;
        lastUsersFetchAt.current = Date.now();
        setLoading(true);

        const data = await listAdminUsers(
          {
            amo_id: isSuperuser ? effectiveAmoId : undefined,
            skip,
            limit,
            search: trimmedSearch || undefined,
          },
          {
            signal: controller.signal,
          }
        );

        setUsers(data);
        lastUsersRequestKey.current = usersRequestKey;
      } catch (err: any) {
        if (err?.name === "AbortError") {
          return;
        }
        console.error("Failed to load users", err);
        setError(
          err?.message ||
            "Could not load users. Please try again or contact Quality/IT."
        );
      } finally {
        if (usersRequestRef.current?.key === usersRequestKey) {
          usersRequestRef.current = null;
        }
        setLoading(false);
      }
    };

    loadUsers();

    return () => {
      if (usersRequestRef.current) {
        usersRequestRef.current.controller.abort();
        usersRequestRef.current = null;
      }
    };
  }, [
    currentUser,
    canAccessAdmin,
    effectiveAmoId,
    isSuperuser,
    skip,
    limit,
    trimmedSearch,
    usersRequestKey,
  ]);

  const handleNewUser = () => {
    const target = amoCode ? `/maintenance/${amoCode}/admin/users/new` : "/login";
    navigate(target);
  };

  const handleManageAssets = () => {
    const target = amoCode ? `/maintenance/${amoCode}/admin/amo-assets` : "/login";
    navigate(target);
  };

  const clearFilter = () => {
    if (!amoCode) return;
    navigate(`/maintenance/${amoCode}/admin/users`, { replace: true });
  };

  const filteredUsers = useMemo(() => {
    if (!activeFilter) return users;
    switch (activeFilter) {
      case "missing_department":
        return users.filter((u) => !u.department_id);
      case "inactive":
        return users.filter((u) => !u.is_active);
      case "attention":
        return users.filter((u) => !u.department_id || !u.is_active);
      default:
        return users;
    }
  }, [activeFilter, users]);

  const exportUsersCsv = () => {
    const rows = filteredUsers.map((u) => ({
      staff_code: u.staff_code ?? "",
      name: u.full_name ?? "",
      email: u.email ?? "",
      role: u.role ?? "",
      department: u.department_id ?? "",
      status: u.is_active ? "Active" : "Inactive",
    }));

    const header = rows.length
      ? Object.keys(rows[0]).join(",")
      : "staff_code,name,email,role,department,status";
    const body = rows
      .map((r) =>
        Object.values(r)
          .map((v) => {
            const s = String(v ?? "");
            const escaped =
              s.includes(",") || s.includes('"') || s.includes("\n")
                ? `"${s.replace(/"/g, '""')}"`
                : s;
            return escaped;
          })
          .join(","),
      )
      .join("\n");

    const csv = rows.length ? `${header}\n${body}\n` : `${header}\n`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "amo_users.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportUsersPdf = () => {
    if (typeof window === "undefined") return;
    const win = window.open("", "_blank", "width=980,height=720");
    if (!win) return;

    const rows = filteredUsers
      .map(
        (u) => `
          <tr>
            <td>${u.staff_code ?? ""}</td>
            <td>${u.full_name ?? ""}</td>
            <td>${u.email ?? ""}</td>
            <td>${u.role ?? ""}</td>
            <td>${u.department_id ?? "—"}</td>
            <td>${u.is_active ? "Active" : "Inactive"}</td>
          </tr>
        `,
      )
      .join("");

    win.document.write(`
      <html>
        <head>
          <title>AMO Users</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; }
            h1 { font-size: 18px; margin-bottom: 12px; }
            table { width: 100%; border-collapse: collapse; font-size: 12px; }
            th, td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; }
            th { background: #f3f4f6; text-transform: uppercase; letter-spacing: 0.04em; font-size: 11px; }
          </style>
        </head>
        <body>
          <h1>AMO Users</h1>
          <table>
            <thead>
              <tr>
                <th>Staff Code</th>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Department</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${rows || `<tr><td colspan="6">No users found.</td></tr>`}
            </tbody>
          </table>
        </body>
      </html>
    `);
    win.document.close();
    win.focus();
    win.print();
  };

  const handleToggleUser = async (user: AdminUserRead) => {
    const nextActive = !user.is_active;
    const label = nextActive ? "reactivate" : "deactivate";
    const ok = window.confirm(
      `Are you sure you want to ${label} ${user.full_name}?`
    );
    if (!ok) return;
    try {
      if (!nextActive) {
        await deactivateAdminUser(user.id);
      } else {
        await updateAdminUser(user.id, { is_active: true });
      }
      setUsers((prev) =>
        prev.map((u) =>
          u.id === user.id ? { ...u, is_active: nextActive } : u
        )
      );
    } catch (err: any) {
      setError(err?.message || "Failed to update user status.");
    }
  };

  const handleAssignDepartment = async (user: AdminUserRead) => {
    const selectedDepartmentId = departmentSelections[user.id];
    if (!selectedDepartmentId) {
      setError("Select a department before assigning.");
      return;
    }

    try {
      setError(null);
      const updated = await updateAdminUser(user.id, {
        department_id: selectedDepartmentId,
      });
      setUsers((prev) =>
        prev.map((item) => (item.id === user.id ? updated : item))
      );
      setDepartmentSelections((prev) => {
        const next = { ...prev };
        delete next[user.id];
        return next;
      });
    } catch (err: any) {
      setError(err?.message || "Failed to assign department.");
    }
  };

  const handleAmoChange = (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    const amo = amos.find((item) => item.id === v);
    const nextMode: DataMode = amo?.is_demo ? "DEMO" : "REAL";
    setContextLoading(true);
    setContextError(null);
    setAdminContext({ active_amo_id: v, data_mode: nextMode })
      .then((ctx) => {
        setActiveAmoId(ctx.active_amo_id);
        setContextMode(ctx.data_mode);
        setLastRealAmoId(ctx.last_real_amo_id);
        if (ctx.active_amo_id) {
          localStorage.setItem(LS_ACTIVE_AMO_ID, ctx.active_amo_id);
        }
        setSkip(0);
      })
      .catch((err: any) => {
        setContextError(err?.message || "Failed to update admin context.");
      })
      .finally(() => setContextLoading(false));
  };

  const handleContextToggle = (nextIsDemo: boolean) => {
    const targetMode: DataMode = nextIsDemo ? "DEMO" : "REAL";
    let targetAmoId = activeAmoId;

    if (targetMode === "DEMO") {
      const demoAmo = amos.find((a) => a.is_demo);
      targetAmoId = activeAmoId && amos.find((a) => a.id === activeAmoId)?.is_demo
        ? activeAmoId
        : demoAmo?.id || null;
      if (!targetAmoId) {
        setContextError("No demo AMO is available.");
        return;
      }
    } else {
      const realCandidate =
        (lastRealAmoId && amos.find((a) => a.id === lastRealAmoId && !a.is_demo)?.id) ||
        (activeAmoId && amos.find((a) => a.id === activeAmoId && !a.is_demo)?.id) ||
        (currentUser?.amo_id && amos.find((a) => a.id === currentUser.amo_id)?.id) ||
        amos.find((a) => !a.is_demo)?.id ||
        null;
      targetAmoId = realCandidate;
      if (!targetAmoId) {
        setContextError("No real AMO is available.");
        return;
      }
    }

    setContextLoading(true);
    setContextError(null);
    setAdminContext({ data_mode: targetMode, active_amo_id: targetAmoId })
      .then((ctx) => {
        setContextMode(ctx.data_mode);
        setLastRealAmoId(ctx.last_real_amo_id);
        setActiveAmoId(ctx.active_amo_id);
        if (ctx.active_amo_id) {
          localStorage.setItem(LS_ACTIVE_AMO_ID, ctx.active_amo_id);
        }
      })
      .catch((err: any) => {
        setContextError(err?.message || "Failed to update admin context.");
      })
      .finally(() => setContextLoading(false));
  };

  const handleAmoFormChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ): void => {
    const { name, value } = e.target;
    const key = name as keyof AmoFormState;
    setAmoForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreateAmo = async (e: React.FormEvent) => {
    e.preventDefault();
    setAmoCreateError(null);
    setAmoCreateSuccess(null);

    const amoCodeValue = amoForm.amoCode.trim();
    const nameValue = amoForm.name.trim();
    const loginSlugValue = amoForm.loginSlug.trim().toLowerCase();

    if (!amoCodeValue || !nameValue || !loginSlugValue) {
      setAmoCreateError("AMO code, name, and login slug are required.");
      return;
    }

    if (RESERVED_LOGIN_SLUGS.has(loginSlugValue)) {
      setAmoCreateError("Login slug is reserved for platform support.");
      return;
    }

    try {
      const created = await createAdminAmo({
        amo_code: amoCodeValue.toUpperCase(),
        name: nameValue,
        login_slug: loginSlugValue,
        icao_code: amoForm.icaoCode.trim() || undefined,
        country: amoForm.country.trim() || undefined,
        contact_email: amoForm.contactEmail.trim() || undefined,
        contact_phone: amoForm.contactPhone.trim() || undefined,
        time_zone: amoForm.timeZone.trim() || undefined,
      });

      setAmoForm({
        amoCode: "",
        name: "",
        loginSlug: "",
        icaoCode: "",
        country: "",
        contactEmail: "",
        contactPhone: "",
        timeZone: "",
      });

      setAmoCreateSuccess(
        `AMO ${created.amo_code} created. You can now add its first user.`
      );
      setLastCreatedAmoId(created.id);
      setActiveAmoId(created.id);
      localStorage.setItem(LS_ACTIVE_AMO_ID, created.id);

      const data = await listAdminAmos();
      setAmos(data);
    } catch (err: any) {
      console.error("Failed to create AMO", err);
      const msg =
        err?.response?.data?.detail ||
        err?.detail ||
        err?.message ||
        "Could not create AMO. Please try again.";
      setAmoCreateError(
        typeof msg === "string"
          ? msg
          : "Could not create AMO. Please try again."
      );
    }
  };

  const activeAmoLabel = useMemo(() => {
    if (!isSuperuser) return null;
    const a = amos.find((x) => x.id === effectiveAmoId);
    return a ? `${a.amo_code} — ${a.name}` : null;
  }, [isSuperuser, amos, effectiveAmoId]);

  if (currentUser && !canAccessAdmin) {
    return null;
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-users"
    >
      <div className="admin-page">
        <PageHeader
          title="User Management"
          subtitle={
            currentUser
              ? `Manage AMO users, roles and access. Signed in as ${currentUser.full_name}.`
              : "Manage AMO users, roles and access."
          }
        />

        {isSuperuser && (
          <Panel
            title="AMO Context"
            subtitle="Select which AMO you are managing. Need to create a new AMO? Use the AMO Management page."
          >
            {contextLoading && <p>Loading context…</p>}
            {contextError && (
              <InlineAlert tone="danger" title="Error">
                <span>{contextError}</span>
              </InlineAlert>
            )}

            {amoLoading && <p>Loading AMOs…</p>}
            {amoError && (
              <InlineAlert tone="danger" title="Error">
                <span>{amoError}</span>
              </InlineAlert>
            )}

            {!amoLoading && !amoError && (
              <div className="form-row">
                <label htmlFor="demoToggle">Data Mode</label>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <input
                    id="demoToggle"
                    type="checkbox"
                    checked={contextMode === "DEMO"}
                    onChange={(e) => handleContextToggle(e.target.checked)}
                  />
                  <span>
                    {contextMode === "DEMO" ? "Demo data" : "Real data"}
                  </span>
                </div>

                <label htmlFor="amoSelect">Active AMO</label>
                <select
                  id="amoSelect"
                  value={effectiveAmoId ?? ""}
                  onChange={(e) => handleAmoChange(e.target.value)}
                  disabled={amos.length === 0}
                >
                  {amos.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.amo_code} — {a.name}
                    </option>
                  ))}
                </select>

                {activeAmoLabel && (
                  <p style={{ marginTop: 8, marginBottom: 0, opacity: 0.85 }}>
                    Viewing users for: <strong>{activeAmoLabel}</strong>
                  </p>
                )}
              </div>
            )}

            <hr style={{ margin: "16px 0" }} />

            <h4 style={{ marginTop: 0 }}>Create a new AMO</h4>
            <p style={{ marginTop: 0, opacity: 0.85 }}>
              Register a new AMO, then create its first admin user.
            </p>

            {amoCreateError && (
              <InlineAlert tone="danger" title="Error">
                <span>{amoCreateError}</span>
              </InlineAlert>
            )}
            {amoCreateSuccess && (
              <InlineAlert tone="success" title="Success">
                <span>{amoCreateSuccess}</span>
              </InlineAlert>
            )}

            <form onSubmit={handleCreateAmo} className="form-grid">
              <div className="form-row">
                <label htmlFor="amoCode">AMO Code</label>
                <input
                  id="amoCode"
                  name="amoCode"
                  type="text"
                  value={amoForm.amoCode}
                  onChange={handleAmoFormChange}
                  placeholder="e.g. SKYJET"
                  required
                />
                <p className="form-hint">Short code used internally and on reports.</p>
              </div>

              <div className="form-row">
                <label htmlFor="amoName">AMO Name</label>
                <input
                  id="amoName"
                  name="name"
                  type="text"
                  value={amoForm.name}
                  onChange={handleAmoFormChange}
                  placeholder="SkyJet Maintenance"
                  required
                />
              </div>

              <div className="form-row">
                <label htmlFor="loginSlug">Login Slug</label>
                <input
                  id="loginSlug"
                  name="loginSlug"
                  type="text"
                  value={amoForm.loginSlug}
                  onChange={handleAmoFormChange}
                  placeholder="skyjet"
                  required
                />
                <p className="form-hint">
                  Login URL:{" "}
                  <code>/maintenance/{amoForm.loginSlug || "your-amo"}/login</code>
                </p>
              </div>

              <div className="form-row">
                <label htmlFor="icaoCode">ICAO Code</label>
                <input
                  id="icaoCode"
                  name="icaoCode"
                  type="text"
                  value={amoForm.icaoCode}
                  onChange={handleAmoFormChange}
                />
              </div>

              <div className="form-row">
                <label htmlFor="country">Country</label>
                <input
                  id="country"
                  name="country"
                  type="text"
                  value={amoForm.country}
                  onChange={handleAmoFormChange}
                />
              </div>

              <div className="form-row">
                <label htmlFor="contactEmail">Contact Email</label>
                <input
                  id="contactEmail"
                  name="contactEmail"
                  type="email"
                  value={amoForm.contactEmail}
                  onChange={handleAmoFormChange}
                />
              </div>

              <div className="form-row">
                <label htmlFor="contactPhone">Contact Phone</label>
                <input
                  id="contactPhone"
                  name="contactPhone"
                  type="tel"
                  value={amoForm.contactPhone}
                  onChange={handleAmoFormChange}
                />
              </div>

              <div className="form-row">
                <label htmlFor="timeZone">Time Zone</label>
                <input
                  id="timeZone"
                  name="timeZone"
                  type="text"
                  value={amoForm.timeZone}
                  onChange={handleAmoFormChange}
                  placeholder="Africa/Nairobi"
                />
              </div>

              <div className="form-actions">
                <Button type="submit">Create AMO</Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleNewUser}
                  disabled={!lastCreatedAmoId}
                >
                  Create first user
                </Button>
              </div>
            </form>
          </Panel>
        )}

        <Panel
          title="Users"
          actions={(
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button type="button" size="sm" onClick={handleNewUser}>
                + Create user
              </Button>
              {isSuperuser && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(`/maintenance/${amoCode}/admin/amos`)}
                >
                  Manage AMOs
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={exportUsersCsv}
                disabled={users.length === 0}
              >
                Export CSV
              </Button>
            </div>
          )}
        >

        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={exportUsersPdf}
            disabled={users.length === 0}
          >
            Export PDF
          </Button>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setSkip(0);
              }}
              placeholder="Search name, email, staff code…"
              className="input"
              style={{ minWidth: 240 }}
            />
            {skip > 0 && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setSkip(Math.max(0, skip - limit))}
                disabled={loading}
              >
                Prev
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setSkip(skip + limit)}
              disabled={loading || users.length < limit}
              title={users.length < limit ? "No more results" : "Next page"}
            >
              Next
            </Button>
          </div>
        </div>

        {loading && <p>Loading users…</p>}
        {error && (
          <InlineAlert tone="danger" title="Error">
            <span>{error}</span>
          </InlineAlert>
        )}
        {departmentsError && (
          <InlineAlert tone="danger" title="Department Error">
            <span>{departmentsError}</span>
          </InlineAlert>
        )}

        {!loading && !error && (
          <>
            {activeFilter && (
              <div className="admin-filter-banner">
                <span>
                  Filtered:{" "}
                  {activeFilter === "missing_department"
                    ? "Users missing department"
                    : activeFilter === "inactive"
                      ? "Inactive users"
                      : "Users requiring attention"}
                </span>
                <Button type="button" size="sm" variant="ghost" onClick={clearFilter}>
                  Clear filter
                </Button>
              </div>
            )}
            <Table>
              <thead>
                <tr>
                  <th>Staff code</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="No users found for this AMO." />
                    </td>
                  </tr>
                )}
                {filteredUsers.map((u) => (
                  <tr key={u.id}>
                    <td>{u.staff_code}</td>
                    <td>{u.full_name}</td>
                    <td>{u.email}</td>
                    <td>{u.role}</td>
                    <td>{departmentMap.get(u.department_id ?? "")?.name ?? "—"}</td>
                    <td>{u.is_active ? "Active" : "Inactive"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {!u.department_id && (
                          <>
                            <select
                              className="input input--compact"
                              aria-label={`Assign department for ${u.full_name}`}
                              value={departmentSelections[u.id] || ""}
                              onChange={(e) =>
                                setDepartmentSelections((prev) => ({
                                  ...prev,
                                  [u.id]: e.target.value,
                                }))
                              }
                              disabled={departmentsLoading}
                            >
                              <option value="">Select department</option>
                              {departments.map((dept) => (
                                <option key={dept.id} value={dept.id}>
                                  {dept.name}
                                </option>
                              ))}
                            </select>
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              onClick={() => handleAssignDepartment(u)}
                              disabled={departmentsLoading}
                            >
                              Assign dept
                            </Button>
                          </>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant={u.is_active ? "danger" : "ghost"}
                          onClick={() => handleToggleUser(u)}
                          title={u.is_active ? "Deactivate user" : "Reactivate user"}
                        >
                          {u.is_active ? "🗑️ Deactivate" : "✅ Reactivate"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Panel>

      <Panel
        title="CRS Asset Setup"
        subtitle="Upload AMO-specific CRS templates and branding assets used in PDF generation."
        actions={(
          <Button type="button" size="sm" onClick={handleManageAssets}>
            Manage CRS assets
          </Button>
        )}
      />
    </div>
    </DepartmentLayout>
  );
};

export default AdminDashboardPage;

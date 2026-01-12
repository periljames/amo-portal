// src/pages/AdminUsageSettingsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import {
  type AdminAmoRead,
  type AdminUserRead,
  listAdminAmos,
  listAdminUsers,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";

type UrlParams = {
  amoCode?: string;
};

type ThrottleStore = {
  amo: Record<
    string,
    {
      limit: number;
      perUser: Record<string, number>;
    }
  >;
  cacheHolidays: boolean;
};

const DEFAULT_THROTTLE: ThrottleStore = {
  amo: {},
  cacheHolidays: true,
};

const clamp = (value: number, min = 0, max = 100) =>
  Math.max(min, Math.min(max, value));

const STORAGE_KEY = "amo_calendar_throttle_settings";

const AdminUsageSettingsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccess = isSuperuser || isAmoAdmin;

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAmoId, setSelectedAmoId] = useState<string | null>(() => {
    const stored = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return stored && stored.trim() ? stored.trim() : null;
  });
  const [store, setStore] = useState<ThrottleStore>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return DEFAULT_THROTTLE;
      return { ...DEFAULT_THROTTLE, ...(JSON.parse(raw) as ThrottleStore) };
    } catch {
      return DEFAULT_THROTTLE;
    }
  });

  useEffect(() => {
    if (!currentUser) return;
    if (canAccess) return;
    navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
  }, [currentUser, canAccess, amoCode, navigate]);

  useEffect(() => {
    if (!canAccess) return;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        if (isSuperuser) {
          const data = await listAdminAmos();
          setAmos(data);
          const fallback =
            selectedAmoId ||
            localStorage.getItem(LS_ACTIVE_AMO_ID) ||
            data[0]?.id ||
            null;
          if (fallback && fallback !== selectedAmoId) {
            setSelectedAmoId(fallback);
          }
        } else {
          setSelectedAmoId((currentUser as any)?.amo_id || null);
        }
      } catch (err: any) {
        setError(err?.message || "Failed to load AMO list.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [canAccess, isSuperuser, currentUser, selectedAmoId]);

  useEffect(() => {
    if (!selectedAmoId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listAdminUsers({ amo_id: selectedAmoId }, { signal: controller.signal })
      .then((data) => setUsers(data))
      .catch((err: any) => {
        if (err?.name === "AbortError") return;
        setError(err?.message || "Failed to load users.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [selectedAmoId]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }, [store]);

  if (currentUser && !canAccess) {
    return null;
  }

  const amoThrottle = selectedAmoId ? store.amo[selectedAmoId]?.limit ?? 70 : 70;
  const updateAmoThrottle = (value: number) => {
    if (!selectedAmoId) return;
    setStore((prev) => ({
      ...prev,
      amo: {
        ...prev.amo,
        [selectedAmoId]: {
          limit: clamp(value),
          perUser: prev.amo[selectedAmoId]?.perUser || {},
        },
      },
    }));
  };

  const updateUserThrottle = (userId: string, value: number) => {
    if (!selectedAmoId) return;
    setStore((prev) => ({
      ...prev,
      amo: {
        ...prev.amo,
        [selectedAmoId]: {
          limit: prev.amo[selectedAmoId]?.limit ?? 70,
          perUser: {
            ...(prev.amo[selectedAmoId]?.perUser || {}),
            [userId]: clamp(value),
          },
        },
      },
    }));
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-settings">
      <header className="page-header">
        <h1 className="page-header__title">Usage throttling & calendar settings</h1>
        <p className="page-header__subtitle">
          Control calendar sync budgets per AMO and per user to keep Google/Outlook usage
          within free-tier limits.
        </p>
      </header>

      {error && (
        <div className="card card--error">
          <p>{error}</p>
        </div>
      )}

      <section className="page-section">
        <div className="card card--form">
          <h3 style={{ marginTop: 0 }}>AMO scope</h3>
          <p className="text-muted">
            Superusers can throttle any AMO; AMO admins can tune only their own AMO.
          </p>

          {isSuperuser && (
            <div className="form-row">
              <label htmlFor="amoSelect">Active AMO</label>
              <select
                id="amoSelect"
                value={selectedAmoId ?? ""}
                onChange={(e) => {
                  const next = e.target.value;
                  setSelectedAmoId(next);
                  localStorage.setItem(LS_ACTIVE_AMO_ID, next);
                }}
                disabled={amos.length === 0}
              >
                {amos.map((amo) => (
                  <option key={amo.id} value={amo.id}>
                    {amo.amo_code} — {amo.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="form-row" style={{ marginTop: 12 }}>
            <label className="form-control range-control">
              <span>AMO calendar sync budget</span>
              <input
                type="range"
                min={0}
                max={100}
                value={amoThrottle}
                onChange={(e) => updateAmoThrottle(Number(e.target.value))}
              />
              <strong>{amoThrottle}%</strong>
            </label>
            <p className="text-muted" style={{ margin: 0 }}>
              Lower values reduce sync frequency and prioritize cached data.
            </p>
          </div>

          <label className="form-control" style={{ marginTop: 12 }}>
            <span>Use holiday cache (24h)</span>
            <select
              value={store.cacheHolidays ? "enabled" : "disabled"}
              onChange={(e) =>
                setStore((prev) => ({
                  ...prev,
                  cacheHolidays: e.target.value === "enabled",
                }))
              }
            >
              <option value="enabled">Enabled</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>
        </div>
      </section>

      <section className="page-section">
        <div className="card card--form">
          <h3 style={{ marginTop: 0 }}>Per-user throttling</h3>
          <p className="text-muted">
            Apply per-user budgets to keep heavy calendar usage under control.
          </p>

          {loading && <p className="text-muted">Loading users…</p>}

          {!loading && users.length === 0 && (
            <p className="text-muted">No users found for this AMO.</p>
          )}

          {users.length > 0 && (
            <div className="table-responsive">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Throttle</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => {
                    const userThrottle =
                      store.amo[selectedAmoId ?? ""]?.perUser[user.id] ?? amoThrottle;
                    return (
                      <tr key={user.id}>
                        <td>
                          {user.full_name || `${user.first_name} ${user.last_name}`} ·{" "}
                          {user.email}
                        </td>
                        <td>{user.role}</td>
                        <td style={{ minWidth: 220 }}>
                          <input
                            type="range"
                            min={0}
                            max={100}
                            value={userThrottle}
                            onChange={(e) =>
                              updateUserThrottle(user.id, Number(e.target.value))
                            }
                          />
                          <span style={{ marginLeft: 8 }}>{userThrottle}%</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminUsageSettingsPage;

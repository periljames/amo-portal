// src/pages/AdminUsageSettingsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import { getApiBaseUrl, normaliseBaseUrl, setApiBaseRuntime } from "../services/config";
import {
  type AdminAmoRead,
  type AdminUserRead,
  listAdminAmos,
  listAdminUsers,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import {
  type PlatformSettings,
  fetchPlatformSettings,
  updatePlatformSettings,
} from "../services/platformSettings";

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
  const location = useLocation();
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
  const [apiBaseDraft, setApiBaseDraft] = useState(() => {
    return getApiBaseUrl();
  });
  const [platformSettings, setPlatformSettings] = useState<PlatformSettings | null>(
    null
  );
  const [platformLoading, setPlatformLoading] = useState(false);
  const [apiBaseMessage, setApiBaseMessage] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);

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

  useEffect(() => {
    if (!isSuperuser) return;
    setPlatformLoading(true);
    fetchPlatformSettings()
      .then((data) => {
        setPlatformSettings(data);
        if (data.api_base_url) {
          setApiBaseDraft(data.api_base_url);
          setApiBaseRuntime(data.api_base_url);
        }
      })
      .catch((err: any) => {
        setError(err?.message || "Failed to load platform settings.");
      })
      .finally(() => setPlatformLoading(false));
  }, [isSuperuser]);

  const handleSaveApiBase = () => {
    const next = normaliseBaseUrl(apiBaseDraft);
    if (!next) {
      setApiBaseMessage("Please enter a valid API base URL.");
      return;
    }
    updatePlatformSettings({ api_base_url: next })
      .then((data) => {
        setPlatformSettings(data);
        setApiBaseRuntime(next);
        setApiBaseMessage("Saved. New API base URL is active.");
      })
      .catch((err: any) => {
        setApiBaseMessage(err?.message || "Failed to save API base URL.");
      });
  };

  const handleClearApiBase = () => {
    updatePlatformSettings({ api_base_url: null })
      .then((data) => {
        setPlatformSettings(data);
        setApiBaseRuntime(null);
        setApiBaseDraft(getApiBaseUrl());
        setApiBaseMessage("Cleared override. Default API base URL restored.");
      })
      .catch((err: any) => {
        setApiBaseMessage(err?.message || "Failed to clear API base URL.");
      });
  };

  const runHealthCheck = async () => {
    const base = normaliseBaseUrl(apiBaseDraft);
    if (!base) {
      setHealthStatus("Enter a valid API base URL before running diagnostics.");
      return;
    }
    setHealthLoading(true);
    setHealthStatus(null);
    try {
      const res = await fetch(`${base}/health`, { method: "GET" });
      const text = await res.text().catch(() => "");
      setHealthStatus(
        `Status ${res.status}: ${text || res.statusText || "OK"}`
      );
    } catch (err: any) {
      setHealthStatus(err?.message || "Health check failed.");
    } finally {
      setHealthLoading(false);
    }
  };

  const formatTimestamp = (value?: string | null) => {
    if (!value) return "Not set";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

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

      {activeFilter && (
        <div className="info-banner info-banner--warning" style={{ margin: "12px 0" }}>
          <span>Filter applied: {activeFilter.replace(/_/g, " ")}</span>
          <button
            type="button"
            className="secondary-chip-btn"
            onClick={() =>
              navigate(`/maintenance/${amoCode}/admin/settings`, { replace: true })
            }
          >
            Clear filter
          </button>
        </div>
      )}

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

      {isSuperuser && (
        <section className="page-section">
          <div className="card card--form">
            <h3 style={{ marginTop: 0 }}>HTTPS & connectivity diagnostics</h3>
            <p className="text-muted">
              Configure the API base URL used by the portal and run a health check. Settings are
              stored server-side for all sessions.
            </p>

            <div className="form-row">
              <label htmlFor="apiBaseUrl">API base URL (HTTPS)</label>
              <input
                id="apiBaseUrl"
                type="url"
                placeholder="https://api.example.com"
                value={apiBaseDraft}
                onChange={(e) => setApiBaseDraft(e.target.value)}
              />
              <p className="text-muted" style={{ marginTop: 6 }}>
                Current default: <strong>{getApiBaseUrl()}</strong>
              </p>
            </div>

            <div className="form-row" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <button type="button" className="btn" onClick={handleSaveApiBase}>
                Save override
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleClearApiBase}>
                Clear override
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={runHealthCheck}
                disabled={healthLoading}
              >
                {healthLoading ? "Running..." : "Run health check"}
              </button>
            </div>

            {apiBaseMessage && (
              <p className="text-muted" style={{ marginTop: 8 }}>
                {apiBaseMessage}
              </p>
            )}

            {healthStatus && (
              <div className="card card--info" style={{ marginTop: 12 }}>
                <strong>Health check:</strong> {healthStatus}
              </div>
            )}

            <div className="card" style={{ marginTop: 16 }}>
              <h4 style={{ marginTop: 0 }}>ACME / Let’s Encrypt status</h4>
              {platformLoading && <p className="text-muted">Loading status…</p>}
              {!platformLoading && (
                <dl style={{ display: "grid", gap: 8, margin: 0 }}>
                  <div>
                    <dt>ACME client</dt>
                    <dd>{platformSettings?.acme_client || "Not set"}</dd>
                  </div>
                  <div>
                    <dt>Directory URL</dt>
                    <dd>{platformSettings?.acme_directory_url || "Not set"}</dd>
                  </div>
                  <div>
                    <dt>Certificate status</dt>
                    <dd>{platformSettings?.certificate_status || "Not set"}</dd>
                  </div>
                  <div>
                    <dt>Issuer</dt>
                    <dd>{platformSettings?.certificate_issuer || "Not set"}</dd>
                  </div>
                  <div>
                    <dt>Expires at</dt>
                    <dd>{formatTimestamp(platformSettings?.certificate_expires_at)}</dd>
                  </div>
                  <div>
                    <dt>Last renewed</dt>
                    <dd>{formatTimestamp(platformSettings?.last_renewed_at)}</dd>
                  </div>
                </dl>
              )}
            </div>
          </div>
        </section>
      )}
    </DepartmentLayout>
  );
};

export default AdminUsageSettingsPage;

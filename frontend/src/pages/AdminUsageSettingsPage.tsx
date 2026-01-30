// src/pages/AdminUsageSettingsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import { setBrandContext } from "../services/branding";
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
  fetchPlatformLogoBlob,
  uploadPlatformLogo,
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
  const [brandingDraft, setBrandingDraft] = useState({
    platform_name: "",
    platform_tagline: "",
    brand_accent: "",
    brand_accent_soft: "",
    brand_accent_secondary: "",
  });
  const [brandingMessage, setBrandingMessage] = useState<string | null>(null);
  const [brandingSaving, setBrandingSaving] = useState(false);
  const [platformLogoUrl, setPlatformLogoUrl] = useState<string | null>(null);
  const [platformLoading, setPlatformLoading] = useState(false);
  const [apiBaseMessage, setApiBaseMessage] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);

  useEffect(() => {
    return () => {
      if (platformLogoUrl) {
        window.URL.revokeObjectURL(platformLogoUrl);
      }
    };
  }, [platformLogoUrl]);

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
        setBrandingDraft({
          platform_name: data.platform_name || "",
          platform_tagline: data.platform_tagline || "",
          brand_accent: data.brand_accent || "",
          brand_accent_soft: data.brand_accent_soft || "",
          brand_accent_secondary: data.brand_accent_secondary || "",
        });
        setBrandContext({
          name: data.platform_name || "AMO Portal",
          tagline: data.platform_tagline || null,
          accent: data.brand_accent || null,
          accentSoft: data.brand_accent_soft || null,
          accentSecondary: data.brand_accent_secondary || null,
        });
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

  useEffect(() => {
    if (!isSuperuser || !platformSettings?.platform_logo_filename) {
      if (platformLogoUrl) {
        window.URL.revokeObjectURL(platformLogoUrl);
      }
      setPlatformLogoUrl(null);
      return;
    }

    let mounted = true;
    fetchPlatformLogoBlob()
      .then((blob) => {
        if (!mounted) return;
        if (!blob) {
          setPlatformLogoUrl(null);
          return;
        }
        const url = window.URL.createObjectURL(blob);
        if (platformLogoUrl) {
          window.URL.revokeObjectURL(platformLogoUrl);
        }
        setPlatformLogoUrl(url);
      })
      .catch(() => {
        if (mounted) setPlatformLogoUrl(null);
      });

    return () => {
      mounted = false;
    };
  }, [isSuperuser, platformSettings?.platform_logo_filename]);

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

  const handleSaveBranding = async () => {
    setBrandingSaving(true);
    setBrandingMessage(null);
    try {
      const updated = await updatePlatformSettings({
        platform_name: brandingDraft.platform_name || null,
        platform_tagline: brandingDraft.platform_tagline || null,
        brand_accent: brandingDraft.brand_accent || null,
        brand_accent_soft: brandingDraft.brand_accent_soft || null,
        brand_accent_secondary: brandingDraft.brand_accent_secondary || null,
      });
      setPlatformSettings(updated);
      setBrandContext({
        name: updated.platform_name || "AMO Portal",
        tagline: updated.platform_tagline || null,
        accent: updated.brand_accent || null,
        accentSoft: updated.brand_accent_soft || null,
        accentSecondary: updated.brand_accent_secondary || null,
      });
      setBrandingMessage("Branding settings saved.");
    } catch (err: any) {
      setBrandingMessage(err?.message || "Failed to save branding settings.");
    } finally {
      setBrandingSaving(false);
    }
  };

  const handlePlatformLogoUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBrandingMessage(null);
    try {
      const latest = await uploadPlatformLogo(files[0]);
      setPlatformSettings(latest);
    } catch (err: any) {
      setBrandingMessage(err?.message || "Failed to upload platform logo.");
    }
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
      <div className="admin-page admin-usage-settings">
        <PageHeader
          title="Platform settings & diagnostics"
          subtitle="Manage branding, connectivity checks, and operational throttles from one place."
        />

        <div className="admin-summary-strip">
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Active AMO</span>
            <span className="admin-summary-item__value">
              {selectedAmoId ? "Selected" : "Unset"}
            </span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Users loaded</span>
            <span className="admin-summary-item__value">{users.length}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">AMO throttle</span>
            <span className="admin-summary-item__value">{amoThrottle}%</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Branding</span>
            <span className="admin-summary-item__value">
              {platformSettings?.platform_logo_filename ? "Logo set" : "Default"}
            </span>
          </div>
        </div>

        {activeFilter && (
          <div className="admin-filter-banner">
            <span>{activeFilter.replace(/_/g, " ")}</span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() =>
                navigate(`/maintenance/${amoCode}/admin/settings`, { replace: true })
              }
            >
              Clear filter
            </Button>
          </div>
        )}

        {error && (
          <InlineAlert tone="danger" title="Error">
            <span>{error}</span>
          </InlineAlert>
        )}

        <div className="admin-page__grid">
          <div className="admin-page__main">
            <Panel
              title="Per-user throttling"
              subtitle="Apply per-user budgets to keep heavy calendar usage under control."
            >
              {loading && <p className="text-muted">Loading users…</p>}

              {!loading && users.length === 0 && (
                <p className="text-muted">No users found for this AMO.</p>
              )}

              {users.length > 0 && (
                <div className="table-responsive">
                  <Table className="table-compact">
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
                  </Table>
                </div>
              )}
            </Panel>

            {isSuperuser && (
              <Panel
                title="Platform branding"
                subtitle="Update the platform name, tagline, colors, and logo."
              >
                <details className="admin-disclosure" open={!!brandingMessage}>
                  <summary>Brand settings</summary>
                  <div className="admin-disclosure__content">
                    <div className="form-row">
                      <label htmlFor="platformName">Platform name</label>
                      <input
                        id="platformName"
                        type="text"
                        value={brandingDraft.platform_name}
                        onChange={(e) =>
                          setBrandingDraft((prev) => ({
                            ...prev,
                            platform_name: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="form-row">
                      <label htmlFor="platformTagline">Footer tagline</label>
                      <input
                        id="platformTagline"
                        type="text"
                        placeholder="Trusted maintenance management for modern AMOs."
                        value={brandingDraft.platform_tagline}
                        onChange={(e) =>
                          setBrandingDraft((prev) => ({
                            ...prev,
                            platform_tagline: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div
                      className="form-row"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                        gap: 12,
                      }}
                    >
                      <div>
                        <label htmlFor="brandAccent">Brand accent</label>
                        <input
                          id="brandAccent"
                          type="color"
                          value={brandingDraft.brand_accent || "#2563eb"}
                          onChange={(e) =>
                            setBrandingDraft((prev) => ({
                              ...prev,
                              brand_accent: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div>
                        <label htmlFor="brandAccentSecondary">Secondary accent</label>
                        <input
                          id="brandAccentSecondary"
                          type="color"
                          value={brandingDraft.brand_accent_secondary || "#1d4ed8"}
                          onChange={(e) =>
                            setBrandingDraft((prev) => ({
                              ...prev,
                              brand_accent_secondary: e.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                    <div className="form-row">
                      <label htmlFor="brandAccentSoft">Accent soft (rgba)</label>
                      <input
                        id="brandAccentSoft"
                        type="text"
                        placeholder="rgba(37, 99, 235, 0.12)"
                        value={brandingDraft.brand_accent_soft}
                        onChange={(e) =>
                          setBrandingDraft((prev) => ({
                            ...prev,
                            brand_accent_soft: e.target.value,
                          }))
                        }
                      />
                      <p className="text-muted" style={{ margin: 0 }}>
                        Used for subtle highlights and focus rings.
                      </p>
                    </div>
                    <div className="form-row">
                      <label htmlFor="platformLogo">Platform logo (.png, .jpg, .svg)</label>
                      <input
                        id="platformLogo"
                        type="file"
                        accept=".png,.jpg,.jpeg,.svg"
                        onChange={(e) => handlePlatformLogoUpload(e.target.files)}
                      />
                      {platformSettings?.platform_logo_filename && (
                        <p className="text-muted" style={{ margin: 0 }}>
                          Current logo: {platformSettings.platform_logo_filename}
                        </p>
                      )}
                      {platformLogoUrl && (
                        <img
                          src={platformLogoUrl}
                          alt="Platform logo preview"
                          style={{
                            maxWidth: 220,
                            borderRadius: 10,
                            border: "1px solid var(--panel-divider)",
                          }}
                        />
                      )}
                    </div>
                    <div
                      className="form-row"
                      style={{ display: "flex", gap: 12, flexWrap: "wrap" }}
                    >
                      <Button
                        type="button"
                        onClick={handleSaveBranding}
                        disabled={brandingSaving}
                      >
                        {brandingSaving ? "Saving..." : "Save branding"}
                      </Button>
                      {brandingMessage && (
                        <span className="text-muted">{brandingMessage}</span>
                      )}
                    </div>
                  </div>
                </details>
              </Panel>
            )}

            {isSuperuser && (
              <Panel
                title="HTTPS & connectivity diagnostics"
                subtitle="Configure the API base URL and run a health check."
              >
                <details className="admin-disclosure">
                  <summary>Diagnostics</summary>
                  <div className="admin-disclosure__content">
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

                    <div
                      className="form-row"
                      style={{ display: "flex", gap: 12, flexWrap: "wrap" }}
                    >
                      <Button type="button" onClick={handleSaveApiBase}>
                        Save override
                      </Button>
                      <Button type="button" variant="secondary" onClick={handleClearApiBase}>
                        Clear override
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() =>
                          window.open("https://www.speedtest.net/", "_blank", "noopener")
                        }
                      >
                        Run Ookla speed test
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={runHealthCheck}
                        disabled={healthLoading}
                      >
                        {healthLoading ? "Running..." : "Run health check"}
                      </Button>
                    </div>

                    {apiBaseMessage && (
                      <p className="text-muted" style={{ marginTop: 8 }}>
                        {apiBaseMessage}
                      </p>
                    )}

                    {healthStatus && (
                      <InlineAlert tone="info" title="Health check">
                        <span>{healthStatus}</span>
                      </InlineAlert>
                    )}

                    <div className="admin-panel" style={{ marginTop: 16 }}>
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
                </details>
              </Panel>
            )}
          </div>

          <div className="admin-page__side">
            <Panel
              title="AMO scope"
              subtitle="Superusers can throttle any AMO; AMO admins can tune only their own."
            >
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
            </Panel>

            {isSuperuser && (
              <Panel
                title="Setup shortcuts"
                subtitle="Jump directly to AMO setup and provisioning."
              >
                <div className="page-section__actions">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => navigate(`/maintenance/${amoCode}/admin/amos`)}
                  >
                    AMO Management
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => navigate(`/maintenance/${amoCode}/admin/users`)}
                  >
                    User Management
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => navigate(`/maintenance/${amoCode}/admin/amo-assets`)}
                  >
                    AMO Assets & Templates
                  </Button>
                </div>
              </Panel>
            )}
          </div>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminUsageSettingsPage;

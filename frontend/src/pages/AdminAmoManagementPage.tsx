// src/pages/AdminAmoManagementPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Badge, Button, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  createAdminAmo,
  deactivateAdminAmo,
  extendAmoTrial,
  listAdminAmos,
  setAdminContext,
  setActiveAmoId as storeActiveAmoId,
  updateAdminAmo,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import {
  disableTenantModule,
  enableTenantModule,
  listTenantModules,
  type ModuleSubscriptionRead,
} from "../services/adminModules";
import {
  fetchCatalog,
  fetchSubscriptionStatus,
  startTrial,
} from "../services/billing";
import type { AdminAmoRead } from "../services/adminUsers";
import type { CatalogSKU, Subscription } from "../types/billing";

type UrlParams = {
  amoCode?: string;
};

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

type AmoProfileState = {
  name: string;
  icaoCode: string;
  country: string;
  contactEmail: string;
  contactPhone: string;
  timeZone: string;
  isDemo: boolean;
  isActive: boolean;
};

const RESERVED_LOGIN_SLUGS = new Set(["system", "root"]);

const AdminAmoManagementPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);

  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const v = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return v && v.trim() ? v.trim() : null;
  });

  const [amoCreateError, setAmoCreateError] = useState<string | null>(null);
  const [amoCreateSuccess, setAmoCreateSuccess] = useState<string | null>(null);
  const [amoActionError, setAmoActionError] = useState<string | null>(null);
  const [amoActionSuccess, setAmoActionSuccess] = useState<string | null>(null);
  const [amoProfileSaving, setAmoProfileSaving] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);
  const [trialSuccess, setTrialSuccess] = useState<string | null>(null);
  const [trialCatalog, setTrialCatalog] = useState<CatalogSKU[]>([]);
  const [trialSubscription, setTrialSubscription] = useState<Subscription | null>(null);
  const [trialSkuCode, setTrialSkuCode] = useState<string>("");
  const [lastCreatedAmoId, setLastCreatedAmoId] = useState<string | null>(null);
  const [moduleSubscriptions, setModuleSubscriptions] = useState<
    Record<string, ModuleSubscriptionRead>
  >({});
  const [modulesLoading, setModulesLoading] = useState(false);
  const [modulesError, setModulesError] = useState<string | null>(null);
  const [moduleActionState, setModuleActionState] = useState<Record<string, boolean>>({});
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
  const [amoProfile, setAmoProfile] = useState<AmoProfileState>({
    name: "",
    icaoCode: "",
    country: "",
    contactEmail: "",
    contactPhone: "",
    timeZone: "",
    isDemo: false,
    isActive: true,
  });

  useEffect(() => {
    if (!currentUser) return;
    if (isSuperuser) return;

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [currentUser, isSuperuser, amoCode, navigate]);

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
            storeActiveAmoId(fallback);
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
  }, [isSuperuser, currentUser?.amo_id]);

  const selectedAmo = useMemo(
    () => amos.find((a) => a.id === activeAmoId) || null,
    [amos, activeAmoId]
  );

  const moduleOptions = useMemo(
    () => [
      { code: "quality", label: "Quality Management System" },
      { code: "training", label: "Training & Competence" },
      { code: "work", label: "Work Orders" },
      { code: "fleet", label: "Fleet & Aircraft" },
      { code: "maintenance_program", label: "Maintenance Program" },
      { code: "reliability", label: "Reliability" },
      { code: "finance_inventory", label: "Finance & Inventory" },
    ],
    []
  );
  const inactiveAmos = useMemo(
    () => amos.filter((amo) => !amo.is_active).length,
    [amos]
  );

  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);

  const filteredAmos = useMemo(() => {
    if (activeFilter !== "inactive") return amos;
    return amos.filter((amo) => !amo.is_active);
  }, [activeFilter, amos]);

  const syncAdminContext = async (amoId: string) => {
    if (!isSuperuser) return;
    try {
      await setAdminContext({ active_amo_id: amoId });
    } catch (err: any) {
      console.error("Failed to set admin context", err);
      setAmoActionError(
        err?.response?.data?.detail ||
          err?.message ||
          "Failed to update the active AMO context."
      );
    }
  };

  useEffect(() => {
    if (!isSuperuser) return;
    if (!activeAmoId) return;
    syncAdminContext(activeAmoId);
  }, [activeAmoId, isSuperuser]);

  if (currentUser && !isSuperuser) {
    return null;
  }

  const handleAmoChange = async (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoId(v);
    storeActiveAmoId(v);
    await syncAdminContext(v);
  };

  const clearFilter = () => {
    if (!amoCode) return;
    navigate(`/maintenance/${amoCode}/admin/amos`, { replace: true });
  };

  const handleAmoFormChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ): void => {
    const { name, value } = e.target;
    const key = name as keyof AmoFormState;
    setAmoForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleProfileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ): void => {
    const { name, value, type, checked } = e.target;
    setAmoProfile((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const loadTrialData = async (amo: AdminAmoRead | null) => {
    if (!amo) {
      setTrialCatalog([]);
      setTrialSubscription(null);
      setTrialSkuCode("");
      return;
    }
    setTrialLoading(true);
    setTrialError(null);
    setTrialSuccess(null);
    try {
      await syncAdminContext(amo.id);
      const [catalog, subscriptionResult] = await Promise.all([
        fetchCatalog(),
        fetchSubscriptionStatus(),
      ]);
      const activeSkus = catalog.filter((sku) => sku.is_active);
      setTrialCatalog(activeSkus);
      setTrialSubscription(subscriptionResult.subscription);
      if (activeSkus.length > 0) {
        const existing =
          !!trialSkuCode && activeSkus.some((sku) => sku.code === trialSkuCode);
        setTrialSkuCode(existing ? trialSkuCode : activeSkus[0].code);
      } else {
        setTrialSkuCode("");
      }
    } catch (err: any) {
      setTrialError(err?.message || "Unable to load subscription status.");
    } finally {
      setTrialLoading(false);
    }
  };

  const loadModuleSubscriptions = async (amo: AdminAmoRead | null) => {
    if (!amo) {
      setModuleSubscriptions({});
      return;
    }
    setModulesLoading(true);
    setModulesError(null);
    try {
      await syncAdminContext(amo.id);
      const data = await listTenantModules(amo.id);
      const next = data.reduce<Record<string, ModuleSubscriptionRead>>((acc, item) => {
        acc[item.module_code] = item;
        return acc;
      }, {});
      setModuleSubscriptions(next);
    } catch (err: any) {
      console.error("Failed to load module subscriptions", err);
      setModulesError(
        err?.response?.data?.detail || err?.message || "Unable to load module subscriptions."
      );
    } finally {
      setModulesLoading(false);
    }
  };

  useEffect(() => {
    loadTrialData(selectedAmo);
    loadModuleSubscriptions(selectedAmo);
  }, [selectedAmo?.id]);

  const handleStartTrial = async () => {
    if (!selectedAmo) return;
    if (!trialSkuCode) {
      setTrialError("Select a plan to start a trial.");
      return;
    }
    const confirmation = window.prompt(
      `Type START TRIAL ${selectedAmo.amo_code} to confirm trial activation.`
    );
    if (confirmation === null) return;
    const expected = `START TRIAL ${selectedAmo.amo_code}`.trim();
    if (confirmation.trim() !== expected) {
      setTrialError("Confirmation phrase did not match. Trial not started.");
      return;
    }
    setTrialLoading(true);
    setTrialError(null);
    setTrialSuccess(null);
    try {
      await syncAdminContext(selectedAmo.id);
      const subscription = await startTrial(trialSkuCode);
      setTrialSubscription(subscription);
      setTrialSuccess(`Trial started for ${selectedAmo.amo_code}.`);
    } catch (err: any) {
      setTrialError(err?.message || "Failed to start trial.");
    } finally {
      setTrialLoading(false);
    }
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
      storeActiveAmoId(created.id);
      await syncAdminContext(created.id);

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

  const handleModuleToggle = async (moduleCode: string, nextEnabled: boolean) => {
    if (!selectedAmo) return;
    setModulesError(null);
    setModuleActionState((prev) => ({ ...prev, [moduleCode]: true }));
    try {
      await syncAdminContext(selectedAmo.id);
      const updated = nextEnabled
        ? await enableTenantModule(selectedAmo.id, moduleCode, {
            status: "ENABLED",
          })
        : await disableTenantModule(selectedAmo.id, moduleCode);
      setModuleSubscriptions((prev) => ({ ...prev, [moduleCode]: updated }));
    } catch (err: any) {
      console.error("Failed to update module subscription", err);
      setModulesError(
        err?.response?.data?.detail || err?.message || "Unable to update module access."
      );
    } finally {
      setModuleActionState((prev) => ({ ...prev, [moduleCode]: false }));
    }
  };

  const handleOpenAmoDashboard = () => {
    if (!selectedAmo?.login_slug) return;
    navigate(`/maintenance/${selectedAmo.login_slug}`, { replace: false });
  };

  const refreshAmos = async () => {
    setAmoActionError(null);
    setAmoActionSuccess(null);
    setAmoLoading(true);
    try {
      const data = await listAdminAmos();
      setAmos(data);
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to refresh AMOs.");
    } finally {
      setAmoLoading(false);
    }
  };

  const handleDeactivateAmo = async (amo: AdminAmoRead) => {
    const ok = window.confirm(
      `Deactivate AMO ${amo.amo_code}? Users will lose access until reactivated.`
    );
    if (!ok) return;
    try {
      await deactivateAdminAmo(amo.id);
      setAmoActionSuccess(`Deactivated AMO ${amo.amo_code}.`);
      await refreshAmos();
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to deactivate AMO.");
    }
  };

  const handleExtendTrial = async (amo: AdminAmoRead) => {
    const raw = window.prompt(
      `Extend trial for ${amo.amo_code} by how many days?`,
      "30"
    );
    if (raw === null) return;
    const days = Number(raw);
    if (!Number.isFinite(days) || days <= 0) {
      setAmoActionError("Enter a valid number of days.");
      return;
    }
    try {
      await extendAmoTrial(amo.id, { extend_days: Math.round(days) });
      setAmoActionSuccess(`Extended trial for ${amo.amo_code} by ${days} days.`);
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to extend trial.");
    }
  };

  const handleOpenAmoProfile = (amo: AdminAmoRead) => {
    handleAmoChange(amo.id);
    navigate(`/maintenance/${amoCode}/admin/amo-profile`);
  };

  const handleReactivateAmo = async (amo: AdminAmoRead) => {
    const ok = window.confirm(`Reactivate AMO ${amo.amo_code}?`);
    if (!ok) return;
    try {
      await updateAdminAmo(amo.id, { is_active: true });
      setAmoActionSuccess(`Reactivated AMO ${amo.amo_code}.`);
      await refreshAmos();
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to reactivate AMO.");
    }
  };

  const handleOpenBilling = async () => {
    if (!selectedAmo?.login_slug) return;
    await syncAdminContext(selectedAmo.id);
    navigate(`/maintenance/${selectedAmo.login_slug}/admin/billing`);
  };

  if (!isSuperuser) {
    return (
      <DepartmentLayout
        amoCode={amoCode ?? "UNKNOWN"}
        activeDepartment="admin-amos"
      >
        <div className="admin-page">
          <PageHeader title="AMO Management" />
          <Panel>
            <p className="admin-muted">You do not have permission to manage AMOs.</p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/maintenance/${amoCode}/admin/overview`)}
            >
              Back to overview
            </Button>
          </Panel>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-amos"
    >
      <div className="admin-page admin-amo-management">
        <PageHeader
          title="AMO Management"
          subtitle="Set the AMO context and resolve account-level access."
          actions={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                const target = document.getElementById("create-amo");
                target?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              New AMO
            </Button>
          }
        />

        <div className="admin-summary-strip">
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Total AMOs</span>
            <span className="admin-summary-item__value">{amos.length}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Inactive AMOs</span>
            <span className="admin-summary-item__value">{inactiveAmos}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Active context</span>
            <span className="admin-summary-item__value">
              {selectedAmo?.amo_code || "Unset"}
            </span>
          </div>
        </div>

        <div className="admin-page__grid">
          <Panel
            title="AMO directory"
            subtitle="Review AMOs that require attention, then take the next action."
          >
            {!amoLoading && !amoError && activeFilter === "inactive" && (
              <div className="admin-filter-banner">
                <span>Filtered: Inactive AMOs</span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={clearFilter}
                >
                  Clear filter
                </Button>
              </div>
            )}

            {amoLoading && <p>Loading AMOs…</p>}
            {amoError && (
              <InlineAlert tone="danger" title="Error">
                <span>{amoError}</span>
              </InlineAlert>
            )}

            {!amoLoading && !amoError && (
              <Table>
                <thead>
                  <tr>
                    <th>AMO</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAmos.length === 0 && (
                    <tr>
                      <td colSpan={3}>No AMOs available.</td>
                    </tr>
                  )}
                  {filteredAmos.map((amo) => (
                    <tr key={amo.id}>
                      <td>
                        <strong>{amo.amo_code}</strong> — {amo.name}
                      </td>
                      <td>
                        <Badge tone={amo.is_active ? "success" : "warning"} size="sm">
                          {amo.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td>
                        <div className="admin-row-actions">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => handleOpenAmoProfile(amo)}
                          >
                            Profile
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => handleExtendTrial(amo)}
                          >
                            Extend trial
                          </Button>
                          {amo.is_active ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => handleDeactivateAmo(amo)}
                            >
                              Deactivate
                            </Button>
                          ) : (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => handleReactivateAmo(amo)}
                            >
                              Reactivate
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>

          <div className="admin-page__side">
            <Panel
              title="Active AMO context"
              subtitle="Use this AMO to open dashboards and manage assets."
            >
              {amoLoading && <p>Loading AMOs…</p>}
              {amoError && (
                <InlineAlert tone="danger" title="Error">
                  <span>{amoError}</span>
                </InlineAlert>
              )}

              {!amoLoading && !amoError && (
                <div className="form-row">
                  <label htmlFor="amoSelect">Active AMO</label>
                  <select
                    id="amoSelect"
                    value={activeAmoId ?? ""}
                    onChange={(e) => handleAmoChange(e.target.value)}
                    disabled={amos.length === 0}
                  >
                    {amos.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.amo_code} — {a.name}
                      </option>
                    ))}
                  </select>

                  {selectedAmo && (
                    <p style={{ marginTop: 8, marginBottom: 0, opacity: 0.85 }}>
                      Active AMO:{" "}
                      <strong>
                        {selectedAmo.amo_code} — {selectedAmo.name}
                      </strong>
                    </p>
                  )}
                </div>
              )}

              {amoActionError && (
                <InlineAlert tone="danger" title="Action failed">
                  <span>{amoActionError}</span>
                </InlineAlert>
              )}
              {amoActionSuccess && (
                <InlineAlert tone="success" title="Success">
                  <span>{amoActionSuccess}</span>
                </InlineAlert>
              )}

              <div className="form-actions">
                <Button
                  type="button"
                  onClick={handleOpenAmoDashboard}
                  disabled={!selectedAmo?.login_slug}
                >
                  Open AMO dashboard
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleOpenBilling}
                  disabled={!selectedAmo?.login_slug}
                >
                  Manage subscription
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}
                >
                  Create first user
                </Button>
              </div>
            </Panel>

            <Panel
              title="Module access"
              subtitle="Toggle paid modules for the active AMO."
            >
              {!selectedAmo && (
                <p className="admin-muted">Select an AMO to manage module access.</p>
              )}
              {selectedAmo && (
                <>
                  {modulesError && (
                    <InlineAlert tone="danger" title="Error">
                      <span>{modulesError}</span>
                    </InlineAlert>
                  )}
                  {modulesLoading ? (
                    <p>Loading modules…</p>
                  ) : (
                    <Table>
                      <thead>
                        <tr>
                          <th>Module</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {moduleOptions.map((module) => {
                          const subscription = moduleSubscriptions[module.code];
                          const status = subscription?.status || "DISABLED";
                          const isEnabled =
                            status === "ENABLED" || status === "TRIAL";
                          const tone =
                            status === "ENABLED" || status === "TRIAL"
                              ? "success"
                              : status === "SUSPENDED"
                                ? "danger"
                                : "warning";
                          return (
                            <tr key={module.code}>
                              <td>{module.label}</td>
                              <td>
                                <Badge tone={tone} size="sm">
                                  {status}
                                </Badge>
                              </td>
                              <td>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={isEnabled ? "ghost" : "primary"}
                                  onClick={() =>
                                    handleModuleToggle(module.code, !isEnabled)
                                  }
                                  disabled={!!moduleActionState[module.code]}
                                >
                                  {moduleActionState[module.code]
                                    ? "Updating…"
                                    : isEnabled
                                      ? "Disable"
                                      : "Enable"}
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  )}
                </>
              )}
            </Panel>

            <Panel
              title="AMO profile"
              subtitle="Open the dedicated profile page to manage tenant details and trials."
            >
              {!selectedAmo && (
                <p className="admin-muted">Select an AMO to manage its profile.</p>
              )}
              {selectedAmo && (
                <Button
                  type="button"
                  onClick={() => handleOpenAmoProfile(selectedAmo)}
                >
                  Open profile page
                </Button>
              )}
            </Panel>

            <Panel
              title="Create AMO"
              subtitle="Register a new AMO when onboarding a new operator."
            >
              <details className="admin-disclosure" id="create-amo" open={!!amoCreateError}>
                <summary>New AMO form</summary>
                <div className="admin-disclosure__content">
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
                      <p className="form-hint">
                        Short code used internally and on reports.
                      </p>
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
                        Used in the login URL:{" "}
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
                        onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}
                        disabled={!lastCreatedAmoId}
                      >
                        Create first user
                      </Button>
                    </div>
                  </form>
                </div>
              </details>
            </Panel>
          </div>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminAmoManagementPage;

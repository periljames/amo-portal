import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  listAdminAmos,
  setAdminContext,
  setActiveAmoId as storeActiveAmoId,
  updateAdminAmo,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import {
  fetchCatalog,
  fetchBillingAuditLogs,
  fetchSubscriptionStatus,
  startTrial,
} from "../services/billing";
import type { AdminAmoRead } from "../services/adminUsers";
import type { BillingAuditLog, CatalogSKU, Subscription } from "../types/billing";

type UrlParams = {
  amoCode?: string;
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

const AdminAmoProfilePage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);

  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const v = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return v && v.trim() ? v.trim() : null;
  });

  const [amoActionError, setAmoActionError] = useState<string | null>(null);
  const [amoActionSuccess, setAmoActionSuccess] = useState<string | null>(null);
  const [amoProfileSaving, setAmoProfileSaving] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);
  const [trialSuccess, setTrialSuccess] = useState<string | null>(null);
  const [trialCatalog, setTrialCatalog] = useState<CatalogSKU[]>([]);
  const [trialSubscription, setTrialSubscription] = useState<Subscription | null>(null);
  const [trialSkuCode, setTrialSkuCode] = useState<string>("");
  const [trialAuditLogs, setTrialAuditLogs] = useState<BillingAuditLog[]>([]);

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

  const selectedAmo = useMemo(
    () => amos.find((a) => a.id === activeAmoId) || null,
    [amos, activeAmoId]
  );

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
    if (!selectedAmo) {
      setAmoProfile({
        name: "",
        icaoCode: "",
        country: "",
        contactEmail: "",
        contactPhone: "",
        timeZone: "",
        isDemo: false,
        isActive: true,
      });
      return;
    }
    setAmoProfile({
      name: selectedAmo.name || "",
      icaoCode: selectedAmo.icao_code || "",
      country: selectedAmo.country || "",
      contactEmail: selectedAmo.contact_email || "",
      contactPhone: selectedAmo.contact_phone || "",
      timeZone: selectedAmo.time_zone || "",
      isDemo: !!selectedAmo.is_demo,
      isActive: !!selectedAmo.is_active,
    });
  }, [selectedAmo]);

  useEffect(() => {
    if (!isSuperuser) return;
    if (!activeAmoId) return;
    syncAdminContext(activeAmoId);
  }, [activeAmoId, isSuperuser]);

  useEffect(() => {
    const loadTrialData = async () => {
      if (!selectedAmo) {
        setTrialCatalog([]);
        setTrialSubscription(null);
        setTrialSkuCode("");
        return;
      }
      setTrialLoading(true);
      setTrialError(null);
      setTrialSuccess(null);
      try {
        await syncAdminContext(selectedAmo.id);
        const [catalog, subscriptionResult] = await Promise.all([
          fetchCatalog(true),
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

    loadTrialData();
  }, [selectedAmo]);

  useEffect(() => {
    const loadAudit = async () => {
      if (!selectedAmo) {
        setTrialAuditLogs([]);
        return;
      }
      try {
        await syncAdminContext(selectedAmo.id);
        const logs = await fetchBillingAuditLogs({
          amo_id: selectedAmo.id,
          event_type: "TRIAL_STARTED",
          limit: 10,
        });
        setTrialAuditLogs(logs);
      } catch (err: any) {
        console.error("Failed to load trial audit logs", err);
      }
    };
    loadAudit();
  }, [selectedAmo]);

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

  const handleProfileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ): void => {
    const { name, value, type, checked } = e.target;
    setAmoProfile((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAmo) {
      setAmoActionError("Select an AMO to edit.");
      return;
    }
    setAmoProfileSaving(true);
    setAmoActionError(null);
    setAmoActionSuccess(null);
    try {
      await updateAdminAmo(selectedAmo.id, {
        name: amoProfile.name.trim() || null,
        icao_code: amoProfile.icaoCode.trim() || null,
        country: amoProfile.country.trim() || null,
        contact_email: amoProfile.contactEmail.trim() || null,
        contact_phone: amoProfile.contactPhone.trim() || null,
        time_zone: amoProfile.timeZone.trim() || null,
        is_demo: amoProfile.isDemo,
        is_active: amoProfile.isActive,
      });
      setAmoActionSuccess(`Updated AMO ${selectedAmo.amo_code}.`);
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to update AMO profile.");
    } finally {
      setAmoProfileSaving(false);
    }
  };

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

  const handleRefreshTrial = async () => {
    if (!selectedAmo) return;
    setTrialLoading(true);
    setTrialError(null);
    try {
      await syncAdminContext(selectedAmo.id);
      const subscriptionResult = await fetchSubscriptionStatus();
      setTrialSubscription(subscriptionResult.subscription);
    } catch (err: any) {
      setTrialError(err?.message || "Unable to refresh subscription status.");
    } finally {
      setTrialLoading(false);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-amos">
      <div className="admin-page">
        <PageHeader
          title="AMO Profile"
          subtitle="Manage tenant profile, status, and trial activation."
          actions={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/maintenance/${amoCode}/admin/amos`)}
            >
              Back to AMO list
            </Button>
          }
        />

        <div className="admin-page__grid">
          <Panel
            title="Select AMO"
            subtitle="Choose which tenant you want to manage."
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
              </div>
            )}
          </Panel>

          <Panel
            title="AMO profile"
            subtitle="Update profile details, activation, and demo state."
          >
            {!selectedAmo && (
              <p className="admin-muted">Select an AMO to view its profile.</p>
            )}
            {selectedAmo && (
              <>
                <form className="form-grid" onSubmit={handleProfileSubmit}>
                  <div className="form-row">
                    <label>AMO code</label>
                    <input type="text" value={selectedAmo.amo_code} disabled />
                  </div>
                  <div className="form-row">
                    <label>Login slug</label>
                    <input type="text" value={selectedAmo.login_slug} disabled />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileName">AMO Name</label>
                    <input
                      id="profileName"
                      name="name"
                      type="text"
                      value={amoProfile.name}
                      onChange={handleProfileChange}
                      required
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileIcao">ICAO Code</label>
                    <input
                      id="profileIcao"
                      name="icaoCode"
                      type="text"
                      value={amoProfile.icaoCode}
                      onChange={handleProfileChange}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileCountry">Country</label>
                    <input
                      id="profileCountry"
                      name="country"
                      type="text"
                      value={amoProfile.country}
                      onChange={handleProfileChange}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileEmail">Contact Email</label>
                    <input
                      id="profileEmail"
                      name="contactEmail"
                      type="email"
                      value={amoProfile.contactEmail}
                      onChange={handleProfileChange}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profilePhone">Contact Phone</label>
                    <input
                      id="profilePhone"
                      name="contactPhone"
                      type="tel"
                      value={amoProfile.contactPhone}
                      onChange={handleProfileChange}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileTimeZone">Time Zone</label>
                    <input
                      id="profileTimeZone"
                      name="timeZone"
                      type="text"
                      value={amoProfile.timeZone}
                      onChange={handleProfileChange}
                      placeholder="Africa/Nairobi"
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileDemo">
                      <input
                        id="profileDemo"
                        name="isDemo"
                        type="checkbox"
                        checked={amoProfile.isDemo}
                        onChange={handleProfileChange}
                      />
                      <span style={{ marginLeft: 8 }}>Demo tenant</span>
                    </label>
                  </div>
                  <div className="form-row">
                    <label htmlFor="profileActive">
                      <input
                        id="profileActive"
                        name="isActive"
                        type="checkbox"
                        checked={amoProfile.isActive}
                        onChange={handleProfileChange}
                      />
                      <span style={{ marginLeft: 8 }}>Active tenant</span>
                    </label>
                  </div>
                  <div className="form-actions">
                    <Button type="submit" disabled={amoProfileSaving}>
                      {amoProfileSaving ? "Saving..." : "Save profile"}
                    </Button>
                  </div>
                </form>

                {amoActionError && (
                  <InlineAlert tone="danger" title="Update failed">
                    <span>{amoActionError}</span>
                  </InlineAlert>
                )}
                {amoActionSuccess && (
                  <InlineAlert tone="success" title="Profile updated">
                    <span>{amoActionSuccess}</span>
                  </InlineAlert>
                )}

                <div className="form-grid" style={{ marginTop: 16 }}>
                  <div className="form-row">
                    <label>Subscription status</label>
                    <input
                      type="text"
                      value={
                        trialSubscription
                          ? `${trialSubscription.status} · ${trialSubscription.term}`
                          : "No active subscription"
                      }
                      disabled
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="trialSku">Trial plan</label>
                    <select
                      id="trialSku"
                      value={trialSkuCode}
                      onChange={(e) => setTrialSkuCode(e.target.value)}
                      disabled={trialLoading || trialCatalog.length === 0}
                    >
                      {trialCatalog.length === 0 && (
                        <option value="">No active plans</option>
                      )}
                      {trialCatalog.map((sku) => (
                        <option key={sku.id} value={sku.code}>
                          {sku.name} · {sku.term} · {sku.trial_days}d trial
                        </option>
                      ))}
                    </select>
                  </div>
                  {trialError && (
                    <InlineAlert tone="danger" title="Trial activation failed">
                      <span>{trialError}</span>
                    </InlineAlert>
                  )}
                  {trialSuccess && (
                    <InlineAlert tone="success" title="Trial activated">
                      <span>{trialSuccess}</span>
                    </InlineAlert>
                  )}
                  <div className="form-actions">
                    <Button
                      type="button"
                      onClick={handleStartTrial}
                      disabled={
                        trialLoading ||
                        !trialSkuCode ||
                        trialSubscription?.status === "ACTIVE" ||
                        trialSubscription?.status === "TRIALING"
                      }
                    >
                      {trialLoading ? "Starting..." : "Start trial"}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleRefreshTrial}
                      disabled={trialLoading}
                    >
                      Refresh status
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() =>
                        navigate(
                          `/maintenance/${selectedAmo.login_slug}/admin/billing`
                        )
                      }
                      disabled={!selectedAmo?.login_slug}
                    >
                      Open billing
                    </Button>
                  </div>
                </div>
              </>
            )}
          </Panel>

          <Panel title="Trial audit log">
            {trialAuditLogs.length === 0 && (
              <p className="text-muted">No trial activations logged yet.</p>
            )}
            {trialAuditLogs.length > 0 && (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {trialAuditLogs.map((log) => (
                  <li key={log.id}>
                    <strong>{log.event_type}</strong>{" "}
                    <span className="text-muted">{log.created_at}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminAmoProfilePage;

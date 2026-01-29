// src/pages/AdminAmoManagementPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  createAdminAmo,
  deactivateAdminAmo,
  extendAmoTrial,
  listAdminAmos,
  updateAdminAmo,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import type { AdminAmoRead } from "../services/adminUsers";

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
  const [lastCreatedAmoId, setLastCreatedAmoId] = useState<string | null>(null);
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
  }, [isSuperuser, currentUser?.amo_id]);

  const selectedAmo = useMemo(
    () => amos.find((a) => a.id === activeAmoId) || null,
    [amos, activeAmoId]
  );

  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);

  const filteredAmos = useMemo(() => {
    if (activeFilter !== "inactive") return amos;
    return amos.filter((amo) => !amo.is_active);
  }, [activeFilter, amos]);

  if (currentUser && !isSuperuser) {
    return null;
  }

  const handleAmoChange = (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoId(v);
    localStorage.setItem(LS_ACTIVE_AMO_ID, v);
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

  const handleEditAmo = async (amo: AdminAmoRead) => {
    const name = window.prompt("Update AMO name:", amo.name || "");
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setAmoActionError("AMO name cannot be empty.");
      return;
    }
    try {
      await updateAdminAmo(amo.id, { name: trimmed });
      setAmoActionSuccess(`Updated AMO ${amo.amo_code}.`);
      await refreshAmos();
    } catch (err: any) {
      setAmoActionError(err?.message || "Failed to update AMO.");
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
      <div className="admin-page">
        <PageHeader
          title="AMO Management"
          subtitle="Set the active AMO context or register a new AMO."
        />

        <Panel
          title="Active AMO Context"
          subtitle="Choose an AMO to manage users, assets, and navigate into the AMO dashboard."
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
              onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}
            >
              Create first user
            </Button>
          </div>
        </Panel>

        <Panel
          title="AMO Actions"
          subtitle="Edit AMO details, extend trial windows, or deactivate access."
        >
          {!amoLoading && !amoError && (
            <div className="table-wrapper">
              {activeFilter === "inactive" && (
                <InlineAlert
                  tone="warning"
                  title="Filter applied"
                  actions={(
                    <Button type="button" size="sm" variant="secondary" onClick={clearFilter}>
                      Clear filter
                    </Button>
                  )}
                >
                  <span>Inactive AMOs</span>
                </InlineAlert>
              )}
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
                      <td>{amo.is_active ? "Active" : "Inactive"}</td>
                      <td>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => handleEditAmo(amo)}
                          >
                            ✏️ Edit
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => handleExtendTrial(amo)}
                          >
                            ⏳ Extend trial
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => handleDeactivateAmo(amo)}
                          >
                            🗑️ Deactivate
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </Panel>

        <Panel
          title="Create a new AMO"
          subtitle="Register a new AMO, then create its first admin user."
        >
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
        </Panel>
      </div>
    </DepartmentLayout>
  );
};

export default AdminAmoManagementPage;

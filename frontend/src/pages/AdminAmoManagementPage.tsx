// src/pages/AdminAmoManagementPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import {
  createAdminAmo,
  listAdminAmos,
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

const AdminAmoManagementPage: React.FC = () => {
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

  const [amoCreateError, setAmoCreateError] = useState<string | null>(null);
  const [amoCreateSuccess, setAmoCreateSuccess] = useState<string | null>(null);
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

  if (currentUser && !isSuperuser) {
    return null;
  }

  const handleAmoChange = (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoId(v);
    localStorage.setItem(LS_ACTIVE_AMO_ID, v);
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

    if (!amoForm.amoCode.trim() || !amoForm.name.trim() || !amoForm.loginSlug.trim()) {
      setAmoCreateError("AMO code, name, and login slug are required.");
      return;
    }

    try {
      const created = await createAdminAmo({
        amo_code: amoForm.amoCode.trim().toUpperCase(),
        name: amoForm.name.trim(),
        login_slug: amoForm.loginSlug.trim().toLowerCase(),
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

  if (currentUser && !canAccessAdmin) {
    return null;
  }

  if (!isSuperuser) {
    return (
      <DepartmentLayout
        amoCode={amoCode ?? "UNKNOWN"}
        activeDepartment="admin-amos"
      >
        <header className="page-header">
          <h1 className="page-header__title">AMO Management</h1>
        </header>
        <div className="card card--form">
          <p>You do not have permission to manage AMOs.</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(`/maintenance/${amoCode}/admin/overview`)}
          >
            Back to overview
          </button>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-amos"
    >
      <header className="page-header">
        <h1 className="page-header__title">AMO Management</h1>
        <p className="page-header__subtitle">
          Create AMOs, set active context, and jump into AMO dashboards.
        </p>
      </header>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 8 }}>Active AMO Context</h3>
          <p style={{ marginTop: 0, opacity: 0.85 }}>
            Choose an AMO to manage users, assets, and navigate into the AMO
            dashboard.
          </p>

          {amoLoading && <p>Loading AMOs…</p>}
          {amoError && <div className="alert alert-error">{amoError}</div>}

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

          <div className="form-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleOpenAmoDashboard}
              disabled={!selectedAmo?.login_slug}
            >
              Open AMO dashboard
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}
            >
              Create first user
            </button>
          </div>
        </div>
      </section>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Create a new AMO</h3>
          <p style={{ marginTop: 0, opacity: 0.85 }}>
            Register a new AMO and then create its first user.
          </p>

          {amoCreateError && (
            <div className="alert alert-error">{amoCreateError}</div>
          )}
          {amoCreateSuccess && (
            <div className="alert alert-success">{amoCreateSuccess}</div>
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
              <button type="submit" className="btn btn-primary">
                Create AMO
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}
                disabled={!lastCreatedAmoId}
              >
                Create first user
              </button>
            </div>
          </form>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminAmoManagementPage;

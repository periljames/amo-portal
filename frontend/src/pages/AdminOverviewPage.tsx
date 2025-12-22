// src/pages/AdminOverviewPage.tsx
import React, { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";

type UrlParams = {
  amoCode?: string;
};

const AdminOverviewPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccessAdmin = isSuperuser || isAmoAdmin;

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

  if (currentUser && !canAccessAdmin) {
    return null;
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-overview"
    >
      <header className="page-header">
        <h1 className="page-header__title">System Admin Overview</h1>
        <p className="page-header__subtitle">
          A clean workspace to monitor, support, and control AMOs across the
          platform.
        </p>
      </header>

      <section className="page-section page-layout">
        <div className="page-section__grid">
          <div className="card card--info">
            <div className="card-header">
              <strong>AMO Management</strong>
            </div>
            <p className="page-section__body">
              Register new AMOs, set active AMO context, and jump into an AMO
              dashboard.
            </p>
            <div className="page-section__actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/amos`)}
              >
                Manage AMOs
              </button>
            </div>
          </div>

          <div className="card card--success">
            <div className="card-header">
              <strong>User Management</strong>
            </div>
            <p className="page-section__body">
              Create the first user for a new AMO, manage roles, and keep access
              in sync.
            </p>
            <div className="page-section__actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/users`)}
              >
                Manage Users
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() =>
                  navigate(`/maintenance/${amoCode}/admin/users/new`)
                }
              >
                Create User
              </button>
            </div>
          </div>

          <div className="card card--warning">
            <div className="card-header">
              <strong>AMO Assets</strong>
            </div>
            <p className="page-section__body">
              Manage logos, CRS templates, and AMO-specific assets for
              documentation.
            </p>
            <div className="page-section__actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() =>
                  navigate(`/maintenance/${amoCode}/admin/amo-assets`)
                }
              >
                Manage Assets
              </button>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <strong>Billing & Usage</strong>
            </div>
            <p className="page-section__body">
              Track usage, subscriptions, and billing activity across all AMOs.
            </p>
            <div className="page-section__actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() =>
                  navigate(`/maintenance/${amoCode}/admin/billing`)
                }
              >
                View Billing
              </button>
            </div>
          </div>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminOverviewPage;

// src/pages/AdminBillingPage.tsx
import React, { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";

type UrlParams = {
  amoCode?: string;
};

const AdminBillingPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;

  useEffect(() => {
    if (!currentUser) return;
    if (isSuperuser) return;

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [currentUser, isSuperuser, amoCode, navigate]);

  if (currentUser && !isSuperuser) {
    return null;
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-billing"
    >
      <header className="page-header">
        <h1 className="page-header__title">Billing & Usage</h1>
        <p className="page-header__subtitle">
          Track usage, plan allocation, and invoicing across AMOs.
        </p>
      </header>

      <section className="page-section page-layout">
        <div className="card card--form">
          <h3 style={{ marginTop: 0 }}>Billing controls</h3>
          <p className="page-section__body">
            Billing metrics and plan management will appear here. Configure your
            billing integrations to unlock usage reporting and invoicing.
          </p>
          <ul>
            <li>Usage per AMO (active users, assets, training sessions)</li>
            <li>Plan tiers and entitlement limits</li>
            <li>Invoices, credits, and payment status</li>
          </ul>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminBillingPage;

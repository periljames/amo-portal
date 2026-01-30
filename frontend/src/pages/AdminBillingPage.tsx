// src/pages/AdminBillingPage.tsx
import React, { useEffect, useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";

type UrlParams = {
  amoCode?: string;
};

const AdminBillingPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();

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

  const activeFilter = new URLSearchParams(location.search).get("filter");

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-billing"
    >
      <div className="admin-page admin-billing">
        <PageHeader
          title="Billing & Usage"
          subtitle="Track usage, plan allocation, and invoicing across AMOs."
        />

        <div className="admin-summary-strip">
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Active AMOs</span>
            <span className="admin-summary-item__value">—</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Active users</span>
            <span className="admin-summary-item__value">—</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Plan status</span>
            <span className="admin-summary-item__value">Configured</span>
          </div>
        </div>

        <div className="admin-page__grid">
          <Panel
            title="Billing controls"
            subtitle="Usage metrics and plan management live here."
          >
            {activeFilter && (
              <div className="admin-filter-banner">
                <span>{activeFilter.replace(/_/g, " ")}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    navigate(`/maintenance/${amoCode}/admin/billing`, {
                      replace: true,
                    })
                  }
                >
                  Clear filter
                </Button>
              </div>
            )}
            <p className="admin-muted">
              Connect billing integrations to unlock usage reporting and invoicing.
            </p>
            <ul className="admin-muted" style={{ margin: 0, paddingLeft: 18 }}>
              <li>Usage per AMO (active users, assets, training sessions)</li>
              <li>Plan tiers and entitlement limits</li>
              <li>Invoices, credits, and payment status</li>
            </ul>
          </Panel>

          <div className="admin-page__side">
            <Panel title="Actions" compact>
              <Button type="button" variant="secondary">
                Review plans
              </Button>
              <Button type="button" variant="secondary">
                View invoices
              </Button>
            </Panel>
            <Panel title="Notes" compact>
              <p className="admin-muted">
                Billing alerts and payment issues will surface here once enabled.
              </p>
            </Panel>
          </div>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminBillingPage;

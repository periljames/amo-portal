// src/pages/AdminBillingPage.tsx
import React, { useEffect, useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
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
      <div className="admin-page">
        <PageHeader
          title="Billing & Usage"
          subtitle="Track usage, plan allocation, and invoicing across AMOs."
        />

        {activeFilter && (
          <InlineAlert
            tone="warning"
            title="Filter applied"
            actions={(
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`, { replace: true })}
              >
                Clear filter
              </Button>
            )}
          >
            <span>{activeFilter.replace(/_/g, " ")}</span>
          </InlineAlert>
        )}

        <Panel title="Billing controls">
          <p className="admin-muted">
            Billing metrics and plan management will appear here. Configure your
            billing integrations to unlock usage reporting and invoicing.
          </p>
          <ul className="admin-muted" style={{ margin: 0, paddingLeft: 18 }}>
            <li>Usage per AMO (active users, assets, training sessions)</li>
            <li>Plan tiers and entitlement limits</li>
            <li>Invoices, credits, and payment status</li>
          </ul>
        </Panel>
      </div>
    </DepartmentLayout>
  );
};

export default AdminBillingPage;

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MoreVertical } from "lucide-react";
import DepartmentLayout from "../Layout/DepartmentLayout";
import PageHeader from "../shared/PageHeader";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import { useToast } from "../feedback/ToastProvider";

type Props = {
  amoCode: string;
  department: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  hideBackButton?: boolean;
};

const QMSLayout: React.FC<Props> = ({
  amoCode,
  department,
  title,
  subtitle,
  actions,
  children,
  hideBackButton = false,
}) => {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const amoDisplay = amoCode !== "UNKNOWN" ? decodeAmoCertFromUrl(amoCode) : "AMO";

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const breadcrumbs = useMemo(() => ([
    { label: `QMS · ${amoDisplay}`, to: `/maintenance/${amoCode}/${department}/qms` },
    { label: title },
  ]), [amoCode, department, title, amoDisplay]);

  useEffect(() => {
    if (department === "quality") return;
    pushToast({
      title: "QMS cockpit is under Quality & Compliance.",
      variant: "info",
    });
    navigate(`/maintenance/${amoCode}/${department}`, { replace: true });
  }, [amoCode, department, navigate, pushToast]);

  if (department !== "quality") {
    return null;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <div className="qms-shell">
        <PageHeader
          title={title}
          subtitle={subtitle}
          breadcrumbs={breadcrumbs}
          actions={
            <div className="qms-header__actions">
              {actions}
              {!hideBackButton ? (
                <>
                  <button
                    type="button"
                    className="secondary-chip-btn qms-header__back-desktop"
                    onClick={() => navigate(`/maintenance/${amoCode}/${department}`)}
                  >
                    Back
                  </button>
                  <div className="qms-header__mobile-overflow">
                    <button
                      type="button"
                      className="secondary-chip-btn qms-header__overflow-toggle"
                      aria-label="Open module actions"
                      onClick={() => setMobileMenuOpen((v) => !v)}
                    >
                      <MoreVertical size={15} />
                    </button>
                    {mobileMenuOpen ? (
                      <div className="qms-header__overflow-menu" role="menu">
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            setMobileMenuOpen(false);
                            navigate(`/maintenance/${amoCode}/${department}`);
                          }}
                        >
                          Back to dashboard
                        </button>
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          }
        />

        <div className="qms-content">{children}</div>
      </div>
    </DepartmentLayout>
  );
};

export default QMSLayout;

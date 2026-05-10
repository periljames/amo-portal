import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MoreVertical } from "lucide-react";
import DepartmentLayout from "../Layout/DepartmentLayout";
import PageHeader from "../shared/PageHeader";
import { decodeAmoCertFromUrl } from "../../utils/amo";

type Props = {
  amoCode: string;
  department?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  hideBackButton?: boolean;
  customHeader?: React.ReactNode;
};

const QMSLayout: React.FC<Props> = ({
  amoCode,
  title,
  subtitle,
  actions,
  children,
  hideBackButton = false,
  customHeader,
}) => {
  const navigate = useNavigate();
  const amoDisplay = amoCode !== "UNKNOWN" ? decodeAmoCertFromUrl(amoCode) : "AMO";
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const breadcrumbs = useMemo(() => ([
    { label: `QMS · ${amoDisplay}`, to: `/maintenance/${amoCode}/qms` },
    { label: title },
  ]), [amoCode, title, amoDisplay]);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-shell">
        {customHeader ?? (
          <PageHeader
            eyebrow={`QMS · ${amoDisplay}`}
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
                      onClick={() => navigate(`/maintenance/${amoCode}/qms`)}
                    >
                      QMS overview
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
                              navigate(`/maintenance/${amoCode}/qms`);
                            }}
                          >
                            QMS overview
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </>
                ) : null}
              </div>
            }
          />
        )}

        <div className="qms-content">{children}</div>
      </div>
    </DepartmentLayout>
  );
};

export default QMSLayout;

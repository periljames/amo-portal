import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
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
};

const QMSLayout: React.FC<Props> = ({
  amoCode,
  department,
  title,
  subtitle,
  actions,
  children,
}) => {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const amoDisplay = amoCode !== "UNKNOWN" ? decodeAmoCertFromUrl(amoCode) : "AMO";

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
          breadcrumbs={[
            {
              label: `QMS · ${amoDisplay}`,
              to: `/maintenance/${amoCode}/${department}/qms`,
            },
            { label: title },
          ]}
          actions={
            <div className="qms-header__actions">
              {actions}
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => navigate(`/maintenance/${amoCode}/${department}`)}
              >
                Back to department dashboard
              </button>
            </div>
          }
        />

        <div className="qms-content">{children}</div>
      </div>
    </DepartmentLayout>
  );
};

export default QMSLayout;

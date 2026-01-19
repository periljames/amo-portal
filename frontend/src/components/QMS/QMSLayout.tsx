import React from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import DepartmentLayout from "../Layout/DepartmentLayout";
import { decodeAmoCertFromUrl } from "../../utils/amo";

type NavItem = {
  id: string;
  label: string;
  path: string;
  description?: string;
};

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
  const location = useLocation();
  const amoDisplay = amoCode !== "UNKNOWN" ? decodeAmoCertFromUrl(amoCode) : "AMO";

  const navItems: NavItem[] = [
    {
      id: "dashboard",
      label: "Dashboard",
      path: `/maintenance/${amoCode}/${department}/qms`,
      description: "Executive summary & live compliance view",
    },
    {
      id: "documents",
      label: "Document Control",
      path: `/maintenance/${amoCode}/${department}/qms/documents`,
      description: "Manuals, procedures, revisions",
    },
    {
      id: "audits",
      label: "Audits & Inspections",
      path: `/maintenance/${amoCode}/${department}/qms/audits`,
      description: "Audit programme & closures",
    },
    {
      id: "change",
      label: "Change Control",
      path: `/maintenance/${amoCode}/${department}/qms/change-control`,
      description: "Change requests & approvals",
    },
    {
      id: "cars",
      label: "CAR Register",
      path: `/maintenance/${amoCode}/${department}/qms/cars`,
      description: "Corrective actions",
    },
    {
      id: "training",
      label: "Training & Competence",
      path: `/maintenance/${amoCode}/${department}/qms/training`,
      description: "Overdue matrix & events",
    },
    {
      id: "events",
      label: "Quality Events",
      path: `/maintenance/${amoCode}/${department}/qms/events`,
      description: "Calendar & milestones",
    },
    {
      id: "kpis",
      label: "KPIs & Review",
      path: `/maintenance/${amoCode}/${department}/qms/kpis`,
      description: "Quality performance indicators",
    },
  ];

  const activeItem = navItems.find((item) =>
    location.pathname.startsWith(item.path)
  );

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <div className="qms-shell">
        <header className="qms-header">
          <div>
            <div className="qms-eyebrow">Quality Management System · {amoDisplay}</div>
            <h1 className="qms-title">{title}</h1>
            {subtitle && <p className="qms-subtitle">{subtitle}</p>}
          </div>
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
        </header>

        <nav className="qms-nav" aria-label="QMS navigation">
          <div className="qms-nav__items">
            {navItems.map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                className={({ isActive }) =>
                  isActive ? "qms-nav__link qms-nav__link--active" : "qms-nav__link"
                }
              >
                <span className="qms-nav__label">{item.label}</span>
                {item.description && (
                  <span className="qms-nav__meta">{item.description}</span>
                )}
              </NavLink>
            ))}
          </div>
          {activeItem && (
            <div className="qms-nav__active">
              <span>Now viewing:</span>
              <strong>{activeItem.label}</strong>
            </div>
          )}
        </nav>

        <div className="qms-content">{children}</div>
      </div>
    </DepartmentLayout>
  );
};

export default QMSLayout;

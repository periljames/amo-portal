// src/components/Layout/DepartmentLayout.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
import { logout } from "../../services/auth";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
};

const DEPARTMENTS = [
  { id: "planning", label: "Planning" },
  { id: "production", label: "Production" },
  { id: "quality", label: "Quality & Compliance" },
  { id: "safety", label: "Safety Management" },
  { id: "stores", label: "Procurement & Stores" },
  { id: "engineering", label: "Engineering" },
  { id: "workshops", label: "Workshops" },
  { id: "admin", label: "System Admin" },
];

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
}) => {
  const theme = useTimeOfDayTheme();
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();

  const handleNav = (deptId: string) => {
    navigate(`/maintenance/${amoCode}/${deptId}`);
  };

  const handleLogout = () => {
    logout();
    navigate(`/maintenance/${amoCode}/login`, { replace: true });
  };

  const amoLabel = amoCode.toUpperCase();

  return (
    <div className={`app-shell app-shell--${theme}`}>
      <aside
        className={
          collapsed
            ? "app-shell__sidebar app-shell__sidebar--collapsed"
            : "app-shell__sidebar"
        }
      >
        <div className="sidebar__header">
          <div className="sidebar__title">
            <span className="sidebar__app">AMO PORTAL</span>
            <span className="sidebar__amo">{amoLabel}</span>
          </div>
          <button
            type="button"
            className="sidebar__collapse-btn"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? "›" : "‹"}
          </button>
        </div>

        <nav className="sidebar__nav">
          {DEPARTMENTS.map((dept) => {
            const isActive = dept.id === activeDepartment;
            return (
              <button
                key={dept.id}
                type="button"
                onClick={() => handleNav(dept.id)}
                className={
                  "sidebar__item" + (isActive ? " sidebar__item--active" : "")
                }
              >
                <span className="sidebar__item-label">{dept.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar__footer">
          <button
            type="button"
            className="sidebar__logout-btn"
            onClick={handleLogout}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="app-shell__main">
        <div className="app-shell__main-inner">{children}</div>
      </main>
    </div>
  );
};

export default DepartmentLayout;

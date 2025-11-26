// src/components/Layout/DepartmentLayout.tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
// ⬅️ CHANGE THIS LINE:
import { logout } from "../../services/auth";  // was ../../services/crs

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

type ColorScheme = "dark" | "light";

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
}) => {
  const theme = useTimeOfDayTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [colorScheme, setColorScheme] = useState<ColorScheme>("dark");
  const navigate = useNavigate();

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    const stored = window.localStorage.getItem("amo_color_scheme") as
      | ColorScheme
      | null;

    const initial: ColorScheme =
      stored === "light" || stored === "dark" ? stored : "dark";

    setColorScheme(initial);
    document.body.dataset.colorScheme = initial;
  }, []);

  useEffect(() => {
    if (typeof document === "undefined" || typeof window === "undefined") return;
    document.body.dataset.colorScheme = colorScheme;
    window.localStorage.setItem("amo_color_scheme", colorScheme);
  }, [colorScheme]);

  const toggleColorScheme = () => {
    setColorScheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const handleNav = (deptId: string) => {
    // ⬅️ FIX PATH: should be /maintenance/<amoCode>/<department>
    navigate(`/maintenance/${amoCode}/${deptId}`);
  };

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const amoLabel = amoCode.toUpperCase();
  const shellClassName = collapsed ? "app-shell app-shell--collapsed" : "app-shell";

  return (
    <div className={shellClassName}>
      <aside className="app-shell__sidebar">
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
            className="sidebar__theme-toggle"
            onClick={toggleColorScheme}
          >
            {colorScheme === "dark" ? "🌞 Light mode" : "🌙 Dark mode"}
          </button>

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

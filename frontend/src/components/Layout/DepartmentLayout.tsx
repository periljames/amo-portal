// src/components/Layout/DepartmentLayout.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
import { getCachedUser, logout } from "../../services/auth";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
};

type DepartmentId =
  | "planning"
  | "production"
  | "quality"
  | "safety"
  | "stores"
  | "engineering"
  | "workshops"
  | "admin";

const DEPARTMENTS: Array<{ id: DepartmentId; label: string }> = [
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

function isDepartmentId(v: string): v is DepartmentId {
  return DEPARTMENTS.some((d) => d.id === v);
}

function isAdminUser(u: any): boolean {
  if (!u) return false;
  return (
    !!u.is_superuser ||
    !!u.is_amo_admin ||
    u.role === "SUPERUSER" ||
    u.role === "AMO_ADMIN"
  );
}

function getUserDisplayName(u: any): string {
  if (!u) return "User";
  return (
    u.full_name ||
    u.name ||
    u.display_name ||
    u.username ||
    u.email ||
    "User"
  );
}

function getUserInitials(u: any): string {
  const name = getUserDisplayName(u).trim();
  if (!name) return "U";
  const parts = name.split(/\s+/).filter(Boolean);
  const a = parts[0]?.[0] ?? "U";
  const b = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (a + b).toUpperCase();
}

function getUserDeptId(u: any): DepartmentId | null {
  const code = (u?.department?.code || u?.department_code || "").toString().trim();
  if (!code) return null;
  const v = code.toLowerCase();
  if (isDepartmentId(v)) return v;
  return null;
}

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
}) => {
  const theme = useTimeOfDayTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [colorScheme, setColorScheme] = useState<ColorScheme>("dark");
  const [profileOpen, setProfileOpen] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  const currentUser = getCachedUser();

  // Admins/SUPERUSER can see all departments and the System Admin area.
  const canAccessAdmin = isAdminUser(currentUser);

  const visibleDepartments = useMemo(() => {
    if (canAccessAdmin) return DEPARTMENTS;

    // Non-admin users: show ONLY their current department in the ribbon.
    const deptId = isDepartmentId(activeDepartment) ? activeDepartment : null;
    if (!deptId) return [];

    // Non-admins never see the System Admin tab.
    if (deptId === "admin") return [];

    const match = DEPARTMENTS.find((d) => d.id === deptId);
    return match ? [match] : [];
  }, [canAccessAdmin, activeDepartment]);

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

  const handleNav = (deptId: DepartmentId) => {
    // Non-admins should not navigate across departments.
    if (!canAccessAdmin) {
      const active = isDepartmentId(activeDepartment) ? activeDepartment : null;
      if (active && deptId === active) {
        navigate(`/maintenance/${amoCode}/${deptId}`);
      }
      return;
    }

    // System Admin is NOT a normal department dashboard; route is explicit.
    if (deptId === "admin") {
      navigate(`/maintenance/${amoCode}/admin`);
      return;
    }

    navigate(`/maintenance/${amoCode}/${deptId}`);
  };

  const resolveDeptForTraining = (): string => {
    // Prefer the current department (unless admin)
    if (isDepartmentId(activeDepartment) && activeDepartment !== "admin") {
      return activeDepartment;
    }

    // Next: user department (if available)
    const userDept = getUserDeptId(currentUser);
    if (userDept && userDept !== "admin") {
      return userDept;
    }

    // Next: first visible non-admin department
    const first = visibleDepartments.find((d) => d.id !== "admin")?.id;
    if (first) return first;

    // Last resort
    return "planning";
  };

  const gotoMyTraining = () => {
    const dept = resolveDeptForTraining();
    navigate(`/maintenance/${amoCode}/${dept}/training`);
  };

  const handleLogout = () => {
    logout();

    // Keep AMO context when logging out
    const code = (amoCode || "").trim();
    if (code) {
      navigate(`/maintenance/${code}/login`, { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  };

  const amoLabel = (amoCode || "AMO").toUpperCase();
  const shellClassName = collapsed
    ? "app-shell app-shell--collapsed"
    : "app-shell";

  const isTrainingRoute = useMemo(() => {
    return location.pathname.includes("/training");
  }, [location.pathname]);

  const profileRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!profileOpen) return;

    const onDown = (e: MouseEvent) => {
      const el = profileRef.current;
      if (!el) return;
      if (e.target instanceof Node && !el.contains(e.target)) {
        setProfileOpen(false);
      }
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };

    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  const deptLabel =
    DEPARTMENTS.find((d) => d.id === (activeDepartment as any))?.label ||
    (activeDepartment || "Department");

  const userName = getUserDisplayName(currentUser);
  const userInitials = getUserInitials(currentUser);

  const currentYear = new Date().getFullYear();

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
          {visibleDepartments.map((dept) => {
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

          <div className="sidebar__divider" />

          <button
            type="button"
            onClick={gotoMyTraining}
            className={
              "sidebar__item" + (isTrainingRoute ? " sidebar__item--active" : "")
            }
            aria-label="My Training"
            title="My Training"
          >
            <span className="sidebar__item-label">My Training</span>
          </button>
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
        <header className="app-shell__topbar">
          <div className="app-shell__topbar-title">
            <div className="app-shell__topbar-heading">{deptLabel}</div>
            <div className="app-shell__topbar-subtitle">
              {amoLabel} · Daily operations workspace
            </div>
          </div>

          <div ref={profileRef} className="profile-menu">
            <button
              type="button"
              onClick={() => setProfileOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={profileOpen}
              className="profile-menu__trigger"
              title={userName}
            >
              <span className="profile-menu__avatar">{userInitials}</span>
              <span className="profile-menu__meta">
                <span className="profile-menu__name">{userName}</span>
                <span className="profile-menu__role">Profile</span>
              </span>
              <span className="profile-menu__caret">{profileOpen ? "▲" : "▼"}</span>
            </button>

            {profileOpen && (
              <div role="menu" className="profile-menu__panel">
                <button
                  type="button"
                  role="menuitem"
                  className="profile-menu__item"
                  onClick={() => {
                    setProfileOpen(false);
                    gotoMyTraining();
                  }}
                >
                  My Training
                </button>

                <button
                  type="button"
                  role="menuitem"
                  className="profile-menu__item"
                  onClick={() => {
                    setProfileOpen(false);
                    toggleColorScheme();
                  }}
                >
                  {colorScheme === "dark"
                    ? "Switch to Light mode"
                    : "Switch to Dark mode"}
                </button>

                <div className="profile-menu__divider" />

                <button
                  type="button"
                  role="menuitem"
                  className="profile-menu__item"
                  onClick={() => {
                    setProfileOpen(false);
                    handleLogout();
                  }}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="app-shell__main-inner">{children}</div>

        <footer className="app-shell__footer">
          <span>© {currentYear} AMO Portal.</span>
          <span>All rights reserved.</span>
        </footer>
      </main>
    </div>
  );
};

export default DepartmentLayout;

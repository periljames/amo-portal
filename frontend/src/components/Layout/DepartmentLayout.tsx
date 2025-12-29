// src/components/Layout/DepartmentLayout.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
import { fetchSubscription } from "../../services/billing";
import type { Subscription } from "../../types/billing";
import { getCachedUser, logout, onSessionEvent } from "../../services/auth";

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

type AdminNavId =
  | "admin-overview"
  | "admin-amos"
  | "admin-users"
  | "admin-assets"
  | "admin-billing";

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

const ADMIN_NAV_ITEMS: Array<{ id: AdminNavId; label: string }> = [
  { id: "admin-overview", label: "Overview" },
  { id: "admin-amos", label: "AMO Management" },
  { id: "admin-users", label: "User Management" },
  { id: "admin-assets", label: "AMO Assets" },
  { id: "admin-billing", label: "Billing & Usage" },
];

type ColorScheme = "dark" | "light";

const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const IDLE_WARNING_MS = 3 * 60 * 1000;

function isDepartmentId(v: string): v is DepartmentId {
  return DEPARTMENTS.some((d) => d.id === v);
}

function isAdminNavId(v: string): v is AdminNavId {
  return ADMIN_NAV_ITEMS.some((d) => d.id === v);
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
  const [idleWarningOpen, setIdleWarningOpen] = useState(false);
  const [idleCountdown, setIdleCountdown] = useState(IDLE_WARNING_MS / 1000);
  const [logoutReason, setLogoutReason] = useState<"idle" | "expired" | null>(
    null
  );
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);

  const navigate = useNavigate();
  const location = useLocation();

  const currentUser = getCachedUser();
  const isSuperuser = !!currentUser?.is_superuser;
  const isTenantAdmin = isSuperuser || !!currentUser?.is_amo_admin;
  const isAdminArea = isAdminNavId(activeDepartment);

  // Admins/SUPERUSER can see all departments and the System Admin area.
  const canAccessAdmin = isAdminUser(currentUser);

  const visibleDepartments = useMemo(() => {
    if (isAdminArea) return [];
    if (canAccessAdmin) return DEPARTMENTS;

    // Non-admin users: show ONLY their current department in the ribbon.
    const deptId = isDepartmentId(activeDepartment) ? activeDepartment : null;
    if (!deptId) return [];

    // Non-admins never see the System Admin tab.
    if (deptId === "admin") return [];

    const match = DEPARTMENTS.find((d) => d.id === deptId);
    return match ? [match] : [];
  }, [canAccessAdmin, activeDepartment, isAdminArea]);

  const visibleAdminNav = useMemo(() => {
    if (!isAdminArea) return [];
    return ADMIN_NAV_ITEMS.filter((i) => {
      if (i.id === "admin-amos" && !isSuperuser) return false;
      if (i.id === "admin-billing" && !isTenantAdmin) return false;
      return true;
    });
  }, [isAdminArea, isSuperuser, isTenantAdmin]);

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
    const targetPath = `/maintenance/${amoCode}/${deptId}`;
    if (
      subscription?.is_read_only &&
      !targetPath.includes("/billing") &&
      !targetPath.includes("/upsell")
    ) {
      navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
        replace: true,
        state: { from: targetPath },
      });
      return;
    }

    // Non-admins should not navigate across departments.
    if (!canAccessAdmin) {
      const active = isDepartmentId(activeDepartment) ? activeDepartment : null;
      if (active && deptId === active) {
        navigate(targetPath);
      }
      return;
    }

    // System Admin is NOT a normal department dashboard; route is explicit.
    if (deptId === "admin") {
      navigate(`/maintenance/${amoCode}/admin/overview`);
      return;
    }

    navigate(targetPath);
  };

  const handleAdminNav = (navId: AdminNavId) => {
    if (subscription?.is_read_only && navId !== "admin-billing") {
      navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
        replace: true,
        state: { from: location.pathname + location.search },
      });
      return;
    }

    switch (navId) {
      case "admin-overview":
        navigate(`/maintenance/${amoCode}/admin/overview`);
        break;
      case "admin-amos":
        navigate(`/maintenance/${amoCode}/admin/amos`);
        break;
      case "admin-users":
        navigate(`/maintenance/${amoCode}/admin/users`);
        break;
      case "admin-assets":
        navigate(`/maintenance/${amoCode}/admin/amo-assets`);
        break;
      case "admin-billing":
        navigate(`/maintenance/${amoCode}/admin/billing`);
        break;
      default:
        break;
    }
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

  const isBillingRoute = useMemo(() => {
    return location.pathname.includes("/billing");
  }, [location.pathname]);

  const isUpsellRoute = useMemo(() => {
    return location.pathname.includes("/upsell");
  }, [location.pathname]);

  const isTrainingRoute = useMemo(() => {
    return location.pathname.includes("/training");
  }, [location.pathname]);

  const isAircraftImportRoute = useMemo(() => {
    return location.pathname.includes("/aircraft-import");
  }, [location.pathname]);

  const isQmsRoute = useMemo(() => {
    return location.pathname.includes("/qms");
  }, [location.pathname]);

  const profileRef = useRef<HTMLDivElement | null>(null);
  const idleWarningTimeoutRef = useRef<number | null>(null);
  const idleLogoutTimeoutRef = useRef<number | null>(null);
  const idleCountdownIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    fetchSubscription()
      .then((sub) => {
        if (!active) return;
        setSubscription(sub);
        setSubscriptionError(null);
      })
      .catch((err: any) => {
        if (!active) return;
        setSubscription(null);
        setSubscriptionError(err?.message || "Unable to load subscription status.");
      });

    return () => {
      active = false;
    };
  }, []);

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

  const clearIdleTimers = () => {
    if (idleWarningTimeoutRef.current) {
      window.clearTimeout(idleWarningTimeoutRef.current);
      idleWarningTimeoutRef.current = null;
    }
    if (idleLogoutTimeoutRef.current) {
      window.clearTimeout(idleLogoutTimeoutRef.current);
      idleLogoutTimeoutRef.current = null;
    }
    if (idleCountdownIntervalRef.current) {
      window.clearInterval(idleCountdownIntervalRef.current);
      idleCountdownIntervalRef.current = null;
    }
  };

  const scheduleIdleTimers = () => {
    clearIdleTimers();
    if (!currentUser || logoutReason) return;

    const warningDelay = Math.max(IDLE_TIMEOUT_MS - IDLE_WARNING_MS, 0);

    idleWarningTimeoutRef.current = window.setTimeout(() => {
      setIdleWarningOpen(true);
      setIdleCountdown(IDLE_WARNING_MS / 1000);
    }, warningDelay);

    idleLogoutTimeoutRef.current = window.setTimeout(() => {
      logout();
      setIdleWarningOpen(false);
      setLogoutReason("idle");
    }, IDLE_TIMEOUT_MS);
  };

  const resetIdleTimers = () => {
    if (!currentUser || logoutReason) return;
    setIdleWarningOpen(false);
    setIdleCountdown(IDLE_WARNING_MS / 1000);
    scheduleIdleTimers();
  };

  useEffect(() => {
    if (!currentUser) return;
    scheduleIdleTimers();

    const activityEvents = [
      "mousemove",
      "keydown",
      "click",
      "scroll",
      "touchstart",
    ];
    const handleActivity = () => {
      if (logoutReason) return;
      resetIdleTimers();
    };

    activityEvents.forEach((evt) =>
      window.addEventListener(evt, handleActivity, { passive: true })
    );

    return () => {
      activityEvents.forEach((evt) =>
        window.removeEventListener(evt, handleActivity)
      );
      clearIdleTimers();
    };
  }, [currentUser, logoutReason]);

  useEffect(() => {
    if (!idleWarningOpen) return;

    idleCountdownIntervalRef.current = window.setInterval(() => {
      setIdleCountdown((prev) => {
        if (prev <= 1) {
          const intervalId = idleCountdownIntervalRef.current;
          if (intervalId) {
            window.clearInterval(intervalId);
            idleCountdownIntervalRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (idleCountdownIntervalRef.current) {
        window.clearInterval(idleCountdownIntervalRef.current);
        idleCountdownIntervalRef.current = null;
      }
    };
  }, [idleWarningOpen]);

  useEffect(() => {
    const unsubscribe = onSessionEvent((detail) => {
      if (detail.type !== "expired") return;
      clearIdleTimers();
      setIdleWarningOpen(false);
      setLogoutReason("expired");
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const shouldBlur = idleWarningOpen || !!logoutReason;
    document.body.classList.toggle("session-timeout-active", shouldBlur);
  }, [idleWarningOpen, logoutReason]);

  useEffect(() => {
    if (!subscription?.is_read_only) return;
    if (isBillingRoute || isUpsellRoute) return;
    navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
      replace: true,
      state: { from: location.pathname + location.search },
    });
  }, [
    subscription?.is_read_only,
    isBillingRoute,
    isUpsellRoute,
    amoCode,
    location.pathname,
    location.search,
    navigate,
  ]);

  const deptLabel =
    ADMIN_NAV_ITEMS.find((d) => d.id === (activeDepartment as AdminNavId))
      ?.label ||
    DEPARTMENTS.find((d) => d.id === (activeDepartment as any))?.label ||
    (activeDepartment || "Department");

  const userName = getUserDisplayName(currentUser);
  const userInitials = getUserInitials(currentUser);

  const currentYear = new Date().getFullYear();
  const returnPath = location.pathname + location.search;
  const formattedCountdown = new Date(idleCountdown * 1000)
    .toISOString()
    .substring(14, 19);
  const formatCountdown = (iso?: string | null): string | null => {
    if (!iso) return null;
    const target = new Date(iso).getTime();
    const now = Date.now();
    const diff = target - now;
    if (diff <= 0) return "0d";
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    if (days > 0) return `${days}d ${hours}h`;
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };
  const trialCountdown = formatCountdown(subscription?.trial_ends_at || null);
  const graceCountdown = formatCountdown(subscription?.trial_grace_expires_at || null);
  const isTrialing = subscription?.status === "TRIALING";
  const isExpired = subscription?.status === "EXPIRED";
  const isReadOnly = !!subscription?.is_read_only;

  const handleStaySignedIn = () => {
    resetIdleTimers();
  };

  const handleIdleLogout = () => {
    logout();
    clearIdleTimers();
    setIdleWarningOpen(false);
    setLogoutReason("idle");
  };

  const handleResumeLogin = () => {
    const code = (amoCode || "").trim();
    const target = code ? `/maintenance/${code}/login` : "/login";
    navigate(target, { replace: true, state: { from: returnPath } });
  };

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
          {visibleAdminNav.map((nav) => {
            const isActive = nav.id === activeDepartment;
            return (
              <button
                key={nav.id}
                type="button"
                onClick={() => handleAdminNav(nav.id)}
                className={
                  "sidebar__item" + (isActive ? " sidebar__item--active" : "")
                }
              >
                <span className="sidebar__item-label">{nav.label}</span>
              </button>
            );
          })}

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

          {!isAdminArea && <div className="sidebar__divider" />}

          {!isAdminArea && activeDepartment === "planning" && (
            <button
              type="button"
              onClick={() =>
                navigate(`/maintenance/${amoCode}/planning/aircraft-import`)
              }
              className={
                "sidebar__item" +
                (isAircraftImportRoute ? " sidebar__item--active" : "")
              }
              aria-label="Setup Aircraft"
              title="Setup Aircraft"
            >
              <span className="sidebar__item-label">Setup Aircraft</span>
            </button>
          )}

          {!isAdminArea && (
            <button
              type="button"
              onClick={gotoMyTraining}
              className={
                "sidebar__item" +
                (isTrainingRoute ? " sidebar__item--active" : "")
              }
              aria-label="My Training"
              title="My Training"
            >
              <span className="sidebar__item-label">My Training</span>
            </button>
          )}

          {!isAdminArea && activeDepartment === "quality" && (
            <button
              type="button"
              onClick={() => navigate(`/maintenance/${amoCode}/quality/qms`)}
              className={
                "sidebar__item" + (isQmsRoute ? " sidebar__item--active" : "")
              }
              aria-label="Quality Management System"
              title="Quality Management System"
            >
              <span className="sidebar__item-label">QMS Overview</span>
            </button>
          )}
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

        {isTrialing && subscription?.trial_ends_at && (
          <div className="info-banner info-banner--soft" style={{ margin: "12px 16px 0" }}>
            <div>
              <strong>Trial in progress</strong>
              <p className="text-muted" style={{ margin: 0 }}>
                {trialCountdown
                  ? `Ends in ${trialCountdown}.`
                  : "Trial ending soon."}{" "}
                Convert to paid to avoid any grace or lockout.
              </p>
            </div>
            <div className="page-section__actions">
              <button
                className="btn btn-primary"
                onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
              >
                Convert to paid
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => navigate(`/maintenance/${amoCode}/upsell`)}
              >
                View plans
              </button>
            </div>
          </div>
        )}

        {isExpired && (
          <div
            className={`card ${isReadOnly ? "card--error" : "card--warning"}`}
            style={{ margin: "12px 16px 0" }}
          >
            <div className="card-header">
              <div>
                <h3 style={{ margin: "4px 0" }}>
                  {isReadOnly ? "Trial locked" : "Trial expired"}
                </h3>
                <p className="text-muted" style={{ margin: 0 }}>
                  {isReadOnly
                    ? "Grace ended; workspace is read-only until a paid plan starts."
                    : graceCountdown
                    ? `Grace expires in ${graceCountdown}.`
                    : "Grace period is in effect. Add a payment method to keep access."}
                </p>
                {subscriptionError && (
                  <p className="text-muted" style={{ margin: 0 }}>
                    {subscriptionError}
                  </p>
                )}
              </div>
              <div className="page-section__actions">
                <button
                  className="btn btn-primary"
                  onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
                >
                  Go to billing
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => navigate(`/maintenance/${amoCode}/upsell`)}
                >
                  See plans
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="app-shell__main-inner">{children}</div>

        <footer className="app-shell__footer">
          <span>© {currentYear} AMO Portal.</span>
          <span>All rights reserved.</span>
        </footer>
      </main>

      {(idleWarningOpen || logoutReason) && (
        <div className="session-timeout-overlay" role="dialog" aria-live="polite">
          <div className="session-timeout-card">
            {idleWarningOpen && !logoutReason && (
              <>
                <h2>Inactivity warning</h2>
                <p>
                  You will be logged out in{" "}
                  <strong>{formattedCountdown}</strong> due to inactivity.
                </p>
                <p>Please click below to stay signed in.</p>
                <div className="session-timeout-actions">
                  <button className="btn btn-secondary" onClick={handleIdleLogout}>
                    Log out now
                  </button>
                  <button className="btn btn-primary" onClick={handleStaySignedIn}>
                    Stay signed in
                  </button>
                </div>
              </>
            )}

            {logoutReason && (
              <>
                <h2>Session ended</h2>
                <p>
                  {logoutReason === "idle"
                    ? "You have been logged out due to inactivity."
                    : "Your session has expired. Please log in again."}
                </p>
                <div className="session-timeout-actions">
                  <button className="btn btn-primary" onClick={handleResumeLogin}>
                    Log in
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DepartmentLayout;

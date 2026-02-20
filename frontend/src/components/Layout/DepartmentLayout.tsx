// src/components/Layout/DepartmentLayout.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { BrandContext } from "../Brand/BrandContext";
import { BrandHeader } from "../Brand/BrandHeader";
import { BrandProvider } from "../Brand/BrandProvider";
import AppShellV2 from "../AppShell/AppShellV2";
import LiveStatusIndicator from "../realtime/LiveStatusIndicator";
import { useToast } from "../feedback/ToastProvider";
import { useAnalytics } from "../../hooks/useAnalytics";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
import { useColorScheme } from "../../hooks/useColorScheme";
import { usePortalRuntimeMode } from "../../hooks/usePortalRuntimeMode";
import { isUiShellV2Enabled } from "../../utils/featureFlags";
import {
  getNotificationPreferences,
  NOTIFICATION_PREFS_EVENT,
  playNotificationChirp,
  pushDesktopNotification,
  setNotificationPreferences,
  type NotificationPreferences,
} from "../../services/notificationPreferences";
import { fetchSubscription } from "../../services/billing";
import type { Subscription } from "../../types/billing";
import { endSession, getCachedUser, getContext, markSessionActivity, onSessionEvent } from "../../services/auth";
import { listDocumentAlerts } from "../../services/fleet";
import { fetchOverviewSummary, type OverviewSummary } from "../../services/adminOverview";
import { qmsListNotifications } from "../../services/qms";
import {
  listTrainingNotifications,
  markAllTrainingNotificationsRead,
  markTrainingNotificationRead,
} from "../../services/training";
import type { TrainingNotificationRead } from "../../types/training";
import {
  DEPARTMENT_ITEMS,
  type DepartmentId,
  canAccessDepartment,
  getAllowedDepartments,
  getAssignedDepartment,
  isAdminUser,
  isDepartmentId,
} from "../../utils/departmentAccess";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

type AdminNavId =
  | "admin-overview"
  | "admin-amos"
  | "admin-users"
  | "admin-assets"
  | "admin-billing"
  | "admin-settings"
  | "admin-email-logs"
  | "admin-email-settings";

const ADMIN_NAV_ITEMS: Array<{ id: AdminNavId; label: string }> = [
  { id: "admin-overview", label: "Overview" },
  { id: "admin-amos", label: "AMO Management" },
  { id: "admin-users", label: "User Management" },
  { id: "admin-assets", label: "AMO Assets" },
  { id: "admin-billing", label: "Billing & Usage" },
  { id: "admin-settings", label: "Usage Throttling" },
  { id: "admin-email-logs", label: "Email Logs" },
  { id: "admin-email-settings", label: "Email Server" },
];


const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const IDLE_WARNING_MS = 3 * 60 * 1000;
const LAYOUT_CACHE_TTL_MS = 5 * 60 * 1000;
const LAYOUT_CACHE_FAST_TTL_MS = 10 * 60 * 1000;
const LAYOUT_CACHE_PREFIX = "amo_portal_layout_cache";
const layoutMemoryCache = new Map<string, LayoutCacheEntry<unknown>>();

type LayoutCacheEntry<T> = {
  value: T;
  savedAt: number;
};

function getLayoutCacheProfile(): {
  maxAgeMs: number;
  useMemory: boolean;
} {
  if (typeof window === "undefined") {
    return { maxAgeMs: LAYOUT_CACHE_TTL_MS, useMemory: false };
  }
  const deviceMemory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4;
  const connection = (navigator as Navigator & {
    connection?: { effectiveType?: string };
  }).connection;
  const effectiveType = connection?.effectiveType;
  const isFastConnection = !effectiveType || effectiveType === "4g";
  const useMemory = deviceMemory >= 8 && isFastConnection;
  return {
    maxAgeMs: useMemory ? LAYOUT_CACHE_FAST_TTL_MS : LAYOUT_CACHE_TTL_MS,
    useMemory,
  };
}

function readLayoutCache<T>(key: string, maxAgeMs: number, useMemory: boolean): T | null {
  if (typeof window === "undefined") return null;
  if (useMemory) {
    const entry = layoutMemoryCache.get(key) as LayoutCacheEntry<T> | undefined;
    if (entry) {
      if (Date.now() - entry.savedAt <= maxAgeMs) {
        return entry.value ?? null;
      }
      layoutMemoryCache.delete(key);
    }
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LayoutCacheEntry<T>;
    if (!parsed?.savedAt) return null;
    if (Date.now() - parsed.savedAt > maxAgeMs) {
      window.localStorage.removeItem(key);
      return null;
    }
    return parsed.value ?? null;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

function writeLayoutCache<T>(key: string, value: T, useMemory: boolean): void {
  if (typeof window === "undefined") return;
  const payload: LayoutCacheEntry<T> = { value, savedAt: Date.now() };
  if (useMemory) {
    layoutMemoryCache.set(key, payload);
  }
  window.localStorage.setItem(key, JSON.stringify(payload));
}

function clearLayoutCache(prefix: string): void {
  if (typeof window === "undefined") return;
  layoutMemoryCache.forEach((_value, key) => {
    if (key.startsWith(prefix)) {
      layoutMemoryCache.delete(key);
    }
  });
  for (let i = window.localStorage.length - 1; i >= 0; i -= 1) {
    const key = window.localStorage.key(i);
    if (key && key.startsWith(prefix)) {
      window.localStorage.removeItem(key);
    }
  }
}

function isAdminNavId(v: string): v is AdminNavId {
  return ADMIN_NAV_ITEMS.some((d) => d.id === v);
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

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
  showPollingErrorBanner = true,
}) => {
  const theme = useTimeOfDayTheme();
  const { scheme: colorScheme, toggle: toggleColorScheme } = useColorScheme();
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const [sidebarDrawerOpen, setSidebarDrawerOpen] = useState(false);
  const [isDesktopSidebar, setIsDesktopSidebar] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<TrainingNotificationRead[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<string | null>(null);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPreferences>(() => getNotificationPreferences());
  const [idleWarningOpen, setIdleWarningOpen] = useState(false);
  const [idleCountdown, setIdleCountdown] = useState(IDLE_WARNING_MS / 1000);
  const [logoutReason, setLogoutReason] = useState<"idle" | "expired" | null>(
    null
  );
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [overviewSummary, setOverviewSummary] = useState<OverviewSummary | null>(null);
  const [overviewSummaryUnavailable, setOverviewSummaryUnavailable] = useState(false);
  const [trialMenuOpen, setTrialMenuOpen] = useState(false);
  const [trialChipHidden, setTrialChipHidden] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { trackEvent } = useAnalytics();
  const { pushToast } = useToast();
  const uiShellV2 = isUiShellV2Enabled();

  useEffect(() => {
    if (!uiShellV2) return;
    document.body.classList.add("app-shell-v2");
    return () => {
      document.body.classList.remove("app-shell-v2");
    };
  }, [uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1025px)");
    const apply = () => setIsDesktopSidebar(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [uiShellV2]);

  const currentUser = getCachedUser();
  const sidebarStorageKey = `amo_sidebar_pinned:${currentUser?.id || "anon"}:${currentUser?.amo_id || amoCode}`;

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    const stored = window.localStorage.getItem(sidebarStorageKey);
    setSidebarPinned(stored === "1");
  }, [sidebarStorageKey, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    window.localStorage.setItem(sidebarStorageKey, sidebarPinned ? "1" : "0");
    if (sidebarPinned) setSidebarDrawerOpen(false);
  }, [sidebarPinned, sidebarStorageKey, uiShellV2]);
  const { isGoLive } = usePortalRuntimeMode();
  const isSuperuser = !!currentUser?.is_superuser;
  const isTenantAdmin = isSuperuser || !!currentUser?.is_amo_admin;
  const isAdminArea = isAdminNavId(activeDepartment);
  const assignedDepartment = getAssignedDepartment(currentUser, getContext().department);
  const allowedDepartments = getAllowedDepartments(currentUser, assignedDepartment);

  // Admins/SUPERUSER can see all departments and the System Admin area.
  const canAccessAdmin = isAdminUser(currentUser);

  const visibleDepartments = useMemo(() => {
    if (isAdminArea) {
      return canAccessAdmin
        ? DEPARTMENT_ITEMS.filter((dept) => dept.id !== "admin")
        : [];
    }
    if (canAccessAdmin) return DEPARTMENT_ITEMS;

    return DEPARTMENT_ITEMS.filter((dept) =>
      allowedDepartments.includes(dept.id)
    );
  }, [canAccessAdmin, isAdminArea, allowedDepartments]);

  const visibleAdminNav = useMemo(() => {
    if (!isAdminArea) return [];
    return ADMIN_NAV_ITEMS.filter((i) => {
      if (i.id === "admin-amos" && !isSuperuser) return false;
      if (i.id === "admin-billing" && !isTenantAdmin) return false;
      if (i.id === "admin-email-settings" && !isSuperuser) return false;
      return true;
    });
  }, [isAdminArea, isSuperuser, isTenantAdmin]);

  useEffect(() => {
    if (!currentUser) return;
    if (isAdminArea) {
      if (!canAccessAdmin) {
        const fallback = assignedDepartment || allowedDepartments[0] || "planning";
        navigate(`/maintenance/${amoCode}/${fallback}`, { replace: true });
      }
      return;
    }

    if (!canAccessAdmin && isDepartmentId(activeDepartment)) {
      if (!allowedDepartments.includes(activeDepartment)) {
        const fallback = assignedDepartment || allowedDepartments[0] || "planning";
        navigate(`/maintenance/${amoCode}/${fallback}`, { replace: true });
      }
    }
  }, [
    activeDepartment,
    allowedDepartments,
    assignedDepartment,
    canAccessAdmin,
    currentUser,
    isAdminArea,
    navigate,
    amoCode,
  ]);

  const adminBadgeMap = useMemo(() => {
    const badges = overviewSummary?.badges || {};
    return {
      "admin-amos": badges.amos,
      "admin-users": badges.users,
      "admin-assets": badges.assets,
      "admin-billing": badges.billing,
      "admin-settings": badges.usage,
    } as Record<string, OverviewSummary["badges"][string] | undefined>;
  }, [overviewSummary?.badges]);

  const overviewSummaryDown = overviewSummary?.system.status === "down";

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.theme = theme;
  }, [theme]);


  const openSidebarDrawer = useCallback((options?: { source?: "edge" | "kbd" | "mobile" }) => {
    if (sidebarPinned) return;
    if (import.meta.env.DEV) {
      console.debug(`[sidebar] open drawer source=${options?.source ?? "unknown"}`);
    }
    setSidebarDrawerOpen(true);
  }, [sidebarPinned]);

  const closeSidebarDrawer = useCallback(() => {
    if (!sidebarPinned) setSidebarDrawerOpen(false);
  }, [sidebarPinned]);

  const navigateWithSidebarClose = useCallback(
    (path: string, options?: { replace?: boolean; state?: unknown }) => {
      closeSidebarDrawer();
      if (!sidebarPinned) setSidebarDrawerOpen(false);
      navigate(path, options as never);
    },
    [closeSidebarDrawer, navigate, sidebarPinned]
  );

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
      if (
        canAccessDepartment(currentUser, assignedDepartment, deptId) &&
        isDepartmentId(deptId)
      ) {
        navigateWithSidebarClose(targetPath);
      }
      return;
    }

    // System Admin is NOT a normal department dashboard; route is explicit.
    if (deptId === "admin") {
      navigateWithSidebarClose(`/maintenance/${amoCode}/admin/overview`);
      return;
    }

    navigateWithSidebarClose(targetPath);
  };

  const handleAdminNav = (navId: AdminNavId, overrideRoute?: string) => {
    if (subscription?.is_read_only && navId !== "admin-billing") {
      navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
        replace: true,
        state: { from: location.pathname + location.search },
      });
      return;
    }

    if (overrideRoute) {
      navigateWithSidebarClose(`/maintenance/${amoCode}${overrideRoute}`);
      return;
    }

    switch (navId) {
      case "admin-overview":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/overview`);
        break;
      case "admin-amos":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/amos`);
        break;
      case "admin-users":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/users`);
        break;
      case "admin-assets":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/amo-assets`);
        break;
      case "admin-billing":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/billing`);
        break;
      case "admin-settings":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/settings`);
        break;
      case "admin-email-logs":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/email-logs`);
        break;
      case "admin-email-settings":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/email-settings`);
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

    if (assignedDepartment && assignedDepartment !== "admin") {
      return assignedDepartment;
    }

    // Next: first visible non-admin department
    const first = visibleDepartments.find((d) => d.id !== "admin")?.id;
    if (first) return first;

    // Last resort
    return "planning";
  };

  const gotoMyTraining = () => {
    const dept = resolveDeptForTraining();
    navigateWithSidebarClose(`/maintenance/${amoCode}/${dept}/training`);
  };

  const resolveLoginSlug = (): string => {
    const parts = location.pathname.split("/").filter(Boolean);
    if (parts[0] === "maintenance" && parts[1]) {
      return parts[1];
    }
    const ctx = getContext();
    return ctx.amoSlug || amoCode || ctx.amoCode || "";
  };

  const handleLogout = () => {
    endSession("manual");

    // Keep AMO context when logging out
    const code = resolveLoginSlug().trim();
    if (code) {
      navigate(`/maintenance/${code}/login`, { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  };

  const amoLabel = (amoCode || "AMO").toUpperCase();
  const shellBase = uiShellV2 ? "app-shell app-shell--v2" : "app-shell";
  const sidebarOpen = sidebarPinned || sidebarDrawerOpen;
  const shellClassName = `${shellBase}${uiShellV2 ? ` app-shell--${sidebarPinned ? "pinned" : "drawer"}${sidebarOpen ? " app-shell--drawer-open" : ""}` : ""}`;
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

  const isComponentImportRoute = useMemo(() => {
    return location.pathname.includes("/component-import");
  }, [location.pathname]);

  const isAircraftDocumentsRoute = useMemo(() => {
    return location.pathname.includes("/aircraft-documents");
  }, [location.pathname]);

  const isWorkOrdersRoute = useMemo(() => {
    return location.pathname.includes("/work-orders") || location.pathname.includes("/tasks/");
  }, [location.pathname]);

  const isManualsRoute = useMemo(() => {
    return location.pathname.includes("/manuals");
  }, [location.pathname]);

  const isQmsRoute = useMemo(() => {
    return location.pathname.includes("/qms");
  }, [location.pathname]);

  const isDocControlRoute = useMemo(() => {
    return location.pathname.startsWith("/doc-control");
  }, [location.pathname]);

  useEffect(() => {
    if (!uiShellV2) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing || event.key === "Process") return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTextTarget =
        !!target && (target.isContentEditable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT");
      const matchesOpenCombo = (event.ctrlKey || event.metaKey) && event.key === "\\";
      if (matchesOpenCombo) {
        event.preventDefault();
        openSidebarDrawer({ source: "kbd" });
        return;
      }
      if (isTextTarget && !event.ctrlKey && !event.metaKey) {
        return;
      }
      if (event.key === "Escape" && !sidebarPinned) {
        setSidebarDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openSidebarDrawer, sidebarPinned, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || !isDesktopSidebar || sidebarPinned) return;

    const clearCloseTimer = () => {
      if (sidebarCloseTimerRef.current) {
        window.clearTimeout(sidebarCloseTimerRef.current);
        sidebarCloseTimerRef.current = null;
      }
    };

    const openDrawer = () => {
      clearCloseTimer();
      openSidebarDrawer({ source: "edge" });
    };

    const scheduleClose = () => {
      clearCloseTimer();
      sidebarCloseTimerRef.current = window.setTimeout(() => {
        setSidebarDrawerOpen(false);
      }, 280);
    };

    const sidebarEl = sidebarRef.current;
    const hotzoneEl = sidebarHotzoneRef.current;
    sidebarEl?.addEventListener("pointerenter", openDrawer);
    sidebarEl?.addEventListener("pointerleave", scheduleClose);
    hotzoneEl?.addEventListener("pointerenter", openDrawer);
    hotzoneEl?.addEventListener("pointerleave", scheduleClose);

    return () => {
      clearCloseTimer();
      sidebarEl?.removeEventListener("pointerenter", openDrawer);
      sidebarEl?.removeEventListener("pointerleave", scheduleClose);
      hotzoneEl?.removeEventListener("pointerenter", openDrawer);
      hotzoneEl?.removeEventListener("pointerleave", scheduleClose);
    };
  }, [isDesktopSidebar, openSidebarDrawer, sidebarPinned, uiShellV2]);

  useEffect(() => {
    if (!isDesktopSidebar || sidebarPinned) return;
    setSidebarDrawerOpen(false);
  }, [isDesktopSidebar, sidebarPinned]);

  type QmsNavItem = {
    id: string;
    label: string;
    path: string;
    matchPrefixes?: string[];
    children?: Array<{ id: string; label: string; path: string; matchPrefixes?: string[] }>;
  };

  const isPathMatch = (pathname: string, path: string, prefixes?: string[]) => {
    if (pathname.startsWith(path)) return true;
    return (prefixes ?? []).some((prefix) => pathname.startsWith(prefix));
  };

  const qmsNavItems = useMemo<QmsNavItem[]>(
    () => [
      {
        id: "qms-dashboard",
        label: "Dashboard",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms`,
      },
      {
        id: "qms-tasks",
        label: "My Tasks",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/tasks`,
      },
      {
        id: "qms-documents",
        label: "Document Control",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/documents`,
      },
      {
        id: "qms-audits",
        label: "Audits & Inspections",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/audits`,
        matchPrefixes: [`/maintenance/${amoCode}/quality/audits`],
        children: [
          {
            id: "qms-audits-plan-schedule",
            label: "Plan / Schedule",
            path: `/maintenance/${amoCode}/quality/audits/schedules/calendar`,
            matchPrefixes: [
              `/maintenance/${amoCode}/quality/audits/schedules/list`,
              `/maintenance/${amoCode}/quality/audits/schedules/`,
            ],
          },
          {
            id: "qms-audits-register",
            label: "Register",
            path: `/maintenance/${amoCode}/quality/audits/closeout/findings`,
            matchPrefixes: [`/maintenance/${amoCode}/quality/audits/closeout/cars`],
          },
          {
            id: "qms-audits-evidence-library",
            label: "Evidence Library",
            path: `/maintenance/${amoCode}/quality/evidence`,
            matchPrefixes: [`/maintenance/${amoCode}/quality/evidence/`],
          },
        ],
      },
      {
        id: "qms-change",
        label: "Change Control",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/change-control`,
      },
      {
        id: "qms-cars",
        label: "CAR Register",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/cars`,
      },
      {
        id: "qms-training",
        label: "Training & Competence",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/training`,
      },
      {
        id: "qms-events",
        label: "Quality Events",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/events`,
      },
      {
        id: "qms-kpis",
        label: "KPIs & Review",
        path: `/maintenance/${amoCode}/${activeDepartment}/qms/kpis`,
      },
      {
        id: "qms-governance",
        label: "Governance",
        path: `/doc-control`,
        children: [
          {
            id: "qms-governance-doc-control",
            label: "Document Control",
            path: `/doc-control`,
            matchPrefixes: ["/doc-control"],
          },
        ],
      },
    ],
    [activeDepartment, amoCode]
  );

  const isReliabilityRoute = useMemo(() => {
    return location.pathname.includes("/reliability");
  }, [location.pathname]);

  const isEhmDashboardRoute = useMemo(() => {
    return location.pathname.endsWith("/ehm") || location.pathname.endsWith("/ehm/dashboard");
  }, [location.pathname]);

  const isEhmTrendsRoute = useMemo(() => {
    return location.pathname.includes("/ehm/trends");
  }, [location.pathname]);

  const isEhmUploadsRoute = useMemo(() => {
    return location.pathname.includes("/ehm/uploads");
  }, [location.pathname]);


  const lockedEventRef = useRef<string | null>(null);
  const profileRef = useRef<HTMLDivElement | null>(null);
  const notificationsRef = useRef<HTMLDivElement | null>(null);
  const previousUnreadRef = useRef(0);
  const idleWarningTimeoutRef = useRef<number | null>(null);
  const idleLogoutTimeoutRef = useRef<number | null>(null);
  const idleCountdownIntervalRef = useRef<number | null>(null);
  const lastActivityRef = useRef<number>(0);
  const pollingInFlightRef = useRef(false);
  const trialMenuRef = useRef<HTMLDivElement | null>(null);
  const lastPollingToastRef = useRef<string | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const sidebarHotzoneRef = useRef<HTMLDivElement | null>(null);
  const sidebarCloseTimerRef = useRef<number | null>(null);

  const isForbiddenError = useCallback((err: unknown): boolean => {
    const message = err instanceof Error ? err.message : String(err);
    return message.includes("403") || message.toLowerCase().includes("forbidden");
  }, []);

  const cacheKeyBase = useMemo(() => {
    return `${LAYOUT_CACHE_PREFIX}:${amoCode}:${currentUser?.id || "anonymous"}`;
  }, [amoCode, currentUser?.id]);

  const cacheProfile = useMemo(() => getLayoutCacheProfile(), []);

  const subscriptionCacheKey = `${cacheKeyBase}:subscription`;
  const overviewCacheKey = `${cacheKeyBase}:overview-summary`;
  const unreadCacheKey = `${cacheKeyBase}:unread-count`;

  useEffect(() => {
    if (!currentUser) {
      clearLayoutCache(`${LAYOUT_CACHE_PREFIX}:`);
    }
  }, [currentUser]);

  useEffect(() => {
    return onSessionEvent((detail) => {
      if (detail.type === "activity") {
        resetIdleTimers();
      }
      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        clearLayoutCache(`${LAYOUT_CACHE_PREFIX}:`);
      }
    });
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    const cachedSubscription = readLayoutCache<Subscription>(
      subscriptionCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (cachedSubscription) {
      setSubscription(cachedSubscription);
      setSubscriptionError(null);
    }

    const cachedOverview = readLayoutCache<OverviewSummary>(
      overviewCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (cachedOverview) {
      setOverviewSummary(cachedOverview);
      setOverviewSummaryUnavailable(false);
    }

    const cachedUnread = readLayoutCache<number>(
      unreadCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (typeof cachedUnread === "number") {
      setUnreadNotifications(cachedUnread);
    }
  }, [
    cacheProfile.maxAgeMs,
    cacheProfile.useMemory,
    currentUser,
    overviewCacheKey,
    subscriptionCacheKey,
    unreadCacheKey,
  ]);

  const refreshSubscription = useCallback(async (opts?: { force?: boolean }) => {
    if (!opts?.force) {
      const cached = readLayoutCache<Subscription>(
        subscriptionCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (cached) {
        setSubscription(cached);
        setSubscriptionError(null);
        return;
      }
    }
    try {
      const sub = await fetchSubscription();
      setSubscription(sub);
      setSubscriptionError(null);
      writeLayoutCache(subscriptionCacheKey, sub, cacheProfile.useMemory);
    } catch (err: any) {
      setSubscription(null);
      setSubscriptionError(err?.message || "Unable to load subscription status.");
      throw err;
    }
  }, [cacheProfile.maxAgeMs, cacheProfile.useMemory, subscriptionCacheKey]);

  const refreshOverviewSummary = useCallback(async (opts?: { force?: boolean }) => {
    if (!isAdminUser(currentUser)) return;
    if (!opts?.force) {
      const cached = readLayoutCache<OverviewSummary>(
        overviewCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (cached) {
        setOverviewSummary(cached);
        setOverviewSummaryUnavailable(false);
        return;
      }
    }
    try {
      const data = await fetchOverviewSummary();
      setOverviewSummary(data);
      setOverviewSummaryUnavailable(false);
      writeLayoutCache(overviewCacheKey, data, cacheProfile.useMemory);
    } catch (err) {
      console.error("Failed to refresh overview summary", err);
      setOverviewSummary(null);
      setOverviewSummaryUnavailable(true);
    }
  }, [cacheProfile.maxAgeMs, cacheProfile.useMemory, currentUser, overviewCacheKey]);

  const refreshUnreadNotifications = useCallback(async (opts?: { force?: boolean }) => {
    if (!currentUser) return;
    if (!opts?.force) {
      const cached = readLayoutCache<number>(
        unreadCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (typeof cached === "number") {
        setUnreadNotifications(cached);
        return;
      }
    }
    const handleModuleCall = async <T,>(
      promise: Promise<T>,
      onSuccess?: (value: T) => void,
      onForbidden?: () => void
    ) => {
      try {
        const data = await promise;
        onSuccess?.(data);
      } catch (err) {
        if (isForbiddenError(err)) {
          onForbidden?.();
          return;
        }
        throw err;
      }
    };

    const trainingPromise = handleModuleCall(
      listTrainingNotifications({ unread_only: true, limit: 100 }),
      (data) => {
        const nextUnread = data.length;
        if (nextUnread > previousUnreadRef.current) {
          playNotificationChirp();
          void pushDesktopNotification("New training notifications", `${nextUnread - previousUnreadRef.current} new item(s) received.`);
        }
        previousUnreadRef.current = nextUnread;
        setUnreadNotifications(nextUnread);
        writeLayoutCache(unreadCacheKey, data.length, cacheProfile.useMemory);
      },
      () => {
        previousUnreadRef.current = 0;
        setUnreadNotifications(0);
        writeLayoutCache(unreadCacheKey, 0, cacheProfile.useMemory);
      }
    );

    const qmsPromise = handleModuleCall(qmsListNotifications());
    const documentsPromise = handleModuleCall(listDocumentAlerts());

    await Promise.all([trainingPromise, qmsPromise, documentsPromise]);
  }, [cacheProfile.maxAgeMs, cacheProfile.useMemory, currentUser, isForbiddenError, unreadCacheKey]);

  const handlePollingFailure = useCallback(
    (err: unknown) => {
      const message = err instanceof Error ? err.message : "Unable to refresh data.";
      setPollingError(message);
    },
    []
  );

  const runPolling = useCallback(
    async (reason: "manual") => {
      if (!currentUser) return;
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      try {
        const force = reason === "manual";
        await refreshSubscription({ force });
        await refreshUnreadNotifications({ force });
        await refreshOverviewSummary({ force });
        setPollingError(null);
      } catch (err: unknown) {
        handlePollingFailure(err);
      } finally {
        pollingInFlightRef.current = false;
      }
    },
    [
      currentUser,
      handlePollingFailure,
      refreshSubscription,
      refreshUnreadNotifications,
      refreshOverviewSummary,
    ]
  );

  const refreshNotifications = useCallback(
    async (opts?: { unreadOnly?: boolean }) => {
      if (!currentUser) return;
      const unreadOnly = opts?.unreadOnly ?? false;
      if (!unreadOnly) {
        setNotificationsLoading(true);
        setNotificationsError(null);
      }
      try {
        const data = await listTrainingNotifications({
          unread_only: unreadOnly,
          limit: 100,
        });
        if (unreadOnly) {
          if (data.length > previousUnreadRef.current) {
            playNotificationChirp();
            void pushDesktopNotification("New notifications", `${data.length - previousUnreadRef.current} new item(s) received.`);
          }
          previousUnreadRef.current = data.length;
          setUnreadNotifications(data.length);
          writeLayoutCache(unreadCacheKey, data.length, cacheProfile.useMemory);
        } else {
          setNotifications(data);
          const unreadCount = data.filter((n) => !n.read_at).length;
          previousUnreadRef.current = unreadCount;
          setUnreadNotifications(unreadCount);
          writeLayoutCache(unreadCacheKey, unreadCount, cacheProfile.useMemory);
        }
      } catch (err: any) {
        if (!unreadOnly) {
          setNotificationsError(err?.message || "Failed to load notifications.");
        }
        handlePollingFailure(err);
      } finally {
        if (!unreadOnly) setNotificationsLoading(false);
      }
    },
    [cacheProfile.useMemory, currentUser, handlePollingFailure, unreadCacheKey]
  );

  useEffect(() => {
    const handlePrefsChange = () => {
      setNotificationPrefs(getNotificationPreferences());
    };
    window.addEventListener(NOTIFICATION_PREFS_EVENT, handlePrefsChange);
    return () => window.removeEventListener(NOTIFICATION_PREFS_EVENT, handlePrefsChange);
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    const intervalMs = notificationPrefs.pollIntervalSeconds * 1000;
    const id = window.setInterval(() => {
      void refreshNotifications({ unreadOnly: true });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [currentUser, notificationPrefs.pollIntervalSeconds, refreshNotifications]);

  useEffect(() => {
    if (notificationsOpen) {
      refreshNotifications();
    }
  }, [notificationsOpen, refreshNotifications]);

  useEffect(() => {
    if (!notificationsOpen) return;

    const onDown = (e: MouseEvent) => {
      const el = notificationsRef.current;
      if (!el) return;
      if (e.target instanceof Node && !el.contains(e.target)) {
        setNotificationsOpen(false);
      }
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNotificationsOpen(false);
    };

    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [notificationsOpen]);

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
      endSession("idle");
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
    resetIdleTimers();
  }, [currentUser, location.pathname, location.search]);

  useEffect(() => {
    if (!currentUser) return;
    scheduleIdleTimers();

    const activityEvents: Array<keyof WindowEventMap> = [
      "mousemove",
      "mousedown",
      "mouseup",
      "keydown",
      "click",
      "scroll",
      "wheel",
      "touchstart",
      "touchmove",
      "pointerdown",
      "pointermove",
      "focus",
    ];
    const handleActivity = () => {
      if (logoutReason) return;
      const now = Date.now();
      if (now - lastActivityRef.current < 1000) return;
      lastActivityRef.current = now;
      markSessionActivity("interaction");
      resetIdleTimers();
    };

    activityEvents.forEach((evt) =>
      window.addEventListener(evt, handleActivity, { passive: true })
    );

    const handleVisibility = () => {
      if (!document.hidden) {
        resetIdleTimers();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      activityEvents.forEach((evt) =>
        window.removeEventListener(evt, handleActivity)
      );
      document.removeEventListener("visibilitychange", handleVisibility);
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

    const key = `${location.pathname}${location.search}`;
    if (lockedEventRef.current !== key) {
      lockedEventRef.current = key;
      trackEvent("ACCESS_BLOCKED", {
        path: location.pathname,
        query: location.search || undefined,
        amo_code: amoCode,
        reason: "read_only_subscription",
      });
    }

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
    trackEvent,
  ]);

  const deptLabel =
    ADMIN_NAV_ITEMS.find((d) => d.id === (activeDepartment as AdminNavId))
      ?.label ||
    DEPARTMENT_ITEMS.find((d) => d.id === (activeDepartment as any))?.label ||
    (activeDepartment || "Department");

  const userName = getUserDisplayName(currentUser);
  const userInitials = getUserInitials(currentUser);
  const resolveNotificationLink = (linkPath?: string | null): string | null => {
    if (!linkPath) return null;
    if (linkPath.startsWith("/profile/training")) {
      return `/maintenance/${amoCode}/${resolveDeptForTraining()}/training`;
    }
    if (linkPath.startsWith("/training/deferrals")) {
      return `/maintenance/${amoCode}/${resolveDeptForTraining()}/training#training-deferrals`;
    }
    if (linkPath.startsWith("/training")) {
      return `/maintenance/${amoCode}/${resolveDeptForTraining()}/training`;
    }
    return linkPath;
  };

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
  const trialHideKey = `ui_shell_trial_hide:${amoCode}:${currentUser?.id ?? "anon"}`;
  const trialSessionKey = `ui_shell_trial_hide_session:${amoCode}:${currentUser?.id ?? "anon"}`;

  useEffect(() => {
    if (!uiShellV2) return;
    const hideUntil = window.localStorage.getItem(trialHideKey);
    const hideUntilValue = hideUntil ? Number(hideUntil) : 0;
    const sessionHidden = window.sessionStorage.getItem(trialSessionKey) === "1";
    const shouldHide = sessionHidden || (hideUntilValue > 0 && hideUntilValue > Date.now());
    setTrialChipHidden(shouldHide);
  }, [trialHideKey, trialSessionKey, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2) return;
    if (!pollingError) {
      lastPollingToastRef.current = null;
      return;
    }
    if (lastPollingToastRef.current === pollingError) return;
    lastPollingToastRef.current = pollingError;
    pushToast({
      title: "Sync issue",
      message: pollingError,
      variant: "error",
    });
  }, [pollingError, pushToast, uiShellV2]);

  useEffect(() => {
    if (!trialMenuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!trialMenuRef.current?.contains(event.target as Node)) {
        setTrialMenuOpen(false);
      }
    };
    window.addEventListener("click", handleClick);
    return () => window.removeEventListener("click", handleClick);
  }, [trialMenuOpen]);

  const handleStaySignedIn = () => {
    resetIdleTimers();
  };

  const handleIdleLogout = () => {
    endSession("idle");
    clearIdleTimers();
    setIdleWarningOpen(false);
    setLogoutReason("idle");
  };

  const handleResumeLogin = () => {
    const code = resolveLoginSlug().trim();
    const target = code ? `/maintenance/${code}/login` : "/login";
    navigate(target, { replace: true, state: { from: returnPath } });
  };

  const handlePollingRetry = () => {
    setPollingError(null);
    runPolling("manual");
  };

  return (
    <BrandProvider
      nameOverride={amoLabel}
      preferStoredName={isAdminArea && isSuperuser}
      logoSource={isAdminArea && isSuperuser ? "platform" : "amo"}
    >
      <BrandContext.Consumer>
        {(brand) => {
          const sidebarContent = (
            <>
              <div className="sidebar__header">
                <BrandHeader variant="sidebar" />

                {uiShellV2 && (
                  <button
                    type="button"
                    className="sidebar__pin-btn"
                    onClick={() => setSidebarPinned((prev) => !prev)}
                    aria-label={sidebarPinned ? "Unpin sidebar" : "Pin sidebar"}
                    title={sidebarPinned ? "Unpin sidebar" : "Pin sidebar"}
                  >
                    {sidebarPinned ? "Unpin" : "Pin"}
                  </button>
                )}
              </div>

              <nav id="app-shell-sidebar-nav" className="sidebar__nav">
                {visibleAdminNav.map((nav) => {
                  const isActive = nav.id === activeDepartment;
                  const badge = adminBadgeMap[nav.id];
                  const badgeUnavailable =
                    overviewSummaryUnavailable || overviewSummaryDown || badge?.available === false;
                  const hasCount =
                    !!badge?.available && !badgeUnavailable && (badge?.count ?? 0) > 0;
                  const showBadge = hasCount || badgeUnavailable;
                  const badgeSeverity = badge?.severity || "info";
                  const badgeRoute = hasCount || badgeUnavailable ? badge?.route : undefined;
                  return (
                    <button
                      key={nav.id}
                      type="button"
                      onClick={() => handleAdminNav(nav.id, badgeRoute)}
                      className={
                        "sidebar__item" + (isActive ? " sidebar__item--active" : "")
                      }
                    >
                      <span className="sidebar__item-label">{nav.label}</span>
                      {nav.id !== "admin-overview" && showBadge && (
                        <span
                          className={`sidebar__badge sidebar__badge--${badgeSeverity} ${
                            hasCount ? "sidebar__badge--count" : "sidebar__badge--dot"
                          }`}
                        >
                          {hasCount ? badge?.count : ""}
                        </span>
                      )}
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

                {((!isAdminArea && visibleDepartments.length > 0) ||
                  (isAdminArea && visibleDepartments.length > 0)) && (
                  <div className="sidebar__divider" />
                )}

                {!isAdminArea && activeDepartment === "planning" && (
                  <>
                    <button
                      type="button"
                      onClick={() =>
                        navigateWithSidebarClose(`/maintenance/${amoCode}/planning/aircraft-import`)
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
                    <button
                      type="button"
                      onClick={() =>
                        navigateWithSidebarClose(`/maintenance/${amoCode}/planning/component-import`)
                      }
                      className={
                        "sidebar__item" +
                        (isComponentImportRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Import Components"
                      title="Import Components"
                    >
                      <span className="sidebar__item-label">Import Components</span>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        navigateWithSidebarClose(`/maintenance/${amoCode}/planning/aircraft-documents`)
                      }
                      className={
                        "sidebar__item" +
                        (isAircraftDocumentsRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Aircraft Documents"
                      title="Aircraft Documents"
                    >
                      <span className="sidebar__item-label">Aircraft Documents</span>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        navigateWithSidebarClose(`/maintenance/${amoCode}/planning/work-orders`)
                      }
                      className={
                        "sidebar__item" +
                        (isWorkOrdersRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Work Orders"
                      title="Work Orders"
                    >
                      <span className="sidebar__item-label">Work Orders</span>
                    </button>
                  </>
                )}

                {!isAdminArea &&
                  (activeDepartment === "production" ||
                    activeDepartment === "engineering") && (
                    <button
                      type="button"
                      onClick={() =>
                        navigateWithSidebarClose(`/maintenance/${amoCode}/${activeDepartment}/work-orders`)
                      }
                      className={
                        "sidebar__item" +
                        (isWorkOrdersRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Work Orders"
                      title="Work Orders"
                    >
                      <span className="sidebar__item-label">Work Orders</span>
                    </button>
                  )}

                {!isAdminArea && (
                  <button
                    type="button"
                    onClick={() =>
                      navigateWithSidebarClose(`/maintenance/${amoCode}/manuals`)
                    }
                    className={
                      "sidebar__item" + (isManualsRoute ? " sidebar__item--active" : "")
                    }
                    aria-label="Manuals"
                    title="Manuals"
                  >
                    <span className="sidebar__item-label">Manuals</span>
                  </button>
                )}

                {!isAdminArea && (
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
                )}

                {!isAdminArea && activeDepartment === "quality" && (
                  <>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/quality/qms`)}
                      className={
                        "sidebar__item" + ((isQmsRoute || isDocControlRoute) ? " sidebar__item--active" : "")
                      }
                      aria-label="Quality Management System"
                      title="Quality Management System"
                    >
                      <span className="sidebar__item-label">QMS Overview</span>
                    </button>
                    {(isQmsRoute || isDocControlRoute) && (
                      <div className="sidebar__qms-nav" aria-label="QMS modules">
                        {qmsNavItems.map((item) => {
                          const isActive = isPathMatch(location.pathname, item.path, item.matchPrefixes);
                          return (
                              <div key={item.id} className="sidebar__qms-node">
                                <button
                                  type="button"
                                  onClick={() => navigateWithSidebarClose(item.path)}
                                  className={
                                    "sidebar__item" +
                                    (isActive ? " sidebar__item--active" : "")
                                  }
                                >
                                  <span className="sidebar__item-label">{item.label}</span>
                                </button>
                                {isActive && item.children?.length ? (
                                  <div className="sidebar__qms-subnav" aria-label={`${item.label} subpages`}>
                                    {item.children.map((child) => {
                                      const childActive = isPathMatch(location.pathname, child.path, child.matchPrefixes);
                                      return (
                                        <button
                                          key={child.id}
                                          type="button"
                                          onClick={() => navigateWithSidebarClose(child.path)}
                                          className={
                                            "sidebar__item sidebar__item--sub" +
                                            (childActive ? " sidebar__item--active" : "")
                                          }
                                        >
                                          <span className="sidebar__item-label">{child.label}</span>
                                        </button>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                            );
                        })}
                      </div>
                    )}
                  </>
                )}

                {!isAdminArea && activeDepartment === "reliability" && (
                  <>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/reliability`)}
                      className={
                        "sidebar__item" +
                        (isReliabilityRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Reliability Reports"
                      title="Reliability Reports"
                    >
                      <span className="sidebar__item-label">Reliability Reports</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/dashboard`)}
                      className={
                        "sidebar__item" +
                        (isEhmDashboardRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring dashboard"
                      title="Engine Health Monitoring dashboard"
                    >
                      <span className="sidebar__item-label">EHM Dashboard</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/trends`)}
                      className={
                        "sidebar__item" + (isEhmTrendsRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring trends"
                      title="Engine Health Monitoring trends"
                    >
                      <span className="sidebar__item-label">EHM Trends</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/uploads`)}
                      className={
                        "sidebar__item" + (isEhmUploadsRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring uploads"
                      title="Engine Health Monitoring uploads"
                    >
                      <span className="sidebar__item-label">EHM Uploads</span>
                    </button>
                  </>
                )}
              </nav>
            </>
          );

          const sidebar = <aside ref={sidebarRef} className="app-shell__sidebar">{sidebarContent}</aside>;
          const trialChipVisible =
            uiShellV2 && isTrialing && subscription?.trial_ends_at && !trialChipHidden;

          const header = (
            <header className="app-shell__topbar">
              <div className="app-shell__topbar-title">
                <BrandHeader variant="topbar" />
                <div className="app-shell__topbar-context">
                  <div className="app-shell__topbar-heading">{deptLabel}</div>
                  <div className="app-shell__topbar-subtitle">{amoLabel}</div>
                </div>
              </div>

              <div className="app-shell__topbar-actions">
                {uiShellV2 && !isDesktopSidebar && !sidebarPinned && (
                  <button
                    type="button"
                    className="sidebar-mobile-toggle"
                    onClick={() => (sidebarDrawerOpen ? setSidebarDrawerOpen(false) : openSidebarDrawer({ source: "mobile" }))}
                    aria-label="Toggle navigation"
                    aria-expanded={sidebarDrawerOpen}
                    aria-controls="app-shell-sidebar-nav"
                  >
                    Menu
                  </button>
                )}
                {uiShellV2 && <LiveStatusIndicator />}
                {uiShellV2 && (
                  <span className={`app-shell__flight-chip ${isGoLive ? "app-shell__flight-chip--live" : "app-shell__flight-chip--demo"}`}>
                    {isGoLive ? "LIVE" : "DEMO"}
                  </span>
                )}
                {trialChipVisible && (
                  <div ref={trialMenuRef} style={{ position: "relative" }}>
                    <button
                      type="button"
                      className="app-shell__status-chip app-shell__status-chip--trial"
                      onClick={() => setTrialMenuOpen((prev) => !prev)}
                      aria-expanded={trialMenuOpen}
                      aria-haspopup="menu"
                    >
                      Trial{trialCountdown ? ` · ${trialCountdown} left` : ""}
                    </button>
                    {trialMenuOpen && (
                      <div className="app-shell__status-menu" role="menu">
                        <div className="app-shell__status-menu-meta">
                          {trialCountdown
                            ? `Trial ends in ${trialCountdown}.`
                            : "Trial ending soon."}
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setTrialMenuOpen(false);
                            navigate(`/maintenance/${amoCode}/upsell`);
                          }}
                        >
                          View plans
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setTrialMenuOpen(false);
                            navigateWithSidebarClose(`/maintenance/${amoCode}/admin/billing`);
                          }}
                        >
                          Convert to paid
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const hideUntil =
                              Date.now() + 7 * 24 * 60 * 60 * 1000;
                            window.localStorage.setItem(
                              trialHideKey,
                              String(hideUntil)
                            );
                            setTrialChipHidden(true);
                            setTrialMenuOpen(false);
                          }}
                        >
                          Hide for 7 days
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            window.sessionStorage.setItem(trialSessionKey, "1");
                            setTrialChipHidden(true);
                            setTrialMenuOpen(false);
                          }}
                        >
                          Hide this session
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <div ref={notificationsRef} className="notification-menu">
                  <button
                    type="button"
                    className="notification-bell"
                    aria-label="Training notifications"
                    aria-expanded={notificationsOpen}
                    onClick={() => setNotificationsOpen((v) => !v)}
                  >
                    <span className="notification-bell__icon">🔔</span>
                    {unreadNotifications > 0 ? (
                      <span className="notification-bell__badge">{unreadNotifications}</span>
                    ) : null}
                  </button>

                  {notificationsOpen && (
                    <div className="notification-panel notification-panel--drawer">
                      <div className="notification-panel__header">
                        <div>
                          <strong>Notifications</strong>
                          <div className="text-muted" style={{ fontSize: 12 }}>
                            {unreadNotifications} unread
                          </div>
                        </div>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={async () => {
                            await markAllTrainingNotificationsRead();
                            await refreshNotifications();
                          }}
                        >
                          Mark all read
                        </button>
                      </div>

                      {notificationsLoading && (
                        <div className="notification-panel__state">
                          Loading notifications…
                        </div>
                      )}

                      {notificationsError && (
                        <div className="notification-panel__state notification-panel__state--error">
                          {notificationsError}
                        </div>
                      )}

                      {!notificationsLoading && !notificationsError && (
                        <div className="notification-panel__list">
                          {notifications.map((note) => (
                            <button
                              type="button"
                              key={note.id}
                              className={`notification-item${
                                note.read_at ? "" : " notification-item--unread"
                              }`}
                              onClick={async () => {
                                if (!note.read_at) {
                                  await markTrainingNotificationRead(note.id, {});
                                }
                                setNotificationsOpen(false);
                                await refreshNotifications();
                                const target = resolveNotificationLink(note.link_path);
                                if (target) {
                                  navigate(target);
                                }
                              }}
                            >
                              <div className="notification-item__title">{note.title}</div>
                              {note.body ? (
                                <div className="notification-item__body">{note.body}</div>
                              ) : null}
                              <div className="notification-item__meta">
                                <span>{new Date(note.created_at).toLocaleString()}</span>
                                <span className="badge badge--neutral">{note.severity}</span>
                              </div>
                            </button>
                          ))}
                          {notifications.length === 0 ? (
                            <div className="notification-panel__state">
                              No notifications yet.
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}
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
                    <span className="profile-menu__caret">
                      {profileOpen ? "▲" : "▼"}
                    </span>
                  </button>

                  {profileOpen && (
                    <div role="menu" className="profile-drawer">
                      <div className="profile-drawer__header">
                        <div className="profile-drawer__avatar">{userInitials}</div>
                        <div>
                          <div className="profile-drawer__name">{userName}</div>
                          <div className="profile-drawer__meta">Profile & settings</div>
                        </div>
                      </div>

                      <button
                        type="button"
                        role="menuitem"
                        className="profile-drawer__item"
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
                        className="profile-drawer__item"
                        onClick={() => {
                          setProfileOpen(false);
                          const dept = resolveDeptForTraining();
                          navigate(`/maintenance/${amoCode}/${dept}/settings/widgets`);
                        }}
                      >
                        Dashboard widgets
                      </button>

                      <button
                        type="button"
                        role="menuitem"
                        className="profile-drawer__item"
                        onClick={() => {
                          setProfileOpen(false);
                          toggleColorScheme();
                        }}
                      >
                        {colorScheme === "system"
                          ? "Theme: System (switch to dark)"
                          : colorScheme === "dark"
                            ? "Theme: Dark (switch to light)"
                            : "Theme: Light (switch to system)"}
                      </button>

                      {isSuperuser && (
                        <>
                          <div className="profile-drawer__divider" />
                          <div className="profile-drawer__prefs">
                            <div className="profile-drawer__prefs-title">Superuser Runtime Controls</div>
                            <label className="profile-drawer__pref-row">
                              <span>Audio chirper</span>
                              <input
                                type="checkbox"
                                checked={notificationPrefs.audioEnabled}
                                onChange={(event) => {
                                  setNotificationPreferences({ audioEnabled: event.target.checked });
                                  setNotificationPrefs(getNotificationPreferences());
                                }}
                              />
                            </label>
                            <label className="profile-drawer__pref-row">
                              <span>Desktop alerts</span>
                              <input
                                type="checkbox"
                                checked={notificationPrefs.desktopEnabled}
                                onChange={(event) => {
                                  setNotificationPreferences({ desktopEnabled: event.target.checked });
                                  setNotificationPrefs(getNotificationPreferences());
                                }}
                              />
                            </label>
                            <label className="profile-drawer__pref-row">
                              <span>Photo uploads</span>
                              <input
                                type="checkbox"
                                checked={notificationPrefs.enablePhotoUploads}
                                onChange={(event) => {
                                  setNotificationPreferences({ enablePhotoUploads: event.target.checked });
                                  setNotificationPrefs(getNotificationPreferences());
                                }}
                              />
                            </label>
                            <label className="profile-drawer__pref-row">
                              <span>Video uploads</span>
                              <input
                                type="checkbox"
                                checked={notificationPrefs.enableVideoUploads}
                                onChange={(event) => {
                                  setNotificationPreferences({ enableVideoUploads: event.target.checked });
                                  setNotificationPrefs(getNotificationPreferences());
                                }}
                              />
                            </label>
                            <label className="profile-drawer__pref-row">
                              <span>Notification poll (sec)</span>
                              <input
                                type="number"
                                min={15}
                                max={600}
                                step={5}
                                value={notificationPrefs.pollIntervalSeconds}
                                onChange={(event) => {
                                  setNotificationPreferences({ pollIntervalSeconds: Number(event.target.value) || 60 });
                                  setNotificationPrefs(getNotificationPreferences());
                                }}
                              />
                            </label>
                          </div>
                        </>
                      )}

                      <div className="profile-drawer__divider" />

                      <button
                        type="button"
                        role="menuitem"
                        className="profile-drawer__item profile-drawer__item--danger"
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
              </div>
            </header>
          );

          const sessionOverlay = (idleWarningOpen || logoutReason) && (
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
          );

          if (!uiShellV2) {
            return (
              <div className={shellClassName}>
                {sidebar}
                <main className="app-shell__main">
                  {header}

                  {showPollingErrorBanner && pollingError && (
                    <div
                      className="info-banner info-banner--warning"
                      role="status"
                      style={{ margin: "12px 0" }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 12,
                        }}
                      >
                        <span>{pollingError}</span>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={handlePollingRetry}
                        >
                          Retry refresh
                        </button>
                      </div>
                    </div>
                  )}

                  {isTrialing && subscription?.trial_ends_at && (
                    <div className="info-banner info-banner--soft" style={{ margin: "12px 16px 0" }}>
                      <div>
                        <strong>Trial in progress</strong>
                        <p className="text-muted" style={{ margin: 0 }}>
                          {trialCountdown ? `Ends in ${trialCountdown}.` : "Trial ending soon."}{" "}
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
                    <span>© {currentYear} {brand.name}.</span>
                    <span>{brand.tagline || "All rights reserved."}</span>
                  </footer>
                </main>
                {sessionOverlay}
              </div>
            );
          }

          return (
            <>
              {uiShellV2 && isDesktopSidebar && !sidebarPinned && (
                <div ref={sidebarHotzoneRef} className="app-shell__edge-hotzone" aria-hidden="true" />
              )}
              {uiShellV2 && !isDesktopSidebar && !sidebarPinned && sidebarDrawerOpen && (
                <button
                  type="button"
                  className="app-shell__mobile-scrim"
                  aria-label="Close navigation menu"
                  onClick={() => setSidebarDrawerOpen(false)}
                />
              )}
              <AppShellV2
                className={shellClassName}
                sidebar={sidebar}
                header={header}
                focusMode={false}
              >
                {isExpired && (
                  <div className={`card ${isReadOnly ? "card--error" : "card--warning"}`}>
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

                {children}

                <footer className="app-shell__footer">
                  <span>© {currentYear} {brand.name}.</span>
                  <span>{brand.tagline || "All rights reserved."}</span>
                </footer>
              </AppShellV2>
              {sessionOverlay}
            </>
          );
        }}
      </BrandContext.Consumer>
    </BrandProvider>
  );
};

export default DepartmentLayout;

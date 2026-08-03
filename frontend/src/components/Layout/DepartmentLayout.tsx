import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bell,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  CreditCard,
  Factory,
  FileText,
  Gauge,
  GraduationCap,
  Home,
  LogOut,
  Mail,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  User,
  Users,
  Warehouse,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";

import {
  buildPortalNavigation,
  isPortalPathActive,
  type PortalNavGroup,
  type PortalNavIcon,
  type PortalNavItem,
} from "../../app/portalRouteManifest";
import {
  endSession,
  extendSession,
  getCachedUser,
  getTokenSecondsRemaining,
  markSessionActivity,
} from "../../services/auth";
import {
  activateAdminProfile,
  deactivateAdminProfile,
  fetchAdminProfileState,
  readCachedAdminProfileState,
  type AdminProfileState,
} from "../../services/adminProfileMode";
import { useColorScheme } from "../../hooks/useColorScheme";
import { BrandContext } from "../Brand/BrandContext";
import { BrandLogo } from "../Brand/BrandLogo";
import { BrandProvider } from "../Brand/BrandProvider";
import LiveStatusIndicator from "../realtime/LiveStatusIndicator";
import "../../styles/components/tenant-shell.css";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const IDLE_WARNING_MS = 60 * 1000;
const SIDEBAR_MIN = 236;
const SIDEBAR_MAX = 420;
const SIDEBAR_DEFAULT = 284;

const ICONS: Record<PortalNavIcon, LucideIcon> = {
  home: Home,
  work: ClipboardCheck,
  calendar: CalendarDays,
  planning: CalendarDays,
  production: Factory,
  maintenance: Wrench,
  quality: ShieldCheck,
  documents: FileText,
  records: BookOpen,
  rostering: CalendarDays,
  training: GraduationCap,
  reliability: Gauge,
  stores: Warehouse,
  safety: ShieldCheck,
  workshops: Wrench,
  settings: Settings,
  users: Users,
  billing: CreditCard,
  mail: Mail,
  chart: BarChart3,
};

const ACCENTS = [
  { id: "tenant", label: "Tenant" },
  { id: "blue", label: "Blue" },
  { id: "teal", label: "Teal" },
  { id: "green", label: "Green" },
  { id: "amber", label: "Amber" },
  { id: "violet", label: "Violet" },
] as const;

type AccentId = (typeof ACCENTS)[number]["id"];

type NavBranchProps = {
  item: PortalNavItem;
  pathname: string;
  level: 0 | 1 | 2;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onNavigate: (path: string) => void;
};

function clampSidebarWidth(value: number): number {
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(value)));
}

function getStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  const value = window.localStorage.getItem(key);
  if (value === null) return fallback;
  return value === "1";
}

function getStoredWidth(key: string): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT;
  const value = Number(window.localStorage.getItem(key));
  return Number.isFinite(value) ? clampSidebarWidth(value) : SIDEBAR_DEFAULT;
}

function labelForDepartment(value: string): string {
  const labels: Record<string, string> = {
    planning: "Planning",
    production: "Production",
    maintenance: "Maintenance",
    quality: "Quality & Compliance",
    "document-control": "Document Control",
    reliability: "Reliability",
    safety: "Safety Management",
    stores: "Procurement & Stores",
    workshops: "Workshops",
    admin: "Administration",
  };
  return labels[value] || value.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function NavBranch({
  item,
  pathname,
  level,
  expanded,
  onToggle,
  onNavigate,
}: NavBranchProps): React.ReactElement {
  const active = isPortalPathActive(pathname, item);
  const childActive = item.children?.some((child) => isPortalPathActive(pathname, child)) ?? false;
  const open = expanded.has(item.id) || childActive;
  const Icon = level === 0 && item.icon ? ICONS[item.icon] : null;
  const nextLevel = Math.min(2, level + 1) as 0 | 1 | 2;

  return (
    <div className={`tenant-nav__branch tenant-nav__branch--level-${level}`}>
      <div className={`tenant-nav__row${active ? " is-active" : ""}${childActive ? " has-active-child" : ""}`}>
        <button
          type="button"
          className="tenant-nav__link"
          onClick={() => onNavigate(item.path)}
          aria-current={active ? "page" : undefined}
          title={item.label}
        >
          {Icon ? <Icon size={17} strokeWidth={2} aria-hidden="true" /> : <span className="tenant-nav__rail" aria-hidden="true" />}
          <span>{item.label}</span>
        </button>
        {item.children?.length ? (
          <button
            type="button"
            className="tenant-nav__expand"
            onClick={() => onToggle(item.id)}
            aria-label={`${open ? "Collapse" : "Expand"} ${item.label}`}
            aria-expanded={open}
          >
            {open ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
          </button>
        ) : null}
      </div>
      {open && item.children?.length ? (
        <div className="tenant-nav__children">
          {item.children.map((child) => (
            <NavBranch
              key={child.id}
              item={child}
              pathname={pathname}
              level={nextLevel}
              expanded={expanded}
              onToggle={onToggle}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function NavigationGroups({
  groups,
  pathname,
  expanded,
  onToggle,
  onNavigate,
}: {
  groups: PortalNavGroup[];
  pathname: string;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onNavigate: (path: string) => void;
}): React.ReactElement {
  return (
    <nav id="tenant-navigation" className="tenant-nav" aria-label="Portal navigation">
      {groups.map((group) => (
        <section key={group.id} className="tenant-nav__group" aria-labelledby={`tenant-nav-${group.id}`}>
          <h2 id={`tenant-nav-${group.id}`}>{group.label}</h2>
          <div className="tenant-nav__items">
            {group.items.map((item) => (
              <NavBranch
                key={item.id}
                item={item}
                pathname={pathname}
                level={0}
                expanded={expanded}
                onToggle={onToggle}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </section>
      ))}
    </nav>
  );
}

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
  showPollingErrorBanner = false,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = getCachedUser();
  const identity = `${currentUser?.id || "anon"}:${currentUser?.amo_id || amoCode}`;
  const pinnedKey = `amo_sidebar_pinned:${identity}`;
  const widthKey = `amo_sidebar_width:${identity}`;
  const accentKey = `amo_portal_accent:${identity}`;
  const { scheme, setScheme } = useColorScheme();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pinned, setPinned] = useState(() => getStoredBoolean(pinnedKey, false));
  const [sidebarWidth, setSidebarWidth] = useState(() => getStoredWidth(widthKey));
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [profileOpen, setProfileOpen] = useState(false);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [accent, setAccent] = useState<AccentId>(() => {
    if (typeof window === "undefined") return "tenant";
    const saved = window.localStorage.getItem(accentKey) as AccentId | null;
    return ACCENTS.some((item) => item.id === saved) ? (saved as AccentId) : "tenant";
  });
  const [adminProfile, setAdminProfile] = useState<AdminProfileState | null>(() => readCachedAdminProfileState(amoCode));
  const [adminProfileBusy, setAdminProfileBusy] = useState(false);
  const [adminProfileError, setAdminProfileError] = useState<string | null>(null);
  const [idleWarning, setIdleWarning] = useState(false);
  const [idleSeconds, setIdleSeconds] = useState(Math.ceil(IDLE_WARNING_MS / 1000));

  const profileRef = useRef<HTMLDivElement | null>(null);
  const lastActivityRef = useRef(Date.now());
  const warningTimerRef = useRef<number | null>(null);
  const logoutTimerRef = useRef<number | null>(null);
  const countdownRef = useRef<number | null>(null);

  const navigation = useMemo(
    () => buildPortalNavigation({
      amoCode,
      user: currentUser,
      contextDepartment: activeDepartment,
      activeDepartment,
      adminModeActive: Boolean(adminProfile?.active),
    }),
    [activeDepartment, adminProfile?.active, amoCode, currentUser],
  );

  const homePath = navigation[0]?.items.find((item) => item.id === "home")?.path || `/maintenance/${encodeURIComponent(amoCode)}`;

  useEffect(() => {
    let active = true;
    fetchAdminProfileState(amoCode)
      .then((state) => {
        if (active) setAdminProfile(state);
      })
      .catch(() => {
        if (active && !adminProfile) setAdminProfile({ eligible: false, active: false });
      });
    return () => { active = false; };
  }, [amoCode]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.portalAccent = accent;
    document.body.dataset.portalAccent = accent;
    window.localStorage.setItem(accentKey, accent);
  }, [accent, accentKey]);

  useEffect(() => {
    window.localStorage.setItem(pinnedKey, pinned ? "1" : "0");
  }, [pinned, pinnedKey]);

  useEffect(() => {
    window.localStorage.setItem(widthKey, String(sidebarWidth));
  }, [sidebarWidth, widthKey]);

  useEffect(() => {
    if (!profileOpen) return;
    const onPointer = (event: PointerEvent) => {
      if (event.target instanceof Node && !profileRef.current?.contains(event.target)) {
        setProfileOpen(false);
        setAppearanceOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
        setAppearanceOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  useEffect(() => {
    const activeIds = new Set<string>();
    const walk = (items: PortalNavItem[]) => {
      for (const item of items) {
        if (item.children?.some((child) => isPortalPathActive(location.pathname, child))) activeIds.add(item.id);
        if (item.children) walk(item.children);
      }
    };
    navigation.forEach((group) => walk(group.items));
    if (activeIds.size) setExpanded((previous) => new Set([...previous, ...activeIds]));
  }, [location.pathname, navigation]);

  const clearIdleTimers = useCallback(() => {
    if (warningTimerRef.current) window.clearTimeout(warningTimerRef.current);
    if (logoutTimerRef.current) window.clearTimeout(logoutTimerRef.current);
    if (countdownRef.current) window.clearInterval(countdownRef.current);
    warningTimerRef.current = null;
    logoutTimerRef.current = null;
    countdownRef.current = null;
  }, []);

  const scheduleIdleTimers = useCallback(() => {
    clearIdleTimers();
    warningTimerRef.current = window.setTimeout(() => {
      setIdleWarning(true);
      setIdleSeconds(Math.ceil(IDLE_WARNING_MS / 1000));
      countdownRef.current = window.setInterval(() => {
        setIdleSeconds((value) => Math.max(0, value - 1));
      }, 1000);
    }, IDLE_TIMEOUT_MS - IDLE_WARNING_MS);
    logoutTimerRef.current = window.setTimeout(() => {
      endSession("idle");
      navigate(`/maintenance/${encodeURIComponent(amoCode)}/login`, { replace: true });
    }, IDLE_TIMEOUT_MS);
  }, [amoCode, clearIdleTimers, navigate]);

  useEffect(() => {
    scheduleIdleTimers();
    let lastBroadcast = 0;
    let lastExtend = 0;
    const handleActivity = (event: Event) => {
      const now = Date.now();
      lastActivityRef.current = now;
      if (idleWarning) {
        setIdleWarning(false);
        setIdleSeconds(Math.ceil(IDLE_WARNING_MS / 1000));
        scheduleIdleTimers();
      }
      if (now - lastBroadcast > 10_000) {
        lastBroadcast = now;
        markSessionActivity(event.type);
      }
      const remaining = getTokenSecondsRemaining();
      if (remaining !== null && remaining <= 300 && now - lastExtend > 60_000) {
        lastExtend = now;
        void extendSession(`shell:${event.type}`).catch(() => undefined);
      }
    };
    const events = ["pointerdown", "keydown", "wheel", "touchstart", "focus"];
    events.forEach((name) => window.addEventListener(name, handleActivity, { passive: true, capture: true }));
    return () => {
      events.forEach((name) => window.removeEventListener(name, handleActivity, { capture: true } as EventListenerOptions));
      clearIdleTimers();
    };
  }, [clearIdleTimers, idleWarning, scheduleIdleTimers]);

  const navigateFromDrawer = useCallback((path: string) => {
    navigate(path);
    if (!pinned) setDrawerOpen(false);
  }, [navigate, pinned]);

  const toggleExpanded = useCallback((id: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const startResize = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    if (!pinned) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const onMove = (moveEvent: PointerEvent) => setSidebarWidth(clampSidebarWidth(startWidth + moveEvent.clientX - startX));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }, [pinned, sidebarWidth]);

  const toggleAdminProfile = useCallback(async () => {
    if (!adminProfile?.eligible || adminProfileBusy) return;
    setAdminProfileBusy(true);
    setAdminProfileError(null);
    try {
      const next = adminProfile.active
        ? await deactivateAdminProfile(amoCode)
        : await activateAdminProfile(amoCode);
      setAdminProfile(next);
      setProfileOpen(false);
      navigate(next.active ? `/maintenance/${encodeURIComponent(amoCode)}/admin/overview` : homePath);
    } catch (error) {
      setAdminProfileError(error instanceof Error ? error.message : "Admin profile could not be changed.");
    } finally {
      setAdminProfileBusy(false);
    }
  }, [adminProfile, adminProfileBusy, amoCode, homePath, navigate]);

  const handleSignOut = useCallback(() => {
    endSession("manual");
    navigate(`/maintenance/${encodeURIComponent(amoCode)}/login`, { replace: true });
  }, [amoCode, navigate]);

  const drawerVisible = pinned || drawerOpen;
  const shellStyle = {
    "--tenant-sidebar-width": `${sidebarWidth}px`,
  } as React.CSSProperties;

  return (
    <BrandProvider nameOverride={amoCode.toUpperCase()} logoSource="amo">
      <BrandContext.Consumer>
        {(brand) => (
          <div
            className={`tenant-shell${pinned ? " tenant-shell--pinned" : ""}${drawerVisible ? " tenant-shell--drawer-open" : ""}`}
            style={shellStyle}
          >
            {!pinned && drawerOpen ? (
              <button className="tenant-shell__scrim" type="button" aria-label="Close navigation" onClick={() => setDrawerOpen(false)} />
            ) : null}

            <aside className="tenant-shell__sidebar" aria-label="Portal navigation drawer" aria-hidden={!drawerVisible}>
              <header className="tenant-shell__sidebar-header">
                <button className="tenant-shell__brand" type="button" onClick={() => navigateFromDrawer(homePath)} title="Open department home">
                  <BrandLogo size={30} />
                  <span>
                    <strong>{brand.name || amoCode.toUpperCase()}</strong>
                    <small>AMO Portal</small>
                  </span>
                </button>
                <div className="tenant-shell__sidebar-actions">
                  <button
                    type="button"
                    className="tenant-shell__icon-button"
                    onClick={() => setPinned((value) => !value)}
                    aria-label={pinned ? "Unpin navigation" : "Pin navigation"}
                    title={pinned ? "Unpin navigation" : "Pin navigation"}
                  >
                    {pinned ? <PinOff size={16} /> : <Pin size={16} />}
                  </button>
                  {!pinned ? (
                    <button type="button" className="tenant-shell__icon-button" onClick={() => setDrawerOpen(false)} aria-label="Close navigation">
                      <X size={17} />
                    </button>
                  ) : null}
                </div>
              </header>

              <NavigationGroups
                groups={navigation}
                pathname={location.pathname}
                expanded={expanded}
                onToggle={toggleExpanded}
                onNavigate={navigateFromDrawer}
              />

              {pinned ? (
                <button
                  type="button"
                  className="tenant-shell__resize-handle"
                  onPointerDown={startResize}
                  aria-label="Resize navigation"
                  title="Drag to resize navigation"
                />
              ) : null}
            </aside>

            <div className="tenant-shell__workspace">
              <header className="tenant-shell__topbar">
                <div className="tenant-shell__topbar-start">
                  <button
                    type="button"
                    className="tenant-shell__menu-button"
                    onClick={() => pinned ? setPinned(false) : setDrawerOpen((value) => !value)}
                    aria-label={drawerVisible ? "Close navigation" : "Open navigation"}
                    aria-expanded={drawerVisible}
                    aria-controls="tenant-navigation"
                  >
                    {drawerVisible && !pinned ? <PanelLeftClose size={19} /> : pinned ? <PanelLeftClose size={19} /> : <Menu size={20} />}
                  </button>
                  <button className="tenant-shell__compact-brand" type="button" onClick={() => navigate(homePath)} aria-label="Open department home">
                    <BrandLogo size={22} />
                  </button>
                  <div className="tenant-shell__context">
                    <strong>{labelForDepartment(activeDepartment)}</strong>
                    <span>{brand.name || amoCode.toUpperCase()}</span>
                  </div>
                  {adminProfile?.active ? (
                    <span className="tenant-shell__admin-chip"><Sparkles size={13} /> Admin profile</span>
                  ) : null}
                </div>

                <div className="tenant-shell__topbar-actions">
                  <LiveStatusIndicator compact />
                  <button
                    type="button"
                    className="tenant-shell__icon-button"
                    onClick={() => navigateFromDrawer(`/maintenance/${encodeURIComponent(amoCode)}/quality/inbox/assigned-to-me`)}
                    aria-label="Notifications and assigned work"
                    title="Notifications and assigned work"
                  >
                    <Bell size={17} />
                  </button>
                  <div className="tenant-shell__profile" ref={profileRef}>
                    <button
                      type="button"
                      className="tenant-shell__profile-trigger"
                      onClick={() => setProfileOpen((value) => !value)}
                      aria-expanded={profileOpen}
                    >
                      <span className="tenant-shell__avatar">
                        {(currentUser?.first_name?.[0] || currentUser?.full_name?.[0] || "U").toUpperCase()}
                        {(currentUser?.last_name?.[0] || "").toUpperCase()}
                      </span>
                      <span className="tenant-shell__profile-name">{currentUser?.full_name || currentUser?.email || "User"}</span>
                      <ChevronDown size={14} aria-hidden="true" />
                    </button>

                    {profileOpen ? (
                      <div className="tenant-shell__profile-menu" role="menu">
                        <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate(`/maintenance/${encodeURIComponent(amoCode)}/profile`); }}>
                          <User size={15} /> View profile
                        </button>

                        {adminProfile?.eligible ? (
                          <button type="button" role="menuitem" onClick={() => void toggleAdminProfile()} disabled={adminProfileBusy}>
                            {adminProfile.active ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
                            {adminProfileBusy ? "Updating admin profile…" : adminProfile.active ? "Admin profile Off" : "Admin profile On"}
                          </button>
                        ) : null}

                        <button type="button" role="menuitem" onClick={() => setAppearanceOpen((value) => !value)} aria-expanded={appearanceOpen}>
                          <SlidersHorizontal size={15} /> Appearance
                          <ChevronRight size={14} className="tenant-shell__profile-chevron" />
                        </button>

                        {appearanceOpen ? (
                          <div className="tenant-shell__appearance" aria-label="Appearance settings">
                            <label>
                              <span>Theme</span>
                              <select value={scheme} onChange={(event) => setScheme(event.target.value as "system" | "light" | "dark")}>
                                <option value="system">System</option>
                                <option value="light">Light</option>
                                <option value="dark">Dark</option>
                              </select>
                            </label>
                            <div className="tenant-shell__accent-picker">
                              <span>Accent</span>
                              <div>
                                {ACCENTS.map((item) => (
                                  <button
                                    key={item.id}
                                    type="button"
                                    className={`tenant-shell__accent tenant-shell__accent--${item.id}${accent === item.id ? " is-selected" : ""}`}
                                    onClick={() => setAccent(item.id)}
                                    aria-label={`Use ${item.label} accent`}
                                    aria-pressed={accent === item.id}
                                    title={item.label}
                                  />
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : null}

                        {adminProfileError ? <div className="tenant-shell__profile-error" role="alert">{adminProfileError}</div> : null}
                        <div className="tenant-shell__profile-divider" />
                        <button type="button" role="menuitem" className="is-danger" onClick={handleSignOut}>
                          <LogOut size={15} /> Sign out
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              </header>

              <main className="tenant-shell__main">
                {showPollingErrorBanner ? null : null}
                <div className="tenant-shell__content">{children}</div>
              </main>
            </div>

            {idleWarning ? (
              <div className="tenant-shell__session-overlay" role="dialog" aria-modal="true" aria-labelledby="idle-title">
                <div className="tenant-shell__session-card">
                  <h2 id="idle-title">Inactivity warning</h2>
                  <p>Your session will end in <strong>{idleSeconds}s</strong>.</p>
                  <div>
                    <button type="button" className="btn btn-secondary" onClick={handleSignOut}>Sign out</button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        lastActivityRef.current = Date.now();
                        setIdleWarning(false);
                        void extendSession("idle-warning").catch(() => undefined);
                        scheduleIdleTimers();
                      }}
                    >
                      Stay signed in
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </BrandContext.Consumer>
    </BrandProvider>
  );
};

export default DepartmentLayout;

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import {
  endSession,
  getCachedUser,
  getToken,
  isAuthenticated,
  type PortalUser,
} from "../../../services/auth";
import {
  PlatformAccessVerificationError,
  verifyCurrentPlatformUser,
} from "../../../services/platformAccess";
import { platformConsoleApi, type PlatformConsoleSearchResult } from "../../../services/platformConsole";
import { persistPlatformDataMode, readPlatformDataMode, withPlatformDataMode } from "../../../services/platformEnvironment";
import "../../../styles/platform-control.css";
import { platformNavSections, type PlatformNavItem } from "./platformNavigation";
import { usePlatformRealtime, type PlatformConsoleSnapshot } from "./usePlatformRealtime";

export const StatusBadge: React.FC<{ value?: unknown }> = ({ value }) => {
  const text = String(value ?? "UNKNOWN");
  const v = text.toUpperCase();
  const cls =
    v.includes("ACTIVE") || v.includes("HEALTHY") || v.includes("SUCCEEDED") || v === "OPEN" || v === "LIVE" || v === "REAL"
      ? "ok"
      : v.includes("FAIL") || v.includes("CRITICAL") || v.includes("LOCK") || v.includes("ERROR") || v.includes("DENIED") || v.includes("OFFLINE")
        ? "bad"
        : v.includes("WARN") || v.includes("PENDING") || v.includes("DEGRADED") || v.includes("TRIAL") || v.includes("CONNECTING") || v === "DEMO"
          ? "warn"
          : "neutral";
  return <span className={`platform-badge ${cls}`}>{text}</span>;
};

export const MetricCard: React.FC<{
  label: string;
  value: React.ReactNode;
  caption?: React.ReactNode;
  tone?: "blue" | "green" | "amber" | "red" | "purple";
  mark?: React.ReactNode;
}> = ({ label, value, caption, tone = "blue", mark }) => (
  <section className={`platform-card platform-metric platform-metric--${tone}`}>
    <div className="platform-metric__shine" />
    <div className="platform-metric__top">
      <div className="label">{label}</div>
      {mark ? <span className="platform-metric__mark">{mark}</span> : null}
    </div>
    <div className="value">{value ?? "-"}</div>
    {caption ? <div className="caption">{caption}</div> : null}
  </section>
);

type PlatformTheme = "dark" | "light" | "system";
type PlatformAccessState = "checking" | "allowed" | "denied";

const THEME_KEY = "amo_platform_theme";
const ACCENT_KEY = "amo_platform_accent";
const DEFAULT_ACCENT = "#3b67f2";
const ACCENTS = ["#4f46e5", "#2563eb", "#0f8b8d", "#a16207", "#c026d3"];
const PLATFORM_ACCESS_CACHE_TTL_MS = 15_000;
const PLATFORM_ACCESS_REVALIDATE_MS = 30_000;

let verifiedPlatformAccess: { token: string; user: PortalUser; verifiedAt: number } | null = null;
let platformVerificationInFlight: { token: string; promise: Promise<PortalUser> } | null = null;

function resolveSystemTheme(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function accentRgb(hex: string): string {
  const clean = hex.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(clean)) return "59, 103, 242";
  return `${Number.parseInt(clean.slice(0, 2), 16)}, ${Number.parseInt(clean.slice(2, 4), 16)}, ${Number.parseInt(clean.slice(4, 6), 16)}`;
}

function navTarget(item: PlatformNavItem) {
  const [pathname, rawQuery = ""] = item.to.split("?");
  return { pathname, query: new URLSearchParams(rawQuery) };
}

function navIsActive(item: PlatformNavItem, pathname: string, search: string) {
  const target = navTarget(item);
  if (target.pathname !== pathname) return false;
  const tab = target.query.get("tab");
  const currentTab = new URLSearchParams(search).get("tab");
  return tab ? tab === currentTab : !currentTab;
}

function badgeValue(snapshot: PlatformConsoleSnapshot | null, key?: string): React.ReactNode {
  if (!key || !snapshot) return null;
  const value = snapshot[key];
  if (value === undefined || value === null || value === "" || value === 0) return null;
  return String(value);
}

function cachedSuperuserForActiveToken(): PortalUser | null {
  if (!isAuthenticated()) return null;
  const user = getCachedUser();
  return user?.is_superuser ? user : null;
}

function initialPlatformAccessState(): PlatformAccessState {
  if (cachedSuperuserForActiveToken()) return "allowed";
  return isAuthenticated() ? "checking" : "denied";
}

function verifyPlatformUserForActiveToken(): Promise<PortalUser> {
  const token = getToken();
  if (!token) return Promise.reject(new Error("No authenticated platform session."));

  if (
    verifiedPlatformAccess?.token === token
    && Date.now() - verifiedPlatformAccess.verifiedAt < PLATFORM_ACCESS_CACHE_TTL_MS
  ) {
    return Promise.resolve(verifiedPlatformAccess.user);
  }
  if (platformVerificationInFlight?.token === token) {
    return platformVerificationInFlight.promise;
  }

  const promise = verifyCurrentPlatformUser()
    .then((freshUser) => {
      if (getToken() === token && freshUser.is_superuser) {
        verifiedPlatformAccess = { token, user: freshUser, verifiedAt: Date.now() };
      } else if (verifiedPlatformAccess?.token === token) {
        verifiedPlatformAccess = null;
      }
      return freshUser;
    })
    .catch((error: unknown) => {
      if (verifiedPlatformAccess?.token === token) verifiedPlatformAccess = null;
      throw error;
    })
    .finally(() => {
      if (platformVerificationInFlight?.token === token) platformVerificationInFlight = null;
    });

  platformVerificationInFlight = { token, promise };
  return promise;
}

export const PlatformShell: React.FC<{
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, subtitle, actions, children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const platformMode = readPlatformDataMode(location.search);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const searchRequestRef = useRef(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const [theme, setTheme] = useState<PlatformTheme>(() => {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "dark" || stored === "light" || stored === "system" ? stored : "dark";
  });
  const [systemTheme, setSystemTheme] = useState<"dark" | "light">(resolveSystemTheme);
  const [accent, setAccent] = useState(() => window.localStorage.getItem(ACCENT_KEY) || DEFAULT_ACCENT);
  const [bootstrapSnapshot, setBootstrapSnapshot] = useState<PlatformConsoleSnapshot | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<PlatformConsoleSearchResult[]>([]);
  const [user, setUser] = useState<PortalUser | null>(() => getCachedUser());
  const [accessState, setAccessState] = useState<PlatformAccessState>(initialPlatformAccessState);
  const [accessError, setAccessError] = useState<string | null>(null);
  const [accessAttempt, setAccessAttempt] = useState(0);
  const realtime = usePlatformRealtime(accessState === "allowed");
  const snapshot = realtime.snapshot ?? bootstrapSnapshot;
  const resolvedTheme = theme === "system" ? systemTheme : theme;
  const style = {
    "--platform-accent": accent,
    "--platform-accent-rgb": accentRgb(accent),
  } as React.CSSProperties;

  useEffect(() => {
    persistPlatformDataMode(platformMode);
  }, [platformMode]);

  useEffect(() => {
    let active = true;
    if (!isAuthenticated()) return () => { active = false; };

    const applyVerification = () => {
      void verifyPlatformUserForActiveToken()
        .then((freshUser) => {
          if (!active) return;
          setUser(freshUser);
          setAccessError(freshUser.is_superuser ? null : "Platform superuser access is required.");
          setAccessState(freshUser.is_superuser ? "allowed" : "denied");
        })
        .catch((error: unknown) => {
          if (!active) return;
          const message = error instanceof Error ? error.message : "Unable to verify platform access.";
          if (error instanceof PlatformAccessVerificationError && error.status >= 400 && error.status < 500) {
            setUser(null);
            setAccessError(message);
            setAccessState("denied");
            return;
          }
          const fallbackUser = cachedSuperuserForActiveToken();
          setUser(fallbackUser ?? getCachedUser());
          setAccessError(message);
          setAccessState(fallbackUser ? "allowed" : "denied");
        });
    };

    applyVerification();
    const revalidationTimer = window.setInterval(applyVerification, PLATFORM_ACCESS_REVALIDATE_MS);
    return () => {
      active = false;
      window.clearInterval(revalidationTimer);
    };
  }, [accessAttempt]);

  useEffect(() => {
    if (accessState !== "allowed") return;
    void platformConsoleApi.bootstrap().then(setBootstrapSnapshot).catch(() => undefined);
  }, [accessState]);

  useEffect(() => {
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => setSystemTheme(media.matches ? "light" : "dark");
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ACCENT_KEY, accent);
  }, [accent]);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") {
        setThemeOpen(false);
        setResults([]);
        searchRef.current?.blur();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  useEffect(() => {
    const clean = query.trim();
    const requestId = ++searchRequestRef.current;
    if (clean.length < 2) return;

    const timer = window.setTimeout(() => {
      setSearching(true);
      void platformConsoleApi.search(clean)
        .then((response) => {
          if (requestId === searchRequestRef.current) setResults(response.items || []);
        })
        .catch(() => {
          if (requestId === searchRequestRef.current) setResults([]);
        })
        .finally(() => {
          if (requestId === searchRequestRef.current) setSearching(false);
        });
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  const initials = useMemo(
    () => user?.full_name?.split(/\s+/).slice(0, 2).map((part) => part[0]).join("") || user?.email?.slice(0, 2)?.toUpperCase() || "SA",
    [user?.email, user?.full_name],
  );

  const signInWithPlatformAccount = () => {
    endSession("manual");
    navigate("/login", { replace: true });
  };

  if (accessState === "checking") {
    return (
      <div className="platform-shell" data-platform-theme={resolvedTheme} style={style}>
        <main className="platform-access-denied">
          <section className="platform-card" role="status" aria-live="polite">
            <h1>Verifying platform access</h1>
            <p>Confirming this session with the platform control plane…</p>
          </section>
        </main>
      </div>
    );
  }

  if (accessState !== "allowed" || !user?.is_superuser) {
    return (
      <div className="platform-shell" data-platform-theme={resolvedTheme} style={style}>
        <main className="platform-access-denied">
          <section className="platform-card">
            <h1>Platform access required</h1>
            <p>{accessError ? `Platform access could not be verified: ${accessError}` : "This console is available only to global platform superusers."}</p>
            {accessError && isAuthenticated() ? (
              <button
                className="platform-btn"
                onClick={() => {
                  setAccessError(null);
                  setAccessState("checking");
                  setAccessAttempt((attempt) => attempt + 1);
                }}
              >
                Retry access check
              </button>
            ) : null}
            <button className="platform-btn primary" onClick={signInWithPlatformAccount}>Sign in with platform account</button>
          </section>
        </main>
      </div>
    );
  }

  const selectSearchResult = (result: PlatformConsoleSearchResult) => {
    setQuery("");
    setResults([]);
    navigate(withPlatformDataMode(result.path, platformMode));
  };

  return (
    <div className="platform-shell" data-platform-theme={resolvedTheme} style={style}>
      <button className="platform-sidebar-scrim" aria-label="Close navigation" data-open={sidebarOpen} onClick={() => setSidebarOpen(false)} />
      <aside className="platform-sidebar" data-open={sidebarOpen}>
        <div className="platform-sidebar__brand">
          <span className="platform-brand-mark">AM</span>
          <span><strong>AMO SaaS</strong><small>Superadmin Console</small></span>
          <button className="platform-icon-btn platform-sidebar__close" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}>×</button>
        </div>
        <nav className="platform-nav" aria-label="Platform navigation">
          {platformNavSections.map((section) => (
            <section className="platform-nav__section" key={section.label}>
              <span className="platform-nav__heading">{section.label}</span>
              {section.items.map((item) => {
                const active = navIsActive(item, location.pathname, location.search);
                return (
                  <Link
                    key={item.to}
                    to={withPlatformDataMode(item.to, platformMode)}
                    className={active ? "active" : undefined}
                    title={item.description}
                    onClick={() => setSidebarOpen(false)}
                  >
                    <span className="platform-nav__mark">{item.mark}</span>
                    <span className="platform-nav__copy"><strong>{item.label}</strong><small>{item.description}</small></span>
                    {badgeValue(snapshot, item.badgeKey) ? <span className="platform-nav__badge">{badgeValue(snapshot, item.badgeKey)}</span> : null}
                  </Link>
                );
              })}
            </section>
          ))}
        </nav>
        <div className="platform-sidebar__status">
          <div><span className={`platform-status-dot ${realtime.status}`} /><strong>System status</strong></div>
          <span>{realtime.status === "live" ? "Live updates connected" : realtime.status === "connecting" ? "Connecting to control plane" : "Live channel unavailable"}</span>
          <small>{realtime.lastUpdated ? `Updated ${realtime.lastUpdated.toLocaleTimeString()}` : "Awaiting first event"}</small>
        </div>
        <a className="platform-public-link" href="/" target="_blank" rel="noreferrer">View public portal <span>↗</span></a>
      </aside>

      <main className="platform-main">
        <header className="platform-global-bar">
          <button className="platform-icon-btn platform-menu-btn" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>☰</button>
          <div className="platform-search-shell">
            <span className="platform-search-icon">⌕</span>
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tenants, users, tickets, or settings…"
              aria-label="Search platform console"
            />
            <kbd>Ctrl K</kbd>
            {query.trim().length >= 2 ? (
              <div className="platform-search-results">
                {searching ? <div className="platform-search-state">Searching…</div> : results.length ? results.map((result) => (
                  <button key={`${result.kind}:${result.id}`} onClick={() => selectSearchResult(result)}>
                    <span className="platform-search-result__kind">{result.kind.slice(0, 2).toUpperCase()}</span>
                    <span><strong>{result.title}</strong><small>{result.subtitle || result.path}</small></span>
                    {result.status ? <StatusBadge value={result.status} /> : null}
                  </button>
                )) : <div className="platform-search-state">No matching platform records.</div>}
              </div>
            ) : null}
          </div>

          <div className="platform-global-actions">
            <StatusBadge value={platformMode} />
            <div className="platform-theme-control">
              <button className="platform-btn compact" onClick={() => setThemeOpen((open) => !open)}>◐ Theme <span>⌄</span></button>
              {themeOpen ? (
                <div className="platform-theme-menu">
                  <span className="platform-menu-label">Appearance</span>
                  {(["dark", "light", "system"] as PlatformTheme[]).map((option) => (
                    <button key={option} className={theme === option ? "selected" : undefined} onClick={() => { setTheme(option); setThemeOpen(false); }}>
                      <span>{option === "dark" ? "◉" : option === "light" ? "○" : "◐"}</span>
                      {option[0].toUpperCase() + option.slice(1)}{option === "dark" ? " (Default)" : ""}
                    </button>
                  ))}
                  <span className="platform-menu-label">Accent presets</span>
                  <div className="platform-accent-row">
                    {ACCENTS.map((preset) => <button key={preset} aria-label={`Use ${preset} accent`} className={accent === preset ? "selected" : undefined} style={{ background: preset }} onClick={() => setAccent(preset)} />)}
                  </div>
                  <label className="platform-accent-custom"><span>Custom primary</span><input type="color" value={accent} onChange={(event) => setAccent(event.target.value)} /></label>
                </div>
              ) : null}
            </div>
            <button className="platform-icon-btn" aria-label="Reconnect live updates" title="Reconnect live updates" onClick={realtime.reconnect}>↻</button>
            <button className="platform-icon-btn platform-notification-btn" aria-label="Open security alerts" title="Open security alerts" onClick={() => navigate(withPlatformDataMode("/platform/security", platformMode))}>♢<span>{snapshot?.critical_security_alerts ? String(snapshot.critical_security_alerts) : ""}</span></button>
            <div className="platform-profile-chip" title={user.email || "Platform user"}>
              <span>{initials}</span>
              <small><strong>{user.email || "Platform user"}</strong><em>Superadmin</em></small>
            </div>
            <button className="platform-icon-btn" aria-label="Sign out" title="Sign out" onClick={() => { endSession("manual"); navigate("/login", { replace: true }); }}>↪</button>
          </div>
        </header>

        <div className="platform-workspace">
          <div className="platform-page">
            <header className="platform-page-header">
              <div className="platform-title">
                <span className="platform-page-emblem">◇</span>
                <div><h1>{title}</h1><p>{subtitle}</p></div>
              </div>
              <div className="platform-page-actions">
                {actions}
              </div>
            </header>
            <div className="platform-page-body">{children}</div>
          </div>
        </div>
      </main>
    </div>
  );
};

export const ErrorState: React.FC<{ error: unknown; retry?: () => void }> = ({ error, retry }) => (
  <div className="platform-error">
    <div><strong>Unable to load this platform section.</strong><p>{error instanceof Error ? error.message : String(error || "Unable to load data.")}</p></div>
    {retry ? <button className="platform-btn" onClick={retry}>Retry</button> : null}
  </div>
);

export const EmptyState: React.FC<{ label: string }> = ({ label }) => <div className="platform-empty">{label}</div>;

export const DataTable: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="platform-table-wrap"><table className="platform-table">{children}</table></div>
);

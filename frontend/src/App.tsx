// src/App.tsx
import React, { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { AppRouter } from "./router";
import TenantRouteBoundary from "./app/TenantRouteBoundary";
import { useTimeOfDayTheme } from "./hooks/useTimeOfDayTheme";
import { useColorScheme } from "./hooks/useColorScheme";
import { ToastProvider } from "./components/feedback/ToastProvider";
import PortalErrorBoundary from "./components/feedback/PortalErrorBoundary";
import GlobalLoadingBar from "./components/feedback/GlobalLoadingBar";
import PortalSessionLifecycle from "./components/auth/PortalSessionLifecycle";
import { onSessionEvent } from "./services/auth";
import { clearAllCachedAdminProfileStates } from "./services/adminProfileMode";
import { resetLoading } from "./services/loading";
import { clearApiResponseCache } from "./services/apiClient";
import { installPortalFetchErrorBridge } from "./services/portalFetchErrorBridge";
import { installPortalInlineErrorMirror } from "./services/portalInlineErrorMirror";
import { installPortalUploadGuard } from "./services/portalUploadGuard";
import { preloadRoute } from "./app/routePreload";

import "./styles/auth.css";

const App: React.FC = () => {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const theme = useTimeOfDayTheme();
  const { scheme } = useColorScheme();

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  void scheme;

  useEffect(() => {
    const removeFetchBridge = installPortalFetchErrorBridge();
    const removeInlineMirror = installPortalInlineErrorMirror();
    const removeUploadGuard = installPortalUploadGuard();
    return () => {
      removeUploadGuard();
      removeInlineMirror();
      removeFetchBridge();
    };
  }, []);

  useEffect(() => {
    return onSessionEvent((detail) => {
      if (detail.type === "authenticated") {
        void queryClient.cancelQueries();
        clearAllCachedAdminProfileStates();
        clearApiResponseCache();
        resetLoading();
      }
      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        void queryClient.cancelQueries();
        queryClient.clear();
        clearAllCachedAdminProfileStates();
        clearApiResponseCache();
        resetLoading();

        const parts = location.pathname.split("/").filter(Boolean);
        const isLoginRoute = location.pathname === "/login"
          || (parts[0] === "maintenance" && parts[2] === "login");
        if (isLoginRoute) return;

        const tenant = (parts[0] === "maintenance" || parts[0] === "t") ? parts[1] : "";
        const loginTarget = tenant ? `/maintenance/${encodeURIComponent(tenant)}/login` : "/login";
        const shouldResume = detail.type === "expired" || detail.type === "idle-logout";
        navigate(loginTarget, {
          replace: true,
          state: {
            from: shouldResume ? `${location.pathname}${location.search}${location.hash}` : undefined,
            sessionReason: detail.type,
          },
        });
      }
    });
  }, [location.hash, location.pathname, location.search, navigate, queryClient]);

  useEffect(() => {
    const preloadFromTarget = (target: EventTarget | null) => {
      if (!(target instanceof Element)) return;
      const anchor = target.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      try {
        const url = new URL(anchor.href, window.location.origin);
        if (url.origin !== window.location.origin) return;
        void preloadRoute(`${url.pathname}${url.search}`).catch(() => undefined);
      } catch {
        // Ignore malformed or non-route links.
      }
    };

    const onPointerOver = (event: PointerEvent) => preloadFromTarget(event.target);
    const onFocusIn = (event: FocusEvent) => preloadFromTarget(event.target);
    const onPointerDown = (event: PointerEvent) => preloadFromTarget(event.target);

    document.addEventListener("pointerover", onPointerOver, { passive: true, capture: true });
    document.addEventListener("focusin", onFocusIn, { capture: true });
    document.addEventListener("pointerdown", onPointerDown, { passive: true, capture: true });
    return () => {
      document.removeEventListener("pointerover", onPointerOver, true);
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, []);

  return (
    <ToastProvider>
      <GlobalLoadingBar />
      <PortalSessionLifecycle />
      <PortalErrorBoundary>
        <TenantRouteBoundary>
          <AppRouter />
        </TenantRouteBoundary>
      </PortalErrorBoundary>
    </ToastProvider>
  );
};

export default App;

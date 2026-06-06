// src/App.tsx
import React, { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { AppRouter } from "./router";

import { useTimeOfDayTheme } from "./hooks/useTimeOfDayTheme";
import { useColorScheme } from "./hooks/useColorScheme";

import { ToastProvider } from "./components/feedback/ToastProvider";
import GlobalLoadingBar from "./components/feedback/GlobalLoadingBar";
import { onSessionEvent } from "./services/auth";
import { resetLoading } from "./services/loading";
import { clearApiResponseCache } from "./services/apiClient";
import { preloadRoute } from "./app/routePreload";

import "./styles/auth.css";

const App: React.FC = () => {
  const queryClient = useQueryClient();
  const theme = useTimeOfDayTheme();
  const { scheme } = useColorScheme();

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  void scheme;


  useEffect(() => {
    return onSessionEvent((detail) => {
      if (detail.type === "authenticated") {
        void queryClient.cancelQueries();
        clearApiResponseCache();
        resetLoading();
      }
      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        void queryClient.cancelQueries();
        queryClient.clear();
        clearApiResponseCache();
        resetLoading();
      }
    });
  }, [queryClient]);

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
      <AppRouter />
    </ToastProvider>
  );
};

export default App;

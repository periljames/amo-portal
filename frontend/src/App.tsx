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

  return (
    <ToastProvider>
      <GlobalLoadingBar />
      <AppRouter />
    </ToastProvider>
  );
};

export default App;

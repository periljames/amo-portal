// src/App.tsx
import React, { useEffect } from "react";

import { AppRouter } from "./router";

import { useTimeOfDayTheme } from "./hooks/useTimeOfDayTheme";
import { useColorScheme } from "./hooks/useColorScheme";

import { ToastProvider } from "./components/feedback/ToastProvider";
import { GlobalLoadingProvider } from "./components/loading/GlobalLoadingProvider";
import GlobalLoaderOverlay from "./components/loading/GlobalLoaderOverlay";

import "./styles/auth.css";

const App: React.FC = () => {
  const theme = useTimeOfDayTheme();
  const { scheme } = useColorScheme();

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  void scheme;

  return (
    <ToastProvider>
      <GlobalLoadingProvider>
        <AppRouter />
        <GlobalLoaderOverlay />
      </GlobalLoadingProvider>
    </ToastProvider>
  );
};

export default App;

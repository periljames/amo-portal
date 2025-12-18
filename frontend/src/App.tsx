// src/App.tsx
import React, { useEffect } from "react";

import { AppRouter } from "./router";

import { useTimeOfDayTheme } from "./hooks/useTimeOfDayTheme";
import { useColorScheme } from "./hooks/useColorScheme";

import "./styles/global.css";
import "./styles/auth.css";

const App: React.FC = () => {
  const theme = useTimeOfDayTheme();
  const { scheme } = useColorScheme();

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  void scheme;

  return <AppRouter />;
};

export default App;

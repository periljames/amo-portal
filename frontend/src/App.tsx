// src/App.tsx
import React, { useEffect } from "react";

import { AppRouter } from "./router";

import { useTimeOfDayTheme } from "./hooks/useTimeOfDayTheme";
import { useColorScheme } from "./hooks/useColorScheme";

import "./styles/global.css";
import "./styles/auth.css";

const App: React.FC = () => {
  const theme = useTimeOfDayTheme();
  const { scheme } = useColorScheme(); // used for its side-effect on <body>

  useEffect(() => {
    // morning / day / evening / night
    document.body.dataset.theme = theme;
  }, [theme]);

  // `scheme` is already applied to body via the hook side-effect
  void scheme; // just to silence “unused” warnings if TS complains

  return <AppRouter />;
};

export default App;

// src/components/UI/ThemeToggle.tsx
import React from "react";
import { useColorScheme } from "../../hooks/useColorScheme";

const ThemeToggle: React.FC = () => {
  const { scheme, resolvedScheme, toggle } = useColorScheme();

  const label =
    scheme === "system"
      ? `🖥️ System (${resolvedScheme})`
      : scheme === "dark"
        ? "🌙 Dark"
        : "🌞 Light";

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle-btn"
      aria-label="Cycle theme mode (dark, light, system)"
      title="Cycle theme: dark → light → system"
    >
      {label}
    </button>
  );
};

export default ThemeToggle;

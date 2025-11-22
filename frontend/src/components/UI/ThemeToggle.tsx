// src/components/UI/ThemeToggle.tsx
import React from "react";
import { useColorScheme } from "../../hooks/useColorScheme";

const ThemeToggle: React.FC = () => {
  const { scheme, toggle } = useColorScheme();

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle-btn"
      aria-label="Toggle light/dark theme"
    >
      {scheme === "dark" ? "🌞 Light" : "🌙 Dark"}
    </button>
  );
};

export default ThemeToggle;

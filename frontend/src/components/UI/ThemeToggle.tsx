// src/components/UI/ThemeToggle.tsx
import React from "react";
import { useColorScheme } from "../../hooks/useColorScheme";
import { Monitor, Moon, Sun } from "lucide-react";

const ThemeToggle: React.FC = () => {
  const { scheme, resolvedScheme, toggle } = useColorScheme();

  const label =
    scheme === "system"
      ? `System (${resolvedScheme})`
      : scheme === "dark"
        ? "Dark"
        : "Light";
  const Icon = scheme === "system" ? Monitor : scheme === "dark" ? Moon : Sun;

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle-btn"
      aria-label={`Cycle theme mode (dark, light, system). Current: ${label}`}
      title="Cycle theme: dark → light → system"
    >
      <Icon size={16} aria-hidden />{label}
    </button>
  );
};

export default ThemeToggle;

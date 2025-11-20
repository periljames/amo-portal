// src/hooks/useTimeOfDayTheme.ts
import { useEffect, useState } from "react";

type ThemeName = "dawn" | "day" | "evening" | "night";

export function useTimeOfDayTheme(): ThemeName {
  const [theme, setTheme] = useState<ThemeName>("day");

  useEffect(() => {
    const update = () => {
      const hour = new Date().getHours();
      if (hour >= 5 && hour < 9) setTheme("dawn");
      else if (hour >= 9 && hour < 17) setTheme("day");
      else if (hour >= 17 && hour < 21) setTheme("evening");
      else setTheme("night");
    };

    update();
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, []);

  return theme;
}

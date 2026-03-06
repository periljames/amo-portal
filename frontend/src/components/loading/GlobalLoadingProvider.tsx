import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { shouldClearTaskOnRouteChange } from "./escalationRules";

export type LoadingPhase =
  | "initializing"
  | "loading"
  | "validating"
  | "verifying"
  | "generating"
  | "finalizing"
  | "syncing"
  | "refreshing"
  | "preparing_download"
  | "completing";

export type LoadingModePreference = "inline" | "section" | "page" | "overlay" | "auto";

export type LoadingTask = {
  id: string;
  scope: string;
  label: string;
  phase: LoadingPhase;
  message?: string;
  progress_percent?: number | null;
  indeterminate?: boolean;
  allow_overlay?: boolean;
  priority?: number;
  started_at: number;
  last_updated_at: number;
  minimum_visible_ms: number;
  escalation_level: number;
  show_long_wait_hint: boolean;
  mode_preference: LoadingModePreference;
  affects_route: boolean;
  persistent: boolean;
};

type StartTaskInput = Partial<Omit<LoadingTask, "id" | "started_at" | "minimum_visible_ms" | "last_updated_at" | "escalation_level" | "show_long_wait_hint">> & {
  label: string;
  scope?: string;
  phase?: LoadingPhase;
  minimum_visible_ms?: number;
};

type LoadingContextValue = {
  tasks: LoadingTask[];
  startLoading: (task: StartTaskInput) => string;
  updateLoading: (taskId: string, patch: Partial<LoadingTask>) => void;
  stopLoading: (taskId: string) => void;
  clearScope: (scope: string) => void;
};

const LoadingContext = createContext<LoadingContextValue | null>(null);

const uid = () => `load-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const GlobalLoadingProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tasks, setTasks] = useState<LoadingTask[]>([]);
  const timers = useRef<Map<string, number>>(new Map());
  const location = useLocation();

  useEffect(
    () => () => {
      timers.current.forEach((timerId) => window.clearTimeout(timerId));
      timers.current.clear();
    },
    []
  );

  useEffect(() => {
    setTasks((prev) => prev.filter((task) => !shouldClearTaskOnRouteChange(task)));
  }, [location.pathname]);

  const startLoading = useCallback((task: StartTaskInput) => {
    const id = uid();
    const now = Date.now();
    const row: LoadingTask = {
      id,
      scope: task.scope || "global",
      label: task.label,
      phase: task.phase || "loading",
      message: task.message,
      progress_percent: task.progress_percent ?? null,
      indeterminate: task.indeterminate ?? true,
      allow_overlay: task.allow_overlay ?? false,
      priority: task.priority ?? 50,
      started_at: now,
      last_updated_at: now,
      minimum_visible_ms: task.minimum_visible_ms ?? 350,
      escalation_level: 0,
      show_long_wait_hint: false,
      mode_preference: task.mode_preference ?? "auto",
      affects_route: task.affects_route ?? false,
      persistent: task.persistent ?? false,
    };
    setTasks((prev) => [...prev, row]);
    return id;
  }, []);

  const updateLoading = useCallback((taskId: string, patch: Partial<LoadingTask>) => {
    setTasks((prev) => prev.map((task) => (task.id === taskId ? { ...task, ...patch, last_updated_at: Date.now() } : task)));
  }, []);

  const stopLoading = useCallback((taskId: string) => {
    setTasks((prev) => {
      const row = prev.find((task) => task.id === taskId);
      if (!row) return prev;
      const existingTimer = timers.current.get(taskId);
      if (existingTimer) {
        window.clearTimeout(existingTimer);
        timers.current.delete(taskId);
      }
      const elapsed = Date.now() - row.started_at;
      const wait = Math.max(0, row.minimum_visible_ms - elapsed);
      if (wait === 0) return prev.filter((task) => task.id !== taskId);
      const timerId = window.setTimeout(() => {
        setTasks((inner) => inner.filter((task) => task.id !== taskId));
        timers.current.delete(taskId);
      }, wait);
      timers.current.set(taskId, timerId);
      return prev;
    });
  }, []);

  const clearScope = useCallback((scope: string) => {
    setTasks((prev) => {
      const scoped = prev.filter((task) => task.scope === scope);
      scoped.forEach((task) => {
        const existingTimer = timers.current.get(task.id);
        if (existingTimer) {
          window.clearTimeout(existingTimer);
          timers.current.delete(task.id);
        }
      });
      return prev.filter((task) => task.scope !== scope);
    });
  }, []);

  const value = useMemo(
    () => ({ tasks, startLoading, updateLoading, stopLoading, clearScope }),
    [tasks, startLoading, updateLoading, stopLoading, clearScope]
  );

  return <LoadingContext.Provider value={value}>{children}</LoadingContext.Provider>;
};

export const useLoadingContext = () => {
  const ctx = useContext(LoadingContext);
  if (!ctx) throw new Error("useLoadingContext must be used inside GlobalLoadingProvider");
  return ctx;
};

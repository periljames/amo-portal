import { useCallback } from "react";
import type { LoadingModePreference, LoadingPhase } from "../components/loading/GlobalLoadingProvider";
import { useGlobalLoading } from "./useGlobalLoading";

type LoaderOptions = {
  scope?: string;
  label: string;
  phase?: LoadingPhase;
  message?: string;
  allow_overlay?: boolean;
  minimum_visible_ms?: number;
  mode_preference?: LoadingModePreference;
  affects_route?: boolean;
  persistent?: boolean;
};

export const useAsyncWithLoader = () => {
  const { startLoading, stopLoading, updateLoading } = useGlobalLoading();

  return useCallback(
    async <T>(fn: () => Promise<T>, options: LoaderOptions): Promise<T> => {
      const taskId = startLoading({
        scope: options.scope,
        label: options.label,
        phase: options.phase || "loading",
        message: options.message,
        allow_overlay: options.allow_overlay,
        minimum_visible_ms: options.minimum_visible_ms,
        mode_preference: options.mode_preference,
        affects_route: options.affects_route,
        persistent: options.persistent,
      });
      try {
        return await fn();
      } finally {
        updateLoading(taskId, { phase: "completing", indeterminate: true });
        stopLoading(taskId);
      }
    },
    [startLoading, stopLoading, updateLoading]
  );
};

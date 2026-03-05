import { useMemo } from "react";
import { useLoadingContext } from "../components/loading/GlobalLoadingProvider";

export const useGlobalLoading = () => useLoadingContext();

export const useScopedLoading = (scope: string) => {
  const { tasks, startLoading, updateLoading, stopLoading, clearScope } = useLoadingContext();
  const scopedTasks = useMemo(() => tasks.filter((task) => task.scope === scope), [tasks, scope]);
  return { tasks: scopedTasks, startLoading, updateLoading, stopLoading, clearScope };
};

import { useCallback, useEffect, useRef, useState } from "react";

/** Aborts obsolete tenant requests and never displays a former tenant's data.
 * Callers choose when a request changes through their stable key; an explicit
 * reload increments the generation without remounting the workflow.
 */
export function usePartnerLoad<T>(loader: (signal: AbortSignal) => Promise<T>, key: string) {
  const loaderRef = useRef(loader);
  useEffect(() => { loaderRef.current = loader; });
  const [generation, setGeneration] = useState(0);
  const reload = useCallback(() => setGeneration((previous) => previous + 1), []);
  const [result, setResult] = useState<{
    key: string; generation: number; value: T | null; pending: boolean; error: string;
  }>(() => ({ key, generation: 0, value: null, pending: true, error: "" }));

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const value = await loaderRef.current(controller.signal);
        if (!controller.signal.aborted) {
          setResult({ key, generation, value, pending: false, error: "" });
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setResult({
            key, generation, value: null, pending: false,
            error: failure instanceof Error ? failure.message : "Unable to load portal records",
          });
        }
      }
    };
    void load();
    return () => controller.abort();
  }, [key, generation]);

  if (result.key !== key || result.generation !== generation) {
    return { value: null as T | null, pending: true, error: "", reload };
  }
  return { value: result.value, pending: result.pending, error: result.error, reload };
}

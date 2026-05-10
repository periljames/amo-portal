import { useCallback, useEffect, useState } from "react";

export function usePlatformData<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const reload = useCallback(() => {
    setLoading(true); setError(null);
    loader().then(setData).catch(setError).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, error, reload };
}

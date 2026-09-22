/**
 * Apply UI state immediately, then commit to the server without holding the
 * caller's click handler on network RTT. Do not use flushSync here — a full
 * page tree commit can cost tens/hundreds of ms and still feels like lag.
 */
export type OptimisticActionOptions<T> = {
  apply: () => void;
  revert: () => void;
  commit: () => Promise<T>;
  onSuccess?: (result: T) => void;
  onError?: (error: unknown) => void;
};

export async function runOptimisticAction<T>(
  options: OptimisticActionOptions<T>,
): Promise<{ ok: true; result: T } | { ok: false; error: unknown }> {
  options.apply();
  try {
    const result = await options.commit();
    options.onSuccess?.(result);
    return { ok: true, result };
  } catch (error) {
    options.revert();
    options.onError?.(error);
    return { ok: false, error };
  }
}

/** Fire-and-forget wrapper so click handlers return before network work. */
export function queueOptimisticAction<T>(options: OptimisticActionOptions<T>): void {
  void runOptimisticAction(options);
}

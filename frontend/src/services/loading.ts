import { useEffect, useState } from "react";

type LoadingListener = (count: number) => void;

let pendingCount = 0;
const listeners = new Set<LoadingListener>();

function emit() {
  for (const listener of listeners) {
    listener(pendingCount);
  }
}

export function beginLoading(): void {
  pendingCount += 1;
  emit();
}

export function endLoading(): void {
  pendingCount = Math.max(0, pendingCount - 1);
  emit();
}

export function withLoading<T>(promise: Promise<T>): Promise<T> {
  beginLoading();
  return promise.finally(() => endLoading());
}

export function subscribeLoading(listener: LoadingListener): () => void {
  listeners.add(listener);
  listener(pendingCount);
  return () => {
    listeners.delete(listener);
  };
}

export function useGlobalLoadingCount(): number {
  const [count, setCount] = useState(pendingCount);
  useEffect(() => subscribeLoading(setCount), []);
  return count;
}

import { useEffect, useState } from "react";

type LoadingMode = "foreground" | "background";
type LoadingListener = (count: number) => void;

type LoadingState = {
  foreground: number;
  background: number;
};

const state: LoadingState = {
  foreground: 0,
  background: 0,
};

const listeners = new Set<LoadingListener>();

function emit() {
  for (const listener of listeners) {
    listener(state.foreground);
  }
}

function begin(mode: LoadingMode): void {
  state[mode] += 1;
  emit();
}

function end(mode: LoadingMode): void {
  state[mode] = Math.max(0, state[mode] - 1);
  emit();
}

export function beginLoading(): void {
  begin("foreground");
}

export function endLoading(): void {
  end("foreground");
}

export function beginBackgroundLoading(): void {
  begin("background");
}

export function endBackgroundLoading(): void {
  end("background");
}

export function withLoading<T>(promise: Promise<T>): Promise<T> {
  beginLoading();
  return promise.finally(() => endLoading());
}

export function withBackgroundLoading<T>(promise: Promise<T>): Promise<T> {
  beginBackgroundLoading();
  return promise.finally(() => endBackgroundLoading());
}

export function resetLoading(): void {
  state.foreground = 0;
  state.background = 0;
  emit();
}

export function subscribeLoading(listener: LoadingListener): () => void {
  listeners.add(listener);
  listener(state.foreground);
  return () => {
    listeners.delete(listener);
  };
}

export function useGlobalLoadingCount(): number {
  const [count, setCount] = useState(state.foreground);
  useEffect(() => subscribeLoading(setCount), []);
  return count;
}

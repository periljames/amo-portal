import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  onAdminProfileChange,
  readCachedAdminProfileState,
} from "./adminProfileMode";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

describe("Admin Profile client lifecycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-03T12:00:00Z"));

    const target = new EventTarget() as EventTarget & {
      sessionStorage: MemoryStorage;
      setTimeout: typeof globalThis.setTimeout;
      clearTimeout: typeof globalThis.clearTimeout;
    };
    target.sessionStorage = new MemoryStorage();
    target.setTimeout = globalThis.setTimeout.bind(globalThis);
    target.clearTimeout = globalThis.clearTimeout.bind(globalThis);
    vi.stubGlobal("window", target);

    if (typeof globalThis.CustomEvent === "undefined") {
      class TestCustomEvent<T> extends Event {
        detail: T;
        constructor(type: string, init: CustomEventInit<T>) {
          super(type);
          this.detail = init.detail as T;
        }
      }
      vi.stubGlobal("CustomEvent", TestCustomEvent);
    }
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("publishes an inactive state when the backend expiry time is reached", () => {
    const amoCode = "tenant-a";
    window.sessionStorage.setItem(
      `amo_admin_profile_session:${amoCode}`,
      JSON.stringify({
        eligible: true,
        active: true,
        session_id: "session-1",
        expires_at: "2026-08-03T12:00:01Z",
        grant_type: "TEMPORARY",
      }),
    );

    const observed: boolean[] = [];
    const unsubscribe = onAdminProfileChange(({ state }) => observed.push(state.active));

    expect(readCachedAdminProfileState(amoCode)?.active).toBe(true);
    vi.advanceTimersByTime(1_050);

    expect(observed).toEqual([false]);
    expect(readCachedAdminProfileState(amoCode)).toMatchObject({
      eligible: true,
      active: false,
      session_id: null,
      expires_at: null,
    });
    unsubscribe();
  });
});

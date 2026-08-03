import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearAllCachedAdminProfileStates,
  onAdminProfileChange,
  readCachedAdminProfileState,
} from "./adminProfileMode";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  clear(): void {
    this.values.clear();
  }
}

describe("Admin Profile client lifecycle", () => {
  let sessionStorage: MemoryStorage;
  let localStorage: MemoryStorage;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-03T12:00:00Z"));

    sessionStorage = new MemoryStorage();
    localStorage = new MemoryStorage();
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "user-a" }));

    const target = new EventTarget() as EventTarget & {
      sessionStorage: MemoryStorage;
      localStorage: MemoryStorage;
      setTimeout: typeof globalThis.setTimeout;
      clearTimeout: typeof globalThis.clearTimeout;
    };
    target.sessionStorage = sessionStorage;
    target.localStorage = localStorage;
    target.setTimeout = globalThis.setTimeout.bind(globalThis);
    target.clearTimeout = globalThis.clearTimeout.bind(globalThis);
    vi.stubGlobal("window", target);
    vi.stubGlobal("sessionStorage", sessionStorage);
    vi.stubGlobal("localStorage", localStorage);

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
    clearAllCachedAdminProfileStates();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("publishes an inactive state for the same user when backend expiry is reached", () => {
    const amoCode = "tenant-a";
    sessionStorage.setItem(
      `amo_admin_profile_session:user-a:${amoCode}`,
      JSON.stringify({
        eligible: true,
        active: true,
        session_id: "session-1",
        expires_at: "2026-08-03T12:00:01Z",
        grant_type: "TEMPORARY",
      }),
    );

    const observed: Array<{ userId: string; active: boolean }> = [];
    const unsubscribe = onAdminProfileChange(({ userId, state }) => {
      observed.push({ userId, active: state.active });
    });

    expect(readCachedAdminProfileState(amoCode)?.active).toBe(true);
    vi.advanceTimersByTime(1_050);

    expect(observed).toEqual([{ userId: "user-a", active: false }]);
    expect(readCachedAdminProfileState(amoCode)).toMatchObject({
      eligible: true,
      active: false,
      session_id: null,
      expires_at: null,
    });
    unsubscribe();
  });

  it("never returns another user's cached elevation in the same tenant tab", () => {
    const amoCode = "tenant-a";
    sessionStorage.setItem(
      `amo_admin_profile_session:user-a:${amoCode}`,
      JSON.stringify({
        eligible: true,
        active: true,
        session_id: "session-user-a",
        expires_at: "2026-08-03T12:10:00Z",
      }),
    );

    expect(readCachedAdminProfileState(amoCode)?.session_id).toBe("session-user-a");

    localStorage.setItem("amo_current_user", JSON.stringify({ id: "user-b" }));

    expect(readCachedAdminProfileState(amoCode)).toBeNull();
    expect(sessionStorage.getItem(`amo_admin_profile_session:user-a:${amoCode}`)).not.toBeNull();

    clearAllCachedAdminProfileStates();
    expect(sessionStorage.length).toBe(0);
  });
});

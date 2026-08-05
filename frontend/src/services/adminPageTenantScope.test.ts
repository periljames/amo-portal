import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  beginAdminPageTenantScope,
  clearAdminPageTenantScope,
  completeAdminPageTenantScope,
  readAdminPageTenantScope,
} from "./adminPageTenantScope";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
let storage: MemoryStorage;

beforeEach(() => {
  storage = new MemoryStorage();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { sessionStorage: storage },
  });
  clearAdminPageTenantScope();
});

afterEach(() => {
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete (globalThis as unknown as { window?: unknown }).window;
});

describe("admin page tenant scope", () => {
  it("binds the AMO confirmed for the latest page request", () => {
    const attempt = beginAdminPageTenantScope({ active_amo_id: "amo-a" });
    completeAdminPageTenantScope(attempt, { user_id: "user-1", active_amo_id: "amo-a" });

    expect(readAdminPageTenantScope("user-1")).toBe("amo-a");
  });

  it("ignores an older response that arrives after a newer context switch", () => {
    const oldAttempt = beginAdminPageTenantScope({ active_amo_id: "amo-a" });
    const latestAttempt = beginAdminPageTenantScope({ active_amo_id: "amo-b" });

    completeAdminPageTenantScope(latestAttempt, { user_id: "user-1", active_amo_id: "amo-b" });
    completeAdminPageTenantScope(oldAttempt, { user_id: "user-1", active_amo_id: "amo-a" });

    expect(readAdminPageTenantScope("user-1")).toBe("amo-b");
  });

  it("fails closed when the server does not confirm the requested AMO", () => {
    const attempt = beginAdminPageTenantScope({ active_amo_id: "amo-a" });

    expect(() => completeAdminPageTenantScope(
      attempt,
      { user_id: "user-1", active_amo_id: "amo-b" },
    )).toThrow(/did not confirm/i);
    expect(readAdminPageTenantScope("user-1")).toBeNull();
  });

  it("does not expose a tab binding to another authenticated user", () => {
    const attempt = beginAdminPageTenantScope(JSON.stringify({ active_amo_id: "amo-a" }));
    completeAdminPageTenantScope(attempt, { user_id: "user-1", active_amo_id: "amo-a" });

    expect(readAdminPageTenantScope("user-2")).toBeNull();
  });
});

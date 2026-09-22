import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import { rememberLoginHome, readLoginHomeHint } from "./loginHomeHint";

describe("loginHomeHint", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => store.clear(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("remembers and reads a tenant landing path", () => {
    rememberLoginHome("safarilink", "/maintenance/safarilink/quality");
    expect(readLoginHomeHint("safarilink")).toBe("/maintenance/safarilink/quality");
  });

  it("rejects non-portal and cross-tenant paths", () => {
    localStorage.setItem("amodb:last-landing:demo", "https://evil.example");
    expect(readLoginHomeHint("demo")).toBeNull();
    localStorage.setItem("amodb:last-landing:demo", "/maintenance/other-tenant/quality");
    expect(readLoginHomeHint("demo")).toBeNull();
    localStorage.setItem("amodb:last-landing:demo", "/maintenance/demo/../other/quality");
    expect(readLoginHomeHint("demo")).toBeNull();
  });
});

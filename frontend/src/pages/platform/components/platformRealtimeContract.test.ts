import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const platformRoot = path.resolve(__dirname, "..");
const shellHook = fs.readFileSync(path.resolve(__dirname, "usePlatformRealtime.ts"), "utf8");
const operationsPage = fs.readFileSync(path.resolve(platformRoot, "PlatformOperationsPage.tsx"), "utf8");

describe("Platform realtime contract", () => {
  it("keeps the isolated Operations Gateway stream owned by PlatformShell", () => {
    expect(shellHook).toContain("operationsStreamUrl(selectedMode)");
    expect(shellHook).not.toContain("/platform/console/events");
    expect(operationsPage).toContain("PLATFORM_CONSOLE_LIVE_EVENT");
    expect(operationsPage).not.toContain("operationsStreamUrl");
    expect(operationsPage).not.toContain("async function stream(");
  });
});

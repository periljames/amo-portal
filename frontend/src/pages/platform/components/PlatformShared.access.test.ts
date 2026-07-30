import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  fileURLToPath(new URL("./PlatformShared.tsx", import.meta.url)),
  "utf8",
);

describe("platform shell access continuity", () => {
  it("does not replace an authenticated cached superuser shell with the verification screen on route changes", () => {
    expect(source).toContain('if (cachedSuperuserForActiveToken()) return "allowed";');
    expect(source).toContain('const [accessState, setAccessState] = useState<PlatformAccessState>(initialPlatformAccessState);');
    expect(source).not.toContain('() => (isAuthenticated() ? "checking" : "denied")');
  });

  it("deduplicates authoritative user verification across platform page remounts", () => {
    expect(source).toContain("verifiedPlatformAccess");
    expect(source).toContain("platformVerificationInFlight");
    expect(source).toContain("verifyPlatformUserForActiveToken()");
  });

  it("expires the token-scoped cache and revalidates a mounted console periodically", () => {
    expect(source).toContain("PLATFORM_ACCESS_CACHE_TTL_MS");
    expect(source).toContain("PLATFORM_ACCESS_REVALIDATE_MS");
    expect(source).toContain("window.setInterval(applyVerification, PLATFORM_ACCESS_REVALIDATE_MS)");
  });

  it("denies authoritative account rejection but preserves the shell for transient failures", () => {
    expect(source).toContain("error instanceof PlatformAccessVerificationError");
    expect(source).toContain('setAccessState("denied");');
    expect(source).toContain('setAccessState(fallbackUser ? "allowed" : "denied");');
  });
});

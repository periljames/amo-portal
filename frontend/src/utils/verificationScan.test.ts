import { describe, expect, it, vi } from "vitest";
import { createHardwareScannerListener, isLikelyScannerBurst, parseScannedCertificate } from "./verificationScan";

describe("parseScannedCertificate", () => {
  it("parses full verify URL", () => {
    expect(parseScannedCertificate("https://portal.example/verify/certificate/TC-001")).toBe("TC-001");
  });

  it("returns raw certificate token", () => {
    expect(parseScannedCertificate("TC-ABC-2026-0001")).toBe("TC-ABC-2026-0001");
  });
});

describe("scanner burst detection", () => {
  it("detects likely scanner burst", () => {
    const chars = "TC123456".split("");
    const ts = [0, 8, 15, 23, 31, 38, 46, 54];
    expect(isLikelyScannerBurst(chars, ts)).toBe(true);
  });

  it("rejects human typing cadence", () => {
    const chars = "TC123456".split("");
    const ts = [0, 120, 260, 420, 590, 760, 910, 1070];
    expect(isLikelyScannerBurst(chars, ts)).toBe(false);
  });

  it("listener emits scan on enter for burst", () => {
    const onScan = vi.fn();
    const listener = createHardwareScannerListener(onScan);
    const text = "TC-9001";
    let t = 0;
    for (const ch of text) {
      listener.onKeyDown({ key: ch, timeStamp: t });
      t += 10;
    }
    listener.onKeyDown({ key: "Enter", timeStamp: t + 10 });
    expect(onScan).toHaveBeenCalledWith(text);
  });
});

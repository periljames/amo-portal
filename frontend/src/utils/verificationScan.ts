export function parseScannedCertificate(input: string): string | null {
  const raw = (input || "").trim();
  if (!raw) return null;
  if (/^https?:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      const parts = url.pathname.split("/").filter(Boolean);
      const idx = parts.findIndex((p) => p === "certificate");
      if (idx >= 0 && parts[idx + 1]) return decodeURIComponent(parts[idx + 1]);
      return null;
    } catch {
      return null;
    }
  }
  return raw;
}

type BurstOptions = {
  minLength?: number;
  maxAvgIntervalMs?: number;
};

export function isLikelyScannerBurst(chars: string[], timestamps: number[], opts: BurstOptions = {}): boolean {
  const minLength = opts.minLength ?? 6;
  const maxAvg = opts.maxAvgIntervalMs ?? 35;
  if (chars.length < minLength) return false;
  if (chars.length !== timestamps.length || timestamps.length < 2) return false;
  let total = 0;
  for (let i = 1; i < timestamps.length; i += 1) {
    total += Math.max(0, timestamps[i] - timestamps[i - 1]);
  }
  const avg = total / (timestamps.length - 1);
  return avg <= maxAvg;
}

export function createHardwareScannerListener(onScan: (value: string) => void, opts: BurstOptions = {}) {
  let chars: string[] = [];
  let times: number[] = [];

  return {
    onKeyDown(event: KeyboardEvent | { key: string; timeStamp: number }) {
      const key = event.key;
      if (key === "Enter") {
        if (isLikelyScannerBurst(chars, times, opts)) {
          onScan(chars.join(""));
        }
        chars = [];
        times = [];
        return;
      }
      if (key.length === 1) {
        chars.push(key);
        times.push(event.timeStamp || Date.now());
      }
      if (chars.length > 128) {
        chars = chars.slice(-64);
        times = times.slice(-64);
      }
    },
  };
}

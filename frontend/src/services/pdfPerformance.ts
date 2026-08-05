export type PdfReaderPerformanceProfile = {
  mode: "constrained" | "balanced" | "burst";
  rangeChunkSize: number;
  renderRadius: number;
  hotPageLimit: number;
  prefetchMarginPx: number;
  maxDevicePixelRatio: number;
};

type NetworkInformationLike = {
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
  saveData?: boolean;
};

type NavigatorWithPerformanceHints = Navigator & {
  connection?: NetworkInformationLike;
  mozConnection?: NetworkInformationLike;
  webkitConnection?: NetworkInformationLike;
  deviceMemory?: number;
};

const KIB = 1024;
const MIB = 1024 * KIB;

function browserHints(): {
  connection?: NetworkInformationLike;
  deviceMemory: number;
  hardwareConcurrency: number;
} {
  if (typeof navigator === "undefined") {
    return { deviceMemory: 4, hardwareConcurrency: 4 };
  }
  const hinted = navigator as NavigatorWithPerformanceHints;
  return {
    connection: hinted.connection || hinted.mozConnection || hinted.webkitConnection,
    deviceMemory: Math.max(1, Number(hinted.deviceMemory || 4)),
    hardwareConcurrency: Math.max(1, Number(hinted.hardwareConcurrency || 4)),
  };
}

/**
 * Use browser network and memory hints to choose a bounded rendering policy.
 * Fast clients fetch large byte ranges and keep a wider page window hot. Slow
 * or data-saving clients retain the progressive path without penalising normal
 * office networks with tiny serial range requests.
 */
export function getPdfReaderPerformanceProfile(): PdfReaderPerformanceProfile {
  const { connection, deviceMemory, hardwareConcurrency } = browserHints();
  const effectiveType = String(connection?.effectiveType || "").toLowerCase();
  const downlink = Number(connection?.downlink || 0);
  const saveData = Boolean(connection?.saveData);
  const constrainedNetwork = saveData || effectiveType === "slow-2g" || effectiveType === "2g";
  const modestNetwork = effectiveType === "3g" || (downlink > 0 && downlink < 5);
  const capableDevice = deviceMemory >= 8 && hardwareConcurrency >= 8;
  const fastNetwork = effectiveType === "4g" || downlink >= 12 || (!connection && capableDevice);

  if (constrainedNetwork) {
    return {
      mode: "constrained",
      rangeChunkSize: 128 * KIB,
      renderRadius: 2,
      hotPageLimit: 5,
      prefetchMarginPx: 900,
      maxDevicePixelRatio: 1.1,
    };
  }

  if (modestNetwork || deviceMemory < 4) {
    return {
      mode: "balanced",
      rangeChunkSize: 512 * KIB,
      renderRadius: 3,
      hotPageLimit: 8,
      prefetchMarginPx: 1800,
      maxDevicePixelRatio: 1.25,
    };
  }

  if (fastNetwork && capableDevice) {
    return {
      mode: "burst",
      rangeChunkSize: 4 * MIB,
      renderRadius: 5,
      hotPageLimit: 15,
      prefetchMarginPx: 5000,
      maxDevicePixelRatio: 1.5,
    };
  }

  return {
    mode: "balanced",
    rangeChunkSize: 1 * MIB,
    renderRadius: 4,
    hotPageLimit: 11,
    prefetchMarginPx: 3200,
    maxDevicePixelRatio: 1.4,
  };
}

export function pdfDevicePixelRatio(maximum?: number): number {
  if (typeof window === "undefined") return 1;
  const ceiling = maximum || getPdfReaderPerformanceProfile().maxDevicePixelRatio;
  return Math.min(window.devicePixelRatio || 1, ceiling);
}

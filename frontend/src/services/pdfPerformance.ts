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
 * Normal office clients receive 20 MiB PDF ranges. A demonstrably stable,
 * high-throughput connection on a capable device receives 50 MiB bursts.
 * Constrained clients retain a progressive path without governing everyone
 * else by the slowest possible network profile.
 */
export function getPdfReaderPerformanceProfile(): PdfReaderPerformanceProfile {
  const { connection, deviceMemory, hardwareConcurrency } = browserHints();
  const effectiveType = String(connection?.effectiveType || "").toLowerCase();
  const downlink = Number(connection?.downlink || 0);
  const rtt = Number(connection?.rtt || 0);
  const saveData = Boolean(connection?.saveData);
  const constrainedNetwork = saveData || effectiveType === "slow-2g" || effectiveType === "2g";
  const modestNetwork = effectiveType === "3g" || (downlink > 0 && downlink < 5);
  const capableDevice = deviceMemory >= 8 && hardwareConcurrency >= 8;
  const superStableNetwork = capableDevice
    && effectiveType === "4g"
    && downlink >= 25
    && (rtt <= 0 || rtt <= 80);

  if (constrainedNetwork) {
    return {
      mode: "constrained",
      rangeChunkSize: 512 * KIB,
      renderRadius: 2,
      hotPageLimit: 5,
      prefetchMarginPx: 900,
      maxDevicePixelRatio: 1.1,
    };
  }

  if (modestNetwork || deviceMemory < 4) {
    return {
      mode: "balanced",
      rangeChunkSize: 4 * MIB,
      renderRadius: 4,
      hotPageLimit: 10,
      prefetchMarginPx: 3000,
      maxDevicePixelRatio: 1.25,
    };
  }

  if (superStableNetwork) {
    return {
      mode: "burst",
      rangeChunkSize: 50 * MIB,
      renderRadius: 8,
      hotPageLimit: 24,
      prefetchMarginPx: 12000,
      maxDevicePixelRatio: 1.6,
    };
  }

  return {
    mode: "balanced",
    rangeChunkSize: 20 * MIB,
    renderRadius: 6,
    hotPageLimit: 18,
    prefetchMarginPx: 7000,
    maxDevicePixelRatio: 1.45,
  };
}

export function pdfDevicePixelRatio(maximum?: number): number {
  if (typeof window === "undefined") return 1;
  const ceiling = maximum || getPdfReaderPerformanceProfile().maxDevicePixelRatio;
  return Math.min(window.devicePixelRatio || 1, ceiling);
}

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
 * Choose a bounded PDF range/render policy from browser network and memory
 * hints. Large 20-50 MiB range requests delayed the first useful page on real
 * technical manuals, especially when traffic crossed a remote/private link.
 * Smaller ranges let PDF.js reach requested objects earlier while streaming
 * remains enabled. Canvas DPR is also capped below the display DPR so nearby
 * virtual pages do not monopolize decode/paint time; zooming still rerenders at
 * the requested CSS size and print/download always use the authoritative PDF.
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
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1,
    };
  }

  if (modestNetwork || deviceMemory < 4) {
    return {
      mode: "balanced",
      rangeChunkSize: 2 * MIB,
      renderRadius: 3,
      hotPageLimit: 8,
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1.15,
    };
  }

  if (superStableNetwork) {
    return {
      mode: "burst",
      rangeChunkSize: 24 * MIB,
      renderRadius: 6,
      hotPageLimit: 16,
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1.35,
    };
  }

  return {
    mode: "balanced",
    rangeChunkSize: 8 * MIB,
    renderRadius: 4,
    hotPageLimit: 12,
    prefetchMarginPx: 0,
    maxDevicePixelRatio: 1.25,
  };
}

export function pdfDevicePixelRatio(maximum?: number): number {
  if (typeof window === "undefined") return 1;
  const ceiling = maximum || getPdfReaderPerformanceProfile().maxDevicePixelRatio;
  return Math.min(window.devicePixelRatio || 1, ceiling);
}

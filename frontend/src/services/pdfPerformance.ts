export type PdfReaderPerformanceProfile = {
  mode: "constrained" | "balanced" | "burst";
  rangeChunkSize: number;
  renderRadius: number;
  hotPageLimit: number;
  prefetchMarginPx: number;
  maxDevicePixelRatio: number;
  maxCanvasPixels: number;
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
 * Keep first-page latency bounded: normal office clients receive 4 MiB PDF
 * ranges and even high-throughput clients stop at 8 MiB. Rendering policy is
 * additionally bounded by a per-canvas pixel budget, so a high-DPI display
 * cannot silently multiply memory use while zooming or scrolling.
 *
 * The page observer is also the authority for the toolbar page number and the
 * active Contents row. Its root margin must therefore remain zero. Nearby-page
 * preloading is provided by renderRadius/hotPageLimit after the truly visible
 * page is selected; treating pages thousands of pixels outside the viewport as
 * visible causes the wrong render window to be retained during jumps.
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
      renderRadius: 1,
      hotPageLimit: 3,
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1.1,
      maxCanvasPixels: 4_000_000,
    };
  }

  if (modestNetwork || deviceMemory < 4) {
    return {
      mode: "balanced",
      rangeChunkSize: 2 * MIB,
      renderRadius: 1,
      hotPageLimit: 4,
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1.25,
      maxCanvasPixels: 6_000_000,
    };
  }

  if (superStableNetwork) {
    return {
      mode: "burst",
      rangeChunkSize: 8 * MIB,
      renderRadius: 2,
      hotPageLimit: 7,
      prefetchMarginPx: 0,
      maxDevicePixelRatio: 1.6,
      maxCanvasPixels: 12_000_000,
    };
  }

  return {
    mode: "balanced",
    rangeChunkSize: 4 * MIB,
    renderRadius: 2,
    hotPageLimit: 5,
    prefetchMarginPx: 0,
    maxDevicePixelRatio: 1.45,
    maxCanvasPixels: 8_000_000,
  };
}

export function pdfDevicePixelRatio(
  maximum?: number,
  widthCssPixels?: number,
  heightCssPixels?: number,
  maximumCanvasPixels?: number,
): number {
  if (typeof window === "undefined") return 1;
  const ceiling = maximum || getPdfReaderPerformanceProfile().maxDevicePixelRatio;
  const desired = Math.min(window.devicePixelRatio || 1, ceiling);
  const area = Math.max(0, Number(widthCssPixels || 0) * Number(heightCssPixels || 0));
  if (!area || !maximumCanvasPixels) return desired;
  return Math.max(0.75, Math.min(desired, Math.sqrt(maximumCanvasPixels / area)));
}

export const PLATFORM_OPS_DEV_PROXY_PATTERN = "^/ops(?:/|$|\\?)";

export const DEV_API_PROXY_PATTERN =
  "^/(auth|accounts|admin|billing|aircraft|work-orders|crs|training|public|quality|qms|platform|reliability|audit|audit-events|bootstrap|integrations|api|notifications|email-logs|tasks|health|healthz|livez|readyz|time|manuals|doc-control|records|foundations|rostering|workforce)(?:/|$|\\?)";

const PLATFORM_OPS_DEV_PATH = new RegExp(PLATFORM_OPS_DEV_PROXY_PATTERN, "i");
const DEV_API_PATH = new RegExp(DEV_API_PROXY_PATTERN, "i");
const PLATFORM_PATH = /^\/platform(?:\/|$|\?)/i;

export type DevProxyTargets = {
  apiTarget: string;
  platformOpsTarget: string;
};

export function resolveDevProxyTargets(env: Record<string, string>): DevProxyTargets {
  return {
    apiTarget: env.VITE_API_PROXY_TARGET?.trim() || env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8080",
    platformOpsTarget: env.VITE_PLATFORM_OPS_PROXY_TARGET?.trim() || "http://127.0.0.1:8090",
  };
}

export function shouldProxyPlatformOps(url: string | undefined): boolean {
  return PLATFORM_OPS_DEV_PATH.test(String(url || ""));
}

export function shouldProxyDevApi(url: string | undefined): boolean {
  return DEV_API_PATH.test(String(url || ""));
}

export function shouldServePlatformSpa(
  method: string | undefined,
  url: string | undefined,
  accept: string | string[] | undefined,
): boolean {
  const normalizedMethod = String(method || "GET").toUpperCase();
  if (normalizedMethod !== "GET" && normalizedMethod !== "HEAD") return false;

  const acceptedTypes = Array.isArray(accept) ? accept.join(",") : String(accept || "");
  return PLATFORM_PATH.test(String(url || "")) && acceptedTypes.toLowerCase().includes("text/html");
}

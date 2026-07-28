export const DEV_API_PROXY_PATTERN =
  "^/(auth|accounts|admin|billing|aircraft|work-orders|crs|training|public|quality|qms|platform|reliability|audit|audit-events|bootstrap|integrations|api|notifications|email-logs|tasks|health|healthz|time|manuals|doc-control|records|foundations|rostering|workforce)(?:/|$|\\?)";

const DEV_API_PATH = new RegExp(DEV_API_PROXY_PATTERN, "i");
const PLATFORM_PATH = /^\/platform(?:\/|$|\?)/i;

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

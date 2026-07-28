const PLATFORM_PATH = /^\/platform(?:\/|$|\?)/i;

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

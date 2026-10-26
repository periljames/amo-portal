/**
 * Cloudflare Pages same-origin reverse proxy for app.venspera.com.
 * React routes and static assets stay in Pages; privileged API and SSE
 * requests go to separately secured HTTPS origins. No browser-visible API
 * hostname, credential rewrite or redirect to an alternate auth origin.
 *
 * Configure API_UPSTREAM and OPS_UPSTREAM as Pages Function environment
 * variables. Origin must be restricted to Cloudflare/Tunnel and TLS.
 */
interface PagesEnv {
  API_UPSTREAM?: string;
  OPS_UPSTREAM?: string;
  ASSETS: { fetch(request: Request): Promise<Response> };
}
interface PagesContext {
  request: Request;
  env: PagesEnv;
}
const API_PATTERN = /^\/(auth|accounts|admin|billing|aircraft|work-orders|crs|training|public|quality|qms|platform|reliability|audit|audit-events|bootstrap|integrations|api|notifications|email-logs|tasks|health|healthz|livez|readyz|time|manuals|doc-control|records|foundations|rostering|workforce)(?:\/|$)/i;
const OPS_PATTERN = /^\/ops(?:\/|$)/i;
const NAVIGATION_PATTERN = /^\/(platform(?:\/|$)|qms\/(audit-access|car-access)(?:\/|$)|verify\/[^/?]+(?:\/|$))/i;

export function resolveEdgeRoute(method: string, path: string, accept: string): "assets" | "api" | "ops" {
  if (method === "GET" || method === "HEAD") {
    if (accept.toLowerCase().includes("text/html") && NAVIGATION_PATTERN.test(path)) return "assets";
  }
  if (OPS_PATTERN.test(path)) return "ops";
  return API_PATTERN.test(path) ? "api" : "assets";
}

function upstreamUrl(value: string | undefined, requestUrl: URL): URL | null {
  if (!value) return null;
  let origin: URL;
  try { origin = new URL(value); } catch { return null; }
  if (origin.protocol !== "https:" || origin.username || origin.password ||
      origin.pathname !== "/" || origin.search || origin.hash ||
      origin.hostname === requestUrl.hostname) return null;
  const target = new URL(requestUrl.pathname + requestUrl.search, origin);
  return target;
}

export async function onRequest(context: PagesContext): Promise<Response> {
  const request = context.request;
  const url = new URL(request.url);
  const mode = resolveEdgeRoute(request.method, url.pathname, request.headers.get("accept") || "");
  if (mode === "assets") {
    const asset = await context.env.ASSETS.fetch(request);
    if (asset.status !== 404 || request.method !== "GET" ||
        !request.headers.get("accept")?.includes("text/html")) return asset;
    return context.env.ASSETS.fetch(new Request(new URL("/index.html", url), request));
  }
  const target = upstreamUrl(mode === "ops" ? context.env.OPS_UPSTREAM : context.env.API_UPSTREAM, url);
  if (!target) return new Response("Secure API upstream is not configured", {
    status: 503, headers: { "Cache-Control": "no-store" },
  });
  const expectedOrigin = url.origin;
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) {
    const receivedOrigin = request.headers.get("origin");
    const referringPage = request.headers.get("referer");
    const fetchSite = request.headers.get("sec-fetch-site");
    let matchingReferer = false;
    if (referringPage) {
      try { matchingReferer = new URL(referringPage).origin === expectedOrigin; }
      catch { matchingReferer = false; }
    }
    // Reject cross-site browser requests even if the Origin header is absent.
    // For cookie-authenticated mutations, require affirmative same-origin
    // provenance instead of treating a missing Origin as implicitly trusted.
    const crossSite = fetchSite !== null && !["same-origin", "none"].includes(fetchSite);
    const validOrigin = receivedOrigin === expectedOrigin;
    const conflictingOrigin = receivedOrigin !== null && !validOrigin;
    const missingCookieProvenance = request.headers.has("cookie") &&
      !(validOrigin || matchingReferer || fetchSite === "same-origin");
    if (conflictingOrigin || crossSite || missingCookieProvenance) {
      return new Response("Cross-origin state-changing request rejected", {
        status: 403, headers: { "Cache-Control": "no-store" },
      });
    }
  }
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-forwarded-for");
  headers.delete("x-forwarded-host");
  headers.delete("x-forwarded-proto");
  headers.delete("x-real-ip");
  headers.set("X-Forwarded-Host", url.host);
  headers.set("X-Forwarded-Proto", "https");
  headers.set("X-Venspera-Edge-Origin", expectedOrigin);
  headers.set("X-Real-IP", request.headers.get("cf-connecting-ip") || "");
  const upstream = await fetch(target.toString(), {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
  });
  const responseHeaders = new Headers(upstream.headers);
  // An API auth endpoint may issue a redirect using the private upstream host.
  // Keep internal infrastructure names and auth cookies off browser navigations.
  const location = responseHeaders.get("Location");
  if (location) {
    try {
      const destination = new URL(location, target);
      if (destination.origin === target.origin) {
        responseHeaders.set("Location",
          new URL(destination.pathname + destination.search + destination.hash, url.origin).toString());
      }
    } catch {
      return new Response("Invalid upstream redirect", {
        status: 502, headers: { "Cache-Control": "no-store" },
      });
    }
  }
  responseHeaders.set("Cache-Control", "private, no-store");
  responseHeaders.set("X-Content-Type-Options", "nosniff");
  // Stream EventSource, large responses and downloads without buffering.
  return new Response(upstream.body, {
    status: upstream.status, statusText: upstream.statusText, headers: responseHeaders,
  });
}

// src/utils/amo.ts

/**
 * Encode a real AMO certificate like "K/AMO/L/070"
 * into a URL-safe slug like "K_AMO_L_070".
 */
export function encodeAmoCertForUrl(cert: string): string {
  return cert.replace(/\//g, "_");
}

/**
 * Decode a slug like "K_AMO_L_070" back into
 * a displayable certificate "K/AMO/L/070".
 */
export function decodeAmoCertFromUrl(code: string): string {
  return code.replace(/_/g, "/");
}

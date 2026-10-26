/** Leave time for a file to traverse a constrained link and be validated server-side. */
export function uploadTimeoutMs(body: BodyInit | null | undefined): number | undefined {
  let bytes = 0;
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    for (const value of body.values()) bytes += typeof value === "string" ? value.length : value.size;
  } else if (typeof Blob !== "undefined" && body instanceof Blob) {
    bytes = body.size;
  } else {
    return undefined;
  }
  return Math.min(60 * 60_000, Math.max(5 * 60_000, Math.ceil(bytes / (16 * 1024)) * 1000 + 60_000));
}

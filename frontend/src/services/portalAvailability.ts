/** Availability failures can use device projections; rejected commands cannot. */
export function isTemporaryPortalFailure(error: unknown): boolean {
  if (error && typeof error === "object" && "status" in error) {
    const status = Number(error.status);
    return [408, 425, 429].includes(status) || status >= 500;
  }
  return error instanceof Error && /offline|failed to fetch|networkerror|network request failed|could not be reached|cached copy|not been cached|timed out|fetch failed/i.test(error.message);
}

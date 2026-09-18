/** One retry deadline shared by every recovery trigger in this tab. */
export class AuthRecoveryBackoff {
  retryAt = 0;
  private failures = 0;

  reset(): void { this.failures = 0; this.retryAt = 0; }

  defer(response?: Response, now = Date.now()): number {
    this.failures += 1;
    const raw = response?.headers.get("Retry-After")?.trim();
    const seconds = raw ? Number(raw) : NaN;
    const serverDelay = Number.isFinite(seconds) ? seconds * 1000
      : raw ? Date.parse(raw) - now : 0;
    const backoff = Math.min(60_000, 2_000 * 2 ** Math.min(this.failures - 1, 5));
    // Positive jitter never retries before the server's deadline.
    this.retryAt = now + Math.max(backoff, Number.isFinite(serverDelay) ? serverDelay : 0)
      + Math.floor(Math.random() * 1_000);
    return this.retryAt;
  }
}

import { portalFetch, type PortalFetchInit } from "./offlineHttp";
import { currentOfflineScope } from "./offlinePersistence";

class InterruptedDownload extends Error {}
const RETRY_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

/** Retry whole GETs; never join bytes from different document revisions. */
export async function fetchFileDownload(path: string, init: PortalFetchInit = {}): Promise<{ response: Response; blob: Blob | null }> {
  const method = (init.method || "GET").toUpperCase();
  const attempts = method === "GET" ? 3 : 1;
  const scope = currentOfflineScope();
  const deadline = Date.now() + (init.timeoutMs ?? 30 * 60_000);
  const checkScope = () => {
    init.signal?.throwIfAborted();
    if (currentOfflineScope() !== scope) throw new DOMException("Account or AMO context changed", "AbortError");
  };
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    checkScope();
    const controller = new AbortController();
    const abort = () => controller.abort(init.signal?.reason);
    init.signal?.addEventListener("abort", abort, { once: true });
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stalled = false;
    const armDeadline = () => {
      clearTimeout(timer);
      const remaining = deadline - Date.now();
      if (remaining <= 0) throw new InterruptedDownload("The download exceeded its transfer deadline. Please retry.");
      timer = setTimeout(() => {
        stalled = true;
        controller.abort(new DOMException("The download stopped receiving data. Please retry.", "AbortError"));
      }, Math.min(90_000, remaining));
    };
    try {
      armDeadline();
      const response = await portalFetch(path, {
        ...init, method, signal: controller.signal, timeoutMs: Math.max(1, deadline - Date.now()),
        offline: { ...init.offline, cache: false, queueMutation: false },
      });
      checkScope();
      if (!response.ok) {
        if (RETRY_STATUSES.has(response.status) && attempt + 1 < attempts) {
          const retryAfter = response.headers.get("retry-after");
          const seconds = retryAfter == null ? NaN : Number(retryAfter);
          const wait = Number.isFinite(seconds) ? seconds * 1000 : retryAfter ? Date.parse(retryAfter) - Date.now() : 500 * (attempt + 1);
          // Long rate limits stay visible to the caller instead of being ignored.
          if (Number.isFinite(wait) && wait >= 0 && wait <= 5000 && Date.now() + wait < deadline) {
            await response.body?.cancel();
            clearTimeout(timer);
            await new Promise<void>(resolve => setTimeout(resolve, wait));
            checkScope();
            continue;
          }
        }
        return { response, blob: null };
      }
      if ((response.headers.get("content-type") || "").includes("text/html") && !response.headers.has("content-disposition")) {
        await response.body?.cancel();
        throw new Error("The file route returned a portal page instead of a file. Nothing was saved.");
      }
      const reader = response.body?.getReader();
      if (!reader) {
        if (Number(response.headers.get("content-length")) > 0) throw new InterruptedDownload("The download was incomplete. Please retry.");
        return { response, blob: new Blob([], { type: response.headers.get("content-type") || "" }) };
      }
      const chunks: BlobPart[] = [];
      let bytes = 0;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          checkScope();
          if (done) break;
          bytes += value.byteLength;
          chunks.push(value.slice().buffer);
          armDeadline();
        }
      } catch (error) {
        void reader.cancel().catch(() => undefined);
        throw error;
      } finally {
        reader.releaseLock();
      }
      const expected = response.headers.get("content-length");
      if (expected != null && !response.headers.get("content-encoding") && Number(expected) !== bytes) {
        throw new InterruptedDownload("The download was incomplete. Please retry.");
      }
      return { response, blob: new Blob(chunks, { type: response.headers.get("content-type") || "application/octet-stream" }) };
    } catch (error) {
      checkScope();
      const networkFailure = error instanceof Error && /server could not be reached|failed to fetch|networkerror/i.test(error.message);
      if (!(stalled || networkFailure || error instanceof TypeError || error instanceof InterruptedDownload) || attempt + 1 >= attempts || Date.now() >= deadline) throw error;
    } finally {
      clearTimeout(timer);
      init.signal?.removeEventListener("abort", abort);
    }
  }
  throw new InterruptedDownload("The download could not be completed. Please retry.");
}

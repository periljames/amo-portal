import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchFileDownload } from "./fileTransfers";
import { apiBlob } from "./typedApi";
import { uploadTimeoutMs } from "./transferPolicy";

const state = vi.hoisted(() => ({ fetch: vi.fn(), scope: "tenant-one" }));
vi.mock("./offlineHttp", () => ({ portalFetch: state.fetch }));
vi.mock("./offlinePersistence", () => ({ currentOfflineScope: () => state.scope }));
vi.mock("./auth", () => ({ authHeaders: () => ({ Authorization: "Bearer test-only" }) }));
beforeEach(() => { state.fetch.mockReset(); state.scope = "tenant-one"; });
afterEach(() => vi.useRealTimers());

describe("complete file transfers", () => {
  it("restarts an interrupted GET and saves only the complete new response", async () => {
    state.fetch.mockResolvedValueOnce(new Response(new ReadableStream({
      start(controller) { controller.enqueue(new Uint8Array([1, 2])); },
      pull(controller) { controller.error(new TypeError("connection interrupted")); },
    }))).mockResolvedValueOnce(new Response("complete", { headers: { "Content-Length": "8" } }));
    const result = await fetchFileDownload("/api/file");
    expect(await result.blob!.text()).toBe("complete");
    expect(state.fetch).toHaveBeenCalledTimes(2);
    expect(state.fetch.mock.calls[1][1].offline).toMatchObject({ cache: false, queueMutation: false });
  });

  it("rejects incomplete success bodies instead of saving a truncated file", async () => {
    state.fetch.mockImplementation(() => new Response("partial", { headers: { "Content-Length": "1000" } }));
    await expect(fetchFileDownload("/api/file")).rejects.toThrow("incomplete");
    expect(state.fetch).toHaveBeenCalledTimes(3);
  });

  it("keeps filenames and authentication when typed API downloads recover", async () => {
    state.fetch.mockRejectedValueOnce(new Error("The server could not be reached and no cached copy is available."))
      .mockResolvedValueOnce(new Response("PDF", { headers: { "Content-Disposition": 'attachment; filename="retained.pdf"', "Content-Type": "application/pdf" } }));
    const result = await apiBlob("/api/evidence/download");
    expect(result.filename).toBe("retained.pdf");
    expect(await result.blob.text()).toBe("PDF");
    expect(new Headers(state.fetch.mock.calls[1][1].headers).get("Authorization")).toBe("Bearer test-only");
  });

  it("does not retry permission errors or uploads", async () => {
    state.fetch.mockResolvedValueOnce(new Response("denied", { status: 403 }));
    expect((await fetchFileDownload("/api/file")).blob).toBeNull();
    expect(state.fetch).toHaveBeenCalledTimes(1);
    state.fetch.mockReset().mockRejectedValue(new TypeError("connection lost"));
    await expect(fetchFileDownload("/api/export", { method: "POST", body: "{}" })).rejects.toThrow("connection lost");
    expect(state.fetch).toHaveBeenCalledTimes(1);
  });

  it("honours a short Retry-After for a backend restart", async () => {
    state.fetch.mockResolvedValueOnce(new Response("starting", { status: 503, headers: { "Retry-After": "0" } }))
      .mockResolvedValueOnce(new Response("complete"));
    expect(await (await fetchFileDownload("/api/file")).blob!.text()).toBe("complete");
    expect(state.fetch).toHaveBeenCalledTimes(2);
  });

  it("does not miscompare compressed lengths against decoded bytes", async () => {
    state.fetch.mockResolvedValueOnce(new Response("decoded content", { headers: { "Content-Length": "9", "Content-Encoding": "gzip" } }));
    expect(await (await fetchFileDownload("/api/file")).blob!.text()).toBe("decoded content");
  });

  it("never saves an HTML fallback as a file", async () => {
    state.fetch.mockResolvedValueOnce(new Response("<html>portal</html>", { headers: { "Content-Type": "text/html" } }));
    await expect(fetchFileDownload("/api/file")).rejects.toThrow("portal page instead of a file");
    expect(state.fetch).toHaveBeenCalledTimes(1);
  });

  it("stops without retrying if the account changes during the body", async () => {
    state.fetch.mockImplementationOnce(() => new Response(new ReadableStream({ start(controller) {
      state.scope = "tenant-two"; controller.enqueue(new Uint8Array([1])); controller.close();
    } })));
    await expect(fetchFileDownload("/api/file")).rejects.toMatchObject({ name: "AbortError" });
    expect(state.fetch).toHaveBeenCalledTimes(1);
  });

  it("cancels stalled bodies using the full transfer deadline", async () => {
    vi.useFakeTimers();
    state.fetch.mockImplementation((_path, init) => new Response(new ReadableStream({ start(controller) {
      init.signal.addEventListener("abort", () => controller.error(init.signal.reason));
    } })));
    const result = expect(fetchFileDownload("/api/file", { timeoutMs: 100 })).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(101);
    await result;
    expect(state.fetch).toHaveBeenCalledTimes(1);
  });

  it("never starts a caller-cancelled download", async () => {
    const controller = new AbortController(); controller.abort();
    await expect(fetchFileDownload("/api/file", { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(state.fetch).not.toHaveBeenCalled();
  });

  it("gives uploads a size-aware deadline without changing JSON reads", () => {
    const form = new FormData(); form.set("file", new Blob([new Uint8Array(8 * 1024 * 1024)]), "evidence.pdf");
    expect(uploadTimeoutMs(form)).toBeGreaterThan(5 * 60_000);
    expect(uploadTimeoutMs(new Blob(["small"])) ).toBe(5 * 60_000);
    expect(uploadTimeoutMs('{"save":true}')).toBeUndefined();
  });
});

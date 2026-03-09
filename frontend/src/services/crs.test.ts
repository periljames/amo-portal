import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "./crs";
import { setApiBaseRuntime } from "./config";

describe("api helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setApiBaseRuntime(null);
  });

  it("throws structured hint when html is returned for json endpoint", async () => {
    setApiBaseRuntime("http://127.0.0.1:8080");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: { get: () => "text/html; charset=utf-8" },
        text: async () => "<html></html>",
      }),
    );

    await expect(apiGet("/records/dashboard")).rejects.toThrow(/Vite dev server/);
  });
});

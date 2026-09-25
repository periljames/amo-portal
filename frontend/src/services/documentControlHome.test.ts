import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({ authHeaders: () => ({}) }));
vi.mock("./config", () => ({ getApiBaseUrl: () => "" }));
vi.mock("./documentControlRetention", () => ({ listDocumentRetentionWork: vi.fn() }));

import { getDocumentControlMyWork } from "./documentControlHome";
import { listDocumentRetentionWork } from "./documentControlRetention";

describe("Document Control review queue resilience", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps review actions available when supplementary queues fail", async () => {
    vi.mocked(listDocumentRetentionWork).mockRejectedValue(new Error("unavailable"));
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).endsWith("/external-source-work")) return new Response("", { status: 503 });
      return new Response(JSON.stringify({ items: [{ id: "workflow:1", kind: "WORKFLOW_DECISION", priority: "ACTION", title: "Review checklist" }], limit: 30 }));
    });
    const result = await getDocumentControlMyWork("tenant");
    expect(result.items.map((item) => item.id)).toEqual(["workflow:1"]);
    expect(result.warnings).toHaveLength(2);
  });

  it("reports a failed primary review queue instead of a misleading empty queue", async () => {
    vi.mocked(listDocumentRetentionWork).mockResolvedValue([]);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    await expect(getDocumentControlMyWork("tenant")).rejects.toThrow("503");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({ authHeaders: () => ({ Authorization: "Bearer test" }) }));
vi.mock("./config", () => ({ getApiBaseUrl: () => "" }));

import {
  compareReaderRevisions,
  createReaderAnnotation,
  decideAnnotationMigration,
  getReaderManifest,
  prepareAnnotationMigrations,
} from "./readerGovernance";

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("reader governance API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads a manifest for an exact immutable revision", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ revision_id: "rev-1" }));
    await getReaderManifest("tenant", "manual-1", "rev-1");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/reader/documents/manual-1/revisions/rev-1/manifest");
  });

  it("posts checksum-bound annotation locations", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ id: "annotation-1" }));
    await createReaderAnnotation("tenant", "manual-1", "rev-1", {
      expected_source_sha256: "a".repeat(64),
      annotation_type: "NOTE",
      visibility: "PRIVATE",
      location: { location_type: "PAGE", page_number: 17, normalized_rects: [] },
    });
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body));
    expect(body.expected_source_sha256).toBe("a".repeat(64));
    expect(body.location.page_number).toBe(17);
  });

  it("compares explicit source and target revision IDs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ sections: [] }));
    await compareReaderRevisions("tenant", "manual-1", "rev-old", "rev-new");
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("source_revision_id=rev-old");
    expect(url).toContain("target_revision_id=rev-new");
  });

  it("prepares and reviews annotation migration through explicit human actions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({}));
    await prepareAnnotationMigrations("tenant", "manual-1", "rev-old", "rev-new");
    await decideAnnotationMigration("tenant", "manual-1", "migration-1", "ACCEPT", "Confirmed against target content.");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ source_revision_id: "rev-old", target_revision_id: "rev-new" });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ decision: "ACCEPT", comments: "Confirmed against target content." });
  });
});
